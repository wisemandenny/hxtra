#!/usr/bin/env python3
"""biquad102 - the 0x102 biquad's coefficients, computed by running the stock code that makes them.

The primitive's coefficient function 0x60a603 (docs/research/sharc/cores/filters.md) works out
K = tan(pi f / fs) and the gain term, then jumps through the table at DM 0xc72dc to the case for
the filter type, which writes five words: [4] = b0, [2] = b1, [0] = b2, [3] = -a1, [1] = -a2.
This module disassembles that code from the stock file (tools/sharc/visa_dis.py, nothing of it is
stored here) and interprets the type cases: it starts at the jump table's target with the
registers the function's head leaves (R7 f, R6 gain dB, R9 Q, R13 fs, R10 pi, R11 K, R15 K^2,
R14 10^(gain/20), R4 10.0, R2 1.0) and serves the library calls it makes (tanf, powf, expf,
sqrtf, divide) in Python. The interpreter knows only the instructions these cases use.

    python3 tools/sharc/biquad102.py [--hxf F] TYPE FREQ [GAIN_DB] [Q]   coefficients, dB at 10 Hz .. 20 kHz
"""
import argparse
import cmath
import functools
import math
import os
import re
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [p for p in (_HERE, os.path.dirname(_HERE)) if p not in sys.path]

import visa_dis  # noqa: E402

CODE = (0x60a600, 0x60aac9)     # the coefficient function's VISA code (short-word addresses)
JUMP_TABLE = 0xc72dc            # DM: one entry per type, 21 words
TYPES = 17                      # types 0..16 have cases of their own; entries 17..20 repeat 1..4
FS = 48000.0

LIB = {0x8c30f: lambda s: math.tan(s.F('F4')), 0x8c5fd: lambda s: s.F('F4') ** s.F('F8'),
       0x8c5cd: lambda s: math.exp(s.F('F4')), 0x8c5b2: lambda s: math.sqrt(s.F('F4')),
       0x8c3ea: lambda s: s.F('F4') / s.F('F8')}


def f2r(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def r2f(r):
    return struct.unpack('<f', struct.pack('<I', r & 0xffffffff))[0]


class Code:
    """The disassembled function: address -> instruction text, the next address, the jump table."""

    def __init__(self, hxf=None):
        img = visa_dis.load(hxf)
        lines = visa_dis.disasm(img.sw, *CODE)
        self.text = {i.addr: i.text for i in lines}
        order = [i.addr for i in lines]
        self.next = dict(zip(order, order[1:]))
        self.table = [img.dm[JUMP_TABLE + t] for t in range(TYPES)]


def split(ins):
    """An instruction's parallel parts, split at top-level commas."""
    parts, depth, cur = [], 0, ''
    for ch in ins:
        depth += (ch == '(') - (ch == ')')
        if ch == ',' and depth == 0:
            parts.append(cur.strip())
            cur = ''
        else:
            cur += ch
    parts.append(cur.strip())
    return parts


class Machine:
    def __init__(self, code, typ, f, g, q, fs=FS):
        self.code, self.typ = code, typ
        self.reg, self.out, self.i5, self.cmp = {}, [0.0] * 5, 0, 0
        k = math.tan(math.pi * f / fs)
        for n, v in dict(R7=f, R10=math.pi, R13=fs, R6=g, R9=q, R11=k, R14=10 ** (g / 20), R15=k * k,
                         R4=10.0, R2=1.0).items():
            self.reg[n] = f2r(v)

    @staticmethod
    def key(t):
        return 'R' + t[1:] if t[0] == 'F' else t

    def F(self, t):
        return r2f(self.reg.get(self.key(t), 0))

    def addr(self, t):
        """Output-buffer index and post-increment of a DM operand through I5, or (None, 0)."""
        m = re.match(r'DM\((-?\d+),I5\)$', t)
        if m:
            return self.i5 + int(m.group(1)), 0
        return {'DM(I5,M5)': (self.i5, 0), 'DM(M6,I5)': (self.i5 + 1, 0), 'DM(I5,M6)': (self.i5, 1)}.get(t, (None, 0))

    def value(self, rhs):
        rhs = rhs.strip()
        if rhs == 'DM(I3,M5)':                      # the type word
            return self.typ
        m = re.match(r'(?:PASS )?(-?)([RFI]\d+|0x[0-9a-f]+)$', rhs)
        if m:
            t = m.group(2)
            v = int(t, 16) if t.startswith('0x') else self.reg.get(self.key(t), 0)
            return f2r(-r2f(v)) if m.group(1) else v
        a = self.addr(rhs)
        if a[0] is not None:
            return f2r(self.out[a[0]])
        m = re.match(r'F(\d+) ([+\-*]) F(\d+)$', rhs)
        if m:
            a, b, op = self.F('F' + m.group(1)), self.F('F' + m.group(3)), m.group(2)
            return f2r(a + b if op == '+' else a - b if op == '-' else a * b)
        m = re.match(r'(MAX|MIN)\(F(\d+), F(\d+)\)$', rhs)
        if m:
            return f2r((max if m.group(1) == 'MAX' else min)(self.F('F' + m.group(2)), self.F('F' + m.group(3))))
        if re.match(r'R(\d+) - R\1$', rhs):
            return 0
        raise ValueError(f'biquad102: operand not modelled: {rhs}')

    def holds(self, c):
        return c is None or {'LT': self.cmp < 0, 'GE': self.cmp >= 0, 'GT': self.cmp > 0, 'LE': self.cmp <= 0,
                             'EQ': self.cmp == 0, 'NE': self.cmp != 0}[c]

    def step(self, ins):
        """One instruction: its parallel moves read before any is written. Returns a control transfer."""
        res, ctl, post = [], None, 0
        for p in split(ins):
            cond = None
            m = re.match(r'IF (\w+) (.*)$', p)
            if m:
                cond, p = m.group(1), m.group(2)
            if not self.holds(cond):
                continue
            if p.startswith(('JUMP (PC, ', 'CALL (PC, ', 'CJUMP ')):
                tgt = int(re.search(r'0x[0-9a-f]+', p).group(0), 16)
                ctl = ('jump' if p.startswith('JUMP') else 'call', tgt, '(DB)' in p)
            elif p.startswith('JUMP (M14,I12)'):
                ctl = ('ret', None, True)
            elif p.startswith('COMP('):
                a, b = [x.strip() for x in p[5:-1].split(',')]
                d = self.F(a) - self.F(b) if a[0] == 'F' else self.reg[a] - self.reg[b]
                self.cmp = (d > 0) - (d < 0)
            elif p in ('NOP', 'RFRAME'):
                pass
            elif '=' in p:
                lhs, rhs = [x.strip() for x in p.split('=', 1)]
                if 'I6' in lhs or 'I6' in rhs or 'I7' in lhs:      # frame and stack traffic
                    continue
                res.append((lhs, self.value(rhs)))
            else:
                raise ValueError(f'biquad102: instruction not modelled: {p}')
        for lhs, v in res:
            a, inc = self.addr(lhs)
            if a is not None:
                self.out[a] = r2f(v)
                post += inc
            else:
                self.reg[self.key(lhs)] = v
        self.i5 += post
        return ctl

    def transfer(self, ctl, pc):
        if ctl[0] == 'ret':
            return None
        if ctl[0] == 'call':
            if ctl[1] not in LIB:
                raise ValueError(f'biquad102: library call not modelled: {ctl[1]:#x}')
            self.reg['R0'] = f2r(LIB[ctl[1]](self))
            return pc
        return ctl[1]

    def run(self):
        pc, pending = self.code.table[self.typ], None
        for _ in range(400):
            ctl = self.step(self.code.text[pc])
            pc = self.code.next[pc]
            if pending:                              # a delayed branch takes effect two instructions on
                pending[0] -= 1
                if pending[0] == 0:
                    c, pending = pending[1], None
                    pc = self.transfer(c, pc)
                if pc is None:
                    return self.out
            if ctl:
                if ctl[2]:
                    pending = [2, ctl]
                else:
                    pc = self.transfer(ctl, pc)
            if pc is None:
                return self.out
        raise RuntimeError('biquad102: no return after 400 instructions')


@functools.lru_cache(maxsize=None)
def code(hxf=None):
    return Code(hxf or os.environ.get('HX_STOMP_HXF'))


def coefs(typ, f, g=0.0, q=0.707, hxf=None):
    """(b, a) of H = (b0 + b1 z^-1 + b2 z^-2) / (1 + a1 z^-1 + a2 z^-2) for type 1..16. Frequency,
    gain and Q are clamped first, as the control path 0x60ab9e does before it calls 0x60a603."""
    if not 0 < typ < TYPES:
        raise ValueError(f'type {typ}: 1..{TYPES - 1}')
    f, g, q = min(max(f, 1.0), 23000.0), min(max(g, -50.0), 30.0), min(max(q, 0.1), 10.0)
    o = Machine(code(hxf), typ, f, g, q).run()
    return [o[4], o[2], o[0]], [1.0, -o[3], -o[1]]


def response(b, a, freqs, fs=FS):
    """Complex response at each frequency."""
    out = []
    for f in freqs:
        z = cmath.exp(-2j * math.pi * f / fs)
        out.append((b[0] + b[1] * z + b[2] * z * z) / (a[0] + a[1] * z + a[2] * z * z))
    return out


def db(x):
    return 20 * math.log10(max(abs(x), 1e-12))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--hxf', default=os.environ.get('HX_STOMP_HXF'))
    ap.add_argument('type', type=int)
    ap.add_argument('freq', type=float)
    ap.add_argument('gain', type=float, nargs='?', default=0.0)
    ap.add_argument('q', type=float, nargs='?', default=0.707)
    a = ap.parse_args(argv)
    if not a.hxf:
        raise SystemExit('no firmware: pass --hxf or set HX_STOMP_HXF')
    b, c = coefs(a.type, a.freq, a.gain, a.q, a.hxf)
    print('b', [round(x, 6) for x in b], 'a', [round(x, 6) for x in c])
    fr = (10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000)
    print('  '.join(f'{f} Hz {db(h):+.2f}' for f, h in zip(fr, response(b, c, fr))))


if __name__ == '__main__':
    main()
