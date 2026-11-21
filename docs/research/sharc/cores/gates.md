# Gate core `0x2720` and the blocks around it

The noise-gate core: which blocks use it, how they wire it and feed it, and the composite format that wiring is in. Status tags as in [conventions.md](../../conventions.md). Found by dumping Entry 4 with `tools/sharc/entry4_blob.py` and `tools/patch_amp.py inspect` (issue #69).

## Who uses it [verified offline]

- **Noise Gate** (mono model 72, composite `0x6000ec`; stereo 294, `0x600041`): one `0x2720` a side. Static Model Table cost 150 mono, 190 stereo.
- **The Input block** (`HelixStomp_AppDSPFlowInput`, model 845, composite `0x600000`): member 39 is the sub-composite `0x600014`, a linked stereo gate (`0x89` sums L and R into a key, then one `0x2720` a side keyed by it).
- **No gate** in FX Loop (mono `0x6000e1`, stereo `0x600035`), Return (`0x6000e2`, `0x600036`), Send or the Mixer (`0x600003`).
- Costs (hundredths of a per cent): FX Loop 140 mono / 173 stereo, Return 141 / 186, Hard Gate 115 / 218. The Input, Output and Mixer rows all hold 1099, but those blocks are not among the preset's nine block objects, so their load is in the fixed 1500 of the preset total ([m4/dsp-cost.md](../../m4/dsp-cost.md)).

## Pids and init [verified offline]

- `0x2720` pid 0 = threshold in dB, pid 1 = decay in seconds; the Noise Gate's Threshold and Decay knobs write them through plain float input nodes (op `0xa`), no conversion. Its init: pid 0 −96, pid 1 0.5, pid 3 100 (pid 3's meaning unknown).
- The Input block writes Threshold and Decay to its sub-composite `0x600014` as pids 1 and 2 (path `[1, 40]`), and Input Gate (a bool) to its root composite as pid 10; its init records reach the two cores inside by path `[2, 40, 6]` and `[2, 40, 3]`.
- **[hypothesis]** Off = threshold −96 dB: the core's own init, low enough that the gate never closes.

## Composite format (Blob 0) [verified offline]

- Header, 7 words: `{0, buffers, members, member records, ports, port list, flags}`. Word 1 is the composite's number of audio buffers: 2 for the mono Return and Noise Gate (buffers 0, 1), 5 for `0x600014`.
- Member record, 20 words: 0 index, 1 connection words (the SHARC walks `>> 1` records of 3 words), 2 connection list, 4 kind (0 a primitive or composite, 1 a copy, 4 the input node, 8 the output node), 5 index, 6 type, 7/8 input count and list, 9/10 output count and list, 11/12 init count and list, 13 DM words, 14 PM words, 17 sub-instances. A sub-composite member's DM/PM words are its members' sums (`0x600014`: 10 and 6).
- Inputs and outputs are one word each, a buffer number. The mono Return: the input node writes buffer 0 (dry); `0x2618` (the return reader; init pid 1 = 4 or 5, the mono bus it reads, which the app's `0x25e6` root members 21 and 22 fill from the Return jacks: [usb-routing.md](../usb-routing.md)) writes buffer 1; `0x2390` (no output, **[hypothesis]** a meter) reads 1; `0x80` (Return level) works on 1 in place; `0x84` (Mix) reads 0 and 1 into 0; the output node reads 0.
- The mono Noise Gate: a copy member puts buffer 0 into 1 (the key), `0x2720` reads `[0, 1]` (signal, key) and writes 0, `0x80` (Level) works on 0.
- Editing a stock composite means writing its member array anew past Blob 0's end and repointing its header: two headers sharing members stop the SHARC at the splash (`sharc_blob0_check`).

## Parameter-map select, op `0x2b` [hypothesis]

- All 637 stock `0x2b` nodes have node words `{1, 4, 2, 2}`: 4 state words and 2 data words, the constants for ports 1 and 2 when unconnected. Port 0 a bool, port 1 the value when false, port 2 when true: a hypothesis from the 60s Bias Trem's on switch (false → its constant 0.105 or 0) and the Return's mute at −120 dB. A Gate switch is one `0x2b` node: data `{−96, −48}`, Gate into port 0, Threshold into port 2, out to `0x2720` pid 0.

## The return reader `0x2618` [verified offline, in ssim on the stock code]

- Registry: process `0x8d872`, control function `0x60f99a` (VISA), 1 DM word, no PM. Only the Return and FX Loop composites use it.
- Its process code reads its jack from its one state word (`I0`, the init pid 1: 4 = L, 5 = R), takes 16 samples from that jack's ring in DM (`0xe45fa..` for 4), zeroes them, and writes them to the buffer at `I2` (it sets `B2`/`L2` = 16 itself).

## The FX Loop gate (`src/sharc/fx_gate.asm`, `tools/patch_gate.py`, `HX_FX_GATE`) [verified on unit, noise-gate-12 and -13]

- A registry wrap of `0x2618`, as the GR meter wraps the compressor cores: the process entry calls the stock code, then gates the 16 samples at the `I2` it was called with; the control entry keeps pids 100..102 (Gate, Threshold in dB, Decay in s) in an 8-entry table keyed by the reader's state (R12's first word = `I0`) and hands every other pid to the stock function.
- The blobs' writers go to the reader's existing path (named by its init records), so no member and no binding is added; Blob 0 is untouched.
- In Block 3 right under the Metronome's kernel: 63 DM words and 151 instructions, 291 normal words of the 299 that builds without the GR meter leave.

## The core's process and control functions [verified offline, disassembled]

- Registry row `0x200538`: init `0x614c71`, control `0x614b8b`, process `0x8e8f2`, 4 DM words, 2 PM words.
- Process: `M1 = 16`, then each sample reads the key with `DM(M1, I1)` (no update) and the signal with `DM(I1, 1)`, and writes `I2`. So a two-input core's inputs are adjacent buffers, the second at `I1 + 16`: the composites wire the key into the buffer after the signal (`[0, 1]`, `[1, 2]`, `[3, 4]`). Its DM block **[hypothesis]**: threshold, decay, a block count, the init's descriptor pointer.
- Control: pids 0..3 only; `pid >> 2` non-zero returns at once, so higher pids reach no stock code.
- Users: the Noise Gate (mono `0x6000ec`, stereo `0x600041`, linked by an `0x89` L + R key) and the Input block's `0x600014`. Input Sidechain wraps it ([features/gate-sidechain.md](../../features/gate-sidechain.md)).
- **[verified on unit]** With Input Gate Off the Input block doesn't run `0x600014` at all: its cores get no calls (gate-sidechain-2).
- Blob writers: all 17,132 in the stock blobs name a one-level path (`[1, slot]`); a writer to a core inside a sub-composite (`[2, 40, 6]`) never reached it (gate-sidechain-1). Init records do use two-level paths.
- The meter `0x2390` (row `0x200378`, process `0x8da6a`, ctrl `0x610441`) reads its 16 samples at `I1` (it sets `L1 = 16`) and writes nothing. In the Input block it is members 34 (buffer 0, L) and 37 (buffer 1, R), between the jack readers `0x2a94` (members 0, 13) and the gate.

## On the unit (RAM runs noise-gate-1..6, 2026-11-14) [verified on unit]

Measured over USB: input on USB 5/6 (`hx_ctl.py` load-preset, Input key 5 = 6), plucks over hiss played in, USB 1/2 recorded, a cable from Send L/R to Return L; a block is alive when Return −60 dB drops the output 60 dB.
- Alive: a composite's member array moved past Blob 0's end; a buffer added; members appended after the last; a copy and `0x2720` inserted mid-array with the model blob's paths renumbered and a node-tree child added for the gate.
- A `0x2720` inserted after the return's meter gates (composite init threshold 0 dB: the hiss −45 → −82 dB), so the core runs there.
- **Dead** (the block passes its input, no knob works): any block whose blob gets a sub-binding for the new gate, with or without knobs, and also with Entry 3 descriptor word 8 raised (in 848 of 861 stock models it is the `0x2390` meters plus `gainReductionMeterCount`) and that meta added. Cause unknown.
- Still dead with everything a stock block's registered members have, added for the new one (noise-gate-7..11): a plain `0x80` registered instead of a gate (first or last child), gates appended without renumbering, parameter-map table F grown by one entry a binding (`pm[23]`, 4 zero words each, one per sub-binding in 789 of 863 stock blobs), a `GainEvent` meter record in the Entry 3 list at descriptor word 12 (7 words `{0, 0x80b98, name, 3, index, min, max}`, count word 8) at the next index or at index 1, and Entry 0 Table 2 byte 40 = 1 (set on exactly the 25 models with a `GainEvent` meter). What else a new sub-binding needs is not known; the gate went the other way (a wrapped return reader).
