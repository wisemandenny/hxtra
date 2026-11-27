#!/usr/bin/env python3
"""pmap - a model's knobs traced through its parameter map to the primitives they set.

For each model: its Entry 3 parameters, its signal chain (composite members in order, the
node tree's overrides applied, init values with the blob's init records over the composite's)
and, per writer, the expression that feeds it, back to the knobs. Nested maps (table F, one
row per node-tree child, in tree order, filled for composites) are followed: a writer to a composite's path with
pid k feeds slot k of that member's map. Layout and ops: docs/research/sharc/model-blobs.md.

    python3 tools/sharc/pmap.py [--hxf F] MODEL...            text, MODEL = name or display name
    python3 tools/sharc/pmap.py [--hxf F] --category distortion,eq [--sub mono] --json OUT
    python3 tools/sharc/pmap.py [--hxf F] --sweep MODEL...    values each knob gives its writers
"""
import argparse
import json
import math
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [p for p in (_HERE, os.path.dirname(_HERE)) if p not in sys.path]

import entry4_blob as e4  # noqa: E402
import kit_patch_amp as kp  # noqa: E402


def fl(v):
    return struct.unpack('<f', struct.pack('<I', v))[0]


def fv(v):
    """A word as a float when it looks like one, else the integer."""
    x = fl(v)
    if 1e-6 <= abs(x) < 1e8:
        return round(x, 6)
    return float(f"{x:.6g}") if 1e-7 <= abs(x) < 1e-6 else v     # float32(±1e-6) is ±9.99999997e-07


class Firmware:
    def __init__(self, path):
        l6, _ = kp.load_l6ia_from_any(path)
        self.e3 = kp.parse_entry3_full(kp.get_entry_swapped(l6, 3))
        e = kp.get_entry_swapped(l6, 4)
        self.w4 = struct.unpack('<%dI' % (len(e) // 4), e)
        self.b0 = e4.blob(self.w4, 0)

    def blob(self, i):
        return e4.blob(self.w4, i)

    def comp(self, cid):
        return e4.parse_composite(self.b0, cid)


def path_at(b, off):
    """A path in a model blob: its length, then one slot per level."""
    return tuple(b[off + 1: off + 1 + b[off]])


def parse_map(b, base):
    """The map whose 24-word header is at pm offset `base` (offsets are pm-relative,
    nested maps included). Header: offsets of tables A..F at words 0, 2, .., 10,
    sizes at 12..17, counts nA..nF at 18..23."""
    po = b[6]
    pm = b[po: po + b[7]]
    h = pm[base: base + 24]
    oA, oB, oC, oD, oF = h[0], h[2], h[4], h[6], h[10]
    nA, nB, nC, nD, _, nF = h[18:24]
    nodes = []
    for k in range(nA):
        n = pm[oA + 10 * k: oA + 10 * k + 10]     # {data_off, 0, id, op, n_out, state, dlen, dlen, is_input, 0}
        nd = {'id': n[2], 'op': n[3], 'state': n[5], 'dlen': n[6], 'input': n[8]}
        if n[3] == 1:                               # writer data {path, pid, kind}: 1 a parameter, 0 a switch
            nd['path'], nd['pid'], nd['kind'] = path_at(b, pm[n[0]]), pm[n[0] + 1], pm[n[0] + 2]
        elif n[6]:
            nd['data'] = [fv(x) for x in pm[n[0]: n[0] + n[6]]]
        nodes.append(nd)
    tables = {}
    for k in range(nB):                             # B: {data_off, 0, node id, 0, count, 0}
        r = pm[oB + 6 * k: oB + 6 * k + 6]
        tables[r[2]] = [fv(x) for x in pm[r[0]: r[0] + r[4]]]
    for nd in nodes:
        if nd['id'] in tables:
            nd['table'] = tables[nd['id']]
    return {'nodes': {n['id']: n for n in nodes},
            'edges': [tuple(pm[oC + 4 * k: oC + 4 * k + 4]) for k in range(nC)],   # {src, dst, src port, dst port}
            'slots': {pm[oD + 4 * k + 2]: pm[oD + 4 * k] for k in range(nD)},       # D: slot -> input node
            'F': [list(pm[oF + 8 * k: oF + 8 * k + 8]) for k in range(nF)]}


def init_records(b):
    """The blob's init records of parameters: path -> {pid: value} (word 3 = 2, a composite's switch, left out)."""
    out = {}
    for k in range(b[11]):
        soff, pid, voff, kind = b[b[10] + 4 * k: b[10] + 4 * k + 4]
        if kind != 2:
            out.setdefault(path_at(b, soff), {})[pid] = fv(b[voff + 1])
    return out


def node_tree(b):
    """path -> overriding type id (None where the node keeps the composite's member)."""
    out = {}

    def walk(o, prefix, top, seen):
        if o in seen or o + 4 > len(b):
            raise ValueError(f'node tree: bad node offset {o:#x}')
        slot, t, co, cc = b[o: o + 4]
        p = prefix if top else prefix + (slot,)
        out[p] = None if t == 0xffffffff else t
        for j in range(cc):
            walk(co + 4 * j, p, False, seen | {o})
    walk(b[2], (), True, frozenset())
    return out


def is_comp(t):
    return 0x600000 <= t < 0x601000


def model_report(fw, m):
    b = fw.blob(m['blob_index'])
    try:
        nt = node_tree(b)
    except ValueError as e:
        raise ValueError(f"{m['name']}: blob {m['blob_index']} is not a model blob ({e})") from None
    root = nt[()]
    if root is None or not is_comp(root):
        raise ValueError(f"{m['name']}: blob {m['blob_index']} is not a model blob (root {root})")
    inits = init_records(b)
    params = {p['slot']: p for p in m['params']}

    def member_type(path):
        t = root
        for i, s in enumerate(path):
            t = nt.get(tuple(path[:i + 1])) or fw.comp(t)['members'][s - 1]['type_id']
        return t

    def expr(mp, nid, slotname, memo):
        if nid not in memo:
            nd = mp['nodes'][nid]
            if nd['input']:
                memo[nid] = slotname(next((s for s, n in mp['slots'].items() if n == nid), None))
            else:
                ins = {dp: expr(mp, src, slotname, memo) for src, dst, _, dp in mp['edges'] if dst == nid}
                r = {'op': hex(nd['op']), 'ins': {str(k): v for k, v in sorted(ins.items())}}
                for k in ('table', 'data'):
                    if k in nd:
                        r[k] = nd[k]
                memo[nid] = r
        return memo[nid]

    def walk_map(base, comp_path, slotname):
        mp = parse_map(b, base)
        memo, writes = {}, []
        for w in (n for n in mp['nodes'].values() if n['op'] == 1):
            src = [s for s, d, _, _ in mp['edges'] if d == w['id']]
            writes.append((w['path'], w['pid'], expr(mp, src[0], slotname, memo) if src else None, w['kind']))
        # Table F has one row per child of this composite's node-tree node, in tree order (not
        # member order); a row is filled, {map_off, ..}, exactly where that child is a composite.
        # A composite member with no node-tree entry (Simple Delay's 0x6000d7) has no map and
        # runs on its init values.
        kids = [p for p in nt if len(p) == len(comp_path) + 1 and p[:len(comp_path)] == tuple(comp_path)]
        assert len(mp['F']) == len(kids), f"{m['displayName']}: {len(mp['F'])} table F rows for {len(kids)} children"
        for p, r in zip(kids, mp['F']):
            assert bool(any(r)) == is_comp(member_type(p)), f"{m['displayName']}: table F row of {list(p)}"
            if not any(r):
                continue
            feeds = {pid: e for wp, pid, e, kind in writes if wp == p and kind}    # a switch (kind 0) feeds none

            def sn(slot, feeds=feeds, p=p):
                if slot in feeds:
                    return feeds[slot]
                v = inits.get(p, {}).get(slot)
                return {'const': v, 'from': f'init {list(p)} pid {slot}'}
            writes += walk_map(r[0], p, sn)
        return writes

    def top_slot(s):
        p = params.get(s)
        return {'knob': (p['displayName'] or p['name']) if p else None, 'slot': s}

    out = {'name': m['name'], 'display': m['displayName'], 'model': m['model_id'], 'blob': m['blob_index'],
           'root': hex(root),
           'params': [{'slot': p['slot'], 'name': p['name'], 'disp': p['displayName'] or p['name'],
                       'type': p['type'], 'min': round(p['min'], 6), 'max': round(p['max'], 6),
                       'default': round(p['default'], 6),
                       'list': {k: v for k, v in p['meta'].items() if k.isdigit()}} for p in m['params']],
           'chain': [], 'writes': []}
    for path, pid, e, kind in walk_map(0, (), top_slot):
        t = member_type(path) if path else root
        if path and is_comp(t) and kind:
            continue                                # fed into that member's nested map; a switch of it stays
        out['writes'].append({'path': list(path), 'type': hex(t) if path else 'root', 'pid': pid, 'expr': e})

    def chain(t, prefix, depth):
        for k, mm in enumerate(fw.comp(t)['members']):
            p = prefix + (k + 1,)
            tt = nt.get(p) or mm['type_id']
            init = {pp: fv(v) for pp, v in mm['init_params']}
            init.update(inits.get(p, {}))
            kind = {4: 'in-port', 8: 'out-port', 1: 'tap'}.get(mm['flags'], hex(tt))
            out['chain'].append({'path': list(p), 'depth': depth, 'type': kind,
                                 'in': [fw.b0[mm['in_off'] + i] for i in range(mm['n_in'])],
                                 'out': [fw.b0[mm['out_off'] + i] for i in range(mm['n_out'])],
                                 'init': init})
            if mm['flags'] == 0 and is_comp(tt):
                chain(tt, p, depth + 1)
    chain(root, (), 0)
    return out


# Node ops (registry rows with small ids; docs/research/sharc/model-blobs.md). Two-input ops whose
# data words fill ports 0, 1 and that recompute on either input; the "hot" ones recompute only on
# port 0 and take one data word as port 1. Selects take their data as ports 1...
BIN = {0x14: lambda a, b: a + b, 0x1b: lambda a, b: a + b, 0x15: lambda a, b: int(a) + int(b),
       0x1c: lambda a, b: int(a) + int(b), 0x18: lambda a, b: a * b, 0x1d: lambda a, b: a * b,
       0x19: lambda a, b: int(a) * int(b), 0x1e: lambda a, b: int(a) * int(b),
       0x45: lambda a, b: a / b if b else None, 0x46: lambda a, b: a / b if b else None,
       0x47: lambda a, b: b ** a, 0x48: lambda a, b: b ** a, 0x2c: min, 0x2d: max,
       0x3d: lambda a, b: int(a > b), 0x3e: lambda a, b: int(a > b), 0x3f: lambda a, b: int(a > b),
       0x40: lambda a, b: int(a > b), 0x41: lambda a, b: int(a == b), 0x42: lambda a, b: int(a == b),
       0x43: lambda a, b: int(a == b), 0x44: lambda a, b: int(a == b),
       0x57: lambda a, b: int(bool(a) and bool(b)), 0x58: lambda a, b: int(bool(a) or bool(b))}
HOT = {0x1b, 0x1c, 0x1d, 0x1e, 0x46, 0x48, 0x3f, 0x40, 0x43, 0x44}
UNARY = {0x23: float, 0x24: int, 0x25: lambda x: int(x != 0), 0x26: lambda x: x, 0x4e: lambda x: int(x == 0),
         0x27: lambda x: 10 ** (x / 20) if x > -120 else 0.0,
         0x28: lambda x: 20 * math.log10(x) if x > 0 else -120.0,
         0x3a: lambda x: x}          # 0x3a: a smoother, its settled value is its input [hypothesis]
SELECT = {0x2a: 2, 0x2b: 2, 0x35: 4, 0x36: 4, 0x37: 8, 0x38: 8}


def evaluate(e, knobs):
    """The value an expression (model_report's 'expr') settles to with knob slot -> value.
    None where an op is not modelled (0x2 readers, 0x17, 0x39 and other rare ones)."""
    if e is None:
        return None
    if 'knob' in e:
        return knobs.get(e['slot'])
    if 'const' in e:
        return e['const']
    op = int(e['op'], 16)
    data = [v - (1 << 32) if isinstance(v, int) and v >= 1 << 31 else v for v in e.get('data') or []]
    ins = {int(k): evaluate(v, knobs) for k, v in e['ins'].items()}
    if op == 0x3:                                   # 9-point curve over 0..1, linear between points
        x = ins.get(0)
        if x is None:
            return None
        t = min(max(8 * x, 0.0), 8.0)
        i = min(int(t), 7)
        return e['table'][i] + (e['table'][i + 1] - e['table'][i]) * (t - i)
    if op == 0x6:                                   # [hypothesis] two knobs into a 3 x 3 table, bilinear
        x, y = ins.get(0), ins.get(1)
        if x is None or y is None:
            return None
        tx, ty = min(max(2 * x, 0.0), 2.0), min(max(2 * y, 0.0), 2.0)
        i, j = min(int(tx), 1), min(int(ty), 1)
        fx, fy, T = tx - i, ty - j, e['table']
        g = lambda a, b: T[3 * b + a]
        return ((g(i, j) * (1 - fx) + g(i + 1, j) * fx) * (1 - fy)
                + (g(i, j + 1) * (1 - fx) + g(i + 1, j + 1) * fx) * fy)
    if op in SELECT:
        ports = {k + 1: v for k, v in enumerate(data)}
        ports.update(ins)
        c = ports.get(0)
        if c is None:
            return None
        if SELECT[op] == 2:
            return ports.get(2 if c else 1)
        return ports.get(1 + min(int(c), SELECT[op] - 1))
    if op in BIN:
        ports = {1: data[0]} if op in HOT and data else dict(enumerate(data))
        ports.update(ins)
        a, b = ports.get(0, 0), ports.get(1, 0)
        return None if a is None or b is None else BIN[op](a, b)
    if op in UNARY:
        x = ins.get(0, data[0] if data else None)
        return None if x is None else UNARY[op](x)
    return None


def knobs_of(e, out=None):
    out = set() if out is None else out
    if isinstance(e, dict):
        if 'knob' in e:
            out.add(e['slot'])
        for v in (e.get('ins') or {}).values():
            knobs_of(v, out)
    return out


def sweep(r, steps=(0, 0.25, 0.5, 0.75, 1)):
    """Per knob: each writer it reaches and the value at the knob's positions (list knobs: every
    entry), the other knobs at their defaults."""
    dflt = {p['slot']: p['default'] for p in r['params']}
    out = []
    for p in r['params']:
        if p['type'] == 1:                          # switch
            pos = [0, 1]
        elif p['type'] == 2:                        # list; an unlabelled one gets 0..8
            pos = [int(k) for k in sorted(p['list'], key=int)] if p['list'] else list(range(9))
        else:
            pos = [p['min'] + s * (p['max'] - p['min']) for s in steps]
        rows = []
        for w in r['writes']:
            if p['slot'] in knobs_of(w['expr']):
                vals = []
                for v in pos:
                    k = dict(dflt)
                    k[p['slot']] = v
                    x = evaluate(w['expr'], k)
                    vals.append(round(x, 4) if isinstance(x, float) else x)
                rows.append({'path': w['path'], 'type': w['type'], 'pid': w['pid'], 'values': vals})
        out.append({'slot': p['slot'], 'knob': p['disp'], 'positions': [round(v, 4) for v in pos], 'writes': rows})
    return out


def show(r):
    print(f"== {r['display']} ({r['name']}, model {r['model']}, blob {r['blob']}, root {r['root']})")
    for p in r['params']:
        rng = p['list'] or f"{p['min']}..{p['max']}"
        print(f"  slot {p['slot']:2d} {p['disp']:14s} type {p['type']} {rng} default {p['default']}")
    for c in r['chain']:
        print('   ' + '  ' * c['depth'], c['path'], c['type'], c['in'], '->', c['out'], c['init'] or '')
    for w in r['writes']:
        print('  W', w['path'], w['type'], 'pid', w['pid'], '=', json.dumps(w['expr']))


def show_sweep(r):
    print(f"== {r['display']} ({r['name']})")
    for k in r['sweep']:
        print(f"  slot {k['slot']:2d} {k['knob']:14s} at {k['positions']}")
        for w in k['writes']:
            print('     ', w['path'], w['type'], 'pid', w['pid'], '->', w['values'])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--hxf', default=os.environ.get('HX_STOMP_HXF'))
    ap.add_argument('--category', help='comma-separated Entry 3 categories')
    ap.add_argument('--sub', default='mono', help="subcategory with --category ('' for all)")
    ap.add_argument('--json', help='write the reports here instead of printing them')
    ap.add_argument('--sweep', action='store_true',
                    help="each knob's effect: the values its writers get at min, 1/4 .. max (switches 0/1, lists every entry)")
    ap.add_argument('model', nargs='*')
    a = ap.parse_args(argv)
    if not a.hxf:
        raise SystemExit('no firmware: pass --hxf or set HX_STOMP_HXF')
    fw = Firmware(a.hxf)
    if a.category:
        cats = a.category.split(',')
        ms = [m for m in fw.e3['models'] if m['meta'].get('category') in cats
              and (not a.sub or m['meta'].get('subcategory') == a.sub)]
    else:
        ms = [kp.find_model(fw.e3, q) for q in a.model]
    reports = [model_report(fw, m) for m in ms]
    if a.sweep:
        for r in reports:
            r['sweep'] = sweep(r)
    if a.json:
        json.dump(reports, open(a.json, 'w'), indent=1)
        print(f'{len(reports)} models -> {a.json}')
    else:
        for r in reports:
            (show_sweep if a.sweep else show)(r)


if __name__ == '__main__':
    main()
