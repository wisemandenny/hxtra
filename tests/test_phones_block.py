"""tools/features/phones_block.py, src/m4/phones_block.s and tools/patch_phones.py: Phones Monitor's virtual setting kept in step with
the stock one in unicorn (a turn sets the stock setting, HP Block as Main L/R; the stock setting changed elsewhere sets this one; the
mode sent inside USB In 1/2 Trim with the last destination send's context and app, or by USB monitoring's sender in a build with it),
the DSP code's room and the firmware it builds; phones.asm's control wrapper splitting the code word both features share."""
import hashlib
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

import block3
import features
import patch_phones
import setting_ids
from features import phones_block as pb
from firmware import assert_virtual, branch_target, built, built_e0

ROOT = Path(__file__).resolve().parent.parent
MODS = features.load()
IDS = setting_ids.by_name()
ID = IDS['phones_block.monitor']
MOD = 0x28e60000
GET_VALUE, SETTER, SETTER_CONTEXT, VIRT_SET = 0x28e1f844, 0x28e1f8f4, 0x28e007ec, 0x28700400
PARAM_FIND, PARAM_SEND = 0x28df35a0, 0x28df35e8
PHONES_ID, TRIM_ID, TRIM_NAME, TRIM_TYPE = 0x9e, 0x99, 4209, 1    # USB In 1/2 Trim (I/O 0x99), a stand-in type
UM_RESEND = 0x28700600
DATA = 0x30000000
CTX, APP, PCTX, INST, HANDLE = DATA, DATA + 0x100, DATA + 0x2000, 0x7777, 0x5150
MAIN_LR, SEND, HP_BLOCK = 0, 1, 2
_code = {}


class Phones:
    def __init__(self, m4emu, usb=False):
        key = 'pb+um' if usb else 'pb'
        if key not in _code:
            inc = f'.equ UM_RESEND, {UM_RESEND | 1:#x}\n' if usb else '@ no USB monitoring\n'
            _code[key] = m4emu.assemble('src/m4/phones_block.s', MODS, IDS, virt_set=VIRT_SET, inc={'phones_block.inc': inc})
        code, self.sym = _code[key]
        self.m = m4emu.M4(code, MOD)
        self.value, self.stock, self.trim = None, 1, -3.0
        self.stored, self.modes = [], []
        self.m.stub(GET_VALUE, self.get_value)
        self.m.stub(SETTER_CONTEXT, lambda m: m.reg('r0', 0x28700800))
        self.m.stub(SETTER, self.setter)
        self.m.stub(VIRT_SET, self.virt_set)
        self.m.stub(PARAM_FIND, self.find)
        self.m.stub(PARAM_SEND, self.param)
        self.resends = 0
        self.m.stub(UM_RESEND, self.resend)
        self.m.map(DATA, 0x4000)
        self.m.u32(CTX + 0xc, PCTX - 4)
        self.m.u32(APP + 0xac8, INST)

    def get_value(self, m):
        pid = m.reg('r0')
        assert pid in (ID, PHONES_ID, TRIM_ID), f'GET_VALUE({pid:#x}): setting 3 is Send/Return R, not the trim (#181)'
        v = {ID: (2, self.value), PHONES_ID: (2, self.stock), TRIM_ID: (TRIM_TYPE, self.trim)}[pid]
        if v[1] is None:
            m.reg('r0', -1)
            return
        m.write(m.reg('r1'), struct.pack('<If' if pid == TRIM_ID else '<II', *v))
        m.reg('r0', 0)

    def resend(self, m):
        self.resends += 1

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
        k = round(value / 1000)
        assert k % 5 == 0, 'no USB monitoring: U is 0'
        self.modes.append((kind, k // 5 - 1, round(value - 1000 * k, 3)))

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
    assert not getattr(pb, 'CONFLICTS', ()), 'builds beside USB monitoring'
    assert pb.ORDER > getattr(__import__('features.usb_monitor').usb_monitor, 'ORDER', 100), 'after usb_monitor: it calls um_resend'
    assert (ID, 112, 2, 2) in [(v, c, b, n) for v, c, b, n, who, _ in setting_ids.VIRTUAL if who == 'phones_block.monitor']
    assert ID == 0xeb


def test_no_mode_before_a_destination_send(ph):
    ph.value = MAIN_LR
    ph.page()
    ph.turn(HP_BLOCK)
    assert ph.modes == []


@pytest.mark.parametrize('value, mode', ((MAIN_LR, 0), (SEND, 0), (HP_BLOCK, 1)))
def test_each_destination_send_carries_the_mode(ph, value, mode):
    ph.value = value
    ph.dest_send()
    assert ph.modes == [(TRIM_TYPE, mode, -3.0)], 'the trim plus 1000 * 5 * (mode + 1), in the trim\'s own type'


def test_an_unset_trim_goes_as_0_db(ph):
    ph.value, ph.trim = HP_BLOCK, None
    ph.dest_send()
    assert ph.modes == [(0, 1, 0.0)], 'as USB monitoring sends it: 0 dB'


def test_turns_set_the_stock_setting_and_the_mode(ph):
    ph.value = MAIN_LR
    ph.dest_send()
    ph.page()                       # the first paint: in step already
    ph.modes.clear()
    ph.turn(HP_BLOCK)
    assert ph.stored == [] and ph.stock == 1, 'HP Block is Main L/R to the stock'
    assert ph.modes == [(TRIM_TYPE, 1, -3.0)]
    ph.turn(SEND)
    assert ph.stored == [2] and ph.modes[-1] == (TRIM_TYPE, 0, -3.0)
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
    """A unit whose stock Phones Monitor was set elsewhere (HX Edit, a stock build): Send is Send, Main L/R keeps HP Block; a change
    sends the mode, which the boot sent from the old value."""
    ph.value, ph.stock = value, stock
    ph.dest_send()
    ph.modes.clear()
    ph.page()
    assert ph.value == now and ph.stored == []
    assert ph.modes == ([] if now == value else [(TRIM_TYPE, int(now == HP_BLOCK), -3.0)])


def test_with_usb_monitoring_a_turn_asks_its_sender(m4emu):
    """In a build with USB monitoring, its sender (usb_monitor.s um_resend) sends the word both modes share; this module sends none."""
    ph = Phones(m4emu, usb=True)
    ph.value = MAIN_LR
    ph.page()                       # the first paint, in step: nothing to send
    assert ph.resends == 0
    ph.turn(HP_BLOCK)
    assert ph.resends == 1 and ph.modes == []
    ph.turn(HP_BLOCK)
    assert ph.resends == 1, 'no turn, no send'
    ph.turn(SEND)
    assert ph.resends == 2 and ph.stored == [2]


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
@pytest.mark.parametrize('usb', (False, True))
def test_firmware(usb):
    env = {'HX_PHONES_BLOCK': '1'} | ({'HX_USB_MONITOR': '1'} if usb else {})
    read, on = built(env, MODS)
    assert 'phones_block' in on and ('usb_monitor' in on) == usb
    for fn, stock in ((pb.DEST_SEND, pb.DEST_SEND_STOCK), (pb.CHANGED, pb.CHANGED_STOCK), (pb.PAGE, pb.PAGE_STOCK)):
        assert read(fn, 4) != stock and branch_target(fn, read(fn, 4)) > fn, f'{fn:#x} is hooked'
    assert_virtual(built_e0(env, MODS), pb, pb.SETTINGS[0])


PHONES_BUILT_MD5 = {
    'HX_PHONES_BLOCK': '2f3e4e6975d8ed250624893607e1eb54',
    'HX_PHONES_BLOCK HX_USB_MONITOR': '4ae31e70e49fb5cef9f1ff2ea3cc32fb',
    'HX_PHONES_BLOCK HX_MIDI_BLOCK HX_CLICK HX_FX_GATE HX_GATE_SC HX_GR HX_USB_MONITOR HX_NAM_SLOTS=2': '97f02f46d11633051b343b74bb681f21',  # the page's default
}


@pytest.mark.firmware
@pytest.mark.parametrize('flags', PHONES_BUILT_MD5)
def test_phones_build(tmp_path, flags):
    """build.py with the Phones block: ALL OK, beside USB monitoring its two wrappers stand for USB monitoring's, the image pinned."""
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    out = tmp_path / 'phones.hxf'
    env = {k: v for k, v in os.environ.items() if not k.startswith('HX_') or k == 'HX_STOMP_HXF'}
    env |= dict(f.split('=') if '=' in f else (f, '1') for f in flags.split())
    r = subprocess.run([sys.executable, str(ROOT / 'build.py'), stock, '-o', str(out), '--no-check'],
                       capture_output=True, text=True, cwd=ROOT, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'ALL OK' in r.stdout
    assert ("the phones' writer and the Level gain's control are the Phones block's wrappers" in r.stdout) == ('HX_USB_MONITOR' in flags)
    assert hashlib.md5(out.read_bytes()).hexdigest() == PHONES_BUILT_MD5[flags]
