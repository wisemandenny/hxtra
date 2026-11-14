"""tools/features/usb_input.py, src/m4/usb_input.s, tools/hx_input.py: the command's registration and its queueing of the host's
UI events run in tests/m4emu.py against the key queue and the reply sender modelled, the host's events for each control, and
the build on the stock firmware."""
import struct

import msgpack
import pytest

import features
import hx_ctl
import hx_input as hi
import usb_commands
from features import usb_input as ui
from firmware import branch_target, menu_entry0, reader, stock_e0
from hx_mirror import STOMP

REGISTER, NO_PARAMS, SEND = 0x28e165f0, 0x28e19205, 0x28e15b30
PUT, QUEUE, ROOM, SLEEP = 0x28db88fc, 0x281f3db0, 0x28db9a58, 0x28e24c58
MOD = 0x28e60000
STREAM, REQUEST, BYTES = 0x28f80000, 0x28f81000, 0x28f82001       # the request's bytes at an odd address, as a parameter may be
_code = {}

FS2_DOWN = bytes([1, 13, 0, 0, 1, 0, 0, 0])
FS2_UP = bytes([1, 13, 0, 0, 2, 0, 0, 0])


class Unit:
    """usb_input.s in the M4, with the key queue (its free bytes, the events put) and the reply sender modelled."""

    def __init__(self, m4emu, text, sym):
        self.sym, self.put, self.sent, self.free, self.slept = sym, [], [], [8000], 0
        self.m = m = m4emu.M4(text, MOD)
        m.stub(REGISTER, lambda m: m.reg('r0', 0))
        m.stub(PUT, lambda m: self.put.append(m.read(m.reg('r0'), 8)))
        m.stub(ROOM, self.room)
        m.stub(SLEEP, self.sleep)
        m.stub(SEND, self.send)

    def room(self, m):
        assert m.reg('r0') == QUEUE
        m.reg('r0', self.free.pop(0) if len(self.free) > 1 else self.free[0])

    def sleep(self, m):
        assert m.reg('r0') == 1000
        self.slept += 1

    def send(self, m):
        n, = m.stack_args(1)
        self.sent.append((m.reg('r0'), m.reg('r1'), m.reg('r2'), m.read(m.reg('r3'), n)))
        m.reg('r0', 0)

    def request(self, params, seq=7, cut=0):
        """ui_cmd's result for a request as the dispatcher hands it over: its bytes, their count, where the parameter starts, seq."""
        blob = msgpack.packb({0x66: seq, 0x64: ui.CMD, 0x65: params}, use_bin_type=False)
        at = len(blob) - len(msgpack.packb(params, use_bin_type=False))
        self.m.write(BYTES, blob)
        self.m.write(REQUEST, struct.pack('<IIIH', BYTES, len(blob) - cut, at, seq))
        r = self.m.call(MOD + self.sym['ui_cmd'], STREAM, REQUEST)
        return r - (1 << 32) if r & 0x80000000 else r


@pytest.fixture
def unit(m4emu):
    if 'input' not in _code:
        _code['input'] = m4emu.assemble('src/m4/usb_input.s', features.load(), {}, inc={'usb.inc': usb_commands.inc('usb_input')})
    return Unit(m4emu, *_code['input'])


# --- the command, in the M4 ---

def test_register_adds_the_command_that_replies_itself(unit):
    unit.m.call(MOD + unit.sym['ui_register'])
    (cmd, desc, _, _), = unit.m.calls(REGISTER)
    assert cmd == ui.CMD == hx_ctl.CMD_INPUT == 0x51
    assert struct.unpack('<3I', unit.m.read(desc, 12)) == (MOD + unit.sym['ui_cmd'] | 1, NO_PARAMS | 1, 0)


def test_an_event_is_put_on_the_key_queue_and_answered_with_nil(unit):
    assert unit.request(FS2_DOWN, seq=0x1234) == 0
    assert unit.put == [FS2_DOWN]
    assert unit.sent == [(STREAM, 0x1234, 0, b'\xc0')], 'status 0, result nil'


def test_events_are_put_in_order_whatever_head_their_string_has(unit):
    events = [bytes([1, k, 0, 0, 1 + k % 2, 0, 0, 0]) for k in range(16)]
    assert unit.request(b''.join(events[:3])) == 0                                # fixstr
    assert unit.request(b''.join(events)) == 0                                    # str16: 128 bytes
    assert unit.request(events[5]) == 0
    assert unit.put == events[:3] + events + [events[5]]
    assert len(unit.sent) == 3


@pytest.mark.parametrize('head', [b'\xc4\x10', b'\xd9\x10'], ids=['bin8', 'str8'])
def test_bin8_and_str8_are_taken_too(unit, head):
    blob = msgpack.packb({0x66: 1, 0x64: ui.CMD}, use_bin_type=False)
    blob = bytes([blob[0] + 1]) + blob[1:] + b'\x65' + head + FS2_UP + FS2_DOWN
    unit.m.write(BYTES, blob)
    unit.m.write(REQUEST, struct.pack('<IIIH', BYTES, len(blob), len(blob) - 18, 1))
    assert unit.m.call(MOD + unit.sym['ui_cmd'], STREAM, REQUEST) == 0
    assert unit.put == [FS2_UP, FS2_DOWN]


@pytest.mark.parametrize('params', [b'', bytes(7), bytes(12), bytes(8 * 17), 5, {0x4b: 1}, None, [FS2_DOWN]],
                         ids=['empty', 'short', 'not-whole', 'too-many', 'int', 'map', 'nil', 'list'])
def test_a_parameter_that_is_not_events_is_refused_and_nothing_put(unit, params):
    assert unit.request(params) == -3
    assert unit.put == [] and unit.sent == [], 'the dispatcher sends the error reply'


@pytest.mark.parametrize('events, cut', [(1, 1), (8, 1), (8, 64 + 1), (8, 64 + 2)], ids=['fixstr', 'str16', 'str16-count', 'str16-head'])
def test_a_parameter_cut_short_is_refused(unit, events, cut):
    assert unit.request(FS2_DOWN * events, cut=cut) == -3 and unit.put == []


def test_a_full_queue_is_waited_for(unit):
    unit.free = [8, 63, 64]
    assert unit.request(FS2_DOWN) == 0
    assert unit.slept == 2 and unit.put == [FS2_DOWN]


def test_a_queue_that_stays_full_is_refused_after_200_ms(unit):
    unit.free = [8, 8000, 10]
    assert unit.request(FS2_DOWN + FS2_UP) == -16
    assert unit.put == [FS2_DOWN], 'the events before it were put'
    assert unit.slept == 1 + 199 and unit.sent == []


# --- the host ---

class FakeCtl:
    def __init__(self):
        self.log = []

    def send_events(self, blob):
        self.log.append(('send', bytes(blob)))


def fake_input():
    ctl = FakeCtl()
    return hi.Input(ctl, sleep=lambda s: ctl.log.append(('sleep', round(s, 3)))), ctl.log


def test_a_press_is_a_down_then_an_up_and_its_release():
    i, log = fake_input()
    i.press('fs2')
    assert log == [('send', FS2_DOWN), ('sleep', hi.CLICK_S), ('send', FS2_UP + bytes([1, 13, 0, 0, 3, 0, 0, 0])),
                   ('sleep', hi.GAP_S)]


def test_a_hold_gives_its_hold_after_a_second_and_no_release_before_it():
    i, log = fake_input()
    i.hold('view', 1.5)
    assert log == [('send', bytes([1, 5, 0, 0, 1, 0, 0, 0])), ('sleep', 1.0), ('send', bytes([1, 5, 0, 0, 5, 0, 0, 0])),
                   ('sleep', 0.5), ('send', bytes([1, 5, 0, 0, 2, 0, 0, 0])), ('sleep', hi.GAP_S)]
    i, log = fake_input()
    i.press('fs1', 1.2)
    assert [e for kind, e in log if kind == 'send'][1] == bytes([1, 12, 0, 0, 5, 0, 0, 0]), 'a press as long as a hold is one'


def test_each_control_has_its_key_or_knob_event():
    assert {n: hi.key(n, 1)[:2] for n in ('fs1', 'fs5', 'knob1', 'knob5', 'view', 'action', 'page_left', 'page_right')} == {
        'fs1': b'\x01\x0c', 'fs5': b'\x01\x10', 'knob1': b'\x01\x00', 'knob5': b'\x01\x04', 'view': b'\x01\x05',
        'action': b'\x01\x06', 'page_left': b'\x01\x07', 'page_right': b'\x01\x08'}
    assert hi.key('fs3', 1, 'touch') == bytes([1, 11, 0, 0, 1, 0, 0, 0])
    i, log = fake_input()
    i.turn('knob3', -4)
    i.turn('knob3', 0)
    assert [e for kind, e in log if kind == 'send'] == [bytes([2, 2, 0, 0]) + struct.pack('<i', -4)]


def test_a_control_with_no_such_event_is_refused():
    with pytest.raises(ValueError, match='knob9 has no press'):
        hi.key('knob9', 1)
    with pytest.raises(ValueError, match='fs4 has no touch'):
        hi.key('fs4', 1, 'touch')
    with pytest.raises(ValueError, match='not a key'):
        hi.key('volume', 1, 'level')


def test_more_events_than_a_request_takes_go_in_several():
    i, log = fake_input()
    i.send(*[FS2_DOWN] * (hi.MAX + 1))
    assert [len(e) for _, e in log] == [8 * hi.MAX, 8]


def test_hx_ctl_sends_them_as_a_string_on_the_ledgers_command():
    sent = []

    class Ed:
        def request(self, cmd, params=None, timeout=None):
            sent.append(msgpack.packb({0x66: 1, 0x64: cmd, 0x65: params}, use_bin_type=False))

    ctl = hx_ctl.HxCtl.__new__(hx_ctl.HxCtl)
    ctl.ed = Ed()
    ctl.send_events(bytearray(FS2_DOWN))
    assert sent[0].endswith(b'\x65\xa8' + FS2_DOWN), 'fixstr 8, as usb_input.s reads it'
    assert hx_ctl.CMD_INPUT == usb_commands.by_feature()['usb_input']
    assert STOMP['fs2']['press'] == [1, 13]


# --- the build, on the stock firmware ---

@pytest.mark.firmware
def test_build_registers_the_command_after_the_editors_beside_the_mirror():
    e0 = stock_e0()
    stock = reader(e0)
    for va, code, _ in ui.CALLED:
        assert stock(va, len(bytes.fromhex(code))) == bytes.fromhex(code)
    assert stock(ui.PUT_QUEUE, 4) == struct.pack('<I', ui.QUEUE)
    assert branch_target(ui.REGISTER_ALL_CALL, stock(ui.REGISTER_ALL_CALL, 4)) == ui.REGISTER_ALL
    for env in ({'HX_USB_INPUT': '1'}, {'HX_USB_INPUT': '1', 'HX_SCREEN_MIRROR': '1'}):
        new, on = menu_entry0(e0, None, env)
        assert {features.name(m) for m in on} >= {'usb_input'} | ({'screen_mirror'} if len(env) == 2 else set())
        assert reader(new)(ui.REGISTER_ALL_CALL, 4) != stock(ui.REGISTER_ALL_CALL, 4)
    assert 'usb_input' not in [features.name(m) for m in menu_entry0(e0, None, {})[1]], 'opt-in'


def test_the_web_page_does_not_offer_it():
    import m4cache
    assert ui.FLAG not in m4cache.web_flags() + m4cache.web_options()
