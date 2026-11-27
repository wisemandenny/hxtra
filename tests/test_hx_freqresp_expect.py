"""tools/hx_freqresp_expect.py and tools/sharc/biquad102.py: the computed EQ curves against the unit's.

tests/data/freqresp_eq_unit.csv is the measured response of tools/freqresp/eq.json on an HX Stomp
(stock 3.80.0 run from RAM, 2026-11-22, noise at -40 dBFS, 8 s a case, tools/hx_freqresp.py),
1/12-octave band centres, one dB column a case, divided by the reference case "dry".
"""
import csv
import functools
import json
import os

import numpy as np
import pytest

import biquad102
import hx_freqresp_expect as hfe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIT = os.path.join(ROOT, 'tests', 'data', 'freqresp_eq_unit.csv')
CASES = os.path.join(ROOT, 'tools', 'freqresp', 'eq.json')
SIMPLE_EQ = ('seq_flat', 'seq_low12', 'seq_high12')


def hxf():
    path = os.environ.get('HX_STOMP_HXF')
    if not path:
        pytest.skip('HX_STOMP_HXF is not set')
    return path


@functools.lru_cache(maxsize=None)
def measured():
    rows = list(csv.reader(open(UNIT)))
    data = np.array([[float(v) for v in r] for r in rows[1:]])
    return data[:, 0], {h: data[:, k] for k, h in enumerate(rows[0]) if k}


@functools.lru_cache(maxsize=None)
def computed():
    fr = hfe.grid()
    return np.array(fr), {k: np.array(v) for k, v in hfe.expected(json.load(open(CASES)), hxf(), fr).items()}


def deviation(case, column):
    """Largest |measured - computed| as tools/hx_freqresp.py reports it: 30 Hz .. 16 kHz, where the
    computed curve is within 40 dB of its maximum."""
    bc, meas = measured()
    ef, exp = computed()
    v = np.interp(np.log(bc), np.log(ef), exp[column])
    m = (bc >= 30) & (bc <= 16000) & (v >= v.max() - 40)
    return float(np.max(np.abs(meas[case][m] - v[m])))


def test_the_fixture_has_every_case_of_the_case_file():
    _, meas = measured()
    assert list(meas) == [c['name'] for c in json.load(open(CASES))['cases']]


@pytest.mark.firmware
def test_every_block_case_matches_the_unit_within_0_15_db():
    # docs/research/sharc/cores/filters.md, EQ cut sections [verified on unit]
    _, exp = computed()
    blocks = [n for n in exp if '|' not in n]
    assert len(blocks) == 20
    for n in blocks:
        col = n + '|off-2378' if n in SIMPLE_EQ else n
        assert deviation(n, col) <= 0.15, n


@pytest.mark.firmware
def test_the_alternatives_the_notes_rule_out_miss_the_unit():
    # Simple EQ's cut members do not act; the Off ends switch the cuts off (filters.md)
    for n in SIMPLE_EQ:
        assert deviation(n, n) > 20
    assert deviation('lhc_off', 'lhc_off|no-switch') > 6


@pytest.mark.firmware
def test_a_2nd_order_low_pass_from_the_stock_code():
    # type 3: unity at DC, -3 dB at f for Q 0.707, 12 dB/oct well above it
    b, a = biquad102.coefs(3, 1000.0, 0.0, 0.707, hxf())
    h = [biquad102.db(x) for x in biquad102.response(b, a, (1.0, 1000.0, 8000.0, 16000.0))]
    assert h[0] == pytest.approx(0.0, abs=1e-3)
    assert h[1] == pytest.approx(-3.01, abs=0.02)
    assert h[2] - h[3] > 11


@pytest.mark.firmware
def test_every_type_gives_a_stable_filter():
    for t in range(1, biquad102.TYPES):
        for f in (30.0, 1000.0, 15000.0):
            _, a = biquad102.coefs(t, f, 6.0, 0.707, hxf())
            poles = np.roots(a)
            assert np.all(np.abs(poles) < 1), (t, f)
