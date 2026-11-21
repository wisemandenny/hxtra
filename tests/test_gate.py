"""The gate in the FX Loop and Return blocks (issue #69): src/sharc/fx_gate.asm in ssim around a stand-in reader, the models' knobs
and their writers to the return reader (tools/patch_gate.py), its place in Block 3 and the registry, its place among build.py's
steps, and its feature (tools/features/fx_gate.py)."""
import hashlib
import importlib.util
import math
import os
import random
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest

import features
import m4cache
import block3
import nam_multi
import patch_amp as pa
import patch_click
import patch_comp as pc
import patch_gate as pg
import sasm
import ssim
from features import fx_gate

ROOT = Path(__file__).resolve().parent.parent
f2u = pg.f2u
QUIET = dict(log=lambda *_: None)


def u2f(u):
    return struct.unpack('<f', struct.pack('<I', u))[0]


# ---- the DSP code, in ssim

READER, CTRL, SRC, OUT = 0x90100, 0x90300, 0x7000, 0x7100   # the stand-in reader and control function; its jack and I2


def dsp():
    """(sim, symbols) of fx_gate.asm with a stand-in reader copying 16 samples from SRC to I2, and a stand-in control function."""
    src = pg.dsp_asm(0xe7a00, 0xe5200)
    for k, v in (('ORIG', READER), ('ORIG_CTRL_2618', CTRL)):
        src, n = re.subn(r'(\.equ %s,\s*)0x[0-9a-fA-F]+' % k, r'\g<1>%#x' % v, src)
        assert n == 1, k
    ret = '    I12 = DM(M7, I6);\n    JUMP (M14, I12) (DB);\n    NOP;\n    RFRAME;'
    assert ret in src
    src = src.replace(ret, '    RTS;')     # the C return needs the caller's frame
    src += f"""
.section dm 0x6f00
FAKE_CTRL: .space 1
.section pm {READER:#x}
    I4 = {SRC:#x};
    I5 = I2;
    LCNTR = 16, DO fr UNTIL LCE;
      F0 = DM(I4, 1);
fr:   DM(I5, 1) = F0;
    RTS;
.section pm {CTRL:#x}
    R0 = 0x777;
    DM(FAKE_CTRL) = R0;
    RTS;
"""
    secs, syms = sasm.assemble(src, 'fx_gate_test')
    s = ssim.Sim()
    s.load(secs)
    return s, syms


def ctrl(s, syms, state, pid, value):
    """The control function as the framework calls it: pid R4, a pointer to the value R8, the state R12 (its first word the reader's I0)."""
    s.wr(0x5000, value)
    s.wr(0x6000, state)
    s.u[4], s.u[8], s.u[12], s.u[3] = pid, 0x5000, 0x6000, 0x1234
    s.call(syms['CTRL_2618'])
    assert s.u[3] == 0x1234


def knobs(s, syms, state, on, thr, decay):
    ctrl(s, syms, state, pg.GATE_PID, int(on))
    ctrl(s, syms, state, pg.GATE_PID + 1, f2u(thr))
    ctrl(s, syms, state, pg.GATE_PID + 2, f2u(decay))


def block(s, syms, state, samples):
    """One 16-sample call of the wrapped reader: what it leaves at I2."""
    for k, x in enumerate(samples):
        s.wr(SRC + k, f2u(x))
    s.u[0x10], s.u[0x12] = state, OUT
    for r in range(1, 10):
        s.u[r] = 0x100 + r
    s.call(syms['ENTRY_2618'])
    assert all(s.u[r] == 0x100 + r for r in range(1, 10)), 'R1..R9 as called'
    return [u2f(s.rd(OUT + k)) for k in range(16)]


def db(xs):
    return 20 * math.log10(math.sqrt(sum(x * x for x in xs) / len(xs)) + 1e-12)


def hiss(rng, level=0.01):
    return [rng.uniform(-level, level) for _ in range(16)]


def tone(k, level=0.3):
    return [level * math.sin(2 * math.pi * 110 * (16 * k + n) / 48000) for n in range(16)]


def test_without_knobs_or_off_the_reader_is_as_stock():
    s, syms = dsp()
    rng = random.Random(1)
    x = hiss(rng)
    assert block(s, syms, 7, x) == pytest.approx(x, abs=1e-9)
    knobs(s, syms, 7, False, 0.0, 0.1)
    x = hiss(rng)
    assert block(s, syms, 7, x) == pytest.approx(x, abs=1e-9)


def test_hiss_under_the_threshold_is_gated():
    s, syms = dsp()
    rng = random.Random(2)
    knobs(s, syms, 7, True, -30.0, 0.1)
    out = [db(block(s, syms, 7, hiss(rng))) for _ in range(300)]      # 0.1 s
    assert out[0] > -46 and out[-1] < -100


def test_a_signal_over_the_threshold_opens_it_within_two_ms():
    s, syms = dsp()
    rng = random.Random(3)
    knobs(s, syms, 7, True, -30.0, 0.1)
    for _ in range(100):
        block(s, syms, 7, hiss(rng))
    gains = []
    for k in range(30):
        x = tone(k)
        gains.append(sum(abs(v) for v in block(s, syms, 7, x)) / sum(abs(v) for v in x))
    assert gains[0] < 0.3 and gains[6] > 0.8 and gains[-1] == pytest.approx(1.0, abs=1e-4)


@pytest.mark.parametrize('decay, ms', [(0.01, (30, 70)), (1.0, (600, 800))])
def test_decay_sets_how_fast_it_closes(decay, ms):
    s, syms = dsp()
    rng = random.Random(4)
    knobs(s, syms, 7, True, -30.0, decay)
    for k in range(10):
        block(s, syms, 7, tone(k))
    n = 0
    while db(block(s, syms, 7, hiss(rng))) > -90:
        n += 1
        assert n < 6000
    assert ms[0] <= n * 16 / 48 <= ms[1]


@pytest.mark.parametrize('thr', [0.0, -30.0, -60.0, -96.0])
def test_threshold_in_db_becomes_a_level(thr):
    s, syms = dsp()
    knobs(s, syms, 7, True, thr, 0.1)
    tab = syms['G_TAB']
    assert s.rd(tab) == 7 and s.rd(tab + 1) == 1
    assert 20 * math.log10(u2f(s.rd(tab + 2))) == pytest.approx(thr, abs=0.2)


@pytest.mark.parametrize('decay', [0.01, 0.1, 1.0])
def test_decay_becomes_a_coefficient_a_sample(decay):
    s, syms = dsp()
    knobs(s, syms, 7, True, -30.0, decay)
    assert u2f(s.rd(syms['G_TAB'] + 3)) == pytest.approx(1 - math.log(1000) / 48000 / decay, rel=1e-6)


def test_each_reader_has_its_own_knobs():
    s, syms = dsp()
    rng = random.Random(5)
    knobs(s, syms, 7, True, -30.0, 0.1)
    knobs(s, syms, 9, False, -30.0, 0.1)
    for _ in range(300):
        a, b = block(s, syms, 7, hiss(rng)), block(s, syms, 9, hiss(rng))
    assert db(a) < -100 and db(b) > -46


def test_a_full_table_takes_new_readers_in_the_first_entry():
    s, syms = dsp()
    for k in range(9):
        knobs(s, syms, 100 + k, True, -30.0, 0.1)
    tab = syms['G_TAB']
    assert [s.rd(tab + 6 * e) for e in range(8)] == [108] + list(range(101, 108))


def test_other_pids_go_to_the_stock_control_function():
    s, syms = dsp()
    for pid in (1, pg.GATE_PID - 1, pg.GATE_PID + 3):
        s.wr(0x6f00, 0)
        ctrl(s, syms, 7, pid, 5)
        assert s.rd(0x6f00) == 0x777
    assert s.rd(syms['G_TAB']) == 0


def test_dsp_sits_under_the_metronome_and_over_the_gr_meter():
    env = {'HX_CLICK': '1', 'HX_FX_GATE': '1', 'HX_GR': '1'}
    dm, pm = block3.place('HX_FX_GATE', env)
    n_dm, n_pm = pg.dsp_size()
    click = block3.place('HX_CLICK', env)[1]
    assert dm + n_dm == pg.nw(pm) and pm + n_pm <= click and pm % 2 == 0
    gr_dm, gr_pm = block3.place('HX_GR', env)
    assert gr_dm < dm and pg.nw(gr_pm) < dm and gr_dm >= block3.room(2)[0]


# ---- the firmware tools/patch_gate.py builds

def stock_l6ia():
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    return pa.load_l6ia_from_any(stock)[0]


@pytest.fixture(scope='module')
def gated():
    data = stock_l6ia()
    return data, pg.patch_gate(pg.patch_dsp(data, **QUIET), **QUIET)


def entries(data):
    e4 = pa.get_entry_swapped(data, 4)
    w4 = struct.unpack('<%dI' % (len(e4) // 4), e4)
    return pa.parse_entry3_full(pa.get_entry_swapped(data, 3)), w4, pa.entry4_blob.blob(w4, 0)


def ldr_blocks(data):
    """Entry 2's INIT blocks before FINAL_INIT: (tag, address, payload words)."""
    e = pa.l6ia.parse(data)[2]
    raw = data[e['payload_off']: e['payload_off'] + e['payload_len']]
    w = struct.unpack('<%dI' % (len(raw) // 4), raw)
    size = {5: lambda c: ((c + 1) & ~1) * 3 // 2, 4: lambda c: c, 3: lambda c: (c + 1) // 2,
            6: lambda c: c * 2, 10: lambda c: c, 9: lambda c: c}
    i, out = 384, []
    while w[i] != 0:
        tag, cnt, addr = w[i:i + 3]
        n = size.get(tag, lambda c: 0)(cnt)
        out.append((tag, addr, tuple(w[i + 3:i + 3 + n])))
        i += 3 + n
    return out


@pytest.mark.firmware
def test_the_reader_enters_the_gate(gated):
    _, new = gated
    dm, pm = pg.dsp_place()
    _, syms = pa.sasm.assemble(pg.dsp_asm(dm, pm), 'fx_gate.asm')
    rec = [b for t, a, b in ldr_blocks(new) if t == 4 and len(b) == 8 and b[0] == pg.READER]
    assert rec[-1][4:6] == (syms['CTRL_2618'], syms['ENTRY_2618'])
    assert any(t == 5 and a == pm for t, a, _ in ldr_blocks(new)) and any(t == 4 and a == dm for t, a, _ in ldr_blocks(new))


@pytest.mark.firmware
@pytest.mark.parametrize('model', pg.MODELS)
def test_models_get_the_three_knobs(gated, model):
    data, new = gated
    old_m = pa.find_model(entries(data)[0], model)
    m = pa.find_model(entries(new)[0], model)
    n = len(old_m['params'])
    assert [p['slot'] for p in m['params']] == list(range(1, n + 4))
    assert [p['name'] for p in m['params'][:n]] == [p['name'] for p in old_m['params']]
    assert [(p['name'], p['displayName'], p['type'], p['min'], p['max'], p['default']) for p in m['params'][n:]] == [
        ('NoiseGate', 'Gate', 1, 0, 0, 0), ('GateThreshold', 'Threshold', 3, -96, 0, -48),
        ('GateDecay', 'Decay', 3, pytest.approx(0.01), 1, pytest.approx(0.1))]
    assert m['params'][n]['meta'] == {'false': 'Off', 'true': 'On', 'displayName': 'Gate', 'displayNameShort': 'Gate'}
    assert m['words'][6] == m['words'][7] == n + 3


@pytest.mark.firmware
@pytest.mark.parametrize('model', pg.MODELS)
def test_knobs_reach_each_reader_as_its_gate_pids(gated, model):
    _, new = gated
    info, w4, b0 = entries(new)
    m = pa.find_model(info, model)
    b = pa.entry4_blob.blob(w4, m['blob_index'])
    po = b[6]
    pm = b[po: po + b[7]]
    nodes = [pm[pm[0] + 10 * k: pm[0] + 10 * k + 10] for k in range(pm[18])]
    edges = [pm[pm[4] + 4 * k: pm[4] + 4 * k + 4] for k in range(pm[20])]
    slots = [pm[pm[6] + 4 * k: pm[6] + 4 * k + 4] for k in range(pm[21])]
    first = len(m['params']) - 2
    ins = [next(s[0] for s in slots if s[2] == first + k) for k in range(3)]
    assert [nodes[k][3] for k in ins] == [0x0d, 0x0a, 0x0a]
    readers = pg.reader_slots(b, b0)
    assert len(readers) == (2 if 'Stereo' in model else 1)
    got = {(b[pm[n[0]] + 1], pm[n[0] + 1], e[0]) for k, n in enumerate(nodes) if n[3] == 1
           for e in edges if e[1] == k and b[pm[n[0]]] == 1 and pm[n[0] + 1] >= pg.GATE_PID}
    assert got == {(r, pg.GATE_PID + k, ins[k]) for r in readers for k in range(3)}
    assert pc.pmap_sizes(pm) == pm[12:18]
    assert not pa.pmap_slots_without_param(pa.get_entry_swapped(new, 4), m['blob_index'], m['params'])


@pytest.mark.firmware
@pytest.mark.parametrize('model', pg.MODELS)
def test_root_defaults_for_the_knobs(gated, model):
    _, new = gated
    info, w4, _ = entries(new)
    m = pa.find_model(info, model)
    b = pa.entry4_blob.blob(w4, m['blob_index'])
    pins = [b[b[10] + 4 * k: b[10] + 4 * k + 4] for k in range(b[11])]
    first = len(m['params']) - 2
    got = {r[1]: b[r[2] + 1] for r in pins if b[r[0]: r[0] + 2] == [1, 0]}
    assert [got[first + k] for k in range(3)] == [f2u(0.0), f2u(-48.0), f2u(0.1)]


@pytest.mark.firmware
def test_blob0_and_the_composites_are_unchanged(gated):
    data, new = gated
    assert entries(data)[2] == entries(new)[2]


def table1(data):
    """{name index: (preset ID, cost)} of an image's Static Model Table (Entry 0 Table 1)."""
    e0 = pa.get_entry_swapped(data, 0)
    segs = pa._parse_e0_segments(e0)
    A = pa.e0_device(segs)
    rd = lambda va, n: e0[pa._e0_vaddr_to_foff(segs, va, n):][:n]
    t1 = struct.unpack('<I', rd(A.TAB1_BASE_PTRS[0], 4))[0]
    _, n1 = pa._decode_thumb_movw(rd(A.TAB1_CNT_INSN, 4))
    rows = [struct.unpack('<IHHI', rd(t1 + 12 * i, 12)) for i in range(n1)]
    return {name: (pid, cost) for name, pid, _, cost in rows}


def ui_counts(data, name_idx):
    """The three parameter counts of a model's UI Model Info Table row (Entry 0 Table 2)."""
    e0 = pa.get_entry_swapped(data, 0)
    segs = pa._parse_e0_segments(e0)
    A = pa.e0_device(segs)
    rd = lambda va, n: e0[pa._e0_vaddr_to_foff(segs, va, n):][:n]
    t2 = struct.unpack('<I', rd(A.TAB2_BASE_PTR, 4))[0]
    _, n2 = pa._decode_thumb_movw(rd(A.TAB2_CNT_INSN, 4))
    row = next(t2 + 44 * i for i in range(n2) if struct.unpack('<I', rd(t2 + 44 * i, 4))[0] == name_idx)
    return struct.unpack('<3I', rd(row + 24, 12))


@pytest.mark.firmware
def test_entry0_counts_and_costs(gated):
    data, new = gated
    t0, t1 = table1(data), table1(new)
    info = entries(data)[0]
    rise = {pa.find_model(info, name)['words'][2]: pg.GATE_COST * (2 if 'Stereo' in name else 1) for name in pg.MODELS}
    assert t1 == {k: (pid, cost + rise.get(k, 0)) for k, (pid, cost) in t0.items()}
    costs = {pid: cost for pid, cost in t1.values()}
    assert (costs[141], costs[232], costs[145], costs[236]) == (160, 161, 213, 226)
    for name in pg.MODELS:
        m = pa.find_model(info, name)
        assert ui_counts(new, m['words'][2]) == (len(m['params']) + 3,) * 3


@pytest.mark.firmware
def test_other_models_and_slot_lists_are_unchanged(gated):
    data, new = gated
    keep = lambda d: [pc.models_view({'models': [m]}) for m in entries(d)[0]['models'] if m['name'] not in pg.MODELS]
    assert keep(data) == keep(new)
    assert pc.slot_lists(pa.get_entry_swapped(data, 3)) == pc.slot_lists(pa.get_entry_swapped(new, 3))


@pytest.mark.firmware
def test_refuses_a_second_run(gated):
    _, new = gated
    with pytest.raises(AssertionError, match='has these knobs already'):
        pg.patch_gate(new, **QUIET)


# ---- with the other model steps, in build.py's order

DEFAULT_E3 = 0xf0d00            # tests/test_gr.py's: amps load [verified on unit]; 0xf3888 drops every amp and preamp


@pytest.mark.firmware
def test_after_the_metronome_and_before_the_gr_knobs():
    added, _ = patch_click.add_click(stock_l6ia(), **QUIET)
    out = pc.patch_comp(pg.patch_gate(added, **QUIET), **QUIET)
    info = entries(out)[0]
    assert pa.find_model(info, patch_click.NAME)
    assert [p['name'] for p in pa.find_model(info, 'HD2_ReturnMono1')['params']][-3:] == [k[0] for k in pg.KNOBS]
    assert [p['name'] for p in pa.find_model(info, pc.COMP_MODELS[0][0])['params']][-3:] == [k[0] for k in pc.GR_KNOBS]
    assert len(pa.get_entry_swapped(out, 3)) <= DEFAULT_E3


GATE_BUILT_MD5 = {
    'HX_FX_GATE': '31bceed929383032fb24b5c80d58d196',
    'HX_FX_GATE HX_GR HX_CLICK HX_REAL_NAMES': '073c695ffa0a2d5ef28274d6c69e715d',      # every DSP and model step, and an Entry 0 renamer
}


@pytest.mark.firmware
@pytest.mark.parametrize('flags', GATE_BUILT_MD5)
def test_gate_build(tmp_path, flags):
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    out = tmp_path / 'gate.hxf'
    env = {k: v for k, v in os.environ.items() if not k.startswith('HX_') or k == 'HX_STOMP_HXF'} | {f: '1' for f in flags.split()}
    r = subprocess.run([sys.executable, str(ROOT / 'build.py'), stock, '-o', str(out), '--no-check'],
                       capture_output=True, text=True, cwd=ROOT, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'ALL OK' in r.stdout
    assert r.stdout.count(': Gate, Threshold, Decay on slots') == len(pg.MODELS)
    assert hashlib.md5(out.read_bytes()).hexdigest() == GATE_BUILT_MD5[flags]
    assert len(pa.get_entry_swapped(pa.load_l6ia_from_any(str(out))[0], 3)) <= DEFAULT_E3


def build_steps(tmp_path, monkeypatch, unit, env):
    """The commands build.py's main() runs for `unit` with `env`, each step stubbed out."""
    spec = importlib.util.spec_from_file_location('hxtra_build', ROOT / 'build.py')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    stock = tmp_path / 'stock.hxf'
    stock.write_bytes(b'not firmware')
    monkeypatch.setattr(build, 'STOCK_MD5', {hashlib.md5(stock.read_bytes()).hexdigest(): unit})
    for k in ('HX_GR', 'HX_CLICK', 'HX_FX_GATE'):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(build.os, 'replace', lambda *a: None)
    monkeypatch.setattr(build.os, 'remove', lambda *a: None)
    monkeypatch.setattr(sys, 'argv', ['build.py', str(stock), '-o', str(tmp_path / 'out.hxf'), '--no-check'])
    ran = []
    monkeypatch.setattr(build, 'run', lambda *a: ran.append(a[1:]) or 'ALL OK')
    build.main()
    return [a[0] for a in ran]


def test_build_runs_the_gate_between_the_metronome_and_the_gr_knobs(tmp_path, monkeypatch):
    ran = build_steps(tmp_path, monkeypatch, 'HX_Stomp', {'HX_CLICK': '1', 'HX_FX_GATE': '1', 'HX_GR': '1'})
    assert ran.index('tools/patch_click.py') < ran.index('tools/patch_gate.py') < ran.index('tools/patch_comp.py')


def test_build_without_the_flag_has_no_gate(tmp_path, monkeypatch):
    assert 'tools/patch_gate.py' not in build_steps(tmp_path, monkeypatch, 'HX_Stomp', {})


def test_web_worker_runs_the_gate_between_the_metronome_and_the_gr_knobs():
    js = (ROOT / 'web/firmware-worker.js').read_text()
    at = lambda s: js.index(s, js.index('step(5,'))
    assert at('"tools/patch_click.py", "build/') < at('"tools/patch_gate.py", "build/') < at('"tools/patch_comp.py", "build/')
    assert 'flags.indexOf("HX_FX_GATE")' in js


# ---- the feature

def test_off_unless_asked_for():
    mods = features.load()
    assert fx_gate.FLAG not in m4cache.web_flags() + m4cache.web_options() and fx_gate.FLAG in m4cache.web_dsp()
    assert fx_gate not in features.enabled(mods, {})
    assert fx_gate in features.enabled(mods, {'HX_FX_GATE': '1'})
    assert not hasattr(fx_gate, 'apply') and not hasattr(fx_gate, 'SETTINGS')


def test_models_are_the_fx_loop_and_return_blocks():
    assert len(pg.MODELS) == 12 and all(('FXLoop' in m or 'Return' in m) for m in pg.MODELS)
    assert pg.KNOBS[0][0] not in [k[0] for k in pc.GR_KNOBS]
