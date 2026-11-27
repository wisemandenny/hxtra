# Teemah! (overdrive)

The Teemah! model, its node tree and its stock primitives, as groundwork for a crossover or dry blend built into a block from stock primitives (issues #148, #149). Status tags as in [conventions.md](../../conventions.md).

## Model [verified offline]

- `HD2_DistTeemahMono`, display name "Teemah!", Entry 3 model 92, Entry 4 blob 92 (1472 words), composite `0x6000cb`. Read with `tools/kit_patch_amp.py inspect <hxf> Teemah`.
- Parameters: slot 1 Gain (float, default 0.52), 2 Bass ("Bass Cut", 0.5), 3 Treble ("TrebleCut", 0.5), 4 Clipping (list Up/Center/Down, 0), 5 Level (0.63).

## Composite `0x6000cb` (mono, buffers as `in → out`) [verified offline]

| Path | Type | Buffers | Init |
|---|---|---|---|
| [1] | in-port | → 0 | |
| [2] | `0x102` | 0 → 0 | type 2, 15.6 Hz, 0, Q 0.707 |
| [3] | `0x6000c2` (drive) | 0 → 0 | |
| [4] | `0x102` | 0 → 0 | none (set from the parameter map) |
| [5] | `0x102` | 0 → 0 | none |
| [6] | `0x80` (Level) | 0 → 0 | 0, 0 |
| [7] | out-port | 0 → | |

Drive `0x6000c2`: `0x103` (0 → 1, nine init words) puts a second signal into buffer 1; three `0x102` (type 0, 1000 Hz, Q 0.707), `0x80`, `0x832` (clipper, 32 DM words), `0x225`, then `0x89` mixes [0, 1] into 0 (pid 1 = −7 dB, pid 2 = 0). So the stock block already sums a second path into the clipped one.

## Parameter map and blob init (blob 92) [verified offline]

Paths as `[1, k]` = top-level slot k (table above: k = 2 is the first `0x102`), `[2, 3, k]` = slot k inside the drive.
- Gain (slot 1) → writer `[1, 3]` pid 1 (drive), no curve node. Bass (2) → `[1, 3]` pid 2. Clipping (4, int) → `[1, 3]` pid 3. Treble (3) → an op `0x3` node → `[1, 4]` pid 2, the frequency of the filter after the drive. Level (5) → an op `0x3` node → `[1, 6]` pid 1 (`0x80` gain).
- The blob's init records override the composite's: `[1, 2]` type 2, 6 Hz, Q 0.707; `[1, 4]` type 1, 723.43 Hz; `[1, 5]` type 2, 15.92 Hz; `[1, 6]` −60 dB until Level writes; drive `[1, 3]` pids 1..3 = 0.264, 0, 0.
- Inside the drive: `[2, 3, 3]` type 2, 50 Hz; `[2, 3, 4]` type 5, 18 kHz; `[2, 3, 5]` type 1, 1000 Hz; `[2, 3, 7]` `0x832` pids 2..5 = −7.5, −13.3, −7.5, −13.3 (two threshold pairs), 7 = 20, 8 = 10 000, 14 = 60; `[2, 3, 9]` `0x89` pid 1 = −7 dB (clipped path), pid 2 = 0 dB (buffer 1 from `0x103`).
- **The drive's pids 1..3 reach its members through the drive's nested map** (table F, [model-blobs.md](../model-blobs.md#map-tables-b-and-f-curves-and-nested-maps-verified-offline)) [verified offline, `tools/sharc/pmap.py Teemah`]. Values as 9-point curves over knob 0..1 (op `0x3`), first → last point:
  - Gain → `[2, 3, 6]` `0x80` 0 → 48.75 dB (pre-clipper gain) and `[2, 3, 5]` `0x102` frequency 22 000 → 1700 Hz.
  - Bass Cut → `[2, 3, 4]` `0x102` (type 5) frequency 2900 → 1320 Hz with gain 0 → −23.8 dB, and `[2, 3, 3]` `0x102` (type 2) 46.4 → 3 Hz.
  - Clipping → `[2, 3, 7]` `0x832` pids 3 and 5, each through a select `0x2b` between −11.1 and −17.4: pid 3 = Clipping == 2 (op `0x43`) ? −17.4 : −11.1; pid 5 = NOT (op `0x4e`) Clipping == 1 ? −17.4 : −11.1. So Up gives (−11.1, −17.4), Center (−11.1, −11.1), Down (−17.4, −17.4) [verified offline, `tools/sharc/pmap.py --sweep Teemah`].
  - Treble Cut → `[1, 4]` frequency 10 610 → 309 Hz: the knob lowers the cutoff. Level → `[1, 6]` −60 → +9 dB (0 dB at 0.625).

## Stock primitives for a crossover

- `0x102` biquad: pid 1 type, 2 frequency (Hz), 3 gain (dB), 4 Q; 9 DM words. Types decoded in [filters.md](filters.md) [verified offline]: 1 / 2 = 1st-order low-pass / high-pass (6 dB/oct), 3 / 4 = 2nd-order low-pass / high-pass (12 dB/oct), 5 / 6 = 1st-order low / high shelf, 7, 10, 12 = peaks, 13 / 14 = 2nd-order shelves. Init values across the 454 stock composites (4096 `0x102` members; 1591 set pid 1 in the composite, 2505 do not): type 0 (pass-through) ×1236, mostly placeholders set later by the map; 2 ×78 (1–300 Hz), 3 ×50 (800–18 000 Hz), 4 ×146 (3–40 Hz), 5 ×64; 1, 6, 7, 10, 13, 14 at most 4 each.
- `0x102`'s coefficient code is `0x60a603` with the jump table at `0xc72dc`; `0x60ad61` and `0xc72f9` are `0x11c`'s ([filters.md](filters.md)). So for a crossover from `0x102`: a 1st-order pair is HP type 2 + LP type 1; an LR4 pair (as the Split crossover) two sections each of type 4 and type 3, Q 0.707.
- `0x84` and `0x89` share one registry body (init `0x610224`, control `0x61017a`, process `0x8da28`, DM 2, PM 2): the same mixer under two IDs [verified offline].
- `0x84`, `0x89`: two-input mixers, pid 1 and 2 = gain of each input in dB (common pairs −3/−3, −6/−6, 0/−120). The Ampeg Opto Comp's Blend drives `0x84` pids 1 and 2 from one knob ([compressors.md](compressors.md)), the model for a Blend knob.

## Implications for Blend / Freq / Split-Crossover [hypothesis]

- With x the input, b the blend, LR4 = two cascaded 2nd-order Butterworth sections (Q 0.707) per side: crossover y = T(HP(x)) + b·LP(x); split y = T(HP(x)) + b·x.
- **Composite route:** a copy of `0x6000cb` with a tap of x into a spare buffer, two `0x102` high-passes before [3], two `0x102` low-passes on the tap, a mixer at the end. Only stock primitives, no SHARC code. Risk from [gates.md](gates.md): members inserted into a composite run, but a block went dead whenever its blob got a sub-binding for a new member. Freq and Blend need exactly such bindings; [model-blobs.md](../model-blobs.md#sub-bindings-and-table-f-verified-offline) has how they pair a member with its node-tree position.
- **Wrapper route:** SHARC code around a member, as `src/sharc/frame_probe.asm` and `src/sharc/fx_gate.asm` do. Works for the gate on the unit, but `0x102` and `0x80` are shared by most blocks, so the wrapper would have to recognise Teemah! instances, and the dry signal has to survive from [2] to [6].
