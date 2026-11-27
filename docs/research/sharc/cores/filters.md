# Filter primitives `0x102` and `0x11c`

The two filter primitives the distortion and EQ blocks are built from: what each type number does, its order and slope, and how frequency, gain and Q act. Status tags as in [conventions.md](../../conventions.md).

How this was found (2026-11-19): the control functions' type branches were run numerically by a small interpreter over `tools/sharc/visa_dis.py` output (start state as the functions' heads leave it: K = tan(πf/fs), A = 10^(g/20)), the resulting coefficients turned into frequency responses at fs = 48 000 Hz and compared with textbook bilinear filters. The process code of `0x102` was not run; for `0x11c` it was read by hand. Status of the type table: **[verified offline]** for the coefficients each type computes; how the process code applies them as noted per primitive.

Notation: f = pid 2 (Hz), g = pid 3 (dB), Q = pid 4, A = 10^(g/20), V = 10^(|g|/20), K = tan(πf/fs). Analog prototypes are in s normalised to 2πf; all bilinear types are prewarped at f, so f is exact.

## `0x102` biquad

- Registry row `0x200040`: init `0x60aceb`, word 3 `0x60ad36`, control `0x60ac56`, process `0x8ce8a`, DM 9, PM 4. Pids: 1 type, 2 frequency, 3 gain, 4 Q. Init: Q 0.7, 1000 Hz.
- Control path: `0x60ac56` is one of four stubs that pass fs (48 000; the others 24 000, 96 000, 192 000) to `0x60ab9e`. That function stores the pid (table at DM `0xc72f5`), clamping frequency to 1..23 000 Hz, gain to −50..+30 dB and Q to 0.1..10, then calls `0x60a603` and copies its five words to state + 4 [verified offline].
- `0x60a603` computes K (tanf `0x8c30f`) and A (powf `0x8c5fd`), then jumps through DM `0xc72dc` (21 entries, `COMPU` against 0x15). Its five output words: [4] = b0, [2] = b1, [0] = b2, [3] = −a1, [1] = −a2 for H = (b0 + b1 z⁻¹ + b2 z⁻²)/(1 + a1 z⁻¹ + a2 z⁻²) [hypothesis, strong: the only reading under which every type is a stable textbook filter; the process code `0x8ce8a` was not traced]. Read this way, the coefficients reproduce the unit's EQ measurement within 0.15 dB, with types 1–7, 12, 13 and 14 acting in the measured chains [verified on unit 2026-11-22, below]; `tools/sharc/biquad102.py` computes them by interpreting the type cases.
- Also used by the branches: divide `0x8c3ea`, sqrtf `0x8c5b2`, expf `0x8c5cd`.

| Type | Branch | Filter | Slope / shape |
|---|---|---|---|
| 0 | `0x60a666` | pass-through (b0 = 1) | flat |
| 1 | `0x60a686` | low-pass, 1st order, 1/(s+1) | −3 dB at f, 6 dB/oct |
| 2 | `0x60a6a8` | high-pass, 1st order, s/(s+1) | −3 dB at f, 6 dB/oct |
| 3 | `0x60a6d4` | low-pass, 2nd order, 1/(s² + s/Q + 1) | 12 dB/oct; Q 0.707 = Butterworth (−3 dB at f) |
| 4 | `0x60a717` | high-pass, 2nd order, s²/(s² + s/Q + 1) | 12 dB/oct |
| 5 | `0x60a761` | low shelf, 1st order | gain g below, 0 dB above; transition between f/V and f, half the dB gain at f/√V; f raised to at least 60 Hz; 6 dB/oct at most |
| 6 | `0x60a7ce` | high shelf, 1st order | transition between f and f·V (f·V capped at 0.499 fs), half the dB gain at f·√V |
| 7 | `0x60a845` | peak (bell) | gain g at f; boost and cut mirror each other; denominator Q = √(Q·A), numerator Q = √(Q/A), i.e. the RBJ peak with Q_RBJ = √Q. Bandwidth between the half-gain (dB) points, independent of g: 1/√Q = 2·sinh(ln 2/2 · BW). Q 0.707 → 1.63 oct, Q 2 → 1.00 oct |
| 8 | `0x60a896` | band-pass, 2nd order, (s/Q)/(s² + s/Q + 1) | 0 dB at f, −3 dB bandwidth f/Q, 6 dB/oct flanks; g unused |
| 9 | `0x60a8c6` | type 7 divided by A | 0 dB at f, −g elsewhere |
| 10 | `0x60a920` | peak, denominator Q = Q, numerator Q = Q/A | boost wider than cut (Q 0.707, ±6 dB: half-gain points 414–2378 Hz boost, 612–1610 Hz cut at f = 1 kHz) |
| 11 | `0x60a96d` | polarity inversion (b0 = −1) | flat |
| 12 | `0x60a975` | peak, RBJ form (gain via 10^(g/40)): denominator Q = Q·√A, numerator Q = Q/√A | boost and cut mirror; 1/Q = 2·sinh(ln 2/2 · BW). Q 0.707 → 1.90 oct, Q 1.4 → 1.0 oct |
| 13 | `0x60a9c4` | low shelf, 2nd order | half the dB gain at f for any g; Q 0.707 without overshoot, larger Q overshoots (Q 2, +6 dB: +8.9 dB at 0.73 f); 12 dB/oct at most |
| 14 | `0x60aa1d` | high shelf, 2nd order | as 13, mirrored |
| 15 | `0x60aa79` | all-pass, 2nd order, (s² − s/Q + 1)/(s² + s/Q + 1) | flat, phase only |
| 16 | `0x60aaa9` | one-pole low-pass, impulse-invariant: b0 = 1 − p, a1 = −p, p = e^(−2πf/fs) | −3 dB at f (low f), 6 dB/oct, does not reach zero at Nyquist |
| 17–20 | | types 1–4 with b scaled by A | as 1–4, plus gain g |

- Used in the 61 mono distortion and 8 mono EQ models (init values): 0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 13, 14, 16; not 9, 11, 15, 17–20.
- **Split crossover** (Entry 3 model 859 `HD2_AppDSPFlowSplitXOver`, preset model 258, composite `0x600001`): per band two cascaded sections, type 3 for the low band, type 4 for the high band, Q 0.707. That is a 4th-order Linkwitz-Riley crossover: −6.02 dB per band at f, **24 dB/oct**, the two bands summing flat (checked numerically at f = 500 Hz: |LP + HP| within 0.003 dB) [verified offline].
- **EQ cut sections** (composite `0x6000d1`: Parametric, Low and High Cut; Simple EQ, Tilt and Low/High Shelf carry the same members without knobs. On the unit Simple EQ measures flat with all gains at 0, so there they do not act; in Tilt and the shelves they do: leaving members 2, 3, 7 and 8 out misses the measured curves by 6.0 (Tilt) and 11.3/12.6 dB (shelves) [verified on unit, 2026-11-22]): Low Cut = type 2 at f/2 then type 4 (Q 0.8) at f, f the knob value: −2.9 dB at f, −6 dB at 0.79 f, 18 dB/oct, no overshoot. High Cut = type 1 at f/2 then type 3 (Q 0.8) at f: not the mirror, −8.9 dB at f, −3 dB at 0.52 f, −6 dB at 0.80 f, 18 dB/oct [verified offline from the map (`tools/sharc/pmap.py --sweep`) and the coefficients above; verified on unit 2026-11-22: in all 20 block cases of `tools/freqresp/eq.json` the computed curves (`tools/hx_freqresp_expect.py`) match the measured ones within 0.15 dB, 30 Hz .. 16 kHz, `tools/hx_freqresp.py`, USB reamping; the measurement is `tests/data/freqresp_eq_unit.csv`, and `tests/test_hx_freqresp_expect.py` repeats the comparison offline]. The knobs' "Off" ends (19.9 Hz, 20 100 Hz) clear root flags ([model-blobs.md](../model-blobs.md#map-ops-verified-offline-unless-tagged)) and so switch the cuts off: flat within 0.01 dB (case `lhc_off`; without the switch the curve would miss by 6.9 dB) [verified on unit, 2026-11-22].
- Teemah! (see [teemah.md](teemah.md)): input `[1, 2]` type 2 = 1st-order high-pass, Treble Cut `[1, 4]` type 1 = 1st-order low-pass, `[1, 5]` type 2 = high-pass; inside the drive, Bass Cut's `[2, 3, 4]` type 5 = 1st-order low shelf (cut), `[2, 3, 3]` type 2 = high-pass, Gain's `[2, 3, 5]` type 1 = low-pass.

## `0x11c` biquad with mix and feedback

- Registry row `0x200060`: init `0x60b271`, word 3 `0x60ad4a`, control `0x60ad61`, process `0x8ceb4`, DM 12, PM 8. Pids 2, 3, 4 = frequency, gain, Q as in `0x102`; the type is pid 1 (init records), never written by a knob in these models.
- Control `0x60ad61`: constants π, 1/48 000, 10.0, 0.05; jump table DM `0xc72f9`, 18 entries (types 0..17), checked with `COMPU(R14, 0x12)`. It writes eight coefficients c0..c7 [verified offline].
- **Process `0x8ceb4`** [verified offline, read by hand]: 16 samples per call (a loop of 7 × 2 and a tail of 2). With x the input:
  - u[n] = c7·x[n] + c6·y[n−1]
  - w[n] = c2·u[n] + c3·u[n−1] + c4·u[n−2] − c0·w[n−1] − c1·w[n−2] (the biquad B)
  - y[n] = c5·x[n] + w[n]
  - So H(z) = (c5 + c7·B(z)) / (1 − c6·z⁻¹·B(z)). c5..c7 are smoothed once per call by a one-pole with r = 0.98349 (a time constant of about 20 ms at 48 kHz); when DM `0xc4cf5` is non-zero they jump at once. c0..c4 are not smoothed. PM state: w[n−1], w[n−2], u[n−1], u[n−2], c6·y[n−1], smoothed c5, c6, c7.

| Type | Filter (B and the mix) | Slope / shape |
|---|---|---|
| 0 | pass-through | flat |
| 1 | low-pass, 1st order (as `0x102` type 1) | 6 dB/oct |
| 2 | low shelf, 1st order: 1 + (A−1)·LP1 for boost; cut computed as its mirror | half the dB gain at f·√V; 6 dB/oct at most |
| 3 | high-pass, 1st order | 6 dB/oct |
| 4 | high shelf, 1st order: 1 + (A−1)·HP1, cut mirrored | half the dB gain at f/√V |
| 5 | low-pass, 2nd order (Q) | 12 dB/oct |
| 6 | low shelf, 2nd order: 1 + (A−1)·LP2, cut mirrored | with Q 0.707 half the dB gain at 0.74 f (±3 dB), 0.85 f (±6 dB), 1.25 f (±15 dB), and a dip of 1.5 dB above f at ±6 dB |
| 7 | band-pass, 2nd order (as `0x102` type 8) | 0 dB at f |
| 8 | peak: boost 1 + (A−1)·BP (as `0x102` type 10); **cut through the feedback** c6 = −(V−1): 1/(1 + (V−1)·z⁻¹·BP) | cut not mirrored: at f = 1 kHz, −6 dB, Q 0.707 it rises to +1.0 dB around 10 kHz |
| 9 | peak, boost as 8, cut as the exact mirror | boost and cut mirror |
| 10 | high-pass, 2nd order (Q) | 12 dB/oct |
| 11 | high shelf, 2nd order: 1 + (A−1)·HP2, cut mirrored | mirror of 6: half the dB gain at 1.35 f (±3 dB), 1.16 f (±6 dB), 0.79 f (±15 dB) |
| 12 | A + one-pole low-pass | unused |
| 13 | A + band-pass | unused |
| 14 | one-pole low-pass, impulse-invariant (as `0x102` type 16) | −3 dB at f, 6 dB/oct |
| 15 | one-pole shelf (1 + (A−1)·one-pole low-pass) | unused |
| 16 | b = K²/D·(1, 1, 1) over the 2nd-order denominator | unclear, unused |
| 17 | one-pole high-pass: 1 − one-pole low-pass (c5 = 1, c7 = −1) | 6 dB/oct; −3.6 dB at f = 1 kHz, levels off at −0.6 dB at Nyquist |

- Used in the 69 models (init values): 0, 1, 3, 4, 5, 6, 8, 9, 11, 14, 17; mostly in the older Line 6 distortions (type 14 in 24 models, 8 in 15, 1, 3 and 17 in 11–13 each).
