"""tools/features/looper.py and src/m4/looper.s: Looper Stop>Ply and Looper DblPress, the handler run in unicorn against a stand-in
for the stock state machine (what it hands the stock and what it does to the looper), the stock code it relies on, and the built state
machine run in unicorn from the stock file with the looper's tick, beside the stock one: press, release and hold from stopped, the
double press, the stock values as stock, every other state and gesture as stock, the double-press gap with DblPress on Release and
Stock, the window after a first press from every other state (opened only by a release that finds the loop playing), a press
between the overdub's post and the worker task, the four combinations of the two settings; and the firmware it builds."""
import functools
import struct

import pytest

import features
import patch_amp as pa
import patch_menu as pm
import setting_ids
from features import looper
from firmware import assert_virtual, branch_target, built, built_e0, reader, stock_e0
from test_hxtra import page_table

MODS = features.load()
IDS = setting_ids.by_name()
STOP_PLAY, DBL_PRESS = IDS['looper.stop_play'], IDS['looper.dbl_press']
PRESS_PLAYS, RELEASE_PLAYS = 0, 1                       # Stop>Ply's values
DBL_RELEASE, DBL_STOCK = 0, 1                           # DblPress's values
WINDOW_TICKS, OVERDUB_TICKS = 20, 21                    # the press's double-press window; the release's deferred overdub
PRESS, RELEASE, HOLD, TAIL = 1, 2, 5, 0                 # TAIL: no case of the state machine's, only its common tail
FS1, FS1_CODE = 0, 12                                   # the press hands over the switch, the release and hold its key code

CODE, STOCK = 0x28e60000, 0x28700000                    # the module, and the stock state machine as the veneer hands it over
L = 0x281298dc                                          # the looper object, 0x28d9609c()
GET_LOOPER, PLAY, STOP, REC, ODUB_OFF, UNDO = 0x28d9609c, 0x28de7c34, 0x28de7cf0, 0x28de77b8, 0x28de7b24, 0x28de7e44
TONE_OF, LISTEN = 0x28d92a98, 0x28e04354                # the state machine's common tail: the DSP listener, once
TICK, LOCK, UNLOCK, POST = 0x28d92264, 0x28e24a90, 0x28e249a8, 0x28d96800     # the looper's tick (r1 the looper), its work post
STATE, FLAGS, LOOP, UNDO_READY, LISTENING = 0x56, 0x4c, 0x60, 0x64, 0x65
STARTED, ACTED, SECOND, POPUP, OVERDUB_IN, WINDOW = 0x66, 0x67, 0x68, 0x6b, 0x6c, 0x74
STOPPED, PLAYING, RECORDING, OVERDUBBING, ONCE, ONCE_OVERDUB = 0, 1, 2, 3, 5, 6
OVERDUB_FLAG = 0x20                                     # the tick's post of the deferred overdub
RECORDS, CONTAINER, FLOAT_ONE = 0x2845ee9c, 115, 0x3f800000     # Stop>Ply's container record: type +8, value +0xc
SIZE = 0x88
_code = {}


def code(m4emu):
    if 'looper' not in _code:
        _code['looper'] = m4emu.assemble('src/m4/looper.s', MODS, IDS)
    return _code['looper']


def setup(m, state=STOPPED, loop=1, window=0, started=0, acted=0, second=0, undo=0, listening=1, popup=0, overdub=0):
    """The looper object, all else 0."""
    m.write(L, bytes(SIZE))
    for off, v in ((STATE, state), (LOOP, loop), (STARTED, started), (ACTED, acted), (SECOND, second), (UNDO_READY, undo),
                   (LISTENING, listening), (POPUP, popup), (OVERDUB_IN, overdub)):
        m.u8(L + off, v)
    m.u32(L + WINDOW, window)


class Handler:
    """looper_event in unicorn: what reaches the stock state machine (the switch, the event, and the looper as it was then), and the
    Play calls, which play a stopped loop as the stock Play does; GET_VALUE answers Stop>Ply with stop_play and DblPress with
    dbl_press (None: unset)."""

    def __init__(self, m4emu, stop_play=RELEASE_PLAYS, dbl_press=DBL_STOCK):
        text, self.sym = code(m4emu)
        self.m = m = m4emu.M4(text, CODE)
        self.settings, self.seen, self.top = {STOP_PLAY: stop_play, DBL_PRESS: dbl_press}, [], (m4emu.RETURN | 1, m4emu.STACK_TOP)
        m.stub(GET_LOOPER, lambda m: m.reg('r0', L))
        m.stub(PLAY, self._play)
        m.stub(pm.GET_VALUE, self._get_value)
        m.stub(STOCK, self._stock)
        setup(m)

    def _play(self, m):
        if m.read(L + STATE, 1)[0] == STOPPED and m.read(L + LOOP, 1)[0]:
            m.u8(L + STATE, PLAYING)

    def _get_value(self, m):
        if self.settings.get(m.reg('r0')) is not None:
            m.u8(m.reg('r1'), 2)
            m.u32(m.reg('r1') + 4, self.settings[m.reg('r0')])
            m.reg('r0', 0)
        else:
            m.reg('r0', -1)

    def _stock(self, m):
        assert (m.reg('lr'), m.reg('sp')) == self.top, 'a tail call, with the caller\'s lr and stack'
        self.seen.append((m.reg('r0'), m.reg('r1'), m.read(L, SIZE)))

    def event(self, ev):
        """One event of FS1 -> (the switch and event the stock got, the looper then) and the Play calls' looper."""
        self.seen.clear()
        self.m.log.clear()
        self.m.call(CODE + self.sym['looper_event'], FS1 if ev == PRESS else FS1_CODE, ev, STOCK | 1)
        (switch, got, then), = self.seen
        return (switch, got, then), [regs[0] for regs in self.m.calls(PLAY)]

    def reads(self):
        return [regs[0] for regs in self.m.calls(pm.GET_VALUE)]


@pytest.fixture
def h(m4emu):
    return Handler(m4emu)


def test_the_settings():
    """Stop>Ply (Press, 0, is stock; Release the default) and DblPress (Release first: the fix is on by default), side by side in
    container 115."""
    stop_play, dbl_press = looper.SETTINGS
    assert (stop_play.key, stop_play.label, stop_play.values, stop_play.default) == \
        ('stop_play', b'Stop>Ply\nLooper', (b'Press', b'Release'), RELEASE_PLAYS)
    assert (dbl_press.key, dbl_press.label, dbl_press.values, dbl_press.default) == \
        ('dbl_press', b'DblPress\nLooper', (b'Release', b'Stock'), DBL_RELEASE)
    for s in looper.SETTINGS:
        head, _, tail = s.label.partition(b'\n')
        assert len(head) <= 8 and len(tail) <= 9
    assert (STOP_PLAY, DBL_PRESS) == (0xe7, 0xe8), 'a unit keeps a setting\'s value by ID: never move it once a build has used it'
    assert [e[:5] for e in setting_ids.VIRTUAL if e[4] and e[4].startswith('looper.')] == \
        [(0xe7, 115, 0, 2, 'looper.stop_play'), (0xe8, 115, 2, 2, 'looper.dbl_press')]
    assert looper.FLAG == 'HX_LOOPER' and looper.MENU == 'Footswitches' and getattr(looper, 'WEB', True) is True


STATES = [dict(state=s, loop=lp, window=w) for s in (STOPPED, PLAYING, RECORDING, OVERDUBBING, ONCE, ONCE_OVERDUB)
          for lp in (0, 1) for w in (0, 12)]


@pytest.mark.parametrize('ev', [PRESS, RELEASE, HOLD, 3, 4])
def test_press_hands_every_event_to_the_stock_unchanged(m4emu, ev):
    h = Handler(m4emu, PRESS_PLAYS)
    for st in STATES:
        setup(h.m, **st)
        before = h.m.read(L, SIZE)
        (_, got, then), plays = h.event(ev)
        assert (got, then, plays) == (ev, before, []), st
        assert h.m.read(L, SIZE) == before


def test_release_holds_the_play_of_a_press_on_a_stopped_loop_back(h):
    """The press opens the double-press window and sets the flags the stock press leaves after its play, without the play; the stock
    then runs only its common tail."""
    (switch, got, then), plays = h.event(PRESS)
    assert (switch, got, plays) == (FS1, TAIL, []) and h.reads() == [STOP_PLAY]
    assert then[WINDOW] == 20 and (then[STARTED], then[ACTED], then[STATE]) == (1, 1, STOPPED)


def test_its_release_plays_then_hands_the_stock_its_release(h):
    h.event(PRESS)
    (switch, got, then), plays = h.event(RELEASE)
    assert (switch, got, plays) == (FS1_CODE, RELEASE, [L])
    assert (then[STARTED], then[ACTED]) == (1, 1), 'the stock release sees a press that acted: it arms no overdub'


def test_its_hold_has_the_stock_hold_stop_and_clear_as_after_a_double_press(h):
    h.event(PRESS)
    (switch, got, then), plays = h.event(HOLD)
    assert (switch, got, plays, then[SECOND], then[STATE]) == (FS1_CODE, HOLD, [], 1, STOPPED)


def test_after_the_hold_a_release_plays_nothing(h):
    h.event(PRESS)
    h.event(HOLD)
    (_, got, _), plays = h.event(RELEASE)
    assert (got, plays) == (RELEASE, [])


ELSEWHERE = [dict(window=1), dict(loop=0), *(dict(state=s) for s in (PLAYING, RECORDING, OVERDUBBING, ONCE, ONCE_OVERDUB))]


@pytest.mark.parametrize('st', ELSEWHERE)
def test_any_other_press_goes_to_the_stock_without_reading_the_setting(h, st):
    setup(h.m, **st)
    before = h.m.read(L, SIZE)
    (_, got, then), plays = h.event(PRESS)
    assert (got, then, plays, h.reads()) == (PRESS, before, [], [])
    (_, got, then), plays = h.event(RELEASE)
    assert (got, then, plays) == (RELEASE, before, [])


@pytest.mark.parametrize('ev', [RELEASE, HOLD])
def test_a_release_or_hold_with_no_press_held_back_goes_to_the_stock(h, ev):
    for st in STATES:
        setup(h.m, **st)
        before = h.m.read(L, SIZE)
        (_, got, then), plays = h.event(ev)
        assert (got, then, plays) == (ev, before, []), st


@pytest.mark.parametrize('ev', [PRESS, RELEASE, HOLD])
def test_any_event_ends_a_held_back_play(h, ev):
    h.event(PRESS)
    setup(h.m, state=PLAYING)
    h.event(ev)
    setup(h.m)
    (_, got, _), plays = h.event(RELEASE)
    assert (got, plays) == (RELEASE, [])


@pytest.mark.parametrize('st', [dict(state=PLAYING), dict(state=RECORDING), dict(loop=0)])
def test_a_release_after_the_looper_changed_does_not_play(h, st):
    """Started by MIDI or a Command Center command, or cleared by a preset change, while the footswitch was down."""
    h.event(PRESS)
    for off, v in st.items():
        h.m.u8(L + {'state': STATE, 'loop': LOOP}[off], v)
    (_, got, _), plays = h.event(RELEASE)
    assert (got, plays) == (RELEASE, [])


@pytest.mark.parametrize('st', [dict(state=PLAYING), dict(state=RECORDING), dict(state=OVERDUBBING), dict(loop=0)])
def test_a_hold_after_the_looper_changed_leaves_it_to_the_stock_hold(h, st):
    """Playing, the stock hold clears, as the flags say the press started playback; recording or overdubbing, or the loop cleared
    by a preset change, it does nothing."""
    h.event(PRESS)
    for off, v in st.items():
        h.m.u8(L + {'state': STATE, 'loop': LOOP}[off], v)
    (_, got, then), _ = h.event(HOLD)
    assert (got, then[SECOND]) == (HOLD, 0)


def test_press_is_stock(m4emu):
    h = Handler(m4emu, PRESS_PLAYS)
    (_, got, then), plays = h.event(PRESS)
    assert (got, plays, then[WINDOW]) == (PRESS, [], 0)


@pytest.mark.parametrize('value', [None, 2, 3])
def test_unset_and_out_of_range_values_read_the_default_release(m4emu, value):
    h = Handler(m4emu, value)
    (switch, got, then), plays = h.event(PRESS)
    assert (switch, got, plays, then[WINDOW]) == (FS1, TAIL, [], 20)
    (_, got, _), plays = h.event(RELEASE)
    assert (got, plays) == (RELEASE, [L])


def window(looper_object):
    return struct.unpack_from('<I', looper_object, WINDOW)[0]


@pytest.mark.parametrize('value', [DBL_RELEASE, None, 2, 3])
def test_dbl_press_release_opens_the_window_for_the_overdubs_21_ticks_only_at_a_release_with_the_loop_playing(m4emu, value):
    """Release (also unset or out of range, as its default): the release of any press but the one that stopped (SECOND) goes to the
    stock with the window at the deferred overdub's 21 ticks while the loop plays; the stock release then arms the overdub or not.
    In every other state it goes to the stock unchanged, without reading the setting."""
    h = Handler(m4emu, PRESS_PLAYS, value)
    for st in STATES:
        setup(h.m, **st)
        before = bytearray(h.m.read(L, SIZE))
        (switch, got, then), plays = h.event(RELEASE)
        if st['state'] == PLAYING:
            struct.pack_into('<I', before, WINDOW, OVERDUB_TICKS)
        reads = [DBL_PRESS] if st['state'] == PLAYING else []
        assert (switch, got, then, plays, h.reads()) == (FS1_CODE, RELEASE, bytes(before), [], reads), st


def test_dbl_press_leaves_the_release_of_the_press_that_stopped_to_the_stock(m4emu):
    h = Handler(m4emu, PRESS_PLAYS, DBL_RELEASE)
    for st in STATES:
        setup(h.m, second=1, **st)
        before = h.m.read(L, SIZE)
        (_, got, then), plays = h.event(RELEASE)
        assert (got, then, plays, h.reads()) == (RELEASE, before, [], []), st


@pytest.mark.parametrize('ev', [PRESS, HOLD, 3, 4])
def test_dbl_press_release_hands_every_other_event_to_the_stock_unchanged(m4emu, ev):
    h = Handler(m4emu, PRESS_PLAYS, DBL_RELEASE)
    for st in STATES:
        setup(h.m, **st)
        before = h.m.read(L, SIZE)
        (_, got, then), plays = h.event(ev)
        assert (got, then, plays) == (ev, before, []) and DBL_PRESS not in h.reads(), st


def test_with_both_on_release_the_held_back_play_comes_before_the_stock_release_with_the_window_open(m4emu):
    """The looper was stopped when the release came: the window follows the state that Play has left."""
    h = Handler(m4emu, RELEASE_PLAYS, DBL_RELEASE)
    h.event(PRESS)
    (_, got, then), plays = h.event(RELEASE)
    assert (got, plays, then[STATE], window(then), then[STARTED], then[ACTED]) == (RELEASE, [L], PLAYING, OVERDUB_TICKS, 1, 1)


# The stock code it relies on


@functools.lru_cache(maxsize=None)
def _built(flags):
    return built_e0({f: '1' for f in flags})


def code_segment(e0):
    _, poff, slen, va, _ = pa._parse_e0_segments(e0)[6]
    return e0[poff:poff + slen], va


def calls_to(data, base, target):
    """Every bl, b.w, b<cond>.w and blx to target, and every word holding its address, in the Thumb code data at base."""
    out = []
    for o in range(0, len(data) - 3, 2):
        h1, h2 = struct.unpack_from('<2H', data, o)
        if h1 & 0xf800 == 0xf000 and h2 & 0xc000 == 0xc000 or h1 & 0xf800 == 0xf000 and h2 & 0xd000 == 0x9000:
            t = branch_target(base + o, data[o:o + 4])
            if t == target or h2 & 0x1000 == 0 and t & ~3 == target & ~3:
                out.append(base + o)
        elif h1 & 0xf800 == 0xf000 and h2 & 0xd000 == 0x8000 and h1 & 0x0380 != 0x0380:     # b<cond>.w; cond 111x is no branch
            off = (h1 >> 10 & 1) << 20 | (h2 >> 11 & 1) << 19 | (h2 >> 13 & 1) << 18 | (h1 & 0x3f) << 12 | (h2 & 0x7ff) << 1
            if base + o + 4 + off - (1 << 21 if off & 1 << 20 else 0) == target:
                out.append(base + o)
        if o % 4 == 0 and struct.unpack_from('<I', data, o)[0] in (target, target | 1):
            out.append(base + o)
    return out


@pytest.mark.firmware
def test_the_footswitch_handler_is_the_state_machines_only_caller():
    """Its press (switch, 1), hold (code, 5) and release (code, 2) calls; nothing else reaches it, by a call or its address."""
    data, base = code_segment(stock_e0())
    assert calls_to(data, base, looper.STATE_MACHINE) == [0x28dd1444, 0x28dd1c6c, 0x28dd1d28]
    read = reader(stock_e0())
    assert read(looper.STATE_MACHINE, 4) == looper.STATE_MACHINE_STOCK
    assert read(0x28dd1442, 2) == bytes.fromhex('0121'), 'movs r1, #1'
    assert read(0x28dd1c6a, 2) == read(0x28dd1d26, 2) == bytes.fromhex('3146'), 'mov r1, r6: the event'
    assert read(0x28de778c, 4) == bytes.fromhex('a0f5fc70'), 'the press latch\'s test: sub.w r0, r0, #504 (the 1 Switch Looper)'
    # The hold and the release reach it only while the latch is set, for the latched switch's code, and clear the latch before
    # the call, so one pending play is that switch's.
    for at, want in ((0x28dd1a9e, '95f88080'), (0x28dd1bec, '95f88030'),           # ldrb.w r8 / r3, [r5, #0x80]: the latch
                     (0x28dd1c2e, '0c3293427ff43baf'), (0x28dd1cee, '0c339f4280d1'),     # [r5, #0x81] + 12 against the code, bne
                     (0x28dd1c5a, '85f88030'), (0x28dd1d14, '85f88030')):                # strb.w r3, [r5, #0x80]: cleared
        assert read(at, len(want) // 2) == bytes.fromhex(want), hex(at)
    assert branch_target(0x28dd1c5e, read(0x28dd1c5e, 4)) == branch_target(0x28dd1d1a, read(0x28dd1d1a, 4)) == 0x28de778c


@pytest.mark.firmware
def test_after_a_hold_the_popup_shows_only_when_the_undo_countdown_runs():
    """UNDO/REDO follows a hold only when [looper + 0x6b] is set, which the Undo verb does and a stop and clear does not."""
    read = reader(stock_e0())
    assert branch_target(0x28dd1c80, read(0x28dd1c80, 4)) == GET_LOOPER
    assert read(0x28dd1c84, 4) == bytes.fromhex('90f86b30'), 'ldrb.w r3, [r0, #0x6b]'
    assert read(0x28dd1c8a, 4) == bytes.fromhex('40f0c581'), 'bne.w 0x28dd2018, the popup'


# The built state machine, run in unicorn with the stock one beside it


class Machine:
    """Entry 0 e0's state machine and the looper's tick in unicorn: stock code and the cave run for real, Stop>Ply and DblPress
    through the virtual settings engine (settings (Stop>Ply, DblPress), or None: container 115 unset). The verbs are stand-ins that
    log their call and move the state as the stock verbs do on these paths; the tick's post logs the flags it posts (the deferred
    overdub, 0x20) and keeps the tick it came in (self.posts, counted from the reset). With worker, the post also runs the work the
    worker task would before the next event: the overdub's toggle (0x28de7b24 from 0x28de7c1e), playing to overdubbing. With
    worker 'queue', the toggle waits for a WORKER step, which logs 'worker', as the worker task runs it after the tick. A MIDI_PLAY
    step logs 'midi' and calls the Play stand-in from outside the footswitch, as MIDI CC 61 or a Command Center Play does."""

    def __init__(self, m4emu, e0, settings=None, worker=False):
        data, va = code_segment(e0)
        self.m = m = m4emu.M4(data, va)
        self.log = []
        for fn, verb in ((PLAY, self._play), (STOP, self._stop), (REC, self._rec), (ODUB_OFF, self._odub_off), (UNDO, self._undo)):
            m.stub(fn, verb)
        m.stub(TONE_OF, lambda m: m.reg('r0', 0x28480000))
        m.stub(LISTEN, lambda m: self.log.append('listen'))
        m.stub(LOCK)
        m.stub(UNLOCK)
        m.stub(POST, self._post)
        self.pending = None
        if reader(e0)(looper.STATE_MACHINE, 4) != looper.STATE_MACHINE_STOCK:
            text, sym = code(m4emu)
            veneer = branch_target(looper.STATE_MACHINE, m.read(looper.STATE_MACHINE, 4))
            self.pending = branch_target(veneer + 8, m.read(veneer + 8, 4)) - sym['looper_event'] + sym['pending']
        m.write(RECORDS + 40 * CONTAINER + 8, struct.pack('<BxxxI', 3, FLOAT_ONE) if settings is None else     # bits 0..1, 2..3
                struct.pack('<BxxxI', 2, settings[0] | settings[1] << 2))
        self.worker = worker
        self.reset()

    def u8(self, off):
        return self.m.read(L + off, 1)[0]

    def _play(self, m):
        self.log.append('play')
        if self.u8(STATE) == STOPPED and self.u8(LOOP) == 1 or self.u8(STATE) == RECORDING:
            m.u8(L + STATE, PLAYING)

    def _stop(self, m):
        self.log.append('stop')
        m.u8(L + STATE, STOPPED)

    def _rec(self, m):
        self.log.append('rec')
        for off, v in ((STATE, RECORDING), (LOOP, 1), (UNDO_READY, 0)):
            m.u8(L + off, v)

    def _odub_off(self, m):
        self.log.append('odub off')
        if self.u8(STATE) == OVERDUBBING:
            m.u8(L + STATE, PLAYING)

    def _undo(self, m):
        self.log.append('undo')
        m.u8(L + POPUP, 100)

    def _post(self, m):
        assert m.reg('r0') == L + 0x30
        self.log.append(('post', m.u32(L + FLAGS)))
        self.posts.append(self.now)
        if m.u32(L + FLAGS) & OVERDUB_FLAG:
            if self.worker == 'queue':
                self.queued = True
            elif self.worker:
                self._toggle()
        m.u32(L + FLAGS, 0)

    def _toggle(self):
        if self.u8(STATE) in (PLAYING, OVERDUBBING):
            self.m.u8(L + STATE, PLAYING + OVERDUBBING - self.u8(STATE))

    def reset(self, **looper_object):
        setup(self.m, **looper_object)
        self.log.clear()
        self.posts, self.now, self.queued = [], 0, False
        if self.pending is not None:
            self.m.u8(self.pending, 0)

    def run(self, *steps):
        """Each step an event (PRESS, RELEASE, HOLD), ('tick', n), WORKER or MIDI_PLAY -> (the verbs and posts, the looper object
        after)."""
        for s in steps:
            if s == WORKER:
                if self.queued:
                    self.queued = False
                    self.log.append('worker')
                    self._toggle()
            elif s == MIDI_PLAY:
                self.log.append('midi')
                self._play(self.m)
            elif isinstance(s, tuple):
                for _ in range(s[1]):
                    self.now += 1
                    self.m.call(TICK, 0, L)
            else:
                self.m.call(looper.STATE_MACHINE, FS1 if s == PRESS else FS1_CODE, s)
        return list(self.log), self.m.read(L, SIZE)


def ticks(n):
    return ('tick', n)


WORKER = ('worker',)                        # the worker task runs the overdub's toggle that a tick queued
MIDI_PLAY = ('midi',)                       # MIDI CC 61 or a Command Center command plays the loop, not the footswitch


@pytest.fixture
def machines(m4emu):
    """(the stock state machine, the built one with Stop>Ply Release, the built one with Press), DblPress on Stock in both."""
    e0 = _built(('HX_LOOPER',))
    return (Machine(m4emu, stock_e0()), Machine(m4emu, e0, (RELEASE_PLAYS, DBL_STOCK)),
            Machine(m4emu, e0, (PRESS_PLAYS, DBL_STOCK)))


@pytest.mark.firmware
def test_a_tap_on_a_stopped_loop_plays_on_its_release_as_a_stock_play_then_release(machines):
    stock, rel, _ = machines
    log, _ = rel.run(PRESS)
    assert log == [] and rel.u8(STATE) == STOPPED and rel.m.u32(L + WINDOW) == 20
    log, after = rel.run(RELEASE, ticks(30))
    assert log == ['play'] and rel.u8(STATE) == PLAYING
    assert stock.run(PRESS, RELEASE, ticks(30)) == (['play'], after), 'no deferred overdub: the looper as after the stock tap'


@pytest.mark.firmware
@pytest.mark.parametrize('held', [0, 30, 99])
def test_a_hold_on_a_stopped_loop_clears_it_without_playing(machines, held):
    """Stop, then the flags the stock clear zeroes: the looper ends as after the stock hold, which played it first. No UNDO/REDO."""
    stock, rel, _ = machines
    log, after = rel.run(PRESS, ticks(held), HOLD)
    assert log == ['stop'] and (after[STATE], after[LOOP], after[SECOND], after[UNDO_READY], after[POPUP]) == (STOPPED, 0, 0, 0, 0)
    assert stock.run(PRESS, ticks(held), HOLD) == (['play', 'stop'], after)
    assert rel.run(RELEASE) == (['stop'], after), 'had a release reached it (the stock handler sends none), it does nothing'


@pytest.mark.firmware
def test_a_hold_clears_the_undo_too_and_the_press_starts_the_dsp_listener_as_stock(machines):
    stock, rel, _ = machines
    for m in machines[:2]:
        m.reset(undo=1, listening=0)
    log, after = rel.run(PRESS, HOLD)
    assert log == ['listen', 'stop'] and (after[UNDO_READY], after[LISTENING]) == (0, 1)
    assert stock.run(PRESS, HOLD) == (['play', 'listen', 'stop'], after)


@pytest.mark.firmware
def test_a_hold_after_the_loop_was_cleared_does_nothing_as_stock(machines):
    """The looper's state and loop zeroed while the footswitch is down (as on a preset change): no Stop, as the stock hold."""
    stock, rel, _ = machines
    for m in machines[:2]:
        m.run(PRESS, ticks(30))
        m.m.u8(L + STATE, STOPPED)
        m.m.u8(L + LOOP, 0)
        m.log.clear()
    assert rel.run(HOLD) == stock.run(HOLD) == ([], rel.m.read(L, SIZE))


@pytest.mark.parametrize('steps, verbs', [
    ((PRESS, RELEASE, ticks(5), PRESS, RELEASE, ticks(30)), ['play', 'stop']),                      # a double press stops
    ((PRESS, ticks(8), RELEASE, ticks(5), PRESS, RELEASE, ticks(30)), ['play', 'stop']),            # its second press in the window
    ((PRESS, RELEASE, ticks(5), PRESS, HOLD), ['play', 'stop', 'stop']),                            # double press and hold clears
    ((PRESS, ticks(30), RELEASE, ticks(5), PRESS, RELEASE, ticks(30)), ['play', ('post', OVERDUB_FLAG)]),   # then overdubs
])
@pytest.mark.firmware
def test_the_double_press_and_what_follows_a_release_time_play_are_stock(machines, steps, verbs):
    """The same verbs and the same looper as stock; only the first play comes on the release."""
    stock, rel, _ = machines
    assert rel.run(*steps) == stock.run(*steps)
    assert stock.log == verbs


SEQUENCES = [(PRESS,), (RELEASE,), (HOLD,), (PRESS, RELEASE, ticks(25)), (PRESS, HOLD), (PRESS, ticks(25), HOLD),
             (PRESS, RELEASE, ticks(3), PRESS, RELEASE, ticks(25)), (PRESS, RELEASE, PRESS, HOLD), (RELEASE, PRESS, ticks(25))]
OBJECTS = [dict(state=s, loop=lp, window=w, started=st, second=sc, undo=u) for s in (STOPPED, PLAYING, RECORDING, OVERDUBBING, ONCE,
           ONCE_OVERDUB) for lp in (0, 1) for w in (0, 12) for st in (0, 1) for sc in (0, 1) for u in (0, 1)]


@pytest.mark.firmware
@pytest.mark.parametrize('steps', SEQUENCES)
def test_press_with_dbl_press_stock_is_stock(machines, steps):
    stock, _, press = machines
    for obj in OBJECTS:
        stock.reset(**obj)
        press.reset(**obj)
        assert press.run(*steps) == stock.run(*steps), obj


@pytest.mark.firmware
@pytest.mark.parametrize('steps', SEQUENCES)
def test_an_unset_container_reads_the_defaults_release_and_release(m4emu, steps):
    e0 = _built(('HX_LOOPER',))
    unset, defaults = Machine(m4emu, e0), Machine(m4emu, e0, (RELEASE_PLAYS, DBL_RELEASE))
    for obj in OBJECTS:
        unset.reset(**obj)
        defaults.reset(**obj)
        assert unset.run(*steps) == defaults.run(*steps), obj


# DblPress: the double-press window against the deferred overdub, through the real tick


HELD = range(26)                            # the first press held 0..25 ticks
AFTER = range(OVERDUB_TICKS + 4)            # the second press 0..24 ticks after the first release: the overdub posts in the 21st
OVERDUB = ('post', OVERDUB_FLAG)            # the tick's post of the deferred overdub
PAIRS = [(sp, dp) for sp in (PRESS_PLAYS, RELEASE_PLAYS) for dp in (DBL_RELEASE, DBL_STOCK)]
FROM_PLAYING, FROM_STOPPED = dict(state=PLAYING), dict(state=STOPPED)


def double_press(held, after):
    return PRESS, ticks(held), RELEASE, ticks(after), PRESS, RELEASE, ticks(OVERDUB_TICKS + 1)


@pytest.fixture
def pairs(m4emu):
    """The stock state machine, and the built one for each (Stop>Ply, DblPress), all with the worker's overdub."""
    e0 = _built(('HX_LOOPER',))
    return Machine(m4emu, stock_e0(), worker=True), {pair: Machine(m4emu, e0, pair, worker=True) for pair in PAIRS}


def outcome(machine, obj, steps):
    """(the verbs and posts, the looper object after, the ticks the posts came in)."""
    machine.reset(**obj)
    return (*machine.run(*steps), machine.posts)


@pytest.mark.firmware
@pytest.mark.parametrize('held', HELD)
def test_on_stock_a_second_press_in_the_gap_overdubs_instead_of_stopping(pairs, held):
    """The window closes 20 ticks after the first press and the overdub posts 21 after its release, so a second press in between
    (held + 1 tick offsets, up to the 21 before the post) does nothing and its release arms the overdub again, 21 ticks later."""
    stock, _ = pairs
    gap = []
    for after in AFTER:
        log, after_obj, posts = outcome(stock, FROM_PLAYING, double_press(held, after))
        if held + after < WINDOW_TICKS:
            assert (log, posts, after_obj[STATE]) == (['stop'], [], STOPPED), after
        elif after < OVERDUB_TICKS:
            gap.append(after)
            assert (log, posts, after_obj[STATE]) == ([OVERDUB], [held + after + OVERDUB_TICKS], OVERDUBBING), after
        else:
            assert (log, posts, after_obj[STATE]) == ([OVERDUB, 'odub off'], [held + OVERDUB_TICKS], PLAYING), after
    assert gap == list(range(max(WINDOW_TICKS - held, 0), OVERDUB_TICKS)) and len(gap) == min(held + 1, OVERDUB_TICKS)


@pytest.mark.firmware
@pytest.mark.parametrize('held', HELD)
def test_dbl_press_release_stops_on_every_second_press_before_the_overdub_and_on_none_after(pairs, held):
    """Before the overdub's post the second press stops, cancels it and leaves the window shut; from the post on it ends the
    overdub as stock. The overdub posts in the same tick as stock."""
    stock, built = pairs
    for (sp, dp), m in built.items():
        if dp != DBL_RELEASE:
            continue
        for after in AFTER:
            got = outcome(m, FROM_PLAYING, double_press(held, after))
            log, after_obj, posts = got
            if after < OVERDUB_TICKS:
                assert (log, posts, after_obj[STATE], after_obj[OVERDUB_IN], window(after_obj)) == (['stop'], [], STOPPED, 0, 0)
            else:
                assert got == outcome(stock, FROM_PLAYING, double_press(held, after)), (sp, after)
                assert (log, posts) == ([OVERDUB, 'odub off'], [held + OVERDUB_TICKS])


@pytest.mark.firmware
@pytest.mark.parametrize('held', HELD)
def test_dbl_press_stock_is_stock_through_the_gap(pairs, held):
    stock, built = pairs
    for obj in (FROM_PLAYING, FROM_STOPPED):
        for after in AFTER:
            want = outcome(stock, obj, double_press(held, after))
            for sp in (PRESS_PLAYS, RELEASE_PLAYS):
                assert outcome(built[sp, DBL_STOCK], obj, double_press(held, after)) == want, (obj, sp, after)


@pytest.mark.firmware
@pytest.mark.parametrize('obj', [FROM_PLAYING, dict(state=OVERDUBBING), dict(state=RECORDING)])
def test_the_overdub_starts_on_the_same_tick_as_stock_with_every_pair(pairs, obj):
    """A press and release on a playing loop arms it, as do pressing to end an overdub or close the loop and pressing again."""
    stock, built = pairs
    first = () if obj is FROM_PLAYING else (PRESS, RELEASE, ticks(WINDOW_TICKS + 1))
    for held in HELD:
        steps = (*first, PRESS, ticks(held), RELEASE, ticks(OVERDUB_TICKS + 1))
        want = outcome(stock, obj, steps)
        assert want[2] == [(WINDOW_TICKS + 1 if first else 0) + held + OVERDUB_TICKS] and want[0][-1] == OVERDUB
        for pair, m in built.items():
            assert outcome(m, obj, steps) == want, (pair, held)


OTHER_STATES = [(dict(loop=0), ['rec'], RECORDING), (dict(state=RECORDING), ['play'], PLAYING),
                (dict(state=OVERDUBBING), ['odub off'], PLAYING), (dict(state=ONCE), [], ONCE),
                (dict(state=ONCE_OVERDUB), [], ONCE_OVERDUB)]       # the first press's verbs, and the state its release finds


@pytest.mark.firmware
@pytest.mark.parametrize('held', HELD)
def test_dbl_press_release_opens_the_window_only_at_a_release_that_finds_the_loop_playing(pairs, held):
    """The loop closed or an overdub ended: with DblPress on Release a second press within 21 ticks of the first release stops, also
    after a first press held 20 ticks or more, which on stock leaves no window (the press then does nothing and its release arms
    the overdub); from 21 ticks on it is stock. Recording started or play once: the release finds the loop not playing, and
    DblPress Release is stock byte for byte, as is DblPress Stock from every state: a long press that started recording, then a
    quick second press, closes the loop and plays."""
    stock, built = pairs
    for obj, first, state in OTHER_STATES:
        for after in AFTER:
            steps = double_press(held, after)
            want = outcome(stock, obj, steps)
            if held + after < WINDOW_TICKS:
                assert (want[0], want[1][STATE]) == (first + ['stop'], STOPPED), (obj, after)
            elif state == RECORDING:
                assert (want[0], want[1][STATE]) == (['rec', 'play'], PLAYING), after
            for (sp, dp), m in built.items():
                got = outcome(m, obj, steps)
                if dp == DBL_STOCK or state != PLAYING or after >= OVERDUB_TICKS:
                    assert got == want, (obj, sp, dp, after)
                else:
                    assert (got[0], got[2], got[1][STATE]) == (first + ['stop'], [], STOPPED), (obj, sp, after)


@pytest.mark.firmware
@pytest.mark.parametrize('held', [WINDOW_TICKS, 50, 99])
def test_after_a_long_press_that_started_recording_a_quick_press_closes_the_loop_as_stock(pairs, held):
    """The first release finds the looper recording, so no pair opens a window: the second press closes the loop and plays."""
    stock, built = pairs
    for after in (0, 1, OVERDUB_TICKS - 1):
        want = outcome(stock, dict(loop=0), double_press(held, after))
        assert (want[0], want[1][STATE], want[1][LOOP]) == (['rec', 'play'], PLAYING, 1), after
        for pair, m in built.items():
            assert outcome(m, dict(loop=0), double_press(held, after)) == want, (pair, after)



@pytest.fixture
def queued(m4emu):
    """As pairs, but the overdub's toggle waits for a WORKER step."""
    e0 = _built(('HX_LOOPER',))
    return Machine(m4emu, stock_e0(), worker='queue'), {pair: Machine(m4emu, e0, pair, worker='queue') for pair in PAIRS}


@pytest.mark.firmware
@pytest.mark.parametrize('held', HELD)
def test_a_press_after_the_overdubs_post_before_the_worker_has_run_is_stock(queued, held):
    """The tick's post only queues the overdub's toggle for the worker task. The window at 21 closes in the tick that posts, so a
    second press, and its release, before the worker has run or around it, is a plain press on a playing loop, as on stock: neither
    a Stop that the queued toggle then follows nor a Stop just after a moment of overdub."""
    stock, built = queued
    for after in range(OVERDUB_TICKS, OVERDUB_TICKS + 4):
        for second in ((WORKER, PRESS, RELEASE), (PRESS, WORKER, RELEASE), (PRESS, RELEASE, WORKER)):
            steps = (PRESS, ticks(held), RELEASE, ticks(after), *second, ticks(OVERDUB_TICKS + 1), WORKER)
            want = outcome(stock, FROM_PLAYING, steps)
            assert 'stop' not in want[0] and want[2][0] == held + OVERDUB_TICKS, (after, second)
            for pair, m in built.items():
                assert outcome(m, FROM_PLAYING, steps) == want, (pair, after, second)


@pytest.mark.firmware
@pytest.mark.parametrize('held', HELD)
def test_the_four_combinations_from_a_stopped_loop(pairs, held):
    """Stop>Ply says when the first press plays (press or release); DblPress how long a second press stops: Stock 20 ticks from
    the first press, Release 21 from its release. A later second press does nothing and its release arms the overdub, as stock."""
    stock, built = pairs
    for after in AFTER:
        steps = double_press(held, after)
        want = outcome(stock, FROM_STOPPED, steps)
        assert want[0] == (['play', 'stop'] if held + after < WINDOW_TICKS else ['play', OVERDUB])
        for sp in (PRESS_PLAYS, RELEASE_PLAYS):
            assert outcome(built[sp, DBL_STOCK], FROM_STOPPED, steps) == want, (sp, after)
            log, after_obj, posts = got = outcome(built[sp, DBL_RELEASE], FROM_STOPPED, steps)
            if after < OVERDUB_TICKS:
                assert (log, posts, after_obj[STATE], after_obj[LOOP]) == (['play', 'stop'], [], STOPPED, 1), (sp, after)
            else:
                assert got == want and posts == [held + after + OVERDUB_TICKS], (sp, after)


@pytest.mark.firmware
@pytest.mark.parametrize('held', [0, 30, 99])
def test_the_four_combinations_hold_a_stopped_loop_as_stop_play_says(pairs, held):
    stock, built = pairs
    want = outcome(stock, FROM_STOPPED, (PRESS, ticks(held), HOLD))
    for (sp, dp), m in built.items():
        got = outcome(m, FROM_STOPPED, (PRESS, ticks(held), HOLD))
        assert got == want if sp == PRESS_PLAYS else (got[0], got[1]) == (['stop'], want[1]), (sp, dp)


@pytest.mark.firmware
@pytest.mark.parametrize('obj', [FROM_PLAYING, FROM_STOPPED])
def test_dbl_press_release_lets_a_double_press_and_hold_clear_until_the_overdub(pairs, obj):
    _, built = pairs
    first = [] if obj is FROM_PLAYING else ['play']
    for held in (0, 25):
        for after in (WINDOW_TICKS - held - 1, OVERDUB_TICKS - 1):
            if after < 0:
                continue
            for sp in (PRESS_PLAYS, RELEASE_PLAYS):
                steps = (PRESS, ticks(held), RELEASE, ticks(after), PRESS, HOLD)
                log, after_obj, posts = outcome(built[sp, DBL_RELEASE], obj, steps)
                assert (log, posts) == (first + ['stop', 'stop'], []), (sp, held, after)
                assert (after_obj[STATE], after_obj[LOOP]) == (STOPPED, 0), (sp, held, after)


@pytest.mark.firmware
@pytest.mark.parametrize('sp', [PRESS_PLAYS, RELEASE_PLAYS])
def test_dbl_press_release_leaves_the_window_shut_after_the_release_of_the_press_that_stopped(pairs, sp):
    """The Stop leaves the loop stopped, so that release finds it not playing: a third press right after a double-press stop starts
    the loop again, as stock."""
    stock, built = pairs
    steps = (PRESS, RELEASE, ticks(10), PRESS, RELEASE, ticks(1), PRESS, RELEASE, ticks(OVERDUB_TICKS + 1))
    got, want = outcome(built[sp, DBL_RELEASE], FROM_STOPPED, steps), outcome(stock, FROM_STOPPED, steps)
    assert got == want and want[0] == ['play', 'stop', 'play']


@pytest.mark.firmware
@pytest.mark.parametrize('obj', [FROM_PLAYING, FROM_STOPPED])
def test_a_play_from_midi_while_the_press_that_stopped_is_down_leaves_the_window_shut(pairs, obj):
    """The release of the press that stopped then finds the loop playing, and only SECOND keeps the window shut: a third press right
    after is a plain press on a playing loop and its release arms the overdub, as stock, not a second double-press Stop."""
    stock, built = pairs
    steps = (PRESS, RELEASE, ticks(5), PRESS, MIDI_PLAY, RELEASE, ticks(5), PRESS, RELEASE, ticks(OVERDUB_TICKS + 1))
    want = outcome(stock, obj, steps)
    assert want[0].count('stop') == 1 and want[0][-1] == OVERDUB and want[1][STATE] == OVERDUBBING
    for sp in (PRESS_PLAYS, RELEASE_PLAYS):
        assert outcome(built[sp, DBL_RELEASE], obj, steps) == want, sp


@pytest.mark.firmware
@pytest.mark.parametrize('steps', [s for s in SEQUENCES if s.count(PRESS) <= 1])
def test_with_release_every_other_state_is_stock(machines, steps):
    """A release or hold with no press held back, and a press anywhere but on a stopped loop with no window open: recording on the
    press, closing the loop, overdub on and off, the double-press stop, hold to undo or clear."""
    stock, rel, _ = machines
    for obj in OBJECTS:
        if obj['state'] == STOPPED and obj['loop'] and not obj['window'] and PRESS in steps:
            continue
        stock.reset(**obj)
        rel.reset(**obj)
        assert rel.run(*steps) == stock.run(*steps), obj


@pytest.mark.firmware
@pytest.mark.parametrize('obj, steps, verbs', [
    (dict(loop=0), (PRESS,), ['rec']),                                          # recording starts on the press
    (dict(state=RECORDING), (PRESS,), ['play']),                                # the loop closes on the press
    (dict(state=OVERDUBBING), (PRESS,), ['odub off']),                          # overdub ends on the press
    (dict(state=PLAYING), (PRESS, RELEASE, ticks(25)), [('post', OVERDUB_FLAG)]),     # and starts after a press and release
    (dict(state=PLAYING, undo=1), (PRESS, HOLD), ['undo']),                     # a hold while playing undoes, with UNDO/REDO
])
def test_with_release_the_other_gestures_act_on_the_press_as_stock(machines, obj, steps, verbs):
    stock, rel, _ = machines
    stock.reset(**obj)
    rel.reset(**obj)
    assert rel.run(*steps) == stock.run(*steps)
    assert rel.log == verbs


# The build


@pytest.mark.firmware
def test_build_owns_the_state_machine_and_hands_looper_event_the_stock(m4emu):
    text, sym = code(m4emu)
    read, on = built({'HX_LOOPER': '1'})
    assert 'looper' in on
    veneer = branch_target(looper.STATE_MACHINE, read(looper.STATE_MACHINE, 4))
    lo, hi = struct.unpack('<2I', read(veneer, 8))
    imm = lambda w: (w >> 16 & 0xff) | (w >> 28 & 7) << 8 | (w >> 10 & 1) << 11 | (w & 0xf) << 12
    assert lo & 0x0f00fbf0 == 0x0200f240 and hi & 0x0f00fbf0 == 0x0200f2c0, 'movw r2 / movt r2'
    stock = imm(lo) | imm(hi) << 16
    assert stock & 1 and read(stock & ~1, 4) == looper.STATE_MACHINE_STOCK
    assert branch_target((stock & ~1) + 4, read((stock & ~1) + 4, 4)) == looper.STATE_MACHINE + 4
    module = branch_target(veneer + 8, read(veneer + 8, 4)) - sym['looper_event']
    assert read(module, len(text)) == text


@pytest.mark.firmware
@pytest.mark.parametrize('setting', looper.SETTINGS, ids=lambda s: s.key)
def test_build_serves_both_settings_as_virtual_settings(setting):
    assert_virtual(_built(('HX_LOOPER',)), looper, setting)


@pytest.mark.firmware
@pytest.mark.parametrize('flags, ids, pages', [
    (('HX_LOOPER',), (17, 97, 98, 99, 0xe7, 0xe8), 2),                          # page 2, beside FS5 Function
    (('HX_LONG_PRESS', 'HX_LOOPER'),
     (17, 97, 98, 99) + tuple(range(0xd2, 0xd7)) + tuple(range(0xda, 0xdf)) + (0xe7, 0xe8, pm.EMPTY_SLOT, pm.EMPTY_SLOT), 6),
])
def test_the_settings_take_the_next_footswitches_slots(flags, ids, pages):
    """After long press's Holds and Functions, when it is built: the last slot of page 5 and the first of page 6."""
    read = reader(_built(flags))
    for site in pm.SITES:
        assert struct.unpack(f'<{len(ids)}H', read(page_table(read, 2, site), 2 * len(ids))) == ids, site
    assert struct.unpack('<I', read(struct.unpack('<I', read(pm.ARRAYS['pages'][1][0], 4))[0] + 8, 4))[0] == pages


@pytest.mark.firmware
def test_without_the_flag_the_state_machine_stays_stock():
    read, on = built({})
    assert 'looper' not in on and read(looper.STATE_MACHINE, 4) == looper.STATE_MACHINE_STOCK


@pytest.mark.firmware
def test_builds_alongside_every_other_feature():
    env = {f: '1' for m in MODS for f in features.flags(m)}
    read, on = built(env)
    assert {'looper', 'long_press', 'tap_command', 'metronome'} <= set(on)
    assert read(looper.STATE_MACHINE, 4) != looper.STATE_MACHINE_STOCK
