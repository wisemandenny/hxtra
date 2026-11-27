"""Input Sidechain on the Noise Gate block (issue #131): src/sharc/gate_sc.asm in ssim around a stand-in gate core, the knob and
its writers, the Input block's source marks (tools/patch_sidechain.py), its place in Block 3 and the registry, its place among
build.py's steps, and its feature (tools/features/gate_sidechain.py)."""
import hashlib
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest

import block3
import features
import m4cache
import patch_amp as pa
import patch_comp as pc
import patch_gate as pg
import patch_sidechain as sc
import sasm
import ssim
from features import gate_sidechain
from test_gate import DEFAULT_E3, QUIET, build_steps, entries, ldr_blocks, stock_l6ia, table1, ui_counts

ROOT = Path(__file__).resolve().parent.parent
f2u = pg.f2u


# ---- the DSP code, in ssim

CORE, CTRL, JACK, METER = 0x90100, 0x90300, 0x90400, 0x90500    # stand-ins: core, control function, jack reader, meter
MBUF = 0x7200                           # a meter's input at I1
SIG, OUT, SEEN = 0x7000, 0x7100, 0x6f10  # a core's [signal, key] at I1, its I2, where the stand-in notes the I1 it got


def dsp():
    """(sim, symbols) of gate_sc.asm with a stand-in core writing the key it was given (I1 + 16..) to I2, and a stand-in control
    function."""
    src = sc.dsp_asm(0xe7a00, 0xe5200)
    for k, v in (('ORIG', CORE), ('ORIG_CTRL_2720', CTRL), ('ORIG_2A94', JACK), ('ORIG_2390', METER)):
        src, n = re.subn(r'(\.equ %s,\s*)0x[0-9a-fA-F]+' % k, r'\g<1>%#x' % v, src)
        assert n == 1, k
    ret = '    I12 = DM(M7, I6);\n    JUMP (M14, I12) (DB);\n    NOP;\n    RFRAME;'
    assert ret in src
    src = src.replace(ret, '    RTS;')     # the C return needs the caller's frame
    src += f"""
.section dm 0x6f00
FAKE_CTRL: .space 3
.section pm {CORE:#x}
    R3 = I1;
    DM({SEEN:#x}) = R3;
    I4 = I1;
    MODIFY(I4, 16);
    I5 = I2;
    LCNTR = 16, DO fr UNTIL LCE;
      F3 = DM(I4, 1);
fr:   DM(I5, 1) = F3;
    RTS;
.section pm {CTRL:#x}
    R0 = 0x777;
    DM(FAKE_CTRL) = R0;
    RTS;
.section pm {JACK:#x}
    R0 = 0x555;
    DM(FAKE_CTRL + 1) = R0;
    RTS;
.section pm {METER:#x}
    R0 = I1;
    DM(FAKE_CTRL + 2) = R0;
    RTS;
"""
    secs, syms = sasm.assemble(src, 'gate_sc_test')
    s = ssim.Sim()
    s.load(secs)
    return s, syms


def ctrl(s, syms, state, pid, value):
    """The control function as the framework calls it: pid R4, a pointer to the value R8, the state R12 (its first word the core's I0)."""
    s.wr(0x5000, value)
    s.wr(0x6000, state)
    s.u[4], s.u[8], s.u[12], s.u[3] = pid, 0x5000, 0x6000, 0x1234
    s.call(syms['CTRL_2720'])
    assert s.u[3] == 0x1234


def knob(s, syms, state, on):
    ctrl(s, syms, state, sc.SC_PID, f2u(1.0) if on else 0)


def meter(s, syms, samples):
    """One call of the wrapped meter on `samples` at I1."""
    for k, x in enumerate(samples):
        s.wr(MBUF + k, f2u(x))
    s.wr(0x6f02, 0)
    s.u[0x11] = MBUF
    for r in (0, 5, 6, 7):
        s.u[r] = 0x200 + r
    saved = {k: s.u[k] for k in (0x14, 0x15, 0x34, 0x35)}     # I4, I5, L4, L5
    s.call(syms['ENTRY_2390'])
    assert s.rd(0x6f02) == MBUF, 'the stock meter runs on its own I1'
    assert [s.u[r] for r in (5, 6, 7)] == [0x205, 0x206, 0x207] and all(s.u[k] == v for k, v in saved.items())
    assert [s.rd(MBUF + k) for k in range(16)] == [f2u(x) for x in samples], 'its input is left alone'


def input_block(s, syms, left, right):
    """The Input block: its jack readers, then its meters on L and R."""
    jack(s, syms)
    jack(s, syms)
    meter(s, syms, left)
    meter(s, syms, right)


def jack(s, syms):
    """The Input block's jack reader, ahead of its gate."""
    s.wr(0x6f01, 0)
    s.call(syms['ENTRY_2A94'])
    assert s.rd(0x6f01) == 0x555, 'the stock reader runs'


def block(s, syms, state, key):
    """One 16-sample call of the wrapped core with its own key `key` (its signal 0.5): the key the core used."""
    for k in range(16):
        s.wr(SIG + k, f2u(0.5))
        s.wr(SIG + 16 + k, f2u(key[k]))
    s.u[0x10], s.u[0x11], s.u[0x12] = state, SIG, OUT       # I0, I1, I2
    for r in (0, 1, 2):
        s.u[r] = 0x100 + r
    saved = {k: s.u[k] for k in (0x14, 0x15, 0x24, 0x34, 0x35)}     # I4, I5, M4, L4, L5
    s.call(syms['ENTRY_2720'])
    assert [s.u[r] for r in (0, 1, 2)] == [0x100, 0x101, 0x102], 'R0..R2 as called'
    assert all(s.u[k] == v for k, v in saved.items() if k != 0x14 and k != 0x15), 'M4, L4, L5 as called'
    assert s.rd(SEEN) == SIG and s.u[0x11] != 0, 'the core gets its own I1'
    assert [s.rd(SIG + k) for k in range(16)] == [f2u(0.5)] * 16, 'the signal is left alone'
    return [round(struct.unpack('<f', struct.pack('<I', s.rd(OUT + k)))[0], 6) for k in range(16)]


def ramp(a):
    return [a + k / 64 for k in range(16)]


def test_an_untracked_core_is_as_stock():
    s, syms = dsp()
    jack(s, syms)
    assert block(s, syms, 7, ramp(0.1)) == ramp(0.1)
    assert s.rd(syms['SC_SEQ']) == 0 and s.rd(syms['SC_TICK']) == 0


def test_the_input_blocks_meters_capture_half_of_l_plus_r():
    s, syms = dsp()
    input_block(s, syms, ramp(0.2), ramp(0.4))
    cap = [struct.unpack('<f', struct.pack('<I', s.rd(syms['SC_CAP'] + k)))[0] for k in range(16)]
    assert cap == pytest.approx([(a + b) / 2 for a, b in zip(ramp(0.2), ramp(0.4))], rel=1e-6)
    assert s.rd(syms['SC_SEQ']) == 1 and s.rd(syms['SC_ARM']) == 0


def test_an_unarmed_meter_is_as_stock():
    s, syms = dsp()
    meter(s, syms, ramp(0.2))
    assert s.rd(syms['SC_SEQ']) == 0 and s.rd(syms['SC_CAP']) == 0


def test_the_jack_reader_arms_two_meters_only():
    s, syms = dsp()
    input_block(s, syms, ramp(0.2), ramp(0.4))
    meter(s, syms, ramp(0.9))                               # a block's meter later in the path
    assert s.rd(syms['SC_SEQ']) == 1 and abs(s.rd(syms['SC_CAP']) - f2u(0.3)) <= 1


def test_a_sidechained_gate_takes_the_inputs_key():
    s, syms = dsp()
    knob(s, syms, 9, True)
    input_block(s, syms, ramp(0.2), ramp(0.2))
    assert block(s, syms, 9, ramp(0.7)) == ramp(0.2)
    input_block(s, syms, ramp(0.3), ramp(0.1))
    assert block(s, syms, 9, ramp(0.7)) == ramp(0.2)


def test_a_noise_gate_disarms_meters_that_didnt_run():
    s, syms = dsp()
    knob(s, syms, 9, False)
    jack(s, syms)
    block(s, syms, 9, ramp(0.7))
    meter(s, syms, ramp(0.4))
    assert s.rd(syms['SC_SEQ']) == 0 and s.rd(syms['SC_ARM']) == 0


def test_with_the_knob_off_the_gate_keeps_its_own_key():
    s, syms = dsp()
    knob(s, syms, 9, True)
    knob(s, syms, 9, False)
    input_block(s, syms, ramp(0.2), ramp(0.2))
    assert block(s, syms, 9, ramp(0.7)) == ramp(0.7)


def test_without_a_fresh_capture_the_gate_keeps_its_own_key():
    s, syms = dsp()
    knob(s, syms, 9, True)
    assert block(s, syms, 9, ramp(0.7)) == ramp(0.7)        # no Input block has run
    input_block(s, syms, ramp(0.2), ramp(0.2))
    assert block(s, syms, 9, ramp(0.7)) == ramp(0.2)
    assert block(s, syms, 9, ramp(0.6)) == ramp(0.6)        # the Input block stopped


def test_the_stereo_gates_two_cores_both_take_it():
    s, syms = dsp()
    knob(s, syms, 9, True)
    knob(s, syms, 10, True)
    input_block(s, syms, ramp(0.2), ramp(0.2))
    assert block(s, syms, 9, ramp(0.7)) == block(s, syms, 10, ramp(0.6)) == ramp(0.2)


def test_knob_writes_keep_one_entry_a_core():
    s, syms = dsp()
    for on in (True, False, True):
        knob(s, syms, 9, on)
    tab = syms['SC_TAB']
    assert [s.rd(tab + 4 * e) for e in range(sc_n(syms))].count(9) == 1 and s.rd(tab + 1) == 1


def sc_n(syms):
    return (syms['SC_END'] - syms['SC_TAB']) // 4


def test_a_full_table_reuses_the_core_idle_longest():
    s, syms = dsp()
    n = sc_n(syms)
    assert n == 16
    for k in range(n):
        knob(s, syms, 100 + k, False)
    for _ in range(3):
        for k in range(n):
            if k != 5:
                block(s, syms, 100 + k, ramp(0.1))         # 105 is a block of a preset no longer loaded
    knob(s, syms, 200, True)
    tab = syms['SC_TAB']
    assert [s.rd(tab + 4 * e) for e in range(n)] == [100 + k if k != 5 else 200 for k in range(n)]


def test_other_pids_go_to_the_stock_control_function():
    s, syms = dsp()
    for pid in (0, 1, 3, sc.SC_PID - 1, sc.SC_PID + 1):
        s.wr(0x6f00, 0)
        ctrl(s, syms, 7, pid, 5)
        assert s.rd(0x6f00) == 0x777
    assert s.rd(syms['SC_TAB']) == 0


def test_mode1_is_restored_before_the_core():
    s, syms = dsp()
    knob(s, syms, 9, True)
    s.u[ssim.U_MODE1] = 0x400000                            # BDCST9, which the wrapper clears while it runs
    input_block(s, syms, ramp(0.2), ramp(0.2))
    assert s.u[ssim.U_MODE1] == 0x400000
    block(s, syms, 9, ramp(0.7))
    assert s.u[ssim.U_MODE1] == 0x400000


def test_dsp_sits_at_the_bottom_of_the_room():
    env = {'HX_CLICK': '1', 'HX_FX_GATE': '1', 'HX_GR': '1', 'HX_USB_MONITOR': '1', 'HX_GATE_SC': '1'}   # the MIDI block off
    dm, pm = block3.place('HX_GATE_SC', env)
    n_dm, n_pm = sc.dsp_size()
    assert dm + n_dm == pg.nw(pm) and pm % 2 == 0
    usb_dm, _ = block3.place('HX_USB_MONITOR', env)
    assert pg.nw(pm + n_pm) <= usb_dm and dm >= block3.room(2)[0]
    after = block3.FEATURES[block3.FEATURES.index(('HX_GATE_SC', 'patch_sidechain')) + 1:]
    assert [f for f, _ in after] == ['HX_MIDI_BLOCK', 'HX_PHONES_BLOCK'], 'only the added blocks below it'


# ---- the firmware tools/patch_sidechain.py builds

@pytest.fixture(scope='module')
def sided():
    data = stock_l6ia()
    return data, sc.patch_sidechain(sc.patch_dsp(data, **QUIET), **QUIET)


def pmap(b):
    """(parameter map, its nodes, its links, its slot rows) of a model blob."""
    pm = b[b[6]: b[6] + b[7]]
    return (pm, [pm[pm[0] + 10 * k: pm[0] + 10 * k + 10] for k in range(pm[18])],
            [pm[pm[4] + 4 * k: pm[4] + 4 * k + 4] for k in range(pm[20])],
            [pm[pm[6] + 4 * k: pm[6] + 4 * k + 4] for k in range(pm[21])])


def writes(b, pid):
    """{(path, pid, source node)} of the blob's writers of pids from `pid` up."""
    pm, nodes, links, _ = pmap(b)
    path = lambda off: tuple(b[off + 1: off + 1 + b[off]])
    return {(path(pm[n[0]]), pm[n[0] + 1], e[0]) for k, n in enumerate(nodes) if n[3] == 1
            for e in links if e[1] == k and pm[n[0] + 1] >= pid}


@pytest.mark.firmware
def test_the_core_enters_the_wrapper(sided):
    _, new = sided
    dm, pm = sc.dsp_place()
    _, syms = pa.sasm.assemble(sc.dsp_asm(dm, pm), 'gate_sc.asm')
    rec = [b for t, a, b in ldr_blocks(new) if t == 4 and len(b) == 8 and b[0] == sc.CORE]
    assert rec[-1][4:6] == (syms['CTRL_2720'], syms['ENTRY_2720'])
    jack = [b for t, a, b in ldr_blocks(new) if t == 4 and len(b) == 8 and b[0] == sc.JACK]
    assert jack[-1][5] == syms['ENTRY_2A94'] and jack[-1][4] == 0x60a5b9, 'the jack reader\'s control function stays stock'
    meter = [b for t, a, b in ldr_blocks(new) if t == 4 and len(b) == 8 and b[0] == sc.METER]
    assert meter[-1][5] == syms['ENTRY_2390'] and meter[-1][4] == 0x610441, 'the meter\'s control function stays stock'
    assert any(t == 5 and a == pm for t, a, _ in ldr_blocks(new)) and any(t in (1, 4) and a == dm for t, a, _ in ldr_blocks(new))


@pytest.mark.firmware
@pytest.mark.parametrize('model', sc.MODELS)
def test_noise_gates_get_input_sidechain(sided, model):
    data, new = sided
    old_m = pa.find_model(entries(data)[0], model)
    m = pa.find_model(entries(new)[0], model)
    n = len(old_m['params'])
    assert [p['slot'] for p in m['params']] == list(range(1, n + 2))
    assert [p['name'] for p in m['params'][:n]] == [p['name'] for p in old_m['params']]
    p = m['params'][n]
    assert (p['name'], p['type'], p['min'], p['max'], p['default']) == ('InputSidechain', 1, 0, 0, 0)
    assert p['meta'] == {'false': 'Off', 'true': 'On', 'displayName': 'Input Sidechain', 'displayNameShort': 'Input SC'}
    assert len(p['meta']['displayNameShort']) <= 8
    assert m['words'][6] == m['words'][7] == n + 1


@pytest.mark.firmware
@pytest.mark.parametrize('model', sc.MODELS)
def test_the_knob_reaches_each_core(sided, model):
    _, new = sided
    info, w4, b0 = entries(new)
    m = pa.find_model(info, model)
    b = pa.entry4_blob.blob(w4, m['blob_index'])
    pm, nodes, _, slots = pmap(b)
    node = next(s[0] for s in slots if s[2] == len(m['params']))
    assert nodes[node][3] == 0x0d
    cores = sc.core_slots(b0, pa.entry4_blob.top_type(b))
    assert cores == ([3, 7] if 'Stereo' in model else [3])
    assert writes(b, sc.SC_PID) == {((c,), sc.SC_PID, node) for c in cores}
    pins = [b[b[10] + 4 * k: b[10] + 4 * k + 4] for k in range(b[11])]
    assert {r[1]: b[r[2] + 1] for r in pins if b[r[0]: r[0] + 2] == [1, 0]}[len(m['params'])] == 0
    assert pc.pmap_sizes(pm) == pm[12:18]
    assert not pa.pmap_slots_without_param(pa.get_entry_swapped(new, 4), m['blob_index'], m['params'])


@pytest.mark.firmware
def test_the_jack_reader_and_meters_lead_the_input_blocks_gate(sided):
    data, _ = sided
    _, w4, b0 = entries(data)
    users = {c for c in range(0x600000, 0x600000 + b0[0xf])
             if any(m['type_id'] == sc.JACK for m in pa.entry4_blob.parse_composite(b0, c)['members'])}
    assert users == {0x600000, 0x600010}, 'the Input blocks of the HX Stomp and HX Effects'
    members = [m['type_id'] for m in pa.entry4_blob.parse_composite(b0, 0x600000)['members']]
    gate = members.index(0x600014)
    assert [k for k, t in enumerate(members) if t == sc.JACK] == [0, 13] and gate > 13
    meters = [k for k, t in enumerate(members) if t == sc.METER]
    assert meters == [34, 37], 'the first two meters after the jack readers, ahead of the gate'
    comp = pa.entry4_blob.parse_composite(b0, 0x600000)['members']
    assert [b0[comp[k]['in_off']] for k in meters] == [0, 1] and b0[comp[gate]['in_off']: comp[gate]['in_off'] + 2] == [0, 1]


@pytest.mark.firmware
def test_blob0_and_blob1_are_unchanged(sided):
    data, new = sided
    old, now = entries(data)[1], entries(new)[1]
    assert pa.entry4_blob.blob(old, 0) == pa.entry4_blob.blob(now, 0)
    assert pa.entry4_blob.blob(old, 1) == pa.entry4_blob.blob(now, 1), 'blob 1 (HelixStomp_App) never changes'


@pytest.mark.firmware
def test_entry0_counts_and_costs(sided):
    data, new = sided
    t0, t1 = table1(data), table1(new)
    info = entries(data)[0]
    rise = {pa.find_model(info, name)['words'][2]: sc.SC_COST * (2 if 'Stereo' in name else 1) for name in sc.MODELS}
    assert t1 == {k: (pid, cost + rise.get(k, 0)) for k, (pid, cost) in t0.items()}
    for name in sc.MODELS:
        m = pa.find_model(info, name)
        assert ui_counts(new, m['words'][2]) == (len(m['params']) + 1,) * 3


@pytest.mark.firmware
def test_other_models_and_slot_lists_are_unchanged(sided):
    data, new = sided
    keep = lambda d: [pc.models_view({'models': [m]}) for m in entries(d)[0]['models'] if m['name'] not in sc.MODELS]
    assert keep(data) == keep(new)
    assert pc.slot_lists(pa.get_entry_swapped(data, 3)) == pc.slot_lists(pa.get_entry_swapped(new, 3))
    w_old, w_new = entries(data)[1], entries(new)[1]
    touched = {pa.find_model(entries(data)[0], n)['blob_index'] for n in sc.MODELS}
    n = len(pa.entry4_blob.directory(w_old))
    assert [pa.entry4_blob.blob(w_old, k) for k in range(n) if k not in touched] == \
           [pa.entry4_blob.blob(w_new, k) for k in range(n) if k not in touched]


@pytest.mark.firmware
def test_refuses_a_second_run(sided):
    _, new = sided
    with pytest.raises(AssertionError, match='has these knobs already'):
        sc.patch_sidechain(new, **QUIET)


# ---- with the other model steps, in build.py's order

@pytest.mark.firmware
def test_after_the_fx_gate_and_before_the_gr_knobs():
    import patch_click
    added, _ = patch_click.add_click(stock_l6ia(), **QUIET)
    out = pc.patch_comp(sc.patch_sidechain(pg.patch_gate(added, **QUIET), **QUIET), **QUIET)
    info = entries(out)[0]
    assert [p['name'] for p in pa.find_model(info, 'HD2_ReturnMono1')['params']][-3:] == [k[0] for k in pg.KNOBS]
    assert [p['name'] for p in pa.find_model(info, sc.MODELS[1])['params']][-1] == sc.KNOB
    assert [p['name'] for p in pa.find_model(info, pc.COMP_MODELS[0][0])['params']][-3:] == [k[0] for k in pc.GR_KNOBS]
    assert len(pa.get_entry_swapped(out, 3)) <= DEFAULT_E3


SC_BUILT_MD5 = {
    'HX_GATE_SC': 'd77b54023ee0732a8cd56052c962523a',
    'HX_GATE_SC HX_FX_GATE HX_GR HX_CLICK HX_USB_MONITOR HX_REAL_NAMES': '77478700bf513954da8fb726dd8318de',  # every DSP step
}


@pytest.mark.firmware
@pytest.mark.parametrize('flags', SC_BUILT_MD5)
def test_sidechain_build(tmp_path, flags):
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    out = tmp_path / 'sc.hxf'
    env = {k: v for k, v in os.environ.items() if not k.startswith('HX_') or k == 'HX_STOMP_HXF'} | {f: '1' for f in flags.split()}
    r = subprocess.run([sys.executable, str(ROOT / 'build.py'), stock, '-o', str(out), '--no-check'],
                       capture_output=True, text=True, cwd=ROOT, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'ALL OK' in r.stdout
    assert r.stdout.count(': Input Sidechain on slot') == len(sc.MODELS)
    assert hashlib.md5(out.read_bytes()).hexdigest() == SC_BUILT_MD5[flags]
    assert len(pa.get_entry_swapped(pa.load_l6ia_from_any(str(out))[0], 3)) <= DEFAULT_E3


def test_build_runs_it_after_the_fx_gate_and_before_the_gr_knobs(tmp_path, monkeypatch):
    monkeypatch.delenv('HX_GATE_SC', raising=False)
    ran = build_steps(tmp_path, monkeypatch, 'HX_Stomp', {'HX_FX_GATE': '1', 'HX_GATE_SC': '1', 'HX_GR': '1'})
    assert ran.index('tools/patch_gate.py') < ran.index('tools/patch_sidechain.py') < ran.index('tools/patch_comp.py')


def test_build_without_the_flag_has_no_sidechain(tmp_path, monkeypatch):
    monkeypatch.delenv('HX_GATE_SC', raising=False)
    assert 'tools/patch_sidechain.py' not in build_steps(tmp_path, monkeypatch, 'HX_Stomp', {})


def test_web_worker_runs_it_after_the_fx_gate_and_before_the_gr_knobs():
    js = (ROOT / 'web/firmware-worker.js').read_text()
    at = lambda s: js.index(s, js.index('step(5,'))
    assert at('"tools/patch_gate.py", "build/') < at('"tools/patch_sidechain.py", "build/') < at('"tools/patch_comp.py", "build/')
    assert 'flags.indexOf("HX_GATE_SC")' in js
    for f in ('tools/patch_sidechain.py', 'tools/features/gate_sidechain.py', 'src/sharc/gate_sc.asm'):
        assert f'"{f}"' in js


# ---- the feature

def test_off_unless_asked_for():
    mods = features.load()
    assert gate_sidechain.FLAG not in m4cache.web_flags() + m4cache.web_options() and gate_sidechain.FLAG in m4cache.web_dsp()
    assert gate_sidechain not in features.enabled(mods, {})
    assert gate_sidechain in features.enabled(mods, {'HX_GATE_SC': '1'})
    assert not hasattr(gate_sidechain, 'apply') and not hasattr(gate_sidechain, 'SETTINGS')
