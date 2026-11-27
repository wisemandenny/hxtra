#!/usr/bin/env python3
"""hx_freqresp_expect.py CASES.json OUT.csv [--hxf F] : the expected magnitude response of each case, computed.

For tools/hx_freqresp.py --expect. A case gets a curve when its model's top-level members are all
in series on buffer 0 and are only 0x102 biquads and 0x80 gains (the EQ blocks; others, the
reference included, get none). Chain and writers come from tools/sharc/pmap.py, each writer's value
at the case's knob values from pmap.evaluate, and each biquad's coefficients from
tools/sharc/biquad102.py, which runs the stock coefficient code; fs = 48 kHz.

The root switches (writers to path [0], pids 0, 1, 3, 4) bypass members 2, 3, 7, 8 of the EQ
composite 0x6000d1 when 0 (docs/research/sharc/cores/filters.md). Variants, as "case|variant":
- "case"            switches a knob writes act as bypasses; members no switch writer reaches run.
- "case|no-switch"  models with switch writers only: every member runs, switches ignored.
- "case|off-2378"   0x6000d1 models without switch writers (Simple EQ, Tilt, the shelves):
                    members 2, 3, 7, 8 off.
Output: "Hz" (1/48 octave, 10 Hz .. 24 kHz), then a dB column a case or variant.
"""
import argparse
import csv
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [p for p in (_HERE, os.path.join(_HERE, 'sharc')) if p not in sys.path]

import biquad102  # noqa: E402
import hx_smoke  # noqa: E402
import patch_amp  # noqa: E402
import pmap  # noqa: E402

BYPASS = {0: (2,), 1: (3,), 3: (7,), 4: (8,)}       # root switch pid -> member it bypasses at 0
EQ_COMPOSITE = '0x6000d1'


def chain_of(r, knobs):
    """[(slot, type, {pid: value})] of the top-level members, or None unless all are 0x102/0x80 on buffer 0."""
    out = []
    for c in r['chain']:
        if c['depth'] != 0 or c['type'] in ('in-port', 'out-port'):
            continue
        if c['type'] not in ('0x102', '0x80') or c['in'] != [0] or c['out'] != [0]:
            return None
        p = dict(c['init'])
        for w in r['writes']:
            if w['path'] == c['path']:
                v = pmap.evaluate(w['expr'], knobs)
                if v is not None:
                    p[w['pid']] = v
        out.append((c['path'][0], c['type'], p))
    return out


def switches_of(r, knobs):
    return {w['pid']: pmap.evaluate(w['expr'], knobs) for w in r['writes'] if w['path'] == [0]}


def response_db(chain, off, freqs, hxf=None):
    h = [1.0 + 0j] * len(freqs)
    for slot, typ, p in chain:
        if slot in off:
            continue
        if typ == '0x80':
            g = 10 ** (float(p.get(1, 0)) / 20)
            h = [x * g for x in h]
            continue
        t = int(p.get(1, 0))
        if t == 0:                                   # type 0 passes the signal through
            continue
        b, a = biquad102.coefs(t, float(p.get(2, 1000.0)), float(p.get(3, 0.0)), float(p.get(4, 0.7)), hxf)
        h = [x * y for x, y in zip(h, biquad102.response(b, a, freqs))]
    return [biquad102.db(x) for x in h]


def expected(cases, hxf, freqs):
    """{column: [dB at each frequency]} for the cases of a case file (its parsed JSON)."""
    fw = pmap.Firmware(hxf)
    layouts = hx_smoke.entry3_layouts(patch_amp.load_l6ia_from_any(hxf)[0])
    by_name = {m['name']: m for m in fw.e3['models']}
    cols, reports = {}, {}
    for c in cases['cases']:
        name = layouts[c['model']][0]
        if name not in reports:
            reports[name] = pmap.model_report(fw, by_name[name])
        r = reports[name]
        knobs = dict(zip(sorted(p['slot'] for p in r['params']), c['params']))
        ch = chain_of(r, knobs)
        if ch is None or all(t == '0x80' for _, t, _ in ch):
            continue
        sw = switches_of(r, knobs)
        if sw:
            off = {s for pid, v in sw.items() if v == 0 for s in BYPASS.get(pid, ())}
            cols[c['name']] = response_db(ch, off, freqs, hxf)
            cols[c['name'] + '|no-switch'] = response_db(ch, set(), freqs, hxf)
        else:
            cols[c['name']] = response_db(ch, set(), freqs, hxf)
            if r['root'] == EQ_COMPOSITE:
                cols[c['name'] + '|off-2378'] = response_db(ch, {2, 3, 7, 8}, freqs, hxf)
    return cols


def grid():
    return [10 * 2 ** (k / 48) for k in range(int(48 * math.log2(24000 / 10)) + 1)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('cases')
    ap.add_argument('out')
    ap.add_argument('--hxf', default=os.environ.get('HX_STOMP_HXF'))
    a = ap.parse_args(argv)
    if not a.hxf:
        raise SystemExit('no firmware: pass --hxf or set HX_STOMP_HXF')
    fr = grid()
    cols = expected(json.load(open(a.cases)), a.hxf, fr)
    with open(a.out, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['Hz'] + list(cols))
        for k, f in enumerate(fr):
            w.writerow([f'{f:.2f}'] + [f'{cols[n][k]:.3f}' for n in cols])
    print(f'{len(cols)} curves -> {a.out}')


if __name__ == '__main__':
    main()
