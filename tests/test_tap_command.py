"""tools/features/tap_command.py and src/m4/tap_command.s: the handlers in unicorn (a Tap command taps and any other fires as stock,
the Command knob's places and turns on an FS slot, which rings blink, the stock beat kept going and its turns, the period from the
BPM), the stock code and tables they rely on (type 9 is complete and inert on stock, the FS list, the beat's sites), and the firmware
it builds."""
import struct

import pytest

import features
import patch_menu as pm
import setting_ids
from features import tap_color as tc, tap_command as cmd
from firmware import branch_target, built, reader, stock_e0

MODS = features.load()
IDS = setting_ids.by_name()
MOD = 0x28e60000
TAP_LED, TAP_LED_AGAIN = 0x28e70000, 0x28e70100
CC = 0x281252b8
CC_TYPES = CC + 0x74
FS_FUNCTIONS, FS_STATE_OBJ = 0x28128a74, 0x28128a70
TAP_CORE, GET_VALUE, EXT_CLOCK, LED_COLOUR = 0x28d9bfa8, 0x28e1f844, 0x28d9685c, 0x28db81fc
STRCPY, NODE = 0x28daad94, 0x28700000
FS_OBJ, FS_NODE, FS_LISTS, NODES = 0x28d96084, 0x28dd7218, 0x28128a80, 0x28700100     # node k at NODES + 0x40k
RED, BLUE, RED_WORD, BLUE_WORD = 0x28e280b0, 0x28e280ac, 0x0300ff, 0xff3200
BEAT_PERIOD, BEAT_ON = 0x281ccc44, 0x281ccc48
TAP_FN, STOMP = 1, 2
FS_LIST = (0, 1, 2, 4, 5, 6, 12, 9, 14, 15, 16)          # None .. Hotkey, Tap, Preset, Snapshot, Looper
STOCK_FS_LIST = (0, 1, 2, 4, 5, 6, 12, 14, 15, 16)
_code = {}


def tap_inc(colour):
    led, again = (TAP_LED | 1, TAP_LED_AGAIN | 1) if colour else (0, 0)
    return f'.equ TAP_LED, {led:#x}\n.equ TAP_LED_AGAIN, {again:#x}\n'


class Tap:
    """tap_command.s in tests/m4emu.py's M4, built with Tap LED Color or without. self.values answers GET_VALUE by ID (missing:
    unset); self.ext is the external clock flag; self.stock what the stock place and turn return. The stubs log their calls."""

    def __init__(self, m4emu, colour=False):
        if colour not in _code:
            _code[colour] = m4emu.assemble(cmd.MODULE, MODS, IDS, inc={'tap.inc': tap_inc(colour)})
        code, self.sym = _code[colour]
        self.m = m4emu.M4(code, MOD)
        self.values, self.ext, self.stock = {26: 1, 14: 0, 16: 120.0}, 0, 0
        for fn in (cmd.FIRE, TAP_CORE, LED_COLOUR, cmd.LED_MODE, TAP_LED, TAP_LED_AGAIN):
            self.m.stub(fn)
        self.m.stub(STRCPY, lambda m: m.write(m.reg('r0'), m.read(m.reg('r1'), 16).split(b'\0')[0] + b'\0'))
        self.nodes = set(range(5))
        self.m.stub(FS_OBJ, lambda m: m.reg('r0', FS_LISTS))
        self.m.stub(FS_NODE, lambda m: m.reg('r0', NODES + 0x40 * m.reg('r1') if m.reg('r1') in self.nodes else 0))
        self.m.write(NODES, bytes(0x40 * 5))
        for fn in (cmd.CHOICE, cmd.STEP, cmd.NODE_NAME):
            self.m.stub(fn, lambda m: m.reg('r0', self.stock))
        self.m.stub(cmd.FS_STATE, lambda m: m.reg('r0', FS_STATE_OBJ))
        self.m.stub(EXT_CLOCK, lambda m: m.reg('r0', self.ext))
        self.m.stub(GET_VALUE, self._get)
        self.m.u32(RED, RED_WORD)
        self.m.u32(BLUE, BLUE_WORD)
        self.footswitches((TAP_FN if k == 2 else STOMP for k in range(5)), (0,) * 5)

    def _get(self, m):
        pid, out = m.reg('r0'), m.reg('r1')
        if pid not in self.values:
            return m.reg('r0', -1)
        v = self.values[pid]
        m.write(out + 4, struct.pack('<f', v) if isinstance(v, float) else struct.pack('<I', v))
        m.reg('r0', 0)

    def footswitches(self, functions, types):
        for k, (f, t) in enumerate(zip(functions, types)):
            self.m.write(FS_FUNCTIONS + 2 * k, bytes([f, 0]))
            self.m.u8(CC_TYPES + 6 + k, t)

    def call(self, sym, *args):
        self.m.log.clear()
        return self.m.call(MOD + self.sym[sym], *args)

    def calls(self, *fns):
        return [(f, regs) for f, regs in self.m.log if f in fns]

    def leds(self):
        return [(f, regs[:2]) for f, regs in self.m.log if f in (LED_COLOUR, cmd.LED_MODE, TAP_LED, TAP_LED_AGAIN)]


@pytest.fixture
def tap(m4emu):
    return Tap(m4emu)


@pytest.fixture
def coloured(m4emu):
    return Tap(m4emu, colour=True)


def test_feature_has_no_settings_and_runs_after_tap_color():
    assert not hasattr(cmd, 'SETTINGS') and cmd.MENU is False
    assert cmd.ORDER > getattr(tc, 'ORDER', 100)


@pytest.mark.parametrize('slot', range(6, 11))
def test_a_tap_command_taps_and_fires_nothing(tap, slot):
    tap.m.u8(CC_TYPES + slot, 9)
    tap.call('tc_fire', CC, slot, 1, 0)
    assert [f for f, _ in tap.calls(TAP_CORE, cmd.FIRE)] == [TAP_CORE]


@pytest.mark.parametrize('k', range(5))
def test_a_tap_leaves_its_command_shown_on(tap, k):
    tap.m.u8(CC_TYPES + 6 + k, 9)
    tap.call('tc_fire', CC, 6 + k, 0, 0)
    assert tap.m.read(NODES + 0x40 * k + 0x20, 1) == b'\x01', 'the toggle flipped it off; the label stays lit'
    assert [regs[:2] for _, regs in tap.calls(FS_NODE)] == [(FS_LISTS, k)]


def test_a_refresh_shows_every_stomp_tap_command_on(tap):
    tap.footswitches((STOMP, STOMP, TAP_FN, STOMP, 6), (9, 0, 9, 9, 9))
    tap.nodes = {0, 2, 4}
    tap.call('tc_refresh')
    assert [tap.m.read(NODES + 0x40 * k + 0x20, 1)[0] for k in range(5)] == [1, 0, 0, 0, 0], \
        'FS1 only: FS3 is TAP, FS4 has no node, FS5 is not a Stomp switch'


@pytest.mark.parametrize('ctype', [0, 1, 2, 4, 5, 6, 12, 14, 15, 16])
def test_every_other_command_fires_as_stock_with_its_arguments(tap, ctype):
    tap.m.u8(CC_TYPES + 8, ctype)
    tap.call('tc_fire', CC, 8, 0, 1)
    assert tap.calls(TAP_CORE, cmd.FIRE) == [(cmd.FIRE, (CC, 8, 0, 1))]


def test_a_tap_sets_the_beat_going_for_a_tap_ring(tap):
    tap.footswitches((STOMP,) * 5, (9, 0, 0, 0, 0))
    tap.m.u8(CC_TYPES + 6, 9)
    tap.call('tc_fire', CC, 6, 1, 0)
    assert tap.m.u32(BEAT_PERIOD) == 500 and tap.m.read(BEAT_ON, 1) == b'\x01'


def test_a_tap_command_gets_a_footswitch_node_named_tap(tap):
    tap.m.write(NODE, bytes(0x40))
    assert tap.call('tc_node', NODE, 9) == 1
    assert tap.m.read(NODE + 0x24, 4) == b'Tap\0'
    assert not tap.calls(cmd.NODE_NAME)


@pytest.mark.parametrize('ctype', [1, 2, 7, 13, 16])
def test_every_other_type_is_named_as_stock(tap, ctype):
    tap.stock = 1
    assert tap.call('tc_node', NODE, ctype) == 1
    assert tap.calls(cmd.NODE_NAME, STRCPY) == [(cmd.NODE_NAME, (NODE, ctype, 0, 0))]


@pytest.mark.parametrize('slot', range(6, 11))
def test_tap_has_its_own_place_on_an_fs_slots_knob(tap, slot):
    assert tap.call('tc_choice', CC, slot, 9) == 7
    assert not tap.calls(cmd.CHOICE)


@pytest.mark.parametrize('stock, ours', [(0, 0), (6, 6), (7, 8), (8, 9), (9, 10)])
def test_preset_snapshot_and_looper_move_one_place_up(tap, stock, ours):
    tap.stock = stock
    assert tap.call('tc_choice', CC, 7, 14) == ours


@pytest.mark.parametrize('slot', [0, 5, 11, 12])
def test_instant_and_exp_slots_keep_the_stock_places(tap, slot):
    tap.stock = 3
    assert tap.call('tc_choice', CC, slot, 9) == 3
    assert tap.calls(cmd.CHOICE) == [(cmd.CHOICE, (CC, slot, 9, 0))]


@pytest.mark.parametrize('i', range(len(FS_LIST)))
def test_the_command_knob_steps_along_the_fs_list_and_stops_at_its_ends(tap, i):
    t = FS_LIST[i]
    assert tap.call('tc_step', CC, 8, t, 1) == FS_LIST[min(i + 1, len(FS_LIST) - 1)]
    assert tap.call('tc_step', CC, 8, t, 2) == FS_LIST[min(i + 1, len(FS_LIST) - 1)], 'one place a call, as stock'
    assert tap.call('tc_step', CC, 8, t, -1 & 0xffffffff) == FS_LIST[max(i - 1, 0)]
    assert not tap.calls(cmd.STEP)


@pytest.mark.parametrize('t', [3, 7, 13, 17, 21])
def test_a_type_not_on_the_fs_list_steps_as_none(tap, t):
    assert tap.call('tc_step', CC, 6, t, 1) == 1
    assert tap.call('tc_step', CC, 6, t, -1 & 0xffffffff) == 0


@pytest.mark.parametrize('slot', [0, 5, 11, 12])
def test_instant_and_exp_slots_step_as_stock(tap, slot):
    tap.stock = 18
    assert tap.call('tc_step', CC, slot, 0, 1) == 18
    assert tap.calls(cmd.STEP) == [(cmd.STEP, (CC, slot, 0, 1))]


@pytest.mark.parametrize('functions, types, rings', [
    ((STOMP, STOMP, TAP_FN), (9, 0, 0), 0b001),
    ((STOMP, STOMP, STOMP), (9, 9, 9), 0b111),
    ((STOMP, STOMP, STOMP), (0, 9, 1), 0b010),
    ((5, 6, TAP_FN), (9, 9, 9), 0b000),          # Scroll mode's FS1/FS2, and FS3 TAP: not Stomp switches
    ((13, 13, 13), (9, 9, 9), 0b000),            # Preset mode
    ((14, 14, 14), (9, 9, 9), 0b000),            # Snapshot mode
])
def test_only_stomp_switches_with_a_tap_command_blink(tap, functions, types, rings):
    tap.footswitches(functions + (STOMP, STOMP), types + (9, 9))
    assert tap.call('tc_active') == rings


def test_the_beat_runs_as_stock_while_fs3_is_tap(tap):
    tap.footswitches((STOMP, STOMP, TAP_FN, STOMP, STOMP), (9, 0, 0, 0, 0))
    assert tap.call('tc_running') == FS_STATE_OBJ


def test_the_beat_stops_as_stock_without_a_tap_ring(tap):
    tap.footswitches((STOMP,) * 5, (0, 0, 0, 9, 9))
    assert tap.call('tc_running') == FS_STATE_OBJ


def test_a_tap_ring_keeps_the_beat_running(tap):
    tap.footswitches((STOMP,) * 5, (0, 9, 0, 0, 0))
    state = tap.call('tc_running')
    assert state != FS_STATE_OBJ and tap.m.read(state + 8, 1) == b'\x01', 'FS3 reads TAP'


def test_the_turn_on_lights_each_tap_ring_red_and_hands_back_the_real_state(tap):
    tap.footswitches((STOMP,) * 5, (9, 0, 9, 0, 0))
    assert tap.call('tc_on') == FS_STATE_OBJ
    assert tap.leds() == [(LED_COLOUR, (0, RED_WORD)), (cmd.LED_MODE, (0, 1)), (LED_COLOUR, (2, RED_WORD)), (cmd.LED_MODE, (2, 1))]


def test_external_clock_lights_them_blue(tap):
    tap.ext = 1
    tap.footswitches((STOMP,) * 5, (0, 9, 0, 0, 0))
    tap.call('tc_on')
    assert tap.leds() == [(LED_COLOUR, (1, BLUE_WORD)), (cmd.LED_MODE, (1, 1))]


def test_without_a_tap_ring_the_turn_on_lights_nothing(tap):
    assert tap.call('tc_on') == FS_STATE_OBJ
    assert tap.leds() == []


def test_with_tap_led_color_the_first_ring_moves_its_colour_on(coloured):
    coloured.footswitches((STOMP,) * 5, (9, 9, 0, 0, 0))
    coloured.call('tc_on')
    assert coloured.leds() == [(TAP_LED, (0, RED_WORD)), (cmd.LED_MODE, (0, 1)), (TAP_LED_AGAIN, (1, RED_WORD)),
                               (cmd.LED_MODE, (1, 1))]


def test_with_fs3_tap_its_own_turn_moves_the_colour_on(coloured):
    coloured.footswitches((STOMP, STOMP, TAP_FN, STOMP, STOMP), (9, 0, 0, 0, 0))
    coloured.call('tc_on')
    assert coloured.leds() == [(TAP_LED_AGAIN, (0, RED_WORD)), (cmd.LED_MODE, (0, 1))]


def test_the_turn_off_turns_off_fs3_only_when_it_is_tap(tap):
    tap.footswitches((STOMP,) * 5, (9, 0, 0, 0, 0))
    tap.call('tc_off', 2, 0)
    assert tap.leds() == [(cmd.LED_MODE, (0, 0))]
    tap.footswitches((STOMP, STOMP, TAP_FN, STOMP, STOMP), (0, 9, 0, 0, 0))
    tap.call('tc_off', 2, 0)
    assert tap.leds() == [(cmd.LED_MODE, (2, 0)), (cmd.LED_MODE, (1, 0))]


@pytest.mark.parametrize('handler', ['tc_refresh', 'tc_setting'])
@pytest.mark.parametrize('bpm', [40.0, 60.0, 97.3, 120.0, 133.0, 240.0, 1.0, 1000.0])
def test_the_refresh_and_a_tempo_change_set_the_period_as_stock_works_it_out(tap, bpm, handler):
    tap.footswitches((STOMP,) * 5, (0, 0, 9, 0, 0))
    tap.values.update({14: 2, 15: bpm, 16: 333.0})
    assert tap.call(handler) == FS_STATE_OBJ
    assert abs(tap.m.u32(BEAT_PERIOD) - int(60000 / bpm)) <= 1
    assert tap.m.read(BEAT_ON, 1) == b'\x01'


@pytest.mark.parametrize('select, bpm', [(0, 16), (1, 16), (2, 15)])
def test_tempo_select_picks_the_bpm_setting_as_stock(tap, select, bpm):
    tap.footswitches((STOMP,) * 5, (9, 0, 0, 0, 0))
    tap.values.update({14: select, 15: 60.0, 16: 120.0})
    tap.call('tc_refresh')
    assert tap.m.u32(BEAT_PERIOD) == {15: 1000, 16: 500}[bpm]


@pytest.mark.parametrize('handler', ['tc_refresh', 'tc_setting'])
@pytest.mark.parametrize('case', ['fs3 tap', 'no tap ring', 'tap led off', 'tap led unset', 'no tempo', 'tempo too fast'])
def test_the_refresh_and_a_tempo_change_leave_the_period_alone(tap, case, handler):
    tap.footswitches((STOMP,) * 5, (9, 0, 0, 0, 0))
    if case == 'fs3 tap':
        tap.footswitches((STOMP, STOMP, TAP_FN, STOMP, STOMP), (9, 0, 0, 0, 0))
    elif case == 'no tap ring':
        tap.footswitches((STOMP,) * 5, (0, 0, 0, 9, 9))
    elif case == 'tap led off':
        tap.values[26] = 0
    elif case == 'tap led unset':
        del tap.values[26]
    elif case == 'no tempo':
        del tap.values[16]
    else:
        tap.values[16] = 2048.0
    tap.m.u32(BEAT_PERIOD, 1234)
    tap.m.u8(BEAT_ON, 1)
    tap.call(handler)
    assert tap.m.u32(BEAT_PERIOD) == 1234
    assert tap.m.read(BEAT_ON, 1) == (b'\x00' if case == 'tap led off' else b'\x01'), 'only Tap Tempo LED Off stops the beat'


def test_module_list_is_the_stock_fs_list_with_tap_after_hotkey(tap):
    sym = tap.sym
    code = _code[False][0]
    assert tuple(code[sym['tc_list']:sym['tc_list'] + len(FS_LIST)]) == FS_LIST
    assert tuple(t for t in FS_LIST if t != 9) == STOCK_FS_LIST


def stock_code(m4emu, start, end):
    read = reader(stock_e0())
    m = m4emu.M4(read(start, end - start), start)
    m.write(0x28e3d1a0, read(0x28e3d1a0, 0x140))            # the FS and Instant lists
    return m


@pytest.mark.firmware
def test_the_stock_fs_list_and_its_places():
    read = reader(stock_e0())
    assert tuple(read(0x28e3d1a9, 9)) == STOCK_FS_LIST[1:]
    assert read(0x28e3d1b2, 2) == b'\0\0', 'the list cannot grow where it is: a string follows'
    assert [struct.unpack('<I', read(cmd.CHOICES + 4 * s, 4))[0] for s in range(13)] == [6] * 6 + [10] * 5 + [2] * 2
    assert stock_e0().count(struct.pack('<I', cmd.CHOICES)) == 1, 'only 0x28de57bc reads the places'


@pytest.mark.firmware
def test_stock_knob_code_matches_what_the_handlers_assume(m4emu):
    m = stock_code(m4emu, 0x28de6400, 0x28de6640)
    for i, t in enumerate(STOCK_FS_LIST):
        nxt, prev = STOCK_FS_LIST[min(i + 1, 9)], STOCK_FS_LIST[max(i - 1, 0)]
        assert [m.call(cmd.STEP, CC, 7, t, d & 0xffffffff) for d in (-1, 1, 2)] == [prev, nxt, nxt]
    assert m.call(cmd.STEP, CC, 7, 9, 1) == 1, 'an unknown type steps as None'
    m = stock_code(m4emu, 0x28de57d0, 0x28de5868)
    assert [m.call(cmd.CHOICE, CC, 7, t) for t in STOCK_FS_LIST] == list(range(10))
    assert m.call(cmd.CHOICE, CC, 7, 9) == 0, 'stock firmware shows Tap as None'
    read = reader(stock_e0())
    assert read(0x28dbd72c, 4) == bytes.fromhex('1028 bed1'), 'cmp r0, #0x10; bne: the turn stops at Looper, the last FS place'


@pytest.mark.firmware
def test_type_9_is_complete_and_inert_in_stock(m4emu):
    read = reader(stock_e0())
    assert read(cmd.NAMES + 8 * 9, 8) == b'CV Out\0\0'
    assert read(cmd.COUNTS + 9, 1) == bytes([2])
    assert tuple(read(0x28e3d10c + 7 * 9, 7)) == (0, 18, 22, 22, 22, 22, 0), 'Command, CV Value'
    m = stock_code(m4emu, 0x28de5cd4, 0x28de5ee0)
    m.u8(CC_TYPES + 7, 9)
    for state in (0, 1):
        m.log.clear()
        m.call(cmd.FIRE, CC, 7, state, 0)
        assert m.log == [], 'type 9 fires nothing, pressed or released'


@pytest.mark.firmware
def test_stock_gives_type_9_no_footswitch_node(m4emu):
    m = stock_code(m4emu, 0x28dd568c, 0x28dd5750)
    m.stub(STRCPY)
    named = {t: m.call(cmd.NODE_NAME, NODE, t) for t in range(1, 17)}
    assert [t for t, ok in named.items() if not ok] == [7, 8, 9, 10, 11, 13], 'Ext Amp, CV and Instant Hotkey get none'


@pytest.mark.firmware
def test_stock_call_sites_and_their_arguments():
    read = reader(stock_e0())
    assert read(cmd.FIRE_CALL, 4) == pm.bl(cmd.FIRE_CALL, cmd.FIRE)
    assert read(cmd.FIRE_CALL - 8, 8) == bytes.fromhex('019a 0346 3946 5046'), 'r0 the Command Center, r1 the slot, r2 the state, r3 momentary'
    for site in cmd.CHOICE_CALLS:
        assert read(site, 4) == pm.bl(site, cmd.CHOICE)
    for site in cmd.NODE_CALLS:
        assert read(site, 4) == pm.bl(site, cmd.NODE_NAME)
    assert read(cmd.STEP_CALL, 4) == pm.bl(cmd.STEP_CALL, cmd.STEP)
    for site in cmd.BEAT_RUN_CALLS + (cmd.BEAT_ON_CALL, cmd.REFRESH_CALL, cmd.SETTING_CALL):
        assert read(site, 4) == pm.bl(site, cmd.FS_STATE)
        assert read(site + 4, 2) in (bytes.fromhex('037a'), bytes.fromhex('00eb')), 'ldrb r3, [r0, #8], or add.w r0, r0, r4, lsl #1'
    assert read(cmd.BEAT_OFF_CALL - 4, 8) == bytes.fromhex('0021 0220') + pm.bl(cmd.BEAT_OFF_CALL, cmd.LED_MODE)
    assert read(0x28de36b6, 4) == pm.bl(0x28de36b6, cmd.FIRE), "snapshot recall's fire stays stock"


@pytest.mark.firmware
def test_a_tempo_setting_change_resets_only_a_tap_footswitchs_beat_on_stock():
    read = reader(stock_e0())
    assert read(0x28dd2708, 6) == bytes.fromhex('6379 0399 192b'), 'cmp r3, #0x19: a setting change event'
    assert struct.unpack('<3I', read(0x28dd272c, 12)) == (cmd.SETTING_CALL - 1,) * 3, 'settings 14, 15 and 16 go to the loop'
    assert read(cmd.SETTING_CALL - 2, 2) == bytes.fromhex('0024'), 'movs r4, #0: from footswitch 1'
    assert read(cmd.SETTING_CALL + 0xc, 2) == bytes.fromhex('012b'), 'cmp r3, #1: TAP'
    assert read(0x28dd27a6, 4) == pm.bl(0x28dd27a6, 0x28dd0ab8), "only then the TAP ring's beat setup"


@pytest.mark.firmware
def test_build_sends_every_site_to_the_module(m4emu):
    read, on = built({'HX_CC_TAP': '1'})
    code, sym = m4emu.assemble(cmd.MODULE, MODS, IDS, inc={'tap.inc': tap_inc(False)})
    assert 'tap_command' in on and 'tap_color' not in on
    module = branch_target(cmd.FIRE_CALL, read(cmd.FIRE_CALL, 4)) - sym['tc_fire']
    assert read(module, len(code)) == code
    sites = {cmd.STEP_CALL: 'tc_step', cmd.BEAT_ON_CALL: 'tc_on', cmd.BEAT_OFF_CALL: 'tc_off', cmd.REFRESH_CALL: 'tc_refresh',
             cmd.SETTING_CALL: 'tc_setting',
             **{s: 'tc_choice' for s in cmd.CHOICE_CALLS}, **{s: 'tc_running' for s in cmd.BEAT_RUN_CALLS},
             **{s: 'tc_node' for s in cmd.NODE_CALLS}}
    for site, handler in sites.items():
        assert branch_target(site, read(site, 4)) == module + sym[handler], hex(site)
    assert [struct.unpack('<I', read(cmd.CHOICES + 4 * s, 4))[0] for s in range(13)] == [6] * 6 + [11] * 5 + [2] * 2
    assert read(cmd.NAMES + 8 * 9, 8) == b'Tap\0\0\0\0\0' and read(cmd.COUNTS + 9, 1) == b'\x01'


@pytest.mark.firmware
def test_with_tap_led_color_the_rings_take_its_handlers(m4emu, monkeypatch):
    seen, real = {}, pm.Patch.module

    def module(self, path, inc=None):
        sym = real(self, path, inc)
        seen[path] = ({k: sym[k] for k in sym.symbols}, inc)
        return sym

    monkeypatch.setattr(pm.Patch, 'module', module)
    built({'HX_CC_TAP': '1', 'HX_TAP_COLOR': '1'})
    tsym, _ = seen[tc.MODULE]
    _, inc = seen[cmd.MODULE]
    assert inc['tap.inc'] == f'.equ TAP_LED, {tsym["tap_led"] | 1:#x}\n.equ TAP_LED_AGAIN, {tsym["tap_led_again"] | 1:#x}\n'


@pytest.mark.firmware
def test_without_the_flag_the_sites_stay_stock():
    read, on = built({})
    assert 'tap_command' not in on
    assert read(cmd.FIRE_CALL, 4) == pm.bl(cmd.FIRE_CALL, cmd.FIRE)
    assert read(cmd.NAMES + 8 * 9, 8) == b'CV Out\0\0'


@pytest.mark.firmware
def test_builds_alongside_every_other_feature():
    env = {f: '1' for m in MODS if not getattr(m, 'CONFLICTS', ()) for f in features.flags(m)}   # but a feature that conflicts
    _, on = built(env)
    assert {'tap_command', 'tap_color', 'bpm', 'long_press', 'metronome', 'preset_color', 'tuner'} <= set(on)
