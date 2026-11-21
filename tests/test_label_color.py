"""tools/features/label_color.py and src/m4/label_color.s: the Global Settings, Edit view and tuner page label calls in unicorn, the
HXtra parameter table and the hooks a build makes."""
import struct

import pytest

import features
import patch_menu as pm
import setting_ids
from features import label_color as lc
from features import tuner
from firmware import branch_target, built, reader, stock_e0, stock_entry

MODS = features.load()
IDS = setting_ids.by_name()
MOD, TRAMPOLINE, INFO, NAME = 0x28e60000, 0x28e5f000, 0x28e5e000, 0x28e5d000
FRAME = 0x28f00000 - 8              # the knob drawer's sp, under the trampoline's push
DELUXE, NAM_ID = 119, 555           # Deluxe Comp Mono, 7 parameters of its own
PARAMS = [(DELUXE, 7), (NAM_ID, 0)]
WHITE, TEAL = 0xffffff, 0x3cceb5
STOCK_ID, HXTRA_ID = 25, IDS['tap_color.color']
_code = {}


class Label:
    """label_color.s in tests/m4emu.py's M4, with the stock label colour and label text stubbed and logged."""

    def __init__(self, m4emu):
        if 'test' not in _code:
            _code['test'] = m4emu.assemble(lc.MODULE, MODS, IDS, inc={'label.inc': lc.label_inc(PARAMS)})
        code, self.sym = _code['test']
        self.m = m4emu.M4(code, MOD)
        # push {r5, lr}; mov r5, r2; blx r3; pop {r5, pc}: the callers' r5 holds the setting ID or the block info
        self.m.load(TRAMPOLINE, bytes.fromhex('20b5 1546 9847 20bd'))
        for fn in (lc.LABEL_COLOUR, lc.PARAM_LABEL):
            self.m.stub(fn)

    def colour(self, slot, pid):
        """The section paint's colour call for slot showing setting pid -> the colour passed on to the stock call."""
        self.m.log.clear()
        self.m.call(TRAMPOLINE, slot, WHITE, pid, MOD + self.sym['label_colour'] | 1)
        (got,) = self.m.calls(lc.LABEL_COLOUR)
        assert got[0] == slot
        return got[1]

    def param(self, knob, preset_id, index, second=None):
        """The knob drawer labelling knob with parameter index of preset_id (the block's second model with second, the first's
        ID) -> the colour set first, or None."""
        first, other = (preset_id, 0xffffffff) if second is None else (second, preset_id)
        self.m.write(INFO, b'\x01' + struct.pack('<II', first, other))
        self.m.u32(FRAME + 0x6c, index)
        self.m.u8(FRAME + 0x70, int(second is not None))
        self.m.log.clear()
        self.m.call(TRAMPOLINE, knob, NAME, INFO, MOD + self.sym['label_param'] | 1)
        assert [c[:2] for c in self.m.calls(lc.PARAM_LABEL)] == [(knob, NAME)], 'then the label'
        colours = self.m.calls(lc.LABEL_COLOUR)
        assert len(colours) <= 1 and all(c[0] == knob for c in colours)
        return colours[0][1] if colours else None


@pytest.fixture
def label(m4emu):
    return Label(m4emu)


def test_the_feature():
    assert lc.FLAG == 'HX_LABEL_COLOR' and getattr(lc, 'WEB', True) is True, 'every web build (user decision)'
    assert not hasattr(lc, 'SETTINGS'), 'no setting yet'
    assert lc.TEAL == TEAL, "Tap LED Color's Teal"


@pytest.mark.parametrize('pid', (0xcc, 0xdf, 0xf9))
def test_an_hxtra_setting_is_teal(label, pid):
    assert label.colour(1, pid) == TEAL


@pytest.mark.parametrize('pid', (0, 25, 26, 0xcb, 0xfa, 0x17e))
def test_a_stock_setting_stays_white(label, pid):
    assert label.colour(1, pid) == WHITE


@pytest.mark.parametrize('index', (7, 8, 9))
def test_a_gr_knob_is_teal(label, index):
    assert label.param(1, DELUXE, index) == TEAL


@pytest.mark.parametrize('index', (0, 6))
def test_a_compressors_own_parameter_keeps_the_page_loops_white(label, index):
    assert label.param(1, DELUXE, index) is None


@pytest.mark.parametrize('index', (0, 5, 9))
def test_every_nam_parameter_is_teal(label, index):
    assert label.param(2, NAM_ID, index) == TEAL


def test_a_stock_model_keeps_white(label):
    assert label.param(0, 120, 9) is None


def test_the_second_model_of_a_block_is_matched_by_its_own_id(label):
    assert label.param(0, NAM_ID, 1, second=DELUXE) == TEAL
    assert label.param(0, 120, 8, second=DELUXE) is None, "the first model's ID does not count"


def test_label_any_gives_the_tuner_page_teal(label):
    label.m.log.clear()
    label.m.call(MOD + label.sym['label_any'], 1, WHITE)
    assert [c[:2] for c in label.m.calls(lc.LABEL_COLOUR)] == [(1, TEAL)]


def test_label_color_is_built_before_tuner():
    assert lc.ORDER < getattr(tuner, 'ORDER', 100) and tuner.LABEL_COLOR == lc.MODULE


def stock_params():
    import patch_amp as pa
    e0 = stock_e0()
    read = reader(e0)
    return lc.hxtra_params(read, lambda a: struct.unpack('<I', read(a, 4))[0], pa._parse_e0_segments(e0), stock_entry(3))


@pytest.mark.firmware
def test_the_table_is_the_gr_compressors_then_metronome():
    import patch_comp
    params = stock_params()
    assert len(params) == len(patch_comp.COMP_MODELS) + 1, 'no NAM in a stock Entry 3'
    assert dict(params)[119] == 7 and dict(params)[121] == 3, 'Deluxe Comp Mono and Red Squeeze Mono'
    assert params[-1] == (lc.METRONOME, 0)


def test_the_metronome_id_is_patch_clicks():
    import patch_click
    assert lc.METRONOME == patch_click.PRESET_ID


@pytest.mark.firmware
def test_build_sends_the_label_calls_to_the_module(m4emu):
    read, on = built({'HX_LABEL_COLOR': '1'})
    assert 'label_color' in on
    code, sym = m4emu.assemble(lc.MODULE, MODS, IDS, inc={'label.inc': lc.label_inc(stock_params())})
    module = branch_target(lc.LABEL_CALL, read(lc.LABEL_CALL, 4)) - sym['label_colour']
    assert read(module, len(code)) == code
    assert branch_target(lc.PARAM_CALL, read(lc.PARAM_CALL, 4)) == module + sym['label_param']


@pytest.mark.firmware
def test_without_the_flag_the_label_calls_stay_stock():
    read, on = built({})
    assert 'label_color' not in on
    assert read(lc.LABEL_CALL, 4) == pm.bl(lc.LABEL_CALL, lc.LABEL_COLOUR)
    assert read(lc.PARAM_CALL, 4) == pm.bl(lc.PARAM_CALL, lc.PARAM_LABEL)


@pytest.mark.firmware
def test_builds_alongside_every_other_feature():
    env = {f: '1' for m in MODS if not getattr(m, 'CONFLICTS', ()) for f in features.flags(m)}   # but a feature that conflicts
    _, on = built(env)
    assert {'label_color', 'tuner', 'gr', 'tap_color'} <= set(on)
