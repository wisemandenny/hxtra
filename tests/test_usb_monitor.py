"""tools/features/usb_monitor.py and src/m4/usb_monitor.s: the handlers in unicorn (path A's Main sent as Send while the setting says
Send/USB or USB Only, everything else untouched; the setting sent after path A's destination inside USB Input Trim; a turn
or a reset sending path A again only when the destination or the mode changes), the firmware it builds (its setting in
Ins/Outs, the virtual setting, the hooks), and the stock facts the trim rests on (USB In 1/2 Trim is I/O setting 0x99, read from
the I/O store as the stock setters send it)."""
import struct

import pytest

import features
import setting_ids
from features import usb_monitor as um
import patch_menu as pm
from firmware import assert_virtual, branch_target, built, built_e0, reader, stock_e0
from test_hxtra import page_table
from test_virtual_settings import MEMCPY, MUTEX_LOCK, MUTEX_UNLOCK, stock_m4

MODS = features.load()
IDS = setting_ids.by_name()
ID = IDS['usb_monitor.path_a']
MOD = 0x28e60000
GET_VALUE = 0x28e1f844
STOCK = 0x28e70000                          # stands in for the moved prologue of 0x28df5760
ENGINE, SET_OUTPUT = 0x28d92a98, 0x28e03c68
PARAM_FIND, PARAM_SEND = 0x28df35a0, 0x28df35e8
TRIM_NAME, TRIM_ID, TRIM_TYPE = 4209, 0x99, 1       # usbInGain0_1, USB In 1/2 Trim, a stand-in for its store's type
IO_FIRST, IO_LAST = 0x96, 0xa4              # the I/O settings, which GET_VALUE reads from the I/O store
IO_STORE, IO_RECORD = 0x2845e98c, 0x2c      # their records: the type byte at +4, the value at +8, the app parameter's handle at +0x1c
IO_LABELS, IO_KEYS = 0x28e252f4, 0x28e3ec68     # by ID - IO_FIRST: their labels (char[27]) and app parameters (i32 string indices)
DATA = 0x30000000                           # a context and an app for um_send to read
CTX, APP, PCTX, INST, HANDLE = DATA, DATA + 0x100, DATA + 0x2000, 0x7777, 0x5150
MAIN, SEND = 1, 6
SEND_USB, USB_ONLY, MAIN_SEND = 1, 2, 3
_code = {}


def io_record(pid):
    return IO_STORE + IO_RECORD * (pid - IO_FIRST)


class Monitor:
    """usb_monitor.s in tests/m4emu.py's M4: GET_VALUE answers self.value (None: unset) for the setting, and an I/O setting from its
    record in the I/O store, as the stock getter does; self.trim is USB In 1/2 Trim's record (None: GET_VALUE fails); the stock
    send, ENGINE and SET_OUTPUT logged."""

    def __init__(self, m4emu):
        if 'um' not in _code:
            _code['um'] = m4emu.assemble('src/m4/usb_monitor.s', MODS, IDS)
        code, self.sym = _code['um']
        self.m = m4emu.M4(code, MOD)
        self.value, self.trim = None, -12.5
        self.m.stub(GET_VALUE, self.get_value)
        self.m.stub(STOCK, lambda m: m.reg('r0', 0x55))
        self.m.stub(ENGINE, lambda m: m.reg('r0', 0x2844adcc))
        self.m.stub(SET_OUTPUT)
        self.has_param, self.modes = True, []
        self.m.stub(PARAM_FIND, self.find)
        self.m.stub(PARAM_SEND, self.param)
        self.m.map(DATA, 0x4000)
        self.m.u32(CTX + 0xc, PCTX - 4)
        self.m.u32(APP + 0xac8, INST)

    def find(self, m):
        assert (m.reg('r0'), m.reg('r1'), m.reg('r2')) == (PCTX, INST, TRIM_NAME), 'USB Input Trim, usbInGain0_1'
        if self.has_param:
            m.u32(m.reg('r3'), HANDLE)
        m.reg('r0', 0 if self.has_param else -3)

    def param(self, m):
        assert (m.reg('r0'), m.reg('r1'), m.reg('r2')) == (PCTX, INST, HANDLE)
        kind, value = struct.unpack('<Bxxxf', m.read(m.reg('r3'), 8))
        code = round(value / 1000)
        self.modes.append((kind, code - 1, value - 1000 * code))

    @property
    def trim(self):
        return self._trim

    @trim.setter
    def trim(self, value):
        self._trim = value
        self.m.write(io_record(TRIM_ID) + 4, struct.pack('<B3xf', TRIM_TYPE, value or 0.0))

    def get_value(self, m):
        pid, out = m.reg('r0'), m.reg('r1')
        if pid != ID:
            assert IO_FIRST <= pid <= IO_LAST, f'GET_VALUE({pid:#x}): not an I/O setting'
            if self.trim is None:
                m.reg('r0', -3)
                return
            m.u8(out, m.read(io_record(pid) + 4, 1)[0])     # the type byte alone, as the stock getter stores it
            m.write(out + 4, m.read(io_record(pid) + 8, 4))
            m.reg('r0', 0)
            return
        if self.value is None:
            m.reg('r0', -1)
        else:
            m.write(m.reg('r1'), struct.pack('<II', 2, self.value))
            m.reg('r0', 0)

    def send(self, ctx, app, path, value):
        """um_send as the owned 0x28df5760 -> (ctx, app, path, value) that reached the stock function."""
        before = len(self.m.calls(STOCK))
        self.m.reg('r12', STOCK | 1)
        assert self.m.call(MOD + self.sym['um_send'], ctx, app, path, value) == 0x55, 'the stock send\'s result'
        got = self.m.calls(STOCK)[before:]
        assert len(got) == 1
        return tuple(got[0])

    def apply(self, sym, *args):
        """The SET_OUTPUT calls (engine, position, value) a handler made."""
        before = len(self.m.calls(SET_OUTPUT))
        self.m.call(MOD + self.sym[sym], *args)
        return [tuple(r[:3]) for r in self.m.calls(SET_OUTPUT)[before:]]


@pytest.fixture
def mon(m4emu):
    return Monitor(m4emu)


def test_feature_setting():
    s, = um.SETTINGS
    assert um.FLAG == 'HX_USB_MONITOR' and um.MENU == 'Ins/Outs'
    assert pm.STOCK_CATEGORIES['Ins/Outs'] == (0, 0x28e3b55c)
    assert s.values == (b'Main L/R', b'Send/USB', b'USB Only', b'Main+Snd') and s.default == 0 and um.WEB == 'dsp'
    assert all(len(v) <= 8 for v in s.values)
    assert (ID, 112, 0, 2) in [(v, c, b, n) for v, c, b, n, who, _ in setting_ids.VIRTUAL if who == 'usb_monitor.path_a']


@pytest.mark.parametrize('value, sent', [(None, MAIN), (0, MAIN), (SEND_USB, SEND), (USB_ONLY, SEND), (MAIN_SEND, MAIN)])
def test_path_a_main_follows_the_setting(mon, value, sent):
    mon.value = value
    assert mon.send(CTX, APP, 0, MAIN) == (CTX, APP, 0, sent)


@pytest.mark.parametrize('path, dest', [(0, 0), (0, SEND), (1, 0), (1, MAIN), (1, SEND)])
def test_everything_else_goes_through(mon, path, dest):
    mon.value = 1
    assert mon.send(CTX, APP, path, dest) == (CTX, APP, path, dest)


@pytest.mark.parametrize('value', [None, 0, SEND_USB, USB_ONLY, MAIN_SEND])
def test_the_mode_follows_path_a(mon, value):
    mon.value = value
    mon.send(CTX, APP, 0, MAIN)
    assert mon.modes == [(TRIM_TYPE, value or 0, -12.5)], 'the setting inside the trim, after the destination'


def test_an_unset_trim_goes_as_0_db(mon):
    mon.value, mon.trim = USB_ONLY, None
    mon.send(CTX, APP, 0, MAIN)
    assert mon.modes == [(0, USB_ONLY, 0.0)]


@pytest.mark.parametrize('trim', [-60.0, 0.0, 18.0])
def test_the_trim_rides_along(mon, trim):
    mon.value, mon.trim = SEND_USB, trim
    mon.send(CTX, APP, 0, MAIN)
    assert mon.modes == [(TRIM_TYPE, SEND_USB, trim)], 'the trim the DSP hands on after taking the mode out'


@pytest.mark.parametrize('path, dest', [(1, 0), (1, SEND)])
def test_path_b_sends_no_mode(mon, path, dest):
    mon.value = USB_ONLY
    mon.send(CTX, APP, path, dest)
    assert mon.modes == []


def test_no_mode_when_the_stock_send_fails(mon):
    mon.value = USB_ONLY
    mon.m.stub(STOCK, lambda m: m.reg('r0', -3))
    mon.m.reg('r12', STOCK | 1)
    assert mon.m.call(MOD + mon.sym['um_send'], CTX, APP, 0, MAIN) == (-3) & 0xffffffff
    assert mon.modes == [] and not mon.m.calls(PARAM_FIND), 'the app is not read when the stock send gave up'


def test_no_mode_without_the_trim_parameter(mon):
    mon.value = USB_ONLY
    mon.has_param = False
    assert mon.send(CTX, APP, 0, MAIN)[3] == SEND
    assert mon.modes == []


def test_send_usb_to_usb_only_sends_again(mon):
    mon.value = SEND_USB
    mon.send(CTX, APP, 0, MAIN)
    mon.value = USB_ONLY
    assert mon.apply('um_changed', 0x3333, ID) == [(0x2844adcc, 9, MAIN)], 'same destination, another mode'
    mon.send(CTX, APP, 0, MAIN)
    assert mon.modes[-1][1] == USB_ONLY
    assert mon.apply('um_page', 0x3333) == []


def test_main_to_main_send_sends_again(mon):
    mon.value = 0
    mon.send(CTX, APP, 0, MAIN)
    mon.value = MAIN_SEND
    assert mon.apply('um_changed', 0x3333, ID) == [(0x2844adcc, 9, MAIN)], 'same destination, another mode'
    assert mon.send(CTX, APP, 0, MAIN)[3] == MAIN
    assert mon.modes[-1][1] == MAIN_SEND


def test_a_turn_sends_path_a_again(mon):
    mon.value = 0
    mon.send(CTX, APP, 0, MAIN)
    mon.value = 1
    assert mon.apply('um_changed', 0x3333, ID) == [(0x2844adcc, 9, MAIN)]
    assert mon.send(CTX, APP, 0, MAIN)[3] == SEND


def test_other_settings_are_ignored(mon):
    mon.send(CTX, APP, 0, MAIN)
    mon.value = 1
    assert mon.apply('um_changed', 0x3333, ID + 1) == []
    assert mon.apply('um_changed', 0x3333, 0x10) == []


def test_a_reset_comes_through_the_page_repaint(mon):
    mon.value = 1
    mon.send(CTX, APP, 0, MAIN)
    mon.value = 0
    assert mon.apply('um_page', 0x3333) == [(0x2844adcc, 9, MAIN)]
    mon.send(CTX, APP, 0, MAIN)                                # where the stock API's call ends on the unit
    assert mon.apply('um_page', 0x3333) == []


def test_nothing_is_sent_when_it_already_matches(mon):
    mon.value = 1
    mon.send(CTX, APP, 0, MAIN)
    assert mon.apply('um_page', 0x3333) == []
    assert mon.apply('um_changed', 0x3333, ID) == []


@pytest.mark.parametrize('first', [None, 0])
def test_nothing_is_sent_while_path_a_is_off_or_unsent(mon, first):
    if first is not None:
        mon.send(CTX, APP, 0, first)
    mon.value = 1
    assert mon.apply('um_changed', 0x3333, ID) == []
    assert mon.apply('um_page', 0x3333) == []


def test_off_unless_asked_for():
    assert um not in features.enabled(MODS, {})
    assert um in features.enabled(MODS, {'HX_USB_MONITOR': '1'})


@pytest.mark.firmware
def test_firmware():
    read, on = built({'HX_USB_MONITOR': '1'}, MODS)
    assert 'usb_monitor' in on
    assert read(um.SEND_FN, 4) != um.SEND_FN_STOCK, 'the send goes to the handler'
    for fn, stock in ((um.CHANGED, um.CHANGED_STOCK), (um.PAGE, um.PAGE_STOCK)):
        assert read(fn, 4) != stock, f'{fn:#x} is chained'
        assert branch_target(fn, read(fn, 4)) > fn, f'{fn:#x} branches to its chain'
    assert_virtual(built_e0({'HX_USB_MONITOR': '1'}, MODS), um, um.SETTINGS[0])


@pytest.mark.firmware
def test_ins_outs_last_empty_slot_holds_the_setting():
    read, _ = built({'HX_USB_MONITOR': '1'}, MODS)
    stock_ids = (0x1f, 0x5e, 2, 3, 0x9a, 0x99, 0x9e, 0x9c)
    for site in pm.SITES:
        table = page_table(read, 0, site)
        assert struct.unpack('<9H', read(table, 18)) == (*stock_ids, ID), site
    pages = struct.unpack('<I', read(pm.ARRAYS['pages'][1][0], 4))[0]
    assert read(pages, 4) == struct.pack('<I', 3), 'Ins/Outs keeps its three pages'


# the stock facts the trim rests on

LABEL, STEP = 0x28d97634, 0x28e20158       # (ID, dst, n): a setting's label; (ID, delta, how): a Global Settings knob's turn
STEP_SET, SET, RESET = setting_ids.SETTERS  # (ctx, ID, &{type, value}, how): the step's, other code's; (ctx, ID, how): a click's
MEMSET, APP_INSTANCE, CHANGE_MESSAGE = 0x28e24b78, 0x28df3550, 0x28e04ea8   # stubs: (dst, byte, n); (ctx, 0); (0, ID, &value)
OUT, DST, SCTX = 0x28f10000, 0x28f10100, 0x28f10200


def stock_code(m4emu):
    """The stock Entry 0's code in unicorn, the mutex and memcpy as stubs."""
    m = stock_m4(m4emu)
    for fn in (MUTEX_LOCK, MUTEX_UNLOCK):
        m.stub(fn)
    m.stub(MEMCPY, lambda m: m.write(m.reg('r0'), m.read(m.reg('r1'), m.reg('r2'))))
    return m


@pytest.mark.firmware
def test_trim_id_is_usb_in_1_2_trim(m4emu):
    """TRIM_ID is USB In 1/2 Trim, and its app parameter is the one um_mode sends: the long-label function takes an I/O setting's
    label from IO_LABELS (shown 'USB In 1/2' over 'Trim'), and IO_KEYS gives usbInGain0_1 (string 4209, tests/test_usbmon.py) for
    it. ID 3, which um_mode read before, is Send/Return R in the main store."""
    read = reader(stock_e0())
    assert read(IO_LABELS + pm.NAME_LEN * (TRIM_ID - IO_FIRST), pm.NAME_LEN).split(b'\0')[0] == b'Trim\nUSB In 1/2'
    assert struct.unpack('<i', read(IO_KEYS + 4 * (TRIM_ID - IO_FIRST), 4)) == (TRIM_NAME,)
    m = stock_code(m4emu)
    for pid, label in ((TRIM_ID, b'Trim\nUSB In 1/2'), (3, b'Return R\nSend/')):
        m.write(DST, b'\0' * pm.NAME_LEN)
        assert m.call(LABEL, pid, DST, pm.NAME_LEN) == 0
        assert m.read(DST, pm.NAME_LEN).split(b'\0')[0] == label, hex(pid)


@pytest.mark.firmware
def test_get_value_reads_the_io_settings_from_the_io_store(m4emu):
    """The stock GET_VALUE takes IDs IO_FIRST..IO_LAST from their records in the I/O store, as Monitor's stub does: the type byte at
    +4 into out (that byte alone) and the value at +8 into out + 4. The IDs either side of the range have no value."""
    m = stock_code(m4emu)
    for pid in range(IO_FIRST, IO_LAST + 1):
        m.write(io_record(pid) + 4, struct.pack('<B3xI', pid - IO_FIRST + 1, 0x5a5a0000 + pid))
    for pid in range(IO_FIRST - 1, IO_LAST + 2):
        m.write(OUT, b'\xee' * 8)
        r0 = m.call(GET_VALUE, pid, OUT)
        if IO_FIRST <= pid <= IO_LAST:
            assert (r0, m.read(OUT, 8)) == (0, struct.pack('<B3sI', pid - IO_FIRST + 1, b'\xee' * 3, 0x5a5a0000 + pid)), hex(pid)
        else:
            assert (r0, m.read(OUT, 8)) == ((-3) & 0xffffffff, b'\xee' * 8), hex(pid)


CALLER = {STEP_SET: STEP + 0xde, SET: 0x28d93dac, RESET: 0x28dceea6}  # a bl to each: the step's, 0x28d93d8c's (masterVolume), a click's


@pytest.mark.firmware
@pytest.mark.parametrize('setter', setting_ids.SETTERS, ids=('step', 'set', 'reset'))
def test_each_stock_setter_sends_the_trim_as_it_stores_it(m4emu, setter):
    """A turn of USB In 1/2 Trim goes through the step (the turn's b.w at 0x28dcefc0) to STEP_SET, and a click to RESET, which takes
    the record's default ({type +0x18, value +0x28}); other code, 0x28d93d8c for one, sets I/O settings with SET. Each sends the
    {type, value} to the app parameter with PARAM_SEND, under the handle in the record (+0x1c), then stores that type and value in
    the record: so GET_VALUE hands um_mode the number the stock last sent, and the DSP gets the trim as it would without the
    feature."""
    read = reader(stock_e0())
    assert branch_target(0x28dcefc0, read(0x28dcefc0, 4)) == STEP
    assert branch_target(CALLER[setter], read(CALLER[setter], 4)) == setter
    m = stock_code(m4emu)
    m.stub(MEMSET, lambda m: m.write(m.reg('r0'), bytes([m.reg('r1') & 0xff]) * m.reg('r2')))
    m.stub(APP_INSTANCE, lambda m: m.reg('r0', INST))
    m.stub(CHANGE_MESSAGE, lambda m: m.reg('r0', 0))
    sent = []

    def param_send(m):
        sent.append((m.reg('r0'), m.reg('r1'), m.reg('r2'), m.read(m.reg('r3'), 8)))
        m.reg('r0', 0)
    m.stub(PARAM_SEND, param_send)
    m.u32(io_record(TRIM_ID) + 0x1c, HANDLE)
    m.u32(SCTX + 0xc, PCTX - 4)
    m.write(io_record(TRIM_ID) + 4, struct.pack('<B3xf', TRIM_TYPE + 1, -6.0))
    m.u8(io_record(TRIM_ID) + 0x18, TRIM_TYPE)
    m.write(io_record(TRIM_ID) + 0x28, struct.pack('<f', 0.0))
    if setter == RESET:
        trim = 0.0
        assert m.call(RESET, SCTX, TRIM_ID, 1) == 0
    else:
        trim = -19.4
        m.write(OUT, struct.pack('<B3xf', TRIM_TYPE, trim))
        assert m.call(setter, SCTX, TRIM_ID, OUT, 1) == 0
    value = struct.pack('<B3xf', TRIM_TYPE, trim)
    assert [(ctx, inst, handle, v[0], v[4:]) for ctx, inst, handle, v in sent] == [(PCTX, INST, HANDLE, TRIM_TYPE, value[4:])]
    assert m.read(io_record(TRIM_ID) + 4, 8) == value
    m.write(DST, b'\xee' * 8)
    assert m.call(GET_VALUE, TRIM_ID, DST) == 0 and m.read(DST, 8) == struct.pack('<B3sf', TRIM_TYPE, b'\xee' * 3, trim)
