# Northern Audio: SHARC / M4 telemetry reference

SPDX-License-Identifier: GPL-3.0-or-later

Companion to [the Northern GR renderer](northern-gr-display.md). This is reference material for maintainers, not an enabled feature or a second transport to install alongside HXtra's GR feature.

Source: the Northern Audio Live 1.0 RC source package (Kompressor v0.15). Credit to Denny Wiseman, Derek Bui and HXtra / hx-stomp-nam-lite contributors. The frame discovery, halfword transport, callback and paint infrastructure came from HXtra. The Northern variant repurposed the existing GR fields to carry the custom compressor's own smoothed reduction value in dB instead of measuring an input/output ratio. No proprietary firmware or stock instruction bytes are reproduced here.

## Status and scope

- [verified on unit, tester report] The original combined Northern Audio firmware displayed responsive GR and numerical dB values, reacted to threshold/ratio and input signal, played both custom effects, and survived preset save and a power cycle.
- [verified offline in original project] The SHARC integration simulator exercised the kernel, wrapper and frame fields, including the counter and direct GR value. See original test excerpt below. This note is not a newly tested HXtra integration.
- [hypothesis] A versioned custom-effect telemetry payload, with instance identity, could be useful beyond GR. The current prototype does not identify the compressor instance in its packet. Multiple instances, mixed stock/custom GR producers, NAM placement, worst-case execution time and stale data behavior need explicit review.
- The original project did not measure numerical GR against physical audio attenuation. The value below is the smoothed reduction of the wet branch before dry/wet mix and output trim, not necessarily the reduction of the final mixed output. It is the final value of each 16-sample block, not a maximum across a UI update interval.

## Existing frame contract and incompatibility

The 256-word outgoing SPI frame and the scanner belong to the existing HXtra infrastructure; see [DSP link](../m4/dsp-link.md) and [GR meter](gr-meter.md).

| Word | M4 byte offset | Northern prototype (DSP-side representation) |
| --- | --- | --- |
| 200 | 800 | Marker 0x600DF00D (or 0xF00D600D for the other frame orientation) |
| 216 | 864 | IEEE float 1.0, sentinel |
| 217 | 868 | IEEE float positive reduction magnitude in dB, limited to 0..60 |
| 218 | 872 | 0x6B000004 |
| 250 | 1000 | Incrementing block counter |
| 251 | 1004 | IEEE float post-input-trim block peak, limited to 0..64 |

On M4 the payload floats/tag are halfword-rotated by 16 bits before decoding. The counter is compared in its received representation. **This is NOT wire-compatible with current HXtra GR.** In particular 0x6B000004 is not a new globally unique tag; it overlaps existing knob encodings. Do not select the Northern decoder using that tag alone. Do not install the prototype wrapper or decoder alongside the stock GR feature without negotiating separate ownership/protocol fields. The old marker and unity sentinel are not sufficient to distinguish all legitimate upstream data.

## SHARC producer: exact excerpts

From `kompressor_kernel.asm` at the gain update and block exit (unrelated processing omitted):

```asm
kp_gain:
    DM(49,I0) = F10;
    DM(54,I0) = F10; // actual gain reduction available for future GR meter
    F1 = -0.115129254649702;
    F0 = F10 * F1;
    CALL kp_exp16;
    F11 = PASS F0;
```

```asm
kp_sample_end: NOP;
    DM(65,I0) = F12; // block peak after input trim
    DM(64,I0) = F11; // actual compensated audio gain as linear multiplier, sampled once per 16 samples
    JUMP n_back;
```

From the modified `src/sharc/frame_probe.asm`. This is the actual Northern entry point, relying on HXtra's existing scanner, data allocations and restore/return code; the hard-coded process address is specific to our 3.80 build and must not be assumed available in current HXtra.

```asm
ENTRY_NORTHERN:
    DM(FP_I0) = I0;
    CALL 0xc4ef8;
    DM(FP_SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    NOP;
    DM(FP_SAVE + 1) = R0;
    DM(FP_SAVE + 2) = R1;
    DM(FP_SAVE + 3) = R2;
    DM(FP_SAVE + 4) = R3;
    DM(FP_SAVE + 5) = R4;
    DM(FP_SAVE + 6) = R5;
    DM(FP_SAVE + 7) = R6;
    DM(FP_SAVE + 8) = R7;
    DM(FP_SAVE + 9) = I4;
    DM(FP_SAVE + 10) = I5;
    DM(FP_SAVE + 11) = L4;
    DM(FP_SAVE + 12) = L5;
    L4 = 0; L5 = 0;
    R0 = 0x3f800000;
    DM(FP_WIN + 0) = R0;              // synthetic input gain 1.0, for ratio conversion on M4
    I4 = DM(FP_I0);
    F0 = DM(54,I4);                  // actual GR in dB, not inferred gain ratio
    F1 = 0.0;
    F0 = MAX(F0,F1);
    F1 = 60.0;
    F0 = MIN(F0,F1);
    DM(FP_WIN + 1) = F0;
    R0 = DM(FP_WC);
    R0 = R0 + 1;
    DM(FP_WC) = R0;
    DM(FP_WIN + 2) = R0;
    F0 = DM(65,I4);                  // input peak, post trim
    F1 = 0.0;
    F0 = MAX(F0,F1);
    F1 = 64.0;
    F0 = MIN(F0,F1);
    DM(FP_WIN + 3) = F0;
    R0 = 0x6b000004;               // V11 protocol: direct dB + peak
    DM(GR_PACK) = R0;
    R1 = DM(FP_CUR);
    R1 = PASS R1;
    IF NE JUMP fp_have;
    R1 = SCAN_A;
    JUMP fp_have;
```

The unity value is a sentinel in the final protocol, not an instruction to compute a ratio (the original source comment predates the direct-dB receiver). Existing HXtra discovery and write loop are reused. The relevant stores after validation of the frame boundaries are:

```asm
    DM(200, I4) = R6;
    R2 = DM(FP_WIN + 0);
    DM(216, I4) = R2;
    R2 = DM(FP_WIN + 1);
    DM(217, I4) = R2;
    R2 = DM(GR_PACK);
    DM(218, I4) = R2;
    R2 = DM(FP_WIN + 2);
    DM(250, I4) = R2;
    R2 = DM(FP_WIN + 3);
    DM(251, I4) = R2;
```

## M4 consumer: exact excerpt

From Northern `src/m4/gr_meter.s`, starting at the receive hook and ending before the input-indicator logic. It receives the frame in r1; no floating-point context is required. It validates the marker, payload and changing counter, then stores the accepted float bit pattern. The age counts RX callbacks rather than wall-clock time.

```asm
frame:
    push {r0-r7, lr}
    sub sp, #20
    mov r7, r1
    adr.w r4, data
    ldr r0, [r4, #28]
    adds r0, #1
    str r0, [r4, #28]
    ldr r0, [r4, #4]
    cmp.w r0, #1024
    it lo
    addlo r0, #1
    str r0, [r4, #4]
    ldr r0, [r7, #800]
    ldr r1, =0xf00d600d
    cmp r0, r1
    bne status
    movs r0, #1
    str r0, [r4, #12]
    ldr.w r0, [r7, #872]
    ror.w r0, r0, #16
    ldr r1, =0x6b000004
    cmp r0, r1
    bne status
    ldr r0, [r7, #864]
    movw r1, #0x3f80
    cmp r0, r1
    bne status
    ldr r1, [r7, #868]
    ror.w r2, r1, #16
    ldr r3, =0x42700000
    cmp r2, r3
    bhi status
    ldr.w r2, [r7, #1000]
    ldr r3, [r4, #52]
    cbz r3, first_window
    ldr r3, [r4, #24]
    cmp r2, r3
    beq status
    b new_window
first_window:
    cmp r2, #0
    beq status
new_window:
    str r2, [r4, #24]
    movs r2, #1
    str r2, [r4, #52]
    movs r2, #0
    str r2, [r4, #4]
    ror.w r1, r1, #16
    str r1, [r4, #0]
    ldr r0, [r4, #8]
    adds r0, #1
    str r0, [r4, #8]
```

The remainder of the original callback reads the peak from offset 1004, checks its float bit pattern against 0x42800000 (64), and then the status code checks marker seen, valid-window flag and age < 1024. The valid GR is compared against float bit patterns for 1..24 dB in an integer loop; the layout count saturates at 24. Invalid/stale data uses an empty meter and dashes. Redraw is requested on change at most every 16 RX callbacks. The existing HXtra shared callback hook and Edit paint hooks were used, with Home hooks disabled; model-name selection was restricted to HD2_DynNorthernKompressorUnits. The extracted renderer in this PR expects whole dB or an invalid sentinel, not the raw float bit pattern.

## ARM to SHARC: use the existing parameter path

There was no new generic control transport. We reused the upstream model-registration / parameter-map mechanism. Eight float inputs in Entry 3 and the host composite in Entry 4 map UI parameters to child parameter IDs (order 7, 5, 8, 9, 10, 11, 6, 15). The DSP reads actual values with units consistent with the UI (Threshold in dB, Ratio as a ratio, Attack stored in seconds, Release and Mix supplied as 0..1 fractions and displayed as percentages). See upstream model blob and registry notes.

The critical bug in early Northern revisions was that injecting the meter reinstalled the *stock* control registry entry, overwriting the custom registration. The UI changed but the algorithm did not receive its expected parameters. The repair was to replay the boot stream's tag-4 writes to obtain the **effective final** record, preserve it, and replace just its processing callback. These values are historical diagnostics specific to the Northern build; they are not allocations recommended for upstream.

From `build_meter.py`:

```python
def effective_registry_record(e2):
    """Replay all tag-4 writes to the eight registry words in boot-stream order."""
    words=struct.unpack('<%dI'%(len(e2)//4),e2)
    i=384; record=[None]*8; base=0x200590
    sizes={5:lambda n:((n+1)&~1)*3//2,4:lambda n:n,3:lambda n:(n+1)//2,
           6:lambda n:n*2,10:lambda n:n,9:lambda n:n,1:lambda n:0,2:lambda n:0}
    while i+3<=len(words):
        tag,n,addr=words[i:i+3]
        if tag==0: break
        if tag==4:
            for a in range(max(addr,base),min(addr+n,base+8)):
                record[a-base]=words[i+3+a-addr]
        if tag not in sizes: raise ValueError(f'Unknown LDR tag {tag}')
        i+=3+sizes[tag](n)
    if None in record: raise ValueError('Incomplete primitive registry record')
    return record
```

```python
    record=effective_registry_record(e2)
    expected=[0x9c75,0x611e90,0,0x611ef4,0x611ddd,0xc4ef8,0x91,0x0d]
    if record != expected:
        raise ValueError(f'Unexpected custom primitive record: {record!r}')
    record[5]=syms['ENTRY_NORTHERN']
    ldr+=pa.pack_init_l32(0x200590,record)
```

## Original offline regression case

The following is the core assertion sequence from `test_gr_e2e.py` after constructing a synthetic complete frame in the SHARC simulator and calling the custom kernel. It is supplied as reference, not a new executable upstream test (it requires the original Northern kernel, simulator setup and wrapper).

```python
    sim.call(syms['ENTRY_NORTHERN'],limit=100000)
    self.assertEqual(sim.rd(frame+200),0x600DF00D)
    self.assertEqual(sim.rd(frame+218),0x6b000004)
    self.assertEqual(sim.rd(frame+250),k+1)
    self.assertAlmostEqual(ssim.b2f(sim.rd(frame+216)),1.,delta=0.001)
    direct_gr=ssim.b2f(sim.rd(frame+217))
    gr=ssim.b2f(sim.rd(inst.i0+54))
    self.assertAlmostEqual(direct_gr,gr,delta=.002)
    self.assertAlmostEqual(ssim.b2f(sim.rd(frame+251)),ssim.b2f(sim.rd(inst.i0+65)),delta=.0001)
```

For integration, keep stock GR working; choose a distinct protocol/instance strategy with the maintainers, verify registry allocation and callback chaining, add producer/consumer tests for halfword encoding, malformed values, repeated/stale packets and instance changes, run upstream regression tests, and test the integrated implementation in RAM before enabling it. No firmware or build binaries accompany this contribution.
