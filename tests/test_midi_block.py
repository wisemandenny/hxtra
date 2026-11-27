"""tools/features/midi_block.py, src/m4/midi_block.s and tools/patch_midi.py: the look at the preset's blocks in unicorn (a MIDI block
turning on or off sends its CC, a PC goes only on turning on, All sends on 16 channels, a new preset sends again, other blocks and
other events are left alone) and the firmware it builds (the post's chain, the model)."""
import hashlib
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

import features
import setting_ids
import patch_midi
from features import midi_block as mb
from firmware import branch_target, built

ROOT = Path(__file__).resolve().parent.parent
MODS = features.load()
IDS = setting_ids.by_name()
CODE = 0x28e60000
MEMSET, ENGINE, BLOCK, BYPASS, PARAM, SEND = 0x28e24b78, 0x28d92a98, 0x28e0fe94, 0x28e04514, 0x28e11338, 0x28dacf6c
SENDER = 0x281252f0
NUMBER_TEXT, NAME_TEXT = 0x2812aae0 + 0x30, 0x2812aae0 + 0x8c     # the Play view's text widgets: a pointer to their text
TEXTS = 0x28f40000
EVENT = 0x28f41000
KNOBS = ('channel', 'type', 'number', 'on', 'off')


class Unit:
    """midi_block.s with a fake preset: blocks {position: (preset ID, on, {knob: value})}."""

    def __init__(self, m4emu):
        code, self.sym = m4emu.assemble('src/m4/midi_block.s', MODS, IDS, inc={'midi_block.inc': f'.equ MIDI_PID, {mb.MIDI_PID}\n'})
        self.m = m4emu.M4(code, CODE)
        self.blocks, self.sent = {}, []
        self.preset(b'01A', b'Clean')
        self.m.stub(MEMSET, self.memset)
        self.m.stub(ENGINE, lambda m: m.reg('r0', 0x2844adcc))
        self.m.stub(BLOCK, self.block)
        self.m.stub(BYPASS, self.bypass)
        self.m.stub(PARAM, self.param)
        self.m.stub(SEND, self.send)

    def preset(self, number, name):
        self.m.write(TEXTS, number + b'\0')
        self.m.write(TEXTS + 0x40, name + b'\0')
        self.m.u32(NUMBER_TEXT, TEXTS)
        self.m.u32(NAME_TEXT, TEXTS + 0x40)

    def memset(self, m):
        m.write(m.reg('r0'), bytes([m.reg('r1') & 0xff]) * m.reg('r2'))

    def block(self, m):
        b = self.blocks.get(m.reg('r1'))
        if b is None:
            m.reg('r0', -1)
            return
        m.write(m.reg('r2') + 1, struct.pack('<H', b[0]))
        m.reg('r0', 0)

    def bypass(self, m):
        b = self.blocks.get(m.reg('r1'))
        if b:
            m.write(m.reg('r2'), bytes([0 if b[1] else 1]))
        m.reg('r0', 0)

    def param(self, m):
        req = struct.unpack('<iI', m.read(m.reg('r2'), 8))
        assert req[0] == -2, 'a parameter by its index'
        value = self.blocks[m.reg('r1')][2][KNOBS[req[1]]]
        m.write(m.reg('r3'), bytes([2]) + struct.pack('<I', value))
        m.reg('r0', 0)

    def send(self, m):
        assert m.reg('r0') == SENDER
        msg = m.read(m.reg('r1'), 12)
        self.sent.append((msg[0], msg[8] + 1, msg[9], msg[10]))

    def ticks(self, n=5):
        """n of the UI task's ticks (5 make one look) -> the messages sent [(kind, channel, d1, d2)]."""
        self.sent = []
        for _ in range(n):
            self.m.write(EVENT, bytes([3, 0, 0, 0, 0, 0, 0, 0]))
            self.m.call(CODE + self.sym['midi_block_post'], EVENT)
        return self.sent


def knobs(channel=1, type=0, number=20, on=127, off=0):
    return dict(channel=channel, type=type, number=number, on=on, off=off)


CC, PC = 3, 5


def test_cc_on_load_and_on_each_turn(m4emu):
    u = Unit(m4emu)
    u.blocks[3] = [mb.MIDI_PID, True, knobs(channel=2, number=64, on=100, off=5)]
    assert u.ticks() == [(CC, 2, 64, 100)], 'the preset loads with it on'
    assert u.ticks() == [], 'nothing while it stays on'
    u.blocks[3][1] = False
    assert u.ticks() == [(CC, 2, 64, 5)]
    u.blocks[3][1] = True
    assert u.ticks() == [(CC, 2, 64, 100)]


def test_looks_five_ticks_apart(m4emu):
    u = Unit(m4emu)
    u.blocks[0] = [mb.MIDI_PID, True, knobs()]
    assert u.ticks(4) == []
    assert u.ticks(1) == [(CC, 1, 20, 127)]


def test_pc_only_on_turning_on(m4emu):
    u = Unit(m4emu)
    u.blocks[12] = [mb.MIDI_PID, False, knobs(type=1, number=7)]
    assert u.ticks() == []
    u.blocks[12][1] = True
    assert u.ticks() == [(PC, 1, 7, 127)]
    u.blocks[12][1] = False
    assert u.ticks() == []


def test_all_channels(m4emu):
    u = Unit(m4emu)
    u.blocks[5] = [mb.MIDI_PID, True, knobs(channel=0, number=1, on=9)]
    assert u.ticks() == [(CC, c, 1, 9) for c in range(1, 17)]


def test_a_new_preset_sends_again(m4emu):
    u = Unit(m4emu)
    u.blocks[5] = [mb.MIDI_PID, True, knobs()]
    assert len(u.ticks()) == 1
    u.preset(b'01B', b'Lead')
    assert u.ticks() == [(CC, 1, 20, 127)]


def test_other_blocks_and_events_are_left_alone(m4emu):
    u = Unit(m4emu)
    u.blocks[1] = [181, True, knobs()]
    assert u.ticks() == []
    before = len(u.m.calls(BLOCK))
    for _ in range(10):
        u.m.write(EVENT, bytes([1, 5, 0, 0, 1, 0, 0, 0]))
        u.m.call(CODE + u.sym['midi_block_post'], EVENT)
    assert len(u.m.calls(BLOCK)) == before, 'a key event is not a tick'


def test_several_blocks_each_send(m4emu):
    u = Unit(m4emu)
    u.blocks[2] = [mb.MIDI_PID, True, knobs(number=1)]
    u.blocks[9 + 22] = [mb.MIDI_PID, False, knobs(number=2)]
    assert u.ticks() == [(CC, 1, 1, 127), (CC, 1, 2, 0)]


def test_preset_id_matches_the_model():
    assert mb.MIDI_PID == patch_midi.PRESET_ID


def test_off_unless_asked_for():
    assert mb not in features.enabled(MODS, {})
    assert mb in features.enabled(MODS, {'HX_MIDI_BLOCK': '1'})


@pytest.mark.firmware
def test_firmware():
    read, on = built({'HX_MIDI_BLOCK': '1'}, MODS)
    assert 'midi_block' in on
    assert read(mb.POST, 4) != mb.POST_STOCK and branch_target(mb.POST, read(mb.POST, 4)) > mb.POST


MIDI_BUILT_MD5 = {
    'HX_MIDI_BLOCK': 'd869d90dfbf2d4309cc2b62aabdc392c',
    'HX_MIDI_BLOCK HX_CLICK HX_FX_GATE HX_GATE_SC HX_GR HX_USB_MONITOR HX_NAM_SLOTS=1': '32093903958cd8e7624f23266556b374',  # beside every DSP option
}


@pytest.mark.firmware
@pytest.mark.parametrize('flags', MIDI_BUILT_MD5)
def test_midi_build(tmp_path, flags):
    """build.py with the MIDI block: ALL OK (Entry 3 within E3_MAX on the final image) and the image pinned."""
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    out = tmp_path / 'midi.hxf'
    env = {k: v for k, v in os.environ.items() if not k.startswith('HX_') or k == 'HX_STOMP_HXF'}
    env |= dict(f.split('=') if '=' in f else (f, '1') for f in flags.split())
    r = subprocess.run([sys.executable, str(ROOT / 'build.py'), stock, '-o', str(out), '--no-check'],
                       capture_output=True, text=True, cwd=ROOT, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'ALL OK' in r.stdout and 'strings and model table back home' in r.stdout
    assert hashlib.md5(out.read_bytes()).hexdigest() == MIDI_BUILT_MD5[flags]
