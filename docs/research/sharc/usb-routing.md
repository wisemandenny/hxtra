# USB routing and the app graph

Where the HX Stomp's inputs and outputs are chosen, and what reaches the computer over USB. Asked by issue #81 (monitoring through the DAW only). The Output block's own mixing into Main and Send is hxtra-a4's #93 research. Status tags as in [conventions.md](../conventions.md).

## What a user sees [community reports, not checked]

- USB 1/2 carries the main output to the computer, and USB 1/2 from the computer plays on the outputs and phones. USB 5/6 to the computer is the dry Main L/R input, and USB 7/8 is the dry Return L/R. Path B's Output reportedly reaches USB 3/4. Path A's Output offers no USB-only destination.
- So monitoring through a DAW without the HX Stomp's direct sound has no setting. Turning Path A's Output level down also silences USB 1/2.
- The Helix Floor, LT and Rack offer Output = USB 3/4 or USB 5/6 instead, which sends the processed sound to the computer only.

## The app graph (Entry 3 and Entry 4 blob 1) [verified offline]

- The routing is a fixed DSP graph, `HelixStomp_App`. Its model record is at e3 `0x19b00` (name string 4029, blob 1) and is not in the main model table. Its parameter records run from `0x80358` to `0x80b78`, 66 of them.
- Routing parameters:

| parameter | slot | type | values |
|---|---|---|---|
| `inputSelect.0`, `inputSelect.1` | 34, 35 | int | 0..7 |
| `outputSelect.1` (path B) | 36 | int | 0..9, default 0 |
| `outputSelect.0` (path A) | 37 | int | 0..9, default 1 |
| `returnType` | 54 | list | 0 Return, 1 Aux In |
| `masterVolSelect` | 55 | list | 1 Phones, 2 Main+HP |
| `usbInGain0_1` | 56 | float dB | -60..18, "USB Input Trim" |
| `applyEQ` | 58 | list | 0 Off, 1 1/4", 2 Send, 3 1/4"+Send |
| `phonesSelect` | 60 | list | 1 Main, 2 FX Send |
| `tunerOutputSelect` | 63 | int | 0..9 |

- The Output block models' `select` (`HelixStomp_AppDSPFlowOutputMain` slot 3, `...OutputSend` slot 100) is also int 0..9. The Input block's `select` (slot 4) is 0..7.
- Blob 1's parameter map wires these to the DSP:
  - `outputSelect.0` → an int input node (op `0xb`) → a writer to path [83], pid 3. The node tree overrides member 83 to composite `0x60000a`.
  - `outputSelect.1` → path [71], pid 100.
  - `usbInGain0_1` → paths [99] and [105], pid 1.
  - `phonesSelect` → two op `0x43` nodes → path [0] (the app itself), pids 42 and 45.
- Composite `0x60000a` (the output block) has two gains `0x225`, an adder `0x2391`, two `0x25e6` with init param 1 = 0 and 1, two `0x2390`, and a `0x25e8` with 2 inputs and init param 1 = 2. What `0x25e6`, `0x25e8` and `0x2391` do: "Where USB audio is made" below.
- **Each destination is one bus** [verified offline, 2026-11-20: the bus primitives' process code with `visa_dis.py --pm`, and which root member reads each bus; this replaces the hypothesis that `0x25e6` writes one output channel and `select` picks its bus]: in `0x60000a` the two `0x25e6` add into mono buses 0 and 1 (Send L/R) and the `0x25e8` into stereo bus 2 (Main). `select` picks which of them run: its op 67 tests turn on [83] pid 1 (Send) or pid 2 (Main) ("How the app turns its parameters into DSP calls"). [hypothesis] The two `0x25e6` run on pid 1 and the `0x25e8` on pid 2: the condition words of their connection records (blob 0 words 13198, 13213 and 13227) are 2, 2 and 4, read as 2 × pid + a polarity bit. So each value has at most one destination (6 = Send L/R; 0, 2..4, 7 and 10..12 none), not a Helix-style "Multi", as the sweep below found on the unit [verified on unit, 2026-11-14] (post-send, #93).
- Blob 1's root node has type `0xffffffff`, and no composite in blob 0's table has the 171 members its node tree uses (the largest, `0x6001ab`, has 154). The app's members are blob 0's own root list instead (see "The app's members" below).

## The M4 rewrites Output select on preset load [verified on unit, 2026-11-14]

How it was tested: a plain build from `next` (image `9b4d2b60…`, boot hxtra-4c-1, RAM run). Every path block was emptied, the input block set to USB 5/6, and each Output select value written into the edit buffer with `hx_ctl.py load-preset` (preset block 9 key `6` for path A, block 19 key `16`.`6` for path B). Plucks from `play_mac` went in on USB 5/6, and `record_mac` recorded all 8 USB channels for 3 s.

- **Path A keeps 0 or 1 only.** Values 2..9 read back as 1 and sound exactly like 1. With 1, the signal is on USB 1/2 at -21.3 dBFS and USB 3..6 are digital zero. With 0, every channel is silent.
- **Path B keeps 0 or 6 only** (6 = Send). 1..5 read back as 0 and 7..9 as 6. With a block on path B, 0 also reads back as 6.
- `hx_ctl.py` still reports such a load as `verified`, so check the value read back, not that word.
- So the 0..9 range in Entry 3 is not reachable from a preset. The rewrite is M4 code: Entry 3 has no value list for these parameters.

## How the M4 sets an output's destination [verified offline, disassembly]

- The M4 names app-graph parameters by their Entry 3 string index. At app setup (`0x28df5d06`..), a loop resolves the table at `0x28e3db60` (mute, muteOutput, muteRampTimeMS, inputSelect.0/1, outputSelect.0/1, splitToLower, joinToLower) into handles at app + `0xacc`.. (outputSelect.0 at `+0xae0`, outputSelect.1 at `+0xae4`). The app object is `[engine] + 0x6484 * dsp`, and its instance handle is at `+0xac8`.
- `0x28df35e8(ctx + 4, instance, handle, &{u8 type, u32 value})` sets one app parameter (type 2 = int). The I/O Global Settings use it too: their keys at `0x28e3ec68` are string indices, e.g. 4217 phonesSelect, 4206 masterVolSelect, 4209 usbInGain0_1.
- **`0x28df5760(ctx, app, path, value)`** sends a destination. It refuses a value above 12 or outside mask `0x1cff` (0..7, 10..12). It stores the value at app + `0x150 * path + 0x2cd`, and 5 at `+0x2a9`. Then it sends it through the outputSelect.0/1 handle. Its getter is `0x28df57d8`.
- `0x28e002a8(engine, path, dsp, value)` checks the same mask, then calls `0x28df5760`. It has three callers, and the output block's setter is one of them.
- **`0x28e0a2fc(engine, block, value)`, the output block's setter, is the rewrite.** It acts only on block types 1 (output A) and 3 (merge, output B). A value of 0 is always set. Otherwise, on path A only 1 is set: other values reach `0x28e0a428` (`mov r11, r8; b` out). On path B only 6 is set, with extra setup at `0x28e0a42c` when `[block + 1] & ~2 == 1`: other values reach `0x28e0a382` (`mov r11, lr; b` out). A refused value changes nothing, which is why the preset reads back the old 1 or 6.
- A probe image (`output_any`, kept out of the repository since USB monitoring replaced it) turned both refusals into branches to the set at `0x28e0a390` (`05e0 00bf` at `0x28e0a382`, `b2e7 00bf` at `0x28e0a428`), so a preset could try every value the mask allows.
- To the computer, USB 5/6 was digital zero throughout, with nothing plugged into the Main inputs. USB 7/8 read about -95 dBFS, an analog noise floor. In none of these takes did the Send→Return L cable show signal on any USB channel.
- **Refuted for USB 1/2:** one last take, played on USB 3/4, 1/2 or 7/8 from the computer with nothing routed, read -21.7 dBFS on USB 7/8 to the computer whichever channel played. The table in "Hardware against software monitoring" below has the DAW on USB 1/2 with Send L in Return L and USB 7/8 at -98, the floor [verified on unit, 2026-11-14], and USB 1/2's playback is added into Main only [verified offline: "The app's members"]. It may have overlapped another session's boot, as noted then. USB 3/4's playback is added to the Send signal read from the bus [verified offline], so with Send in Return it should come back on 7/8 [hypothesis: not measured].

## What each destination does [verified on unit, 2026-11-14]

How it was tested: the sweep above on that probe build from `next` (image `5c82add0…`, boot usb-monitor-2, RAM run). Path A's Output select was set to each value the mask allows, with path B empty. Send L ran into Return L through a mono cable. The setting reads back as written now.

| path A Output select | USB to the computer |
|---|---|
| 1, 5 | 1/2 at -21.3 dBFS (Main); 3..8 as with no signal |
| 6 | **3/4 at -21.3 dBFS, 1/2 silent**; 7/8 at -21.8 dBFS through the cable |
| 0, 2, 3, 4, 7, 10, 11, 12 | silent everywhere (destinations the HX Stomp lacks) |
| 8, 9 | refused by `0x28df5760`'s mask |

- **USB 3/4 to the computer is the Send bus**: Send L/R and USB 3/4 carry the same signal. **USB 7/8 is Return L/R, dry**: the cable's Send L arrives on both 7 and 8, so a mono Return feeds both. USB 5/6 is the dry Main input, digital zero with nothing plugged in.
- So **path A Output = 6 is USB-only monitoring (issue #81)**. The processed sound goes to the computer on USB 3/4 and to the Send jacks, while Main, the phones (phonesSelect = Main) and USB 1/2 carry only the computer's playback. Stock firmware refuses it on path A. On path B the forum workaround reaches the same Send bus.
- **No value sends to Main and Send together** (no Helix-style Multi), so issue #93 gets nothing from this setting.
- Path B (a block kept on B, Output A = 1) gave no signal on any channel for any value, so path B was probably getting no audio in the test preset. Not conclusive. Value 5 on path B failed to load.

## Hardware against software monitoring, measured at the jacks [verified on unit, 2026-11-14]

How it was tested: same image and run as above. Main Out L went into input 1 of a Volt 4, the phones into input 2, both line level at a similar gain. The HX Stomp's USB and the Volt were recorded at the same time, 3 s per take. "Guitar" means plucks on USB 5/6 with input A set to USB 5/6. "DAW" means plucks on USB 1/2 from the computer. Levels are in dBFS.

| case | USB 1/2 | USB 3/4 | USB 7/8 (Return) | Main L | phones |
|---|---|---|---|---|---|
| nothing playing (noise floor) | silent | silent | -98 | -62 | -86 |
| Output A = Main, guitar | -21.3 | silent | -98 | **-7.4** | **-58.9** |
| Output A = Send, guitar | silent | **-21.3** | -21.8 | -62.1 (floor) | -86.0 (floor) |
| Output A = Send, DAW | silent | silent | -98 | -24.2 | -77.0 |
| Output A = Main, DAW | silent | silent | -98 | -24.2 | -77.0 |
| stock: A level -120, block on B, A/B split even, Output B = Send, guitar | silent | -27.5 | -27.9 | -63.1 (floor) | -85.9 (floor) |

- **Output A = Send is software monitoring.** The processed sound reaches only the computer (USB 3/4) and the Send jacks. Main and the phones stay at their noise floor, and the computer's playback on USB 1/2 still reaches both, exactly as with Main. This answers issue #81.
- **The stock route does the same**: path A's Output level at -120 dB, a block on path B, and Output B = Send. Only the even split's 6 dB is lost. It costs a block and a split, but needs no HXtra.
- The phones read lower than Main L only because of their own volume and the Volt's gain. Each column is compared with its own noise floor.
- **Caution:** on 2026-11-16 the Volt's inputs turned out to be the other way round (input 1 the phones, input 2 Main; see "Which writer is which"). If they were already so here, the last two columns are swapped: Main at -58.9 with the guitar, the phones at -7.4.

## Send and FX Loop blocks share the Send bus [verified on unit, 2026-11-16]

How it was tested: the USB Monitor build (image `997d079e…`, boot usb-monitor-5) with Path A Out on Send/USB, nothing plugged into Return, plucks on USB 5/6, one block in path A's first slot. Send L/R is preset ID 254, kind 29; FX Loop L/R is 145, kind 13 (Table 1 and the Send/Return browser items).

| path A | USB 3/4 |
|---|---|
| no block | -21.3 dBFS |
| Send L/R, Send -6 dB, DryThru 0 dB | -17.8 dBFS: the send (-27.3) and the output (-21.3) added |
| FX Loop L/R, Send 0 dB, Mix 0.5 | -15.3 dBFS: two copies added |

- A Send or FX Loop block's send and an output set to Send are summed into one bus, the Send jacks and USB 3/4 together. Neither replaces the other.
- So with an FX Loop block, an output on Send feeds back through whatever is in the loop.
- The HX Stomp adds a fourth value (a bool) to an FX Loop block's parameters when it loads one.

## Where USB audio is made (Option B research, 2026-11-16) [verified offline, disassembly]

- **The output block composite `0x60000a`'s `0x25e6`/`0x25e8` members add into buses** [verified offline, 2026-11-20: their process code with `visa_dis.py --pm`; an earlier reading here had them as meter taps]: `0x25e6` adds its 16-sample input into mono bus k (DM `0xe45ba + 16k`), `0x25e8` its two inputs into stereo bus k (DM `0xe467a + 32k`), k being the instance's state word (init param 1); they return at once when k is not below DM `0xc73d5` (mono) or `0xc73d6` (stereo). `0x2618` and `0x261a` read a mono or stereo bus and clear it (process `0x8d872` and `0x8d88a`; the Return's reader, [cores/gates.md](cores/gates.md)). `0x25e6` (one input, init 0 or 1) and `0x25e8` (two inputs, init 2) also sit in `0x600009`, `0x600013`, `0x600035`, `0x600037`, `0x6000e1` and `0x6000e3`. Which bus each member adds into is its init param; which members run is the destination's switches ("Each destination is one bus" above). Their registry entries (DM `0x200000`, post-send) agree:
  - `0x25e6` at `0x200390`: init `0x6105be`, ctrl `0x6105a5`, process `0x8db2a`, 1 DM word, no PM.
  - `0x25e8` at `0x200398`: init `0x6105ea`, ctrl `0x6105d1`, process `0x8db42`, 1 DM word.
  - The rest of `0x60000a`: `0x225` at `0x2002a0` (process `0x8d7f5`), `0x2390` at `0x200378` (process `0x8da6a`), and `0x2391` at `0x200400` (process `0x8dca9`, no init or ctrl): an adder, the sum of its two 16-sample inputs (adjacent buffers, read from `I1` and `I1 + 16`) into its output [verified offline, `visa_dis.py --pm`, 2026-11-20; once read as a pan/mix].
- Entry 0 segment 3 (`0x20000000`, 48 KB) holds the USB device: the UTF-16 strings "LINE 6", "HX Stomp", "HX Stomp Msg Pipe", "HX Stomp Audio Ctrl", "HX Stomp MIDI" at `0x2000617e`.., 21 literals of USB0 (`0x40006000`, `0x400061c0` ENDPTCTRL) and 21 of I2S0 (`0x400a2000`). Its code is Thumb-1 only (`movs`, `mov lr, r8`, `bx` through registers), so it is most likely the LPC4350's Cortex-M0 coprocessor's.
- The USB audio interfaces (configuration descriptor at `0x20006048`, 304 bytes) are UAC2. They carry 8 channels each way in 4-byte slots of 24 bits. Endpoint `0x03` (iso OUT, from the computer) and `0x83` (iso IN, to it) each take up to 224 bytes a microframe.
- **I2S0 is the 8-channel audio link with the SHARC.** DAO/DAI are `0x7fb`/`0x87fb` (32-bit words, WS half-period 32, slave). The FIFO service at `0x20000bb0` counts words modulo 8 (`ands` with 7 in `[ctx+0x18]`) and resyncs on bit 0 of a received word. The callbacks are registered at `0x20000402` with context `0x20006338`: `0x20003311` gives the next word to send, `0x20003391` the place for the next word received, and `0x20003401` handles a resync.
- **The coprocessor is a straight pipe.** The receive callback `0x20003390` writes each word at the next 4 bytes of the current USB IN buffer (descriptor `[ctx+0x30] + 32 * [ctx+0x40]`: buffer `+0x10`, length `+0x18`) and steps through 8 buffers. Received I2S slot k is USB channel k + 1 to the computer, with no table between them. The send side marks slot 0 by bit 0 (`0x20003330`..).
- So USB 3/4 to the computer is whatever the SHARC puts in I2S slots 2 and 3, and nothing on the LPC side can tell the Send bus's copy for USB from its copy for the Send jacks. **A USB-only output has to be made in the SHARC.**

## The SHARC's audio ports (Entry 2) [verified offline]

- Entry 2's code: 11,635 48-bit instructions in PM at `0x8c100..0x8ee95` (tag 5). Everything else is VISA: 16-bit parcels at short-word addresses `0x13ac4a..0x183138` (tag 3, **high half first**, count in parcels; tag-1 zero fills between them are code too) and in DDR2 at `0x600000..` (tag 10 words at `0x300000..0x30d06e`, low half first). `tools/sharc/visa_dis.py` (#118) disassembles both. Its VISA forms match the ADSP-2136x/2137x/214xx Programming Reference rev 2.4, chapter 10. Register names are checked against the ADSP-214xx Hardware Reference rev 1.1, Appendix B.
- IOP register addresses (def21469.h, SPORT `SPCTLn` at `0xc00`/`0xc01`/`0x400`/`0x401`/`0x800`/`0x801`/`0x4800`/`0x4801`, SRU at `0x2430..0x247b`) appear as 32-bit immediates in VISA 48-bit parcels `1002 0000 <reg>` (read) and `1102 0000 <reg>` (write, **[hypothesis]** type 14 `ureg <-> DM(addr32)`):
  - The DAI/SRU routing is set up at short-word `0x6092d0..0x609650` (SRU_PIN0..4, SRU_PBEN0..3, SRU_CLK0/4/5, SRU_DAT0, SRU_FS0/4).
  - The SPORT DMA chain pointers are cleared at `0x60925f..0x609290` (CPSP0A, 0B, 1A, 2A, 4A, 4B, 5A, 6A), and SPCTL0, 1, 5 and 6 are written at `0x609296..0x6092b0`.
  - The 48-bit PM code also writes SPCTL2 (19 places, from `0x8c11e`), SPCTL4 (`0x8c129`..), SRU_CLK2 (`0x8c49f`), SRU_CLK4 (`0x8d39d`..) and SRU_DAT1 (`0x8e64e`).
- **The SRU setup's pattern** [verified offline, `visa_dis.py`]: `1002 0000 <reg>` reads the register into R2, `cc2X` ANDs it with a mask in RX, `cd2X` ORs in a value from RX, and `1102 0000 <reg>` writes it back. The masks and values come from `0f8r hhhh` (32-bit parcel pair: Rr = a 16-bit immediate) and `0f0r hhhh llll` (48-bit: Rr = a 32-bit immediate). Each DMA chain pointer is loaded from DM (`1002 000e 14xx` is `R2 = DM(0xe14xx)`, a load; a NOP follows) and stored to its CPSP.
- **SPORT modes** [verified offline: the immediates stored to SPCTLn at `0x609296..0x6092b0`, decoded with the ADSP-2146x SPCTL fields, I2S mode]. Every SPORT runs in I2S mode (OPMODE, bit 11) with 32-bit words (SLEN 31). So 8 channels come in and 8 go out, as stereo pairs:

  | SPORT | SPCTL | direction, data channels |
  |---|---|---|
  | 0 | `0x013d29f1` | receive, A and B |
  | 1 | `0x000d29f1` | receive, A |
  | 2 | `0x000d29f1` | receive, A |
  | 4 | `0x033d29f1` | transmit, A and B |
  | 5 | `0x020d29f1` | transmit, A |
  | 6 | `0x020d29f1` | transmit, A |

  **[hypothesis]** The LPC link is one receiving and one transmitting SPORT clocked at four times the sample rate (8 words a 48 kHz sample, as the LPC side counts). SRU_CLK5 and SRU_FS4 (SPORT6/7's clock and frame sync) get their own source, `0x1d`, at `0x609641`/`0x609649`. Its SHARC→LPC side is then SPORT6 A, and USB 3/4 are its words 2 and 3 of each 8.
- **SRU writes** (replayed from the `1002`/`cc`/`cd`/`1102` sequences): SRU_DAT0 gets fields `0x5000`, `0x0e000000`, `0x11` and `0x480`, SRU_CLK0 and SRU_FS0 get the same values (`0x7000`, `0x38000000`, `0x1d`, `0x3a0`, `0x01d00000`), and SRU_CLK4 gets `0x6` and `0xc0`. Reading them as routing needs the DAI chapter's field codes and the board's pin wiring, not done.
- **The SPORT DMA chain pointers** come from an array of eight words at DM `0xe1492..0xe14ae`, 4 apart: SPORT2A `0xe1492`, 5A `0xe1496`, 0A `0xe149a`, 0B `0xe149e`, 1A `0xe14a2`, 4A `0xe14a6`, 4B `0xe14aa`, 6A `0xe14ae`. They are loaded at `0x60925b..0x60928c`. No code names those addresses as immediates, so whatever fills them uses a pointer.
- **`0x6082b3` is not the SPORT setup** (an earlier hypothesis, refuted with `visa_dis.py`). It builds five 7-word DMA blocks (`M3 = 7`) at `0xe1470..` after two 0x100-word copies from `0xc3cb6`/`0xc3eb6` into `0xe0f6a`. That is the 1 KB SPI link frames to the M4 (`m4/dsp-link.md`). Its object is at `0xc3c8f`, with handlers `0x173a0c`/`0x1739c7`.

## The SHARC's I/O: ports, main loop, and the I/O primitives [verified offline, `visa_dis.py`, 2026-11-16]

- **The SPORT driver** is at internal VISA `0x17615a..0x1762cf` and numbers eight ports:

  | port | SPORT | direction | buffer (words a block) |
  |---|---|---|---|
  | 0 | 2A | in, **from the computer (USB)** | 0x80 (16 samples × 8 slots) |
  | 1 | 5A | out, **to the computer (USB)** | 0x80 |
  | 2 | 0A | in | 0x20 (16 × stereo) |
  | 3 | 0B | in | 0x20 |
  | 4 | 1A | in | 0x20 |
  | 5 | 4A | out | 0x20 |
  | 6 | 4B | out | 0x20 |
  | 7 | 6A | out | 0x20 |

  - The setup `0x17615a(port, ...)` builds a ring of three TCBs a port. The TCB pointers are at DM `0xe1492 + 4 * port`, with the next two TCBs at `+0x20` and `+0x40`. The chain pointer bit (19) is set, and the buffers are consecutive at `R8 + n * length`.
  - The buffer length comes from jump table DM `0xc4cd9`: `0x80` for ports 0 and 1, `0x20` for the rest. The hypothesis that SPORT6 is the USB link is refuted.
  - `0x176228(port)` reads the port's DMA index register (`IISP2A 0x440`, `IISP5A 0x848`, `IISP0A 0xc40`, `0B 0xc44`, `1A 0xc48`, `4A 0x840`, `4B 0x844`, `6A 0x4840`; jump table `0xc4ce1`) and returns the buffer the core may use now.
- **The main loop** `0x1763a4..0x176460`:
  1. It waits for the block (`0x8eaf4(0xc5b3c)`).
  2. It stores each port's current buffer at DM `0xc5b44` (port 0), `0xc5b45` (port 1) and `0xc5b4c..0xc5b51` (ports 2..7).
  3. It runs the graph (`0x17418a`, with the object at DM `0xc4d11`).
- **Inputs and outputs are graph primitives.** Each instance's `DM(0,I0)` is a channel index, `I1` its input buffer (outputs) or `I2` its output buffer (inputs). Each works on 16 samples a block. Registry rows are at DM `0x200000`:

  | primitive | registry | process | what |
  |---|---|---|---|
  | `0x2a94` | `0x200000` | `0x8cdbb` | jack input, ports 2/3 (ch ≥ 3 is port 3), stereo; fixed → float |
  | `0x2a97` | `0x200008` | `0x8cdca` | jack input, port 4 |
  | `0x2a9b` | `0x200010` | `0x8cdd2` | USB input (port 0), finds the 8-slot frame by bit 0, then reads slot ch |
  | `0x2aa8` | `0x200018` | `0x8ce33` | jack output, port 5 (SP4A), stereo, ch parity = L/R |
  | `0x2aaa` | `0x200020` | `0x8ce36` | jack output, port 6 (SP4B) |
  | `0x2aac` | `0x200028` | `0x8ce11` | **USB output** (port 1): slot ch of 8 (`[0xc5b45] + ch`, stride 8). It clips, fixes, clears bit 0 and sets it on ch 0 only (the LPC's frame sync) |
  | `0x2aab` | `0x200030` | `0x8ce30` | jack output, port 7 (SP6A) |

  The outputs share init `0x60a5e2` and ctrl `0x60a5ed`; the inputs share `0x60a5ae` (or `0x60a5cf`) and ctrl `0x60a5b9`.
- So **USB 3/4 to the computer is the `0x2aac` instances with ch 2 and 3**, and the Send jacks are one of the jack-output writers (port 5, 6 or 7), ch pair unknown. They are separate primitive instances fed from the same bus. **[hypothesis]** A registry-wrapped jack-output writer that writes silence for the Send pair while Path A Out is on USB-only gives a true USB-only output (path A on Send, the Send jacks muted). The same writer, adding the Main writer's input, gives #93's Main+Send.
- **Composite `0x600000`** (49 members, 13 in, 6 out) is the fixed I/O block, and `0x600010` (31 members) is a smaller variant. `0x600000` holds:
  - jack inputs `0x2a94` ch 2 and 5, `0x2a97` ch 0 and 1;
  - USB inputs `0x2a9b` ch 2..7;
  - USB outputs `0x2aac` ch 4 and 5: USB 5/6 to the computer, the dry Main inputs.

  No composite in blob 0 holds a jack-output writer (`0x2aa8`/`0x2aaa`/`0x2aab`). Their instances sit in the app's top composite, which blob 0 does not hold.
- **Which writer is which** [verified on unit, 2026-11-16, post-send's probe images post-send-5 (payload `d05c1900…`) and post-send-6 (`8f1dba83…`); Main and phones corrected by post-send-7]:
  - The probe muted, then toned (3 kHz square), each (jack writer, ch) in turn. A preset had Main and Send both carrying plucks from USB 5/6 (path B on Send).
  - USB was recorded with Send L → Return L to USB 7/8, and a Volt 4 recorded the phones (input 1) and Main (input 2). The probes took them the other way round (input 1 Main, input 2 the phones), which swapped Main and the phones in the first version of this table. post-send-7 settled it: with Volume Knob Controls on Phones, the knob moved input 1 by 44 dB and left input 2 as it was, and the cables were confirmed.
  - Each output answered to exactly one key, in tone and in mute:

  | output | writer | ch | call order in a block |
  |---|---|---|---|
  | Main L (input 2) | `0x2aa8` (SP4A, port 5) | 1 (ch 0 is Main R) | 1st, 2nd (ch 0, ch 1) |
  | Send L | `0x2aaa` (SP4B, port 6) | 0 | 3rd |
  | Send R | `0x2aaa` (SP4B, port 6) | 1 | 4th |
  | phones (one side; input 1) | `0x2aab` (SP6A, port 7) | 0 | 5th |
  | phones (the other side) | `0x2aab` (SP6A, port 7) | 1 | 6th |

  - The call order comes from post-send-6. Muting `0x2aab` ch 0 dropped input 1 (the phones) by 36.1 dB. The call order is each writer instance's place among the jack writers in a block, written digitally to USB 6.
  - Only those six jack-writer instances run. Send R follows because `0x2aaa` has just the two instances and ch 0 is Send L.
  - In every block Main is written first, then Send, then the phones. So code in the phones' writer can add Main (kept by Main's writer) into the Send words in the same block: Main+Snd, `src/sharc/main_send.asm`.
  - Main's ch 1 is Main L: input 2 answered to ch 1, and its cable comes from Main L (2026-11-16).
  - The SP4A ch 7 dip in the first probe was the plucks (post-send's RMS shows none).
  - **Open:** in post-send-6's take, USB 7/8 to the computer was digital zero for the whole take, stock steps included. Its `0x2aac` wrapper changes ch 4 and 5. post-send-5 (ch 5 only) had the Return on 7/8. A take on plain `next` would rule the probe in or out.
- So **a USB-only output = Path A on Send, with the `0x2aaa` (SP4B) writer's ch 0 and 1 instances writing silence.** USB 3/4 (`0x2aac` ch 2, 3) still carries the Send bus.


## Blob 1 cannot change [verified on unit, 2026-11-16]

A new app parameter for the output mode needed blob 1 (HelixStomp_App) to grow. Every image that changed blob 1 froze at boot (RAM runs `usb-monitor-7*`, all with the same M4 and DSP code):

| image | blob 1 | boots |
|---|---|---|
| 7a, 7c, 7e, 7f | stock (M4 side; DSP wraps; Entry 3 string move; an Entry 3 app parameter with no blob change) | yes |
| 7j | stock words, moved to the end of Entry 4 | yes |
| 7k | its parameter map 2 zero words longer | no |
| 7h, 7b, 7g | an input node; a writer to [83, 10], with the tables copied or grown in place | no |
| 7m (`6ef1e863…`) | one word of table F's unused row 89, 0 → 1, same size | no |

So blob 1's contents are checked, not only its size: no feature may edit it.

## How the app turns its parameters into DSP calls [verified offline]

- A parameter map's nodes run inside blob 1, before any DSP code: op `0xa`/`0xb` float/int inputs, op 1 writers {path, pid, 1}, op 2 readers, op `0x43` (67) a test against one constant, op `0x58` (88) a lookup (table B). Table F lists nested maps, one per composite member that has parameters, with the same header; a write to a composite's path with pid k sets that member's map's slot k.
- **Path A's destination never reaches DSP code as a number.** `outputSelect.0` → [83] pid 3 → nested map 58 (the output block's), slot 3 → op 67 tests ==6 → [83] pid 1 (Send), ==1 and ==5 → op 88 → [83] pid 2 (Main). Any other value turns both off, which is why 2..4, 7 and 10..12 are silent. The tuner's output (`tunerOutputSelect` → [85] pid 3, nested map 17298) works the same way.
- **`usbInGain0_1` (USB Input Trim, slot 56, string 4209; the Global Setting USB In 1/2 Trim, I/O setting `0x99`)** goes from a float input straight to writers [99] pid 1 and [105] pid 1, nothing between: its raw float reaches those members' control function. USB monitoring sends its mode this way ([features/usb-monitor.md](../features/usb-monitor.md), which has how `0x99` was found). [verified on unit, 2026-11-20] It trims USB 1/2's playback on Main by its dB: with the trim at -18.8 dB, a pluck on USB 1/2 came back from Main L through Return L 18.7 dB lower in one session and 18.2 dB lower in another (a build without USB monitoring; [features/usb-monitor.md](../features/usb-monitor.md)).
- **`masterVolume`** (string 4197, the key of I/O setting `0x9d`, which `0x28d93d8c` writes from an event's float; [hypothesis] that this is the VOLUME knob's handler, by the function pointer at `0x28d96d84`) [verified offline: blob 1's parameter map]: a curve node (op 3) writes the phones' Level gains [133] and [134] pid 1 (root members 132 and 133), and an op `0x2b` node whose port 0 is `masterVolSelect` == 1 (Phones) passes it to Main's Level gains [119] and [123] pid 1 (members 118 and 122). By the op `0x2b` reading in [cores/gates.md](cores/gates.md) [hypothesis], Main's gain stays constant with Volume Knob Controls on Phones. So the VOLUME knob sets the phones and Main with Main+HP, and the phones alone with Phones [hypothesis: offline only; Main+HP not measured on the unit]. Main's side also rests on root switch 43: Main's Level gains (members 118 and 122) and the copy 119 are switched by it (condition word 86 = 2 × 43, read as in "Each destination is one bus" above; the copies 120 and 121, which take Main past the gains, have 87), and nothing we know of writes switch 43. [verified on unit, post-send-7] With Phones, the knob moved the phones by 44 dB and left Main as it was; Main+HP has not been measured.

## The app's members [verified offline]

- Blob 0's header words 10 and 11 (`0xaa`, `0x16`) are a root member list: 170 records of 20 words at word `0x16`, as composite members are (record word 0 its index, word 6 its type). Slot k of blob 1 is member k − 1; blob 1's node tree overrides some (slot 83: base `0x600009`, overridden to the output block `0x60000a`).
- Members 98 and 104 (slots 99 and 105), not overridden, are `0x80`, the Level gain (registry row `0x200298`, control `0x60f3e2`, process `0x8d7f5`), init (1, 0), (2, 0).
- The list's most common types: `0x600004` ×16, `0x60000b` ×8, `0x600008` ×7, `0x2391` ×7, `0x2aac` ×6, `0x80` ×6.
- **Where USB playback is mixed** [verified offline, 2026-11-20: the root member list's buffers traced from member 85 to 135]: USB 1/2's playback (`0x2a9b` ch 1 and 0, members 97 and 103) goes through the trims (98 and 104) and is added into Main after Global EQ (`0x2391`, 100 and 105), before Main's Level gains (118 and 122): those gains act on it as on the guitar (whether VOLUME drives them: masterVolume below [hypothesis]). USB 3/4's playback (`0x2a9b` ch 2 and 3, members 108 and 113) is added to the Send signal read from the bus (85 and 86, two `0x2618`, read mono buses 0 and 1; 111 and 116 add) with no gain and goes out the Send writer (127 and 128). USB out to the computer (89..92) is written before either is added.

## Open

- The physical Main output for values 2..4, 7 and 10..12: only USB was recorded for them.
- What HX Edit shows for path A's Output with Send/USB on.
