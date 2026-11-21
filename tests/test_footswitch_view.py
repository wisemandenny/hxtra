"""tools/features/footswitch_view.py and src/m4/footswitch_view.s: VIEW's cycle (Play -> Edit -> Footswitches -> Play) run in
unicorn against the key events' post, the Play view's reactivation, the screen's tiles against a fake Play view and controllers,
and the firmware it builds."""
import struct

import pytest

import features
import setting_ids
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
        code, self.sym = m4emu.assemble('src/m4/footswitch_view.s', MODS, IDS,
                                        inc={'footswitch_view.inc': f'.equ PID_INFO, {INFO:#x}\n.equ PID_MAX, {fv.PID_MAX}\n'})
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
