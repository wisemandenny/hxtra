#!/usr/bin/env python3
"""patch_gate.py - a noise gate built into the FX Loop and Return blocks (issue #69), as the Input block has one.

usage: patch_gate.py <in .hxf | L6IA> <out .hxf | L6IA> [--donor stock.hxf]

Each model in MODELS gets the knobs Gate (Off by default), Threshold and Decay after its own, and src/sharc/fx_gate.asm gates what
its return reader (primitive 0x2618) brings in, before the block's Return level and Mix; the dry signal and the Send are not gated.
Stereo models gate each side on its own. A new member in a block's composite gets no knob writes unless it is bound, and binding one
stops the block (docs/research/sharc/cores/gates.md), so the gate is a wrapper around the reader the blocks already have:
  Entry 2: fx_gate.asm in Block 3 where tools/block3.py places it (dsp_place), and primitive 0x2618's process and control
           functions entering it.
  Entry 4: each model's blob gets one input node per knob, a root default for each, and writers handing them to each of its
           readers as pids GATE_PID.., which the wrapper's control function keeps.
  Entry 3: the knobs' parameter and state records, copied from the Input block's noiseGate, threshold and decay.
  Entry 0: each model's UI Model Info Table row counts the knobs, and its Static Model Table cost rises by GATE_COST a reader.
Run it after every step that adds models (add-model, add-fx-model, patch_click.py), which rebuild Entry 3's and Entry 4's tails,
and before tools/patch_comp.py.
"""
import os
import struct

import patch_amp as pa
import nam_multi
import patch_comp as pc

ASM = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'sharc', 'fx_gate.asm')
INPUT_MODEL = 'HelixStomp_AppDSPFlowInput'
# (name, the Input block's parameter it copies, displayName): Gate's displayName is 'Input Gate' there
KNOBS = (('NoiseGate', 'noiseGate', 'Gate'), ('GateThreshold', 'threshold', None), ('GateDecay', 'decay', None))
INPUT_OP = {1: 0x0d, 3: 0x0a}       # parameter type (bool, float) -> parameter-map input node op
READER, ORIG, ORIG_CTRL = 0x2618, 0x8d872, 0x60f99a     # the return reader, its stock process code and control function
GATE_PID = 100                      # fx_gate.asm's: Gate, Threshold, Decay as pids 100..102, past the reader's own pid 1
MODELS = tuple(f'HD2_{kind}Mono{k}' for kind in ('FXLoop', 'Return') for k in range(1, 5)) + \
         tuple(f'HD2_{kind}Stereo{k}' for kind in ('FXLoop', 'Return') for k in ('1_2', '3_4'))
GATE_COST = 20                      # a reader: ~260 cycles a 16-sample block, 0.2% of the DSP [hypothesis: not measured]


def f2u(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def nw(pm):
    """The normal-word address of Block 3's 48-bit address pm (even)."""
    return nam_multi.NW3 + (pm - nam_multi.NW3) * 3 // 2


def dsp_asm(dm, pm):
    """fx_gate.asm with its data at dm and its code at pm."""
    return open(ASM).read().replace('GATE_DM_BASE', f'{dm:#x}').replace('GATE_PM_BASE', f'{pm:#x}')


def dsp_size():
    """(data words, instructions) of fx_gate.asm."""
    secs, _ = pa.sasm.assemble(dsp_asm(nam_multi.B3, nam_multi.NW3), 'fx_gate.asm')
    return tuple(sum(len(s.words) for s in secs if s.kind == k) for k in ('dm', 'pm'))


def patch_dsp(l6ia_bytes, placement, log=print):
    """Entry 2: fx_gate.asm at dsp_place(), and the reader's process and control functions entering it."""
    dm, pm = placement
    secs, syms = pa.sasm.assemble(dsp_asm(dm, pm), 'fx_gate.asm')
    entries = pa.l6ia.parse(l6ia_bytes)
    e2 = l6ia_bytes[entries[2]['payload_off']: entries[2]['payload_off'] + entries[2]['payload_len']]
    ldr = []
    for sec in secs:
        ldr += (pa.pack_init_l48 if sec.kind == 'pm' else pa.pack_init_l32)(sec.addr, sec.words)
        log(f"[+] Entry 2: gate {len(sec.words)} {'instructions' if sec.kind == 'pm' else 'words'} @ {sec.kind.upper()} {sec.addr:#x}")
    ldr += pa.wrap_primitive(e2, f'{READER:#x}:{ORIG:#x}', syms['ENTRY_2618'], (ORIG_CTRL, syms['CTRL_2618']))
    new, _, _ = pa.l6ia.rebuild_archive(l6ia_bytes, {2: pa.l6ia.swap32(pa.inject_sharc_ldr_blocks(e2, ldr))})
    return new


def reader_slots(b, b0):
    """The node-tree slots of the members of the blob's composite running the reader."""
    members = pa.entry4_blob.parse_composite(b0, pa.entry4_blob.top_type(b))['members']
    return [k + 1 for k, m in enumerate(members) if m['type_id'] == READER]


def blob_add_gate(b, first_slot, readers, defaults, pid=GATE_PID):
    """A model blob with an input node per knob (slots first_slot..) and a root default for each, each feeding a writer per reader
    slot of `readers` that hands its value to that reader as pid + k. Laid out as patch_comp.blob_add_knobs does: the
    parameter map, init records and relocation list are rebuilt after the node tree, nothing before the parameter map moves."""
    assert b[0] == 3 and b[6] < b[10] < b[4] < b[8] and b[8] + 2 * b[9] == len(b), 'unexpected blob layout'
    po, pl, pin, npin, ini, nini, sub, nsub = b[6], b[7], b[10], b[11], b[4], b[5], b[8], b[9]
    pm = list(b[po: po + pl])
    assert pc.pmap_sizes(pm) == pm[12:18], 'the parameter map\'s sizes do not follow its tables'
    a, c, d, e = pm[0], pm[4], pm[6], pm[8]
    nA, nC, nD, nE = pm[18], pm[20], pm[21], pm[22]
    nodes = [pm[a + 10 * k: a + 10 * k + 10] for k in range(nA)]
    ct = [pm[c + 4 * k: c + 4 * k + 4] for k in range(nC)]
    dt = [pm[d + 4 * k: d + 4 * k + 4] for k in range(nD)]
    et = [pm[e + 4 * k: e + 4 * k + 4] for k in range(nE)]
    assert sorted(r[2] for r in dt) == list(range(1, first_slot)), 'slot map is not slots 1..n'
    pins = [b[pin + 4 * k: pin + 4 * k + 4] for k in range(npin)]
    root = {r[0] for r in pins if r[3] == 1 and b[r[0]: r[0] + 2] == [1, 0]}
    assert len(root) == 1, 'no single root path among the init records'
    root = root.pop()
    paths = []
    for s in readers:                   # each reader's path, as its init records (its jack) name it
        found = {r[0] for r in pins if b[r[0]: r[0] + 2] == [1, s]}
        assert len(found) == 1, f'no single path to the reader at slot {s}'
        paths.append(found.pop())
    n = len(defaults)
    for k, (_, _, _, typ) in enumerate(defaults):
        nodes.append([nodes[0][0], 0, nA + k, INPUT_OP[typ], 1, 2, 0, 0, 1, 0])
        dt.append([nA + k, nE + k, first_slot + k, 0])
        et.append([nA + k, nE + k, nE + k, 0])
    writers = []                        # where each writer's path word is in the parameter map, for the relocation list
    for p in paths:
        for k in range(n):
            writers.append(len(pm))
            nodes.append([len(pm), 0, len(nodes), 1, 0, 3, 3, 3, 0, 0])
            pm += [p, pid + k, 1]
            ct.append([nA + k, len(nodes) - 1, 0, 0])
    pm[0] = len(pm)
    pm += [w for nd in nodes for w in nd]
    pm[4] = len(pm)
    pm += [w for r in ct for w in r]
    pm[6] = len(pm)
    pm += [w for r in dt for w in r]
    pm[8] = len(pm)
    pm += [w for r in et for w in r]
    pm[18], pm[20], pm[21], pm[22] = len(nodes), len(ct), len(dt), len(et)
    pm[12:18] = pc.pmap_sizes(pm)

    out = list(b[:po])
    new_po = len(out)
    out += pm
    new_pin = len(out)
    vals = new_pin + 4 * (npin + n) + 2 * (nini + len(writers) + n) + 2 * nsub
    for r in pins:
        out += r
    for k in range(n):
        out += [root, first_slot + k, vals + 2 * k, 1]
    new_ini = len(out)
    for k in range(nini):
        t, off = b[ini + 2 * k: ini + 2 * k + 2]
        if po <= off < po + pl:
            off += new_po - po
        elif pin <= off < pin + 4 * npin:
            off += new_pin - pin
        else:
            assert off < po, f'relocation at {off:#x} is in no table this moves'
        out += [t, off]
    for w in writers:
        out += [1, new_po + w]
    for k in range(n):
        out += [1, new_pin + 4 * (npin + k)]
    new_sub = len(out)
    out += b[sub: sub + 2 * nsub]
    assert all(w < po for w in b[sub: sub + 2 * nsub]), 'a sub-binding points past the node tree'
    assert len(out) == vals
    for _, _, dflt, _ in defaults:
        out += [1, f2u(dflt)]
    out[4], out[5], out[6], out[7] = new_ini, nini + len(writers) + n, new_po, len(pm)
    out[8], out[10], out[11] = new_sub, new_pin, npin + n
    return out


def knob_records(info):
    """(name, displayName or None, the Input block's parameter record) of each knob."""
    src = {p['name']: p for p in pa.find_model(info, INPUT_MODEL)['params']}
    return [(name, disp, src[base]) for name, base, disp in KNOBS]


def e3_add_gate(e3, model_name, S, knobs):
    """Entry 3 with KNOBS appended to the model's parameters and states. Returns (Entry 3, first new slot, old count)."""
    e3 = bytearray(e3)
    info = pa.parse_entry3_full(bytes(e3))
    m = pa.find_model(info, model_name)
    assert m['name'] == model_name
    d = list(m['words'])
    n_par, n_st = d[7], d[6]
    assert n_par == n_st and all(p['slot'] == k + 1 for k, p in enumerate(m['params'])), \
        f'{model_name}: parameters and states are not one per slot 1..{n_par}'
    assert not {p['name'] for p in m['params']} & {k[0] for k in knobs}, f'{model_name} has these knobs already'
    base = pa._align(len(e3), 4)
    e3 += bytes(base - len(e3))
    tail, params, states = bytearray(), [], []
    for k, (name, disp, src) in enumerate(knobs):
        meta = [(key, disp if key == 'displayName' and disp else val) for key, val in src['meta'].items()]
        pm_off = base + len(tail)
        tail += b''.join(struct.pack('<3I', S[key], 7, S[val]) for key, val in meta)
        params.append(struct.pack('<5I3f', len(meta), pm_off, S[name], src['type'], n_par + 1 + k,
                                  src['min'], src['max'], src['default']))
        states.append(struct.pack('<5I', 0, 0x80b98, S[name + 'State'], src['type'], n_st + k))
    d[10] = base + len(tail)
    tail += bytes(e3[m['words'][10]: m['words'][10] + 20 * n_st]) + b''.join(states)
    d[11] = base + len(tail)
    tail += bytes(e3[m['words'][11]: m['words'][11] + 32 * n_par]) + b''.join(params)
    d[6], d[7] = n_st + len(knobs), n_par + len(knobs)
    e3 += tail
    struct.pack_into('<14I', e3, m['off'], *d)
    struct.pack_into('<I', e3, 8, len(e3))
    if len(e3) > pa.E3_MAX:
        raise SystemExit(f'Entry 3 would be {len(e3):#x} bytes; its partition holds {pa.E3_MAX:#x}')
    return bytes(e3), n_par + 1, n_par


def e0_add_cost(e0, name_idx, cost):
    """Entry 0 with the model's Static Model Table (Table 1) cost raised by cost. Returns (Entry 0, old cost)."""
    e0 = bytearray(e0)
    segs = pa._parse_e0_segments(e0)
    A = pa.e0_device(segs)
    fo = lambda va, ln=4: pa._e0_vaddr_to_foff(segs, va, ln)
    t1 = struct.unpack_from('<I', e0, fo(A.TAB1_BASE_PTRS[0]))[0]
    _, cnt = pa._decode_thumb_movw(e0[fo(A.TAB1_CNT_INSN): fo(A.TAB1_CNT_INSN) + 4])
    rows = [t1 + 12 * i for i in range(cnt) if struct.unpack_from('<I', e0, fo(t1 + 12 * i))[0] == name_idx]
    assert len(rows) == 1, f'{len(rows)} rows for string {name_idx} in the Static Model Table'
    r = fo(rows[0] + 8)
    old = struct.unpack_from('<I', e0, r)[0]
    struct.pack_into('<I', e0, r, old + cost)
    return bytes(e0), old


def patch_gate(l6ia_bytes, models=MODELS, log=print):
    e0 = pa.get_entry_swapped(l6ia_bytes, 0)
    e3 = pa.get_entry_swapped(l6ia_bytes, 3)
    e4 = pa.get_entry_swapped(l6ia_bytes, 4)
    before, before_e3 = pa.parse_entry3_full(e3), e3
    knobs = knob_records(before)
    wanted = [k[0] for k in knobs] + [k[0] + 'State' for k in knobs] + [d for _, d, _ in knobs if d] + \
             [s for _, _, src in knobs for kv in src['meta'].items() for s in kv]
    e3, S = pc.e3_add_strings(e3, wanted)
    assert pc.models_view(before) == pc.models_view(pa.parse_entry3_full(e3)), 'the string section move changed a model'
    assert pc.slot_lists(before_e3) == pc.slot_lists(e3), 'the string section move changed a slot list'
    defaults = [(name, disp, src['default'], src['type']) for name, disp, src in knobs]
    for name in models:
        m = pa.find_model(pa.parse_entry3_full(e3), name)
        w4 = struct.unpack('<%dI' % (len(e4) // 4), e4)
        b = pa.entry4_blob.blob(w4, m['blob_index'])
        readers = reader_slots(b, pa.entry4_blob.blob(w4, 0))
        e3, first, old = e3_add_gate(e3, name, S, knobs)
        e4 = pc.e4_replace_blob(e4, m['blob_index'], blob_add_gate(b, first, readers, defaults))
        e0 = pc.e0_set_param_counts(e0, m['words'][2], old, old + len(KNOBS))
        e0, cost = e0_add_cost(e0, m['words'][2], GATE_COST * len(readers))
        chk = pa.parse_entry3_full(e3)['models'][m['idx']]
        assert [p['slot'] for p in chk['params']] == list(range(1, old + 1 + len(KNOBS)))
        assert not pa.pmap_slots_without_param(e4, m['blob_index'], chk['params'])
        log(f"[+] {name}: Gate, Threshold, Decay on slots {first}..{first + len(KNOBS) - 1} to {len(readers)} reader(s), "
            f"DSP cost {cost} -> {cost + GATE_COST * len(readers)}")
    new, _, _ = pa.l6ia.rebuild_archive(l6ia_bytes, {0: e0, 3: e3, 4: e4})
    return new
