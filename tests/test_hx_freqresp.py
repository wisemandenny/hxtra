"""tools/hx_freqresp.py: the analysis on a synthetic recording, and the case files against the stock file."""
import glob
import os

import numpy as np
import pytest

import hx_freqresp as fr

RATE = 48000


def test_noise_is_the_xorshift_stream_at_its_level():
    x = fr.noise(RATE, -20.0)
    assert 20 * np.log10(np.sqrt(np.mean(x ** 2))) == pytest.approx(-20.0, abs=0.1)
    assert np.array_equal(x, fr.noise(RATE, -20.0))


def test_a_delayed_two_tap_filter_is_found_and_measured():
    # y = (x[n] + x[n-1]) / 2, recorded 1234 samples late: |H| = |cos(pi f / fs)|
    x = fr.noise(6 * RATE, -20.0)
    y = 0.5 * (x[1:] + x[:-1])[1234 - 1: 1234 - 1 + 4 * RATE]
    k, peak = fr.align(y, x)
    assert k == 1234 and peak > 20
    a = fr.analyse(y, RATE, -20.0)
    assert a["h"] is not None
    f = np.fft.rfftfreq(fr.NFFT, 1 / RATE)
    c, p = fr.bands(f, np.abs(a["h"]) ** 2)
    db = 10 * np.log10(p)
    want = 20 * np.log10(np.abs(np.cos(np.pi * c / RATE)))
    m = c <= 16000
    assert np.max(np.abs(db[m] - want[m])) < 0.1


def test_crossings_and_slopes_of_a_first_order_low_pass():
    c = 20 * 2 ** (np.arange(121) / 12)
    db = -10 * np.log10(1 + (c / 1000) ** 2)
    assert fr.crossings(c, db, -3.0103) == [pytest.approx(1000, rel=0.01)]
    lo, hi = fr.slopes(c, db)
    assert lo is None and hi == pytest.approx(-6.0, abs=0.3)


@pytest.mark.firmware
@pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(os.path.dirname(fr.__file__), "freqresp", "*.json"))))
def test_case_files_fit_the_stock_models(path):
    if not os.environ.get("HX_STOMP_HXF"):
        pytest.skip("HX_STOMP_HXF is not set")
    ref, cases = fr.load_cases(path)                # exits on a wrong model, knob count or range
    assert cases[0]["name"] == ref and all("model_name" in c for c in cases)
