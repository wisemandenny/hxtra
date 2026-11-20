"""The GR meter across a preset change (issue #176): the DSP wrapper (frame_probe.asm, in ssim) feeds the M4 meter (gr_meter.s,
in unicorn) through a frame buffer that the stock DSP keeps sending.

The stock DSP sends the M4 frames from two fixed buffers (the link's DMA handler calls the send callback 0x173d12 with
R8 = DM(0xc4cc5) + k * DM(0xc4cc7), k = 0 or 1, at 0x175ffa..0x176016). The callback writes the buffer's word 0 (0x173e75),
word 1 (0x173e7b) and trailer at length - 1 (0x173e8c). Through I5, when set, it writes a magic, a header and a trailer again
(0x173e80, 0x173e82, 0x173e93); what I5 points to is not traced (a second copy, or the buffer itself). The queued messages go
from word 2 (0x1745b2) of one of the two. Nothing in it writes the words between the last message and the trailer.
stock_send() models the buffer."""
import struct

import pytest

from test_gr import DIVIDER, FRAME, FRAME_VA, MODULE, Meter, block, knobs, lit, probe, rot16

SEL = 0                                   # Meter's GET_VALUE stub reads setting 0x15 as 0: segment 0 is the selected one
METERED, OTHER = 0x96000, 0x97000         # the metered compressor's state; another compressor's
MIDDLE, TOP = 0, 1


def stock_send(s, payload=8):
    """The stock send callback refilling a frame buffer: magic, header, a short message, trailer. The tail stays as it was."""
    s.wr(FRAME + 0, 0xFACEF00D)
    s.wr(FRAME + 1, 0x01000000 | payload)
    for k in range(payload):
        s.wr(FRAME + 2 + k, 0x1000 + k)
    s.wr(FRAME + 255, 0xD00FECAF)


def stock_divider():
    """The Home view's four divider segments as the stock layout leaves them: (colour, x, y, w, h)."""
    return [(0xffffff if k == SEL else 0x666666, 80 * k, 0x77, 80, 2 if k == SEL else 1) for k in range(4)]


def divider(m):
    return [struct.unpack('<5I', m.m.read(DIVIDER + 0x1c * k, 20)) for k in range(4)]


def all_off(m):
    """The meter is off, none of our 46 widgets is lit, and the divider is stock."""
    ours = [m.m.u32(MODULE + m.sym['widgets'] + 0x1c * k) for k in range(46)]
    return m.word('data', 5) == 0 and not any(ours) and divider(m) == stock_divider()


def home(m4emu):
    m = Meter(m4emu)
    for k, (c, x, y, w, h) in enumerate(stock_divider()):
        m.m.write(DIVIDER + 0x1c * k, struct.pack('<5I', c, x, y, w, h))
    return m


def receive(s, m):
    """One frame from the DSP: the stock callback refills the buffer, the M4 receives it and the Home view repaints."""
    stock_send(s)
    m.m.write(FRAME_VA, struct.pack('<256I', *(rot16(s.rd(FRAME + k)) for k in range(256))))
    m.call('frame', 0, FRAME_VA)
    m.call('layout')


def meter_on(m4emu, pos=MIDDLE, gain=1.0):
    """A Deluxe Comp at Mtr Pos `pos`, Mtr Size M, its core's gain `gain`, run for one window: the meter shows."""
    s, sym = probe()
    knobs(s, sym, 'CTRL_271A', METERED, pos, 0, 2)
    m = home(m4emu)
    for _ in range(64):
        block(s, sym, 'ENTRY_271A', METERED, 0.5, gain=gain)
    receive(s, m)
    assert m.word('data', 5) == 1, 'the meter shows'
    return s, sym, m


@pytest.mark.parametrize('next_preset', ['no compressor', 'a compressor at Mtr Size Off'])
@pytest.mark.parametrize('pos, gain', [(MIDDLE, 1.0), (TOP, 0.25)], ids=['dark at Middle', 'lit at Top'])
def test_meter_goes_off_after_a_preset_change(m4emu, pos, gain, next_preset):
    """The next preset does not run the metered core: within the M4's 1024 frames the meter is off and the divider stock."""
    s, sym, m = meter_on(m4emu, pos, gain)
    if pos == MIDDLE:
        assert divider(m) != stock_divider() and all(c == 0 for c, *_ in divider(m)), 'the dark band takes the divider'
    else:
        assert lit(m, TOP) == 7, '12 dB of reduction as the preset changes'
    if next_preset != 'no compressor':
        knobs(s, sym, 'CTRL_271A', OTHER, MIDDLE, 0, 0)
    for _ in range(1100):
        if next_preset != 'no compressor':
            block(s, sym, 'ENTRY_271A', OTHER, 0.5)
        receive(s, m)
    assert all_off(m)


def test_meter_goes_off_when_the_frames_lose_the_marker(m4emu):
    """Frames without the marker count the same way."""
    s, sym, m = meter_on(m4emu)
    for k in range(3, 255):
        s.wr(FRAME + k, 0)
    for _ in range(1100):
        receive(s, m)
    assert all_off(m)


def test_meter_goes_off_when_mtr_size_off_hands_it_to_a_gone_core(m4emu):
    """CORES keeps an earlier preset's cores: Mtr Size Off on the metered block hands the meter to one that no longer runs."""
    s, sym, m = meter_on(m4emu)
    knobs(s, sym, 'CTRL_271A', OTHER, TOP, 0, 2)
    for _ in range(64):
        block(s, sym, 'ENTRY_271A', OTHER, 0.5, gain=0.25)
        receive(s, m)
    assert lit(m, TOP) == 7
    knobs(s, sym, 'CTRL_271A', OTHER, TOP, 0, 0)
    assert s.rd(sym('GR_CORE')) == METERED
    for _ in range(1100):
        block(s, sym, 'ENTRY_271A', OTHER, 0.5, gain=0.25)
        receive(s, m)
    assert all_off(m)


def test_frame_tail_outlives_the_metered_core(m4emu):
    """After the metered core stops, the frames still carry its marker, knobs and window: the M4 counts the frames since the
    last new window and turns the meter off at 1024."""
    s, sym, m = meter_on(m4emu)
    tail = [s.rd(FRAME + k) for k in (200, 218, 250)]
    for _ in range(1023):
        receive(s, m)
    assert (m.word('data', 1), m.word('data', 5)) == (1023, 1)
    receive(s, m)
    assert (m.word('data', 1), m.word('data', 5)) == (1024, 0)
    assert [s.rd(FRAME + k) for k in (200, 218, 250)] == tail == [0x600DF00D, 0x6B000002, 1]


def test_frame_count_stops_at_its_top(m4emu):
    """The count of frames since a new window stops at 0xffffffff: wrapped to 0, it would show the gone core's meter again."""
    s, sym, m = meter_on(m4emu)
    for _ in range(1024):
        receive(s, m)
    assert all_off(m)
    m.m.u32(MODULE + m.sym['data'] + 4, 0xfffffff0)
    shown = []
    for _ in range(40):
        receive(s, m)
        shown.append(m.word('data', 5))
    assert shown == [0] * 40 and m.word('data', 1) == 0xffffffff and all_off(m)


def test_meter_stays_on_while_the_metered_core_runs(m4emu):
    """A running core closes a window every 64 blocks whatever the signal, so the meter stays on past 1024 frames."""
    s, sym, m = meter_on(m4emu)
    for _ in range(1100):
        block(s, sym, 'ENTRY_271A', METERED, 0.0)
        receive(s, m)
    assert m.word('data', 5) == 1 and m.word('data', 1) < 64


def test_next_metered_compressor_brings_the_meter_back(m4emu):
    """Once the old tail has turned the meter off, another compressor set to Mtr Size M takes it: its frames repeat the old
    window until its own first one closes, and that one shows the meter."""
    s, sym, m = meter_on(m4emu)
    for _ in range(1100):
        receive(s, m)
    assert all_off(m)
    knobs(s, sym, 'CTRL_271A', OTHER, TOP, 0, 2)
    shown = []
    for _ in range(64):
        block(s, sym, 'ENTRY_271A', OTHER, 0.5, gain=0.25)
        receive(s, m)
        shown.append(m.word('data', 5))
    assert shown == [0] * 63 + [1]
    assert lit(m, TOP) == 7
