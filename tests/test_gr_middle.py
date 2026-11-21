"""The GR meter at Middle after a stock Home layout (issue #185): gr_meter.s against the stock Home layout and paint and the
boot ROM's widget code (the setters, the node's damage, erase and draw), run in unicorn from the stock Entry 0.

Our widgets 40..45 (Middle's slots 4..9) are drawn again only if their nodes are dirty, and two things black them out:
- The stock layout 0x28dc87cc sizes the four divider segments back to 80 px. A setSize that changes the size adds the old
  and new rectangles to the node's damage (0x10003284), and the paint's erase fills the damage with black. In the next paint
  the meter's layout sizes the segments back to 30 px, but their damage keeps the 80 px: segment 3's covers x 96..175, over
  widgets 40 and 41 (slots 4 and 5, x 128..157 and 160..189).
- On a change of the footswitch mode (setting 0x15) the top view's handler 0x28dc9e38 first clears the whole framebuffer to 0
  (0x28db8554, by DMA), and then the Home view's handler runs the stock layout, whose setVisible marks the divider and the
  labels dirty but none of ours.
So in the paint after a stock layout the meter marks the lit ones of 40..45 dirty.
The labels' layouts are stubbed here, so the screen holds only the divider and our widgets: at Middle the whole screen is
compared, at Top and Bottom only the marks.
tests/test_gr.py's Meter stubs the setters, so the last tests here only check the mark."""
import struct

import pytest

import patch_amp as pa
from firmware import stock_e0
from test_gr import (COMP_NAMES, DIVIDER, FRAME_VA, GET_VALUE, LIGHTS_DB, MODULE, REDRAW, SET_COLOR, SET_POS, SET_SIZE,
                     Meter, rot16, swapped)

HOME, FB = 0x2812a05c, 0x28d1ce98                       # the Home view; framebuffer 0, 320 columns of 240 pixels, bottom-up
INIT, LAYER, SET_VISIBLE = 0x28e24988, 0x28e24a18, 0x28e24b00
STOCK_LAYOUT, STOCK_PAINT = 0x28dc87cc, 0x28dc8d38
LABELS, PRESET_LABELS = 0x28dc853c, 0x28dc712c          # the footswitch labels' layouts, stubbed
ROM_LOCK, ROM_UNLOCK = 0x100034bc, 0x100034d0           # the ROM mutex: one thread here
ROM_CODE = 0x100000f0                                   # where Entry 0's copy of the boot ROM's functions goes
BLACK_FILL = 0x10001968                                 # the erase's fill of a node's damage
STOMP, SNAPSHOT = 0, 3                                  # setting 0x15, the footswitch mode: the stock layout selects that segment
MIDDLE, TOP, BOTTOM = 0, 1, 3
SIZES = {'S': 1, 'M': 2, 'L': 3, 'XL': 4}


class Home:
    """The Home view's divider as the Home constructor builds it, our 46 widgets, and the paint as the UI loop runs it with
    the meter's hooks."""

    def __init__(self, m4emu):
        import features.gr as gr
        code, self.sym = m4emu.assemble('src/m4/gr_meter.s', [], {}, inc=gr.inc(COMP_NAMES))
        m = self.m = m4emu.M4(code, MODULE)
        e0 = stock_e0()
        for _, off, n, dst, _ in pa._parse_e0_segments(e0):
            if dst == ROM_CODE or dst >= 0x28000000:        # the boot ROM's functions; the app's data and code
                m.load(dst, e0[off:off + n])
        self.mode, self.window = STOMP, 0
        m.stub(GET_VALUE, lambda m: (m.u32(m.reg('r1') + 4, self.mode if m.reg('r0') == 0x15 else 0), m.reg('r0', 0)))
        for fn in (REDRAW, LABELS, PRESET_LABELS, ROM_LOCK, ROM_UNLOCK):
            m.stub(fn)
        m.write(HOME, bytes(0xa80))                         # the Home view, up to the end of its divider's nodes
        for k in range(4):
            w = DIVIDER + 0x1c * k
            m.call(INIT, w, HOME + 0x9e0 + 0x28 * k)
            m.call(LAYER, w, 6)
            m.call(SET_COLOR, w, 0x666666)
            m.call(SET_SIZE, w, 80, 1)
            m.call(SET_POS, w, 80 * k, 0x77)
            m.call(SET_VISIBLE, w, 1)
        m.u8(HOME + 5, 1)                                   # the stock layout runs only once this is set
        m.u8(HOME + 0x61, 1)                                # Snapshot mode then lays its labels out with PRESET_LABELS
        m.call(MODULE + self.sym['construct'])
        self.stock_layout(STOMP)
        self.paint()
        self.paint()                                        # with the divider clean, each node's damage is its own place again

    def frame(self, lit, pos=MIDDLE, dir_=0, size=SIZES['M']):
        """A frame from the DSP with a new window, its reduction half a dB over light `lit`'s step."""
        self.window += 1
        w = [0] * 256
        w[200] = 0xf00d600d
        w[218] = rot16(0x6B000000 | pos << 16 | dir_ << 8 | size)
        b = 10 ** (-(LIGHTS_DB[lit - 1] + 0.5) / 20)
        w[216], w[217], w[250], w[251] = swapped(1.0), swapped(b), self.window, swapped(0.5)
        self.m.write(FRAME_VA, struct.pack('<256I', *w))
        self.m.call(MODULE + self.sym['frame'], 0, FRAME_VA)

    def meter(self, lit, pos=MIDDLE, dir_=0, size=SIZES['M']):
        """A frame and the paint it asks for."""
        self.frame(lit, pos, dir_, size)
        self.paint()

    def paint(self):
        self.m.call(MODULE + self.sym['erase'], FB, HOME)
        self.m.call(STOCK_PAINT, FB, HOME)
        self.m.call(MODULE + self.sym['draw'], FB)

    def stock_layout(self, mode):
        """The stock Home layout, as a select runs it, in footswitch mode `mode`."""
        self.mode = mode
        self.m.call(STOCK_LAYOUT, HOME, 0)

    def mode_change(self, mode, paint_between=False):
        """A change of the footswitch mode: the top view's handler clears the whole framebuffer to 0, then the Home view's
        handler runs the stock layout with the new mode. The paint thread may run between the two."""
        self.m.write(FB, bytes(320 * 240 * 2))
        if paint_between:
            self.paint()
        self.stock_layout(mode)

    def screen(self):
        return self.m.read(FB, 320 * 240 * 2)


def dirty(h, first=40, n=6):
    """The dirty bytes of our widgets first..first + n - 1 (by default 40..45, Middle's slots 4..9), in a Home or a Meter."""
    nodes = MODULE + h.sym['nodes']
    return [h.m.read(nodes + 0x28 * i + 0x24, 1)[0] for i in range(first, first + n)]


@pytest.mark.firmware
@pytest.mark.parametrize('lit', [5, 6, 7])
@pytest.mark.parametrize('mode', [STOMP, SNAPSHOT], ids=['Stomp', 'Snapshot'])
@pytest.mark.parametrize('size', SIZES.values(), ids=SIZES.keys())
@pytest.mark.parametrize('dir_', [0, 1], ids=['Normal', 'Reverse'])
def test_middle_band_is_whole_after_a_stock_layout(m4emu, dir_, size, mode, lit):
    """At 5 lights only one of widgets 40 and 41 is lit: 40 in Normal, 41 in Reverse."""
    h = Home(m4emu)
    h.meter(lit, MIDDLE, dir_, size)
    before = h.screen()
    h.stock_layout(mode)
    h.paint()
    assert h.screen() == before


@pytest.mark.firmware
@pytest.mark.parametrize('lit', [5, 6, 7, 8])
@pytest.mark.parametrize('size', SIZES.values(), ids=SIZES.keys())
@pytest.mark.parametrize('dir_', [0, 1], ids=['Normal', 'Reverse'])
@pytest.mark.parametrize('paint_between', [False, True], ids=['clear-layout', 'clear-paint-layout'])
def test_middle_band_is_whole_after_a_footswitch_mode_change(m4emu, paint_between, dir_, size, lit):
    """Stomp to Snapshot, then back. The clear blacks out the whole band, not only what the segments' damage covers: from 7
    lights in Normal, and at any count in Reverse, a widget beyond 40 and 41 is lit."""
    h = Home(m4emu)
    h.meter(lit, MIDDLE, dir_, size)
    before = h.screen()
    for mode in (SNAPSHOT, STOMP):
        h.mode_change(mode, paint_between)
        h.paint()
        assert h.screen() == before


@pytest.mark.firmware
def test_middle_band_is_whole_after_the_meters_own_relayout(m4emu):
    """64 frames after the meter shows, its erase runs the stock layout before its own."""
    h = Home(m4emu)
    h.meter(7)
    before = h.screen()
    for _ in range(70):
        h.frame(7)
    h.paint()
    assert h.screen() == before


@pytest.mark.firmware
def test_middle_band_is_whole_when_the_level_dips_to_5_after_a_stock_layout(m4emu):
    """Light 6 goes dark and comes back, so only light 5 keeps whatever the erase left."""
    h = Home(m4emu)
    h.meter(7)
    before = h.screen()
    h.stock_layout(SNAPSHOT)
    h.paint()
    h.meter(5)
    h.meter(7)
    assert h.screen() == before


@pytest.mark.firmware
@pytest.mark.parametrize('pos', [TOP, BOTTOM], ids=['Top', 'Bottom'])
def test_edge_marks_none_of_its_lights_after_a_stock_layout(m4emu, pos):
    """A negative control: off Middle the segments stay stock, so their width says nothing, and the layout marks none of
    40..45 and none of the edge's own ten widgets. The band itself is not compared. The labels are stubbed here, but on the
    unit the switch icons' erase reaches row 9 of a Bottom band, and a mode change's clear blacks out the whole meter at Top
    and Bottom; the mark covers neither."""
    h = Home(m4emu)
    h.meter(7, pos)
    h.stock_layout(SNAPSHOT)
    h.m.call(MODULE + h.sym['layout'])
    assert dirty(h) == [0] * 6
    assert dirty(h, 10 * (pos - 1), 10) == [0] * 10


@pytest.mark.firmware
def test_a_colour_change_marks_only_its_light(m4emu):
    """Eight lights to nine: setColor marks widget 44 (slot 8) alone."""
    h = Home(m4emu)
    h.meter(8)
    h.frame(9)
    h.m.call(MODULE + h.sym['layout'])
    assert dirty(h) == [0, 0, 0, 0, 1, 0]


@pytest.mark.firmware
def test_a_paint_with_nothing_new_erases_nothing(m4emu):
    h = Home(m4emu)
    h.meter(7)
    fills = []
    h.m.uc.hook_add(m4emu.unicorn.UC_HOOK_CODE, lambda *_: fills.append(h.m.reg('r1')), begin=BLACK_FILL, end=BLACK_FILL)
    h.paint()
    assert fills == []


@pytest.mark.firmware
def test_the_mark_adds_no_old_damage_to_a_light_resized_in_the_same_paint(m4emu):
    """XL to S, a stock layout, then S to M with 7 lights: the marked widgets 40..42 are erased over the same rows as 43,
    which is dark and not marked."""
    h = Home(m4emu)
    h.meter(7, MIDDLE, 0, SIZES['XL'])
    h.meter(7, MIDDLE, 0, SIZES['S'])
    h.stock_layout(SNAPSHOT)
    fills = []

    def fill(*_):
        fills.append((h.m.reg('r1'), h.m.reg('r2'), h.m.reg('r3'), h.m.u32(h.m.reg('sp'))))

    h.m.uc.hook_add(m4emu.unicorn.UC_HOOK_CODE, fill, begin=BLACK_FILL, end=BLACK_FILL)
    h.meter(7, MIDDLE, 0, SIZES['M'])
    rows = {x: (y, height) for x, y, w, height in fills if x >= 128}
    assert rows[128] == rows[160] == rows[192] == rows[224]


# ---- the mark alone, in test_gr.py's Meter: no firmware needed

def clean(m):
    nodes = MODULE + m.sym['nodes']
    for i in range(40, 46):
        m.m.u8(nodes + 0x28 * i + 0x24, 0)


def stock_sizes(m):
    """What the stock layout does to the segments in Stomp mode: 80 px wide, segment 0 2 px high, where they are."""
    for k in range(4):
        m.m.write(DIVIDER + 0x1c * k + 12, struct.pack('<2I', 80, 2 if k == 0 else 1))


@pytest.mark.parametrize('db, marked', [(8.5, [1, 1, 0, 0, 0, 0]), (15, [1, 1, 1, 1, 0, 0]), (26, [1] * 6)])
def test_m4_middle_marks_its_lit_lights_after_a_stock_layout(m4emu, db, marked):
    m = Meter(m4emu)
    m.frame(1.0, 10 ** (-db / 20), window=1, pos=MIDDLE)
    clean(m)
    stock_sizes(m)
    m.call('layout')
    assert dirty(m) == marked


def test_m4_middle_marks_nothing_for_a_colour(m4emu):
    m = Meter(m4emu)
    m.frame(1.0, 10 ** (-8.5 / 20), window=1, pos=MIDDLE)
    clean(m)
    m.frame(1.0, 10 ** (-10.5 / 20), window=2, pos=MIDDLE)     # one more light
    assert m.setters() == [SET_COLOR]
    assert dirty(m) == [0] * 6


def test_m4_top_marks_nothing_after_a_stock_layout(m4emu):
    m = Meter(m4emu)
    m.frame(1.0, 10 ** (-8.5 / 20), window=1, pos=TOP)
    stock_sizes(m)
    m.call('layout')
    assert dirty(m) == [0] * 6
