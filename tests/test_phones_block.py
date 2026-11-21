"""tools/features/phones_block.py, src/m4/phones_block.s and tools/patch_phones.py: Phones Monitor's virtual setting kept in step with
the stock one in unicorn (a turn sets the stock setting, HP Block as Main L/R; the stock setting changed elsewhere sets this one; the
mode sent inside USB Input Trim with the last destination send's context and app), the DSP code's room and the firmware it builds."""
import struct

import pytest

import block3
import features
import patch_phones
import setting_ids
from features import phones_block as pb
from firmware import assert_virtual, branch_target, built, built_e0

MODS = features.load()
IDS = setting_ids.by_name()
ID = IDS['phones_block.monitor']
MOD = 0x28e60000
GET_VALUE, SETTER, SETTER_CONTEXT, VIRT_SET = 0x28e1f844, 0x28e1f8f4, 0x28e007ec, 0x28700400
PARAM_FIND, PARAM_SEND = 0x28df35a0, 0x28df35e8
PHONES_ID, TRIM_ID, TRIM_NAME = 0x9e, 3, 4209
DATA = 0x30000000
CTX, APP, PCTX, INST, HANDLE = DATA, DATA + 0x100, DATA + 0x2000, 0x7777, 0x5150
MAIN_LR, SEND, HP_BLOCK = 0, 1, 2
_code = {}


class Phones:
    def __init__(self, m4emu):
        if 'pb' not in _code:
            _code['pb'] = m4emu.assemble('src/m4/phones_block.s', MODS, IDS, virt_set=VIRT_SET)
        code, self.sym = _code['pb']
        self.m = m4emu.M4(code, MOD)
        self.value, self.stock, self.trim = None, 1, -3.0
        self.stored, self.modes = [], []
        self.m.stub(GET_VALUE, self.get_value)
        self.m.stub(SETTER_CONTEXT, lambda m: m.reg('r0', 0x28700800))
        self.m.stub(SETTER, self.setter)
        self.m.stub(VIRT_SET, self.virt_set)
        self.m.stub(PARAM_FIND, self.find)
        self.m.stub(PARAM_SEND, self.param)
        self.m.map(DATA, 0x4000)
        self.m.u32(CTX + 0xc, PCTX - 4)
        self.m.u32(APP + 0xac8, INST)

    def get_value(self, m):
        pid = m.reg('r0')
        v = {ID: (2, self.value), PHONES_ID: (2, self.stock), TRIM_ID: (3, self.trim)}[pid]
        if v[1] is None:
            m.reg('r0', -1)
            return
        m.write(m.reg('r1'), struct.pack('<If' if v[0] == 3 else '<II', *v))
        m.reg('r0', 0)

    def setter(self, m):
        assert (m.reg('r0'), m.reg('r1'), m.reg('r3')) == (0x28700800, PHONES_ID, 1)
        self.stock = struct.unpack('<I', m.read(m.reg('r2') + 4, 4))[0]
        self.stored.append(self.stock)

    def virt_set(self, m):
        assert m.reg('r0') == ID
        self.value = m.reg('r1')

    def find(self, m):
        assert (m.reg('r0'), m.reg('r1'), m.reg('r2')) == (PCTX, INST, TRIM_NAME)
        m.u32(m.reg('r3'), HANDLE)
        m.reg('r0', 0)

    def param(self, m):
        assert (m.reg('r0'), m.reg('r1'), m.reg('r2')) == (PCTX, INST, HANDLE)
        kind, value = struct.unpack('<Bxxxf', m.read(m.reg('r3'), 8))
        code = round(value / 1000)
        self.modes.append((kind, code - 6, round(value - 1000 * code, 3)))

    def dest_send(self):
        self.m.call(MOD + self.sym['phones_block_dest_before'], CTX, APP, 0, 1)
        self.m.call(MOD + self.sym['phones_block_dest_after'], 0)

    def turn(self, value):
        self.value = value
        self.m.call(MOD + self.sym['phones_block_changed'], 0, ID)

    def page(self):
        self.m.call(MOD + self.sym['phones_block_page'], 0)


@pytest.fixture
def ph(m4emu):
    return Phones(m4emu)


def test_feature_setting():
    assert pb.MENU == 'Ins/Outs' and pb.REPLACES == PHONES_ID
    assert pb.SETTINGS[0].values == (b'Main L/R', b'Send', b'HP Block')
    assert 'usb_monitor' in pb.CONFLICTS


def test_no_mode_before_a_destination_send(ph):
    ph.value = MAIN_LR
    ph.page()
    ph.turn(HP_BLOCK)
    assert ph.modes == []


@pytest.mark.parametrize('value, mode', ((MAIN_LR, 0), (SEND, 0), (HP_BLOCK, 1)))
def test_each_destination_send_carries_the_mode(ph, value, mode):
    ph.value = value
    ph.dest_send()
    assert ph.modes == [(3, mode, -3.0)], 'a float: the trim plus 1000 * (mode + 6)'


def test_an_unset_trim_goes_as_0_db(ph):
    ph.value, ph.trim = HP_BLOCK, None
    ph.dest_send()
    assert ph.modes == [(3, 1, 0.0)]


def test_turns_set_the_stock_setting_and_the_mode(ph):
    ph.value = MAIN_LR
    ph.dest_send()
    ph.page()                       # the first paint: in step already
    ph.modes.clear()
    ph.turn(HP_BLOCK)
    assert ph.stored == [] and ph.stock == 1, 'HP Block is Main L/R to the stock'
    assert ph.modes == [(3, 1, -3.0)]
    ph.turn(SEND)
    assert ph.stored == [2] and ph.modes[-1] == (3, 0, -3.0)
    ph.turn(MAIN_LR)
    assert ph.stored == [2, 1]


def test_other_settings_are_ignored(ph):
    ph.value = HP_BLOCK
    ph.dest_send()
    ph.modes.clear()
    ph.m.call(MOD + ph.sym['phones_block_changed'], 0, ID + 1)
    assert ph.modes == [] and ph.stored == []


@pytest.mark.parametrize('value, stock, now', ((MAIN_LR, 2, SEND), (SEND, 1, MAIN_LR), (HP_BLOCK, 2, SEND), (HP_BLOCK, 1, HP_BLOCK)))
def test_the_stock_setting_decides_at_the_first_paint(ph, value, stock, now):
    """A unit whose stock Phones Monitor was set elsewhere (HX Edit, a stock build): Send is Send, Main L/R keeps HP Block."""
    ph.value, ph.stock = value, stock
    ph.page()
    assert ph.value == now and ph.stored == []


def test_dsp_code_fits_and_is_placed():
    env = {'HX_PHONES_BLOCK': '1', 'HX_MIDI_BLOCK': '1'}
    dm, pm = block3.place('HX_PHONES_BLOCK', env)
    secs, syms, kpm, _ = patch_phones.layout(dm, pm)
    assert kpm % 2 == 0 and kpm > pm
    assert syms['PH_BUS'] >= dm


def test_off_unless_asked_for():
    assert pb not in features.enabled(MODS, {})
    assert pb in features.enabled(MODS, {'HX_PHONES_BLOCK': '1'})


@pytest.mark.firmware
def test_firmware():
    read, on = built({'HX_PHONES_BLOCK': '1'}, MODS)
    assert 'phones_block' in on
    for fn, stock in ((pb.DEST_SEND, pb.DEST_SEND_STOCK), (pb.CHANGED, pb.CHANGED_STOCK), (pb.PAGE, pb.PAGE_STOCK)):
        assert read(fn, 4) != stock and branch_target(fn, read(fn, 4)) > fn, f'{fn:#x} is chained'
    assert_virtual(built_e0({'HX_PHONES_BLOCK': '1'}, MODS), pb, pb.SETTINGS[0])
