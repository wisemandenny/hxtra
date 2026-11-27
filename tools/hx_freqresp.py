#!/usr/bin/env python3
"""hx_freqresp.py CASES.json OUTDIR [--level DBFS] [--secs S] [--expect CSV] [--reanalyse] : magnitude
response of stock blocks on the HX Stomp over USB, one case a block and knob setting.

CASES.json (examples in tools/freqresp/):
  {"reference": "dry",
   "cases": [{"name": "dry",   "model": 260, "params": [0.0]},
             {"name": "lc100", "model": 130, "params": [100.0, 20100.0, 0.0], "note": "Low Cut 100 Hz"},
             {"name": "lin",   "model": 302, "params": [0.0, 0.5, 0.5, 0, 0.63], "louder": 10}]}
  model  = Table 1 preset ID (the ID a preset stores; tools/hx_smoke.py entry3_layouts lists them),
  params = the knob values in Entry 3 slot order, in the knob's own unit (Hz, dB; 0..1 knobs as 0..1;
           list knobs as integers). With the stock .hxf at hand (HX_STOMP_HXF, else ../HX_Stomp_v3.80.0_*.hxf)
           count, range and type are checked and the types set (the unit drops a preset with a wrong type).
  kind   = block kind (default 1, the effects); louder = dB added to --level for this case (a linearity
           probe); note = free text for the summary. reference (default "dry") is the case every other
           one is divided by; it must come first.

Each case puts one block in slot 0 of path A (everything else cleared). build/noise_mac plays its fixed-seed
xorshift noise into USB 5/6 (the input block set to USB 5/6 once, after the first case) and build/record_mac
records USB 1. The noise is regenerated here and found in the recording by cross-correlation, so
H = S_yx / S_xx (Welch, Hann, 16384 points = 2.9 Hz at 48 kHz), divided by the reference case's H. Where the
noise is not found (a correlation peak under 20 times the median) the case falls back to the PSD ratio.
Shown on 1/12-octave bands, 20 Hz .. 20 kHz (a band's mean where it holds 3 bins or more, below about
400 Hz interpolated between bins on log scales).

Writes OUTDIR/<case>.wav, OUTDIR/response.csv (band centre Hz, one dB column a case, and with --expect the
expected curves as "<case>~exp" and "<case>~exp|<variant>") and OUTDIR/summary.txt: per case the -3 and
-6 dB points relative to the curve's maximum, the flank slopes in dB/oct (fitted where the curve lies 10 to
30 dB below its maximum), for a boost or cut of 3 dB or more its extreme and half-gain points, and the
same for each expected curve with the largest deviation from it (30 Hz .. 16 kHz, where the expected curve
is within 40 dB of its maximum). --expect CSV: "Hz" and one column a case or case|variant, in dB.
--reanalyse reads the WAVs already in OUTDIR and touches no device.

The edit buffer is saved first and written back at the end. Needs the installed firmware to answer hx_ctl
(stock 3.80.0 or an HXtra build), HX Edit closed. Each case is one preset write, plus the input block and the
restore: stock 3.80 stops answering after about 30 a boot, so a run refuses more than --max-writes (28).

Helpers (built once; HX_MAC_HELPERS names their folder, default build/):
  swiftc -O tools/mac/noise_mac.swift -o build/noise_mac
  swiftc -O tools/mac/record_mac.swift -o build/record_mac
"""
import argparse, csv, glob, json, os, subprocess, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hx_smoke as hs

ROOT = hs.ROOT
HELPERS = os.environ.get("HX_MAC_HELPERS", os.path.join(ROOT, "build"))
NOISE = os.path.join(HELPERS, "noise_mac")
RECORDER = os.path.join(HELPERS, "record_mac")
NFFT = 16384
PER_OCT = 12
TRIM = 0.3                                   # seconds dropped at the start of each recording


# --------------------------------------------------------------------------- cases

def stock_hxf():
    p = os.environ.get("HX_STOMP_HXF")
    if p and os.path.exists(p):
        return p
    c = sorted(glob.glob(os.path.join(ROOT, "..", "HX_Stomp_v3.80.0_*.hxf")))
    return c[0] if c else None


def load_cases(path):
    d = json.load(open(path))
    cases = d["cases"]
    ref = d.get("reference", "dry")
    if not cases or cases[0]["name"] != ref:
        sys.exit(f"{path}: the first case must be the reference '{ref}'")
    names = [c["name"] for c in cases]
    if len(set(names)) != len(names):
        sys.exit(f"{path}: case names repeat")
    hxf = stock_hxf()
    if not hxf:
        print("warning: no stock .hxf found, knob values unchecked (write floats with a point)", flush=True)
        return ref, cases
    import patch_amp
    lay = hs.entry3_layouts(patch_amp.load_l6ia_from_any(hxf)[0])
    for c in cases:
        if c["model"] not in lay:
            sys.exit(f"case {c['name']}: preset ID {c['model']} is no browser model")
        name, ps = lay[c["model"]]
        if len(ps) != len(c["params"]):
            sys.exit(f"case {c['name']}: {name} has {len(ps)} knobs, {len(c['params'])} values given")
        vals = []
        for q, v in zip(ps, c["params"]):
            v = bool(v) if q["type"] == 1 else int(v) if q["type"] == 2 else float(v)
            if q["type"] != 1 and not q["lo"] - 1e-6 <= v <= q["hi"] + 1e-6:
                sys.exit(f"case {c['name']}: {q['name']} = {v} outside {q['lo']}..{q['hi']}")
            vals.append(v)
        c["params"], c["model_name"] = vals, name
    return ref, cases


def fmt_params(vals):
    out = []
    for v in vals:
        if isinstance(v, bool):
            out.append("true" if v else "false")
        elif isinstance(v, int):
            out.append(str(v))
        else:
            out.append(repr(float(v)))
    return ",".join(out)


# --------------------------------------------------------------------------- device

def ctl(*a, timeout=20):
    return hs.run("tools/hx_ctl.py", "--timeout", "8", *a, timeout=timeout)


def place(c):
    r = ctl("set-model", "--slot", "0", "--model-id", str(c["model"]), "--clear-after", "--clear-path-b",
            "--kind", str(c.get("kind", 1)), "--params", fmt_params(c["params"]))
    return "verified" in r.stdout, r.stdout + r.stderr


def usb_input(tmp):
    j = os.path.join(tmp, "edit_usb.json")
    ctl("get-preset", "-o", j)
    d = json.load(open(j)); d["preset"]["0"]["22"][0]["20"]["5"] = 6        # the input block: USB 5/6
    json.dump(d, open(j, "w"))
    return "verified" in ctl("load-preset", j).stdout


def take(wav, secs, level_db):
    play = subprocess.Popen([NOISE, "HX Stomp", str(secs + 2), "5,6", str(level_db)], stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    subprocess.run([RECORDER, "HX Stomp", str(secs), wav], capture_output=True, timeout=secs + 30)
    play.wait()


# --------------------------------------------------------------------------- analysis

_UNIT = np.empty(0)


def noise(n, level_db):
    """The samples build/noise_mac plays: xorshift32 from 0x9e3779b9, uniform, RMS level_db dBFS."""
    global _UNIT
    if len(_UNIT) < n:
        s, out = 0x9e3779b9, [0] * n
        for k in range(n):
            s ^= (s << 13) & 0xffffffff; s ^= s >> 17; s ^= (s << 5) & 0xffffffff
            out[k] = s
        _UNIT = np.array(out, dtype=np.float64) / 0xffffffff * 2 - 1
    return _UNIT[:n] * 10 ** (level_db / 20) * np.sqrt(3)


def read(wav):
    x, rate = hs.read_wav(wav)
    return np.asarray(x[int(TRIM * rate):], dtype=np.float64), rate


def align(y, x):
    """Lag k with y[n] ~ x[n + k], and the peak's ratio to the median of |correlation|."""
    n = 1 << int(np.ceil(np.log2(len(x) + len(y))))
    c = np.fft.irfft(np.fft.rfft(x, n) * np.conj(np.fft.rfft(y, n)), n)[:len(x) - len(y) + 1]
    a = np.abs(c)
    k = int(np.argmax(a))
    return k, float(a[k] / (np.median(a) + 1e-30))


def welch(y, x=None, n=NFFT):
    w = np.hanning(n); hop = n // 2
    syy, syx, sxx = 0, 0, 0
    for k in range(0, len(y) - n + 1, hop):
        Y = np.fft.rfft(y[k:k + n] * w)
        syy = syy + np.abs(Y) ** 2
        if x is not None:
            X = np.fft.rfft(x[k:k + n] * w)
            syx, sxx = syx + Y * np.conj(X), sxx + np.abs(X) ** 2
    return syy, (syx / sxx if x is not None else None)


def analyse(y, rate, level_db):
    """{'pyy': PSD, 'h': complex H or None, 'peak': correlation ratio}."""
    x = noise(len(y) + int(3.5 * rate), level_db)
    k, peak = align(y, x)
    if peak < 20 or k + len(y) > len(x):
        return {"pyy": welch(y)[0], "h": None, "peak": peak}
    pyy, h = welch(y, x[k:k + len(y)])
    return {"pyy": pyy, "h": h, "peak": peak}


def bands(f, p, lo=20.0, hi=20000.0, per_oct=PER_OCT):
    c = lo * 2 ** (np.arange(int(round(np.log2(hi / lo) * per_oct)) + 1) / per_oct)
    lp = np.log(np.maximum(p[1:], 1e-30))
    out = []
    for fc in c:
        m = (f >= fc * 2 ** (-0.5 / per_oct)) & (f < fc * 2 ** (0.5 / per_oct))
        out.append(p[m].mean() if m.sum() >= 3 else np.exp(np.interp(np.log(fc), np.log(f[1:]), lp)))
    return c, np.array(out)


def crossings(c, db, level):
    """Band centres where the curve crosses `level` (log-interpolated)."""
    out = []
    for k in range(1, len(c)):
        a, b = db[k - 1] - level, db[k] - level
        if np.isfinite(a) and np.isfinite(b) and (a < 0) != (b < 0):
            r = a / (a - b)
            out.append(float(np.exp(np.log(c[k - 1]) + r * np.log(c[k] / c[k - 1]))))
    return out


def slopes(c, db):
    """(low flank, high flank) dB/oct, fitted where the curve lies 10..30 dB below its maximum."""
    i = int(np.nanargmax(db)); mx = db[i]
    out = []
    for side in (slice(0, i), slice(i + 1, None)):
        cc, dd = c[side], db[side]
        m = np.isfinite(dd) & (dd <= mx - 10) & (dd >= mx - 30)
        out.append(float(np.polyfit(np.log2(cc[m]), dd[m], 1)[0]) if m.sum() >= 3 else None)
    return out


def hz(v):
    return "[" + ", ".join(f"{x:.0f}" if x >= 100 else f"{x:.1f}" for x in v) + "]"


def describe(c, db):
    i = int(np.nanargmax(db)); mx = db[i]
    lo, hi = slopes(c, db)
    s = (f"max {mx:+.2f} dB at {c[i]:.0f} Hz; -3 dB {hz(crossings(c, db, mx - 3))}; "
         f"-6 dB {hz(crossings(c, db, mx - 6))}; slopes {'-' if lo is None else f'{lo:+.1f}'} / "
         f"{'-' if hi is None else f'{hi:+.1f}'} dB/oct")
    m = (c >= 30) & (c <= 16000)
    j = int(np.nanargmax(np.abs(np.where(m, db, 0))))
    g = db[j]
    if abs(g) >= 3:
        s += f"; extreme {g:+.2f} dB at {c[j]:.0f} Hz, half gain ({g / 2:+.2f} dB) at {hz(crossings(c, db, g / 2))}"
    return s


def load_expect(path):
    with open(path) as fh:
        rows = list(csv.reader(fh))
    head = rows[0]
    data = np.array([[float(v) if v not in ("", "nan") else np.nan for v in r] for r in rows[1:]])
    return data[:, 0], {h: data[:, k] for k, h in enumerate(head) if k}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cases")
    ap.add_argument("outdir")
    ap.add_argument("--level", type=float, default=-40.0, help="noise RMS in dBFS (default -40)")
    ap.add_argument("--secs", type=float, default=8.0, help="seconds recorded a case (default 8)")
    ap.add_argument("--expect", help="CSV of expected curves (Hz, then case or case|variant columns, dB)")
    ap.add_argument("--reanalyse", action="store_true", help="analyse the WAVs in OUTDIR, no device")
    ap.add_argument("--max-writes", type=int, default=28, help="preset writes allowed a run (default 28)")
    a = ap.parse_args()
    ref, cases = load_cases(a.cases)
    writes = len(cases) + 2
    print(f"{len(cases)} cases, {writes} preset writes", flush=True)
    os.makedirs(a.outdir, exist_ok=True)
    if not a.reanalyse:
        if writes > a.max_writes:
            sys.exit(f"{writes} preset writes exceed --max-writes {a.max_writes}: split the case file")
        for tool in (NOISE, RECORDER):
            if not os.path.exists(tool):
                sys.exit(f"missing {tool}: build it as the docstring says (HX_MAC_HELPERS names the folder)")
        if not hs.alive(2):
            sys.exit("the HX Stomp does not answer (USB connected? HX Edit closed?)")
        backup = os.path.join(a.outdir, "edit_buffer_before.json")
        ctl("get-preset", "-o", backup)
        print(f"edit buffer saved to {backup}", flush=True)
        usb_set = False
        try:
            for c in cases:
                ok, log = place(c)
                if ok and not usb_set:
                    ok = usb_set = usb_input(a.outdir)
                if not ok:
                    print(f"{c['name']:12} not placed:\n{log}", flush=True)
                    continue
                take(os.path.join(a.outdir, c["name"] + ".wav"), a.secs, a.level + c.get("louder", 0))
                print(f"{c['name']:12} recorded", flush=True)
        finally:
            r = ctl("load-preset", backup)
            print("edit buffer restored" if "verified" in r.stdout else f"edit buffer NOT restored:\n{r.stdout}{r.stderr}")

    res, rate = {}, 48000
    for c in cases:
        wav = os.path.join(a.outdir, c["name"] + ".wav")
        if not os.path.exists(wav):
            continue
        y, rate = read(wav)
        r = analyse(y, rate, a.level + c.get("louder", 0))
        r["rms"] = 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12)
        res[c["name"]] = r
        print(f"{c['name']:12} {len(y) / rate:.1f} s, {r['rms']:.1f} dBFS, "
              f"{'noise found' if r['h'] is not None else 'noise NOT found, PSD ratio'} (peak {r['peak']:.0f})",
              flush=True)
    if ref not in res:
        sys.exit("no reference recorded")
    f = np.fft.rfftfreq(NFFT, 1 / rate)
    R = res[ref]
    cols, how = {}, {}
    for c in cases:
        r = res.get(c["name"])
        if r is None:
            continue
        if r["h"] is not None and R["h"] is not None:
            p, how[c["name"]] = np.abs(r["h"] / R["h"]) ** 2, f"H1 (peak {r['peak']:.0f})"
        else:
            p = r["pyy"] / R["pyy"] / 10 ** (c.get("louder", 0) / 10)
            how[c["name"]] = f"PSD ratio (peak {r['peak']:.0f})"
        bc, h = bands(f, p)
        cols[c["name"]] = 10 * np.log10(h)
    exp = {}
    if a.expect:
        ef, ecols = load_expect(a.expect)
        for name in list(cols):
            for h, v in ecols.items():
                if h == name or h.startswith(name + "|"):
                    exp[f"{name}~exp{h[len(name):]}"] =np.interp(np.log(bc), np.log(ef), v)
    lines = []
    for c in cases:
        n = c["name"]
        if n not in cols:
            lines.append(f"{n}: not recorded")
            continue
        lines.append(f"{n}" + (f"  ({c['note']})" if c.get("note") else "") + f"  [{how[n]}]")
        lines.append(f"    measured  {describe(bc, cols[n])}")
        for k, v in exp.items():
            if k == n + "~exp" or k.startswith(n + "~exp|"):
                m = (bc >= 30) & (bc <= 16000) & (v >= np.nanmax(v) - 40)
                dev = np.nanmax(np.abs(cols[n][m] - v[m])) if m.any() else np.nan
                lines.append(f"    {k[len(n) + 1:]:9} {describe(bc, v)}")
                lines.append(f"    {'':9} largest deviation measured - expected: {dev:.2f} dB")
    allc = dict(cols); allc.update(exp)
    with open(os.path.join(a.outdir, "response.csv"), "w") as fh:
        fh.write("Hz," + ",".join(allc) + "\n")
        for k, fc in enumerate(bc):
            fh.write(f"{fc:.1f}," + ",".join(f"{allc[n][k]:.2f}" for n in allc) + "\n")
    open(os.path.join(a.outdir, "summary.txt"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
