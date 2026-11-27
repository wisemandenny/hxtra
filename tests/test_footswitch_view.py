"""tools/features/footswitch_view.py and src/m4/footswitch_view.s: VIEW's cycle (Play -> Edit -> Footswitches -> Play) run in
unicorn against the key events' post, the Play view's reactivation, the screen's tiles against a fake Play view and controllers,
and the firmware it builds."""
import struct

import pytest

import features
import setting_ids
import kit_patch_amp as kit
from features import footswitch_view as fv
from firmware import branch_target, built

MODS = features.load()
IDS = setting_ids.by_name()
CODE, EVENT, INFO = 0x28e60000, 0x28f40000, 0x28f50000
SCREEN = 0x28128260
REQUEST_VIEW = 0x28d96320
LOCK, UNLOCK, REPAINT = 0x28e249a0, 0x28e24a30, 0x28db8508
TOP_HANDLER, HOME_HANDLER = 0x28dca554, 0x28dc9128
PRESS, RELEASE = 1, 2
VIEW, NO_KEY = 5, 0xff


class View:
    def __init__(self, m4emu):
        inc = (f'.equ TAB1_BASE_PTR, {INFO:#x}\n.equ TAB1_CNT_INSN, {INFO + 4:#x}\n'
               f'.equ TAB2_BASE_PTR, {INFO + 8:#x}\n.equ TAB2_CNT_INSN, {INFO + 12:#x}\n')
        code, self.sym = m4emu.assemble('src/m4/footswitch_view.s', MODS, IDS, inc={'footswitch_view.inc': inc})
        self.m = m4emu.M4(code, CODE)
        self.requests, self.handlers = [], []
        self.m.stub(REQUEST_VIEW, lambda m: self.requests.append(m.reg('r0')))
        for fn in (LOCK, UNLOCK, REPAINT):
            self.m.stub(fn)
        self.m.stub(TOP_HANDLER, lambda m: self.handlers.append(('top', m.reg('r1'))))
        self.m.stub(HOME_HANDLER, lambda m: self.handlers.append(('home', m.reg('r1'))))

    def post(self, screen, code, kind):
        self.m.u8(SCREEN, screen)
        self.m.write(EVENT, bytes([1, code, 0, 0]) + struct.pack('<I', kind))
        self.m.call(CODE + self.sym['footswitch_view_post'], EVENT)
        return self.m.read(EVENT, 2)[1]         # the key code the stock post then sees

    def shown(self):
        return self.m.read(CODE + self.sym['state'], 4)[1]


def test_view_cycle(m4emu):
    """VIEW in Edit arms the screen and goes on to the stock (which shows Play, and the screen over it); VIEW on the screen is taken
    (its press and everything to its release become NO_KEY), asks for the Play view and has the view controller reactivate it."""
    v = View(m4emu)
    assert v.post(1, VIEW, PRESS) == VIEW and v.m.read(CODE + v.sym['state'], 1)[0] == 1       # armed, passed on
    v.m.write(CODE + v.sym['state'], bytes([0, 1, 0, 0]))                                     # the paint showed it
    assert v.post(0, VIEW, PRESS) == NO_KEY and v.requests == [0] and v.shown() == 0
    assert v.post(0, VIEW, 3) == NO_KEY                                                # swallowed until its release
    assert v.post(0, VIEW, RELEASE) == NO_KEY
    assert v.post(0, VIEW, PRESS) == VIEW                                              # in Play, screen off: stock
    v.m.call(CODE + v.sym['footswitch_view_controller'])
    assert v.handlers == [('top', 0), ('home', 0), ('top', 1), ('home', 1)]           # Play deactivated, then activated
    v.handlers.clear()
    v.m.call(CODE + v.sym['footswitch_view_controller'])
    assert v.handlers == []                                                            # once


def test_another_screen_turns_it_off(m4emu):
    """Leaving Play another way (the tuner, the Menu): the next event while that screen is up (a tick, say) clears the screen, so the
    return to Play shows Play; in Play, events leave it on."""
    v = View(m4emu)
    v.m.write(CODE + v.sym['state'], bytes([0, 1, 0, 0]))
    v.m.u8(SCREEN, 0)
    v.m.write(EVENT, bytes([3, 0, 0, 0, 0, 0, 0, 0]))
    v.m.call(CODE + v.sym['footswitch_view_post'], EVENT)
    assert v.shown() == 1
    v.m.u8(SCREEN, 4)
    v.m.call(CODE + v.sym['footswitch_view_post'], EVENT)
    assert v.shown() == 0


def test_paints_after_every_other_play_view_painter():
    """More Snapshots' paints (and Real block names' Table 2) come first: ORDER after them."""
    order = [features.name(m) for m in MODS]
    assert order.index('footswitch_view') > max(order.index(n) for n in ('more_snapshots', 'real_names', 'long_press'))
    assert getattr(fv, 'WEB', True) is True, 'in every web build: it takes no DSP'


def tables(v, models):
    """Table 1 and Table 2 in memory, as the tables' pointer literals and count movws point at them: models [(preset ID, name,
    category)], each with its name index."""
    t1, t2 = INFO + 0x100, INFO + 0x1000
    for k, (pid, name, cat) in enumerate(models):
        v.m.write(t1 + 12 * k, struct.pack('<IHHI', 0x1000 + k, pid, 0, 10))
        row = bytearray(44)                                             # Table 2 in another order than Table 1
        row[4:20] = name.ljust(16, b'\0')
        row[0x15] = cat
        struct.pack_into('<I', row, 0, 0x1000 + k)
        v.m.write(t2 + 44 * (len(models) - 1 - k), bytes(row))
    v.m.u32(INFO, t1)
    v.m.write(INFO + 4, kit._encode_thumb_movw(3, len(models)))
    v.m.u32(INFO + 8, t2)
    v.m.write(INFO + 12, kit._encode_thumb_movw(1, len(models)))


def test_a_blocks_row_comes_from_the_tables_at_run_time(m4emu):
    """model_row: a preset ID through Table 1 to its Table 2 row, wherever the tables are and however many rows they have, so a
    model added after the menu step (the Metronome 181, the MIDI block 380, the Phones block 381) has its name and category."""
    v = View(m4emu)
    models = [(7, b'Scream 808', 2), (181, b'Metronome', 0x19), (380, b'MIDI', 5), (381, b'Phones', 5), (300 + 2 ** 9, b'X', 1)]
    tables(v, models)
    for pid, name, cat in models:
        row = v.m.call(CODE + v.sym['model_row'], pid)
        assert row and v.m.read(row + 4, 16).rstrip(b'\0') == name and v.m.read(row + 0x15, 1)[0] == cat
    assert v.m.call(CODE + v.sym['model_row'], 999) == 0


@pytest.mark.parametrize('n', (0, 1, 0x1ff, 0x340, 0xffff))
def test_movw_imm(m4emu, n):
    v = View(m4emu)
    for rd in (0, 3, 9):
        v.m.write(INFO, kit._encode_thumb_movw(rd, n))
        assert v.m.call(CODE + v.sym['movw_imm'], INFO) == n


def test_other_keys_pass(m4emu):
    v = View(m4emu)
    v.m.write(CODE + v.sym['state'], bytes([0, 1, 0, 0]))
    for code in (0, 1, 2, 6):
        assert v.post(0, code, PRESS) == code
    assert v.requests == []


@pytest.mark.firmware
def test_firmware():
    """The post and the view controller each get a chain whose before handler is the module's; both Play paints chain to its paint."""
    read, on = built({'HX_FOOTSWITCH_VIEW': '1'})
    assert 'footswitch_view' in on
    for site in (fv.POST, fv.CONTROLLER):
        assert branch_target(site, read(site, 4)) is not None, f'{site:#x} not hooked'
    for lit, stock in ((fv.TOP_PAINT_LIT, fv.TOP_PAINT), (fv.HOME_PAINT_LIT, fv.HOME_PAINT)):
        assert struct.unpack('<I', read(lit, 4))[0] != stock
