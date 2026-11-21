"""tools/block3.py: the Block 3 room NAM A2 Lite's slots leave, what each DSP feature costs of it, and where each one goes."""
import ast
import itertools
from pathlib import Path

import pytest

import block3
import m4cache
import nam_multi

ROOT = Path(__file__).resolve().parent.parent
EVERY = [f for f, _ in block3.FEATURES]


def env_of(flags, slots=None):
    return {f: '1' for f in flags} | ({block3.VAR: str(slots)} if slots is not None else {})


def ranges(flag, env):
    """[start, end) normal words of the feature's data and code."""
    n_dm, n_pm = block3.size(flag)
    dm, pm = block3.place(flag, env)
    return (dm, dm + n_dm), (block3.nw(pm), block3.nw(pm + n_pm + (n_pm & 1)))


def overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def test_layout_is_that_of_the_kernel_build_py_builds():
    tree = ast.parse((ROOT / 'build.py').read_text())
    kernel = next(ast.literal_eval(n.value) for n in tree.body
                  if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', None) == 'KERNEL')
    for slots in (3, 2):
        with nam_multi.flags(kernel['HX_Stomp'][1:]):
            _, built = nam_multi.build(slots)
        lay = block3.layout(slots)
        assert (lay.n_code, lay.n_cold, lay.cold_pm, lay.b3_to) == (built.n_code, built.n_cold, built.cold_pm, built.b3_to)
    assert block3.layout(3).cold_pm != nam_multi.layout([]).cold_pm      # build.py's flags change the cold code


def test_room_grows_as_nam_slots_go():
    words = [block3.words(s) for s in block3.SLOTS]
    assert block3.SLOTS == (3, 2, 1, 0) and words == sorted(words)
    assert words[:2] == [512, 2528]
    lo, hi = block3.room(0)
    assert lo == nam_multi.B3 and hi <= nam_multi.COLD_END


def test_room_is_clear_of_the_kernel():
    for slots in (3, 2, 1):
        lo, hi = block3.room(slots)
        lay = block3.layout(slots)
        assert lo == lay.b3_to and hi == lay.cold_nw
        assert not any(overlap((lo, hi), c) for c in lay.claims())


def test_room_ends_at_an_even_instruction():
    for slots in block3.SLOTS:
        hi = block3.room(slots)[1]
        assert block3.nw(block3.pm_at(hi)) == hi and block3.pm_at(hi) % 2 == 0


def test_costs_are_whole_instruction_pairs():
    assert {f: block3.cost(f) for f in EVERY} == {'HX_CLICK': 213, 'HX_FX_GATE': 291, 'HX_GR': 780, 'HX_USB_MONITOR': 414,
                                                        'HX_GATE_SC': 324}
    for f in EVERY:
        n_dm, n_pm = block3.size(f)
        assert block3.cost(f) % 3 == 0 and block3.cost(f) >= n_dm + n_pm * 3 // 2


@pytest.mark.parametrize('slots', block3.SLOTS)
def test_every_selection_that_fits_places_clear_of_each_other_and_inside_the_room(slots):
    lo, hi = block3.room(slots)
    for n in range(len(EVERY) + 1):
        for on in itertools.combinations(EVERY, n):
            env = env_of(on, slots)
            if not block3.fits(slots, on):
                with pytest.raises(SystemExit, match=f'{slots} NAM slots leave'):
                    block3.slots(env)
                continue
            got = [r for f in on for r in ranges(f, env)]
            assert all(lo <= a and b <= hi for a, b in got)
            assert not any(overlap(a, b) for a, b in itertools.combinations(got, 2))
            assert hi - min((a for a, _ in got), default=hi) <= sum(block3.cost(f) for f in on)


def test_features_pack_down_from_the_top_in_order():
    env = env_of(EVERY, 2)
    click, gate, gr, usb, sc = (ranges(f, env) for f in EVERY)
    assert click[1][1] == block3.room(2)[1]
    assert sc[0][1] <= sc[1][0] <= sc[1][1] <= usb[0][0]
    assert usb[0][1] <= usb[1][0] <= usb[1][1] <= gr[0][0]
    assert gr[0][1] <= gr[1][0] <= gr[1][1] <= gate[0][0] <= gate[1][1] <= click[1][0]


def test_a_feature_keeps_its_place_whatever_comes_after_it():
    # the Metronome's kernel and the gate where #105 put them: under NAM's cold code, beside three slots
    env = env_of(['HX_CLICK', 'HX_FX_GATE'], 3)
    assert block3.place('HX_CLICK', env)[1] == 0xe5386 and block3.place('HX_FX_GATE', env) == (0xe7c26, 0xe52ee)
    assert block3.place('HX_FX_GATE', env | {'HX_GR': '1', block3.VAR: '2'}) == (0xe7c26, 0xe52ee)


def test_slots_unset_is_the_most_that_fit():
    assert block3.slots({}) == 3
    assert block3.slots(env_of(['HX_CLICK', 'HX_FX_GATE'])) == 3
    assert block3.slots(env_of(['HX_GR'])) == 2
    assert block3.slots(env_of(EVERY)) == 2


def test_slots_set_is_checked():
    assert block3.slots(env_of(EVERY, 0)) == 0
    with pytest.raises(SystemExit, match='HX_NAM_SLOTS is one of 3, 2, 1, 0'):
        block3.slots({block3.VAR: '4'})
    with pytest.raises(SystemExit, match='HX_GR take 780 words of Block 3; 3 NAM slots leave 512'):
        block3.slots(env_of(['HX_GR'], 3))


def test_features_are_the_web_pages_dsp_features():
    assert sorted(EVERY) == sorted(m4cache.web_dsp())


def test_build_py_kernel_takes_the_slot_count():
    assert block3.kernel('HX_Stomp', 3) == ['tools/sharc/nam_multi.py', '--mid-sweep']
    assert block3.kernel('HX_Stomp', 1)[-2:] == ['--slots', '1']


# ---- whole builds with each slot count, pinned as tests/test_firmware.py pins the default one

SLOTS_BUILT_MD5 = {
    'HX_NAM_SLOTS=1 HX_GR HX_CLICK HX_FX_GATE': 'f5d5c34db76ab801a7325a34c5712070',
    'HX_NAM_SLOTS=0 HX_GR HX_CLICK HX_FX_GATE HX_REAL_NAMES': '36fad3d1451bf38267ddf07d13eed0c5',     # no NAM A2 Lite: no kernel, patch_menu.py on the stock image
    'HX_NAM_SLOTS=0 HX_GR HX_FX_GATE': '8b1450dbacf082b77617e07384e5905c',               # no add-model before patch_comp: its strings grow at the tail
    'HX_NAM_SLOTS=0 HX_GR HX_GATE_SC': '149c68591e6239ef4e619e964d925d3f',
    'HX_NAM_SLOTS=0 HX_FX_GATE HX_GATE_SC': '63244c67d1280f7b0b2d7789b688d4dd',      # patch_sidechain.py's strings, after patch_gate.py's
}


@pytest.mark.firmware
@pytest.mark.parametrize('flags', SLOTS_BUILT_MD5)
def test_slots_build(tmp_path, flags):
    import hashlib
    import os
    import subprocess
    import sys
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    out = tmp_path / 'slots.hxf'
    env = {k: v for k, v in os.environ.items() if not k.startswith('HX_') or k == 'HX_STOMP_HXF'}
    env.update(f.split('=', 1) if '=' in f else (f, '1') for f in flags.split())
    r = subprocess.run([sys.executable, str(ROOT / 'build.py'), stock, '-o', str(out), '--no-check'],
                       capture_output=True, text=True, cwd=ROOT, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    slots = flags.split()[0].split('=')[1]
    assert f'NAM slots: {slots}\n' in r.stdout and 'ALL OK' in r.stdout and ' size 0x' in r.stdout
    assert ('tools/sharc/nam_multi.py' in r.stdout) == (slots != '0')
    assert ('NAM A2 Lite' in r.stdout) == (slots != '0')
    assert hashlib.md5(out.read_bytes()).hexdigest() == SLOTS_BUILT_MD5[flags]

