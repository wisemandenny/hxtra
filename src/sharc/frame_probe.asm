// frame_probe.asm - the GR meter's DSP side: a wrapper around the compressor cores (primitives 0x271a, 0x2719, 0x2710) that calls
// the stock process code and, for the metered core, measures the peaks of its input and output over a window; and their control
// functions, which keep the blocks' Mtr knobs. It finds the DSP's outgoing SPI frames in memory and writes into their unused tail
// what the M4 (src/m4/gr_meter.s) reads. tools/patch_comp.py places it in Block 3 above NAM's slots (GR_DM_BASE, GR_PM_BASE).
//
// A frame is 256 words: FACEF00D first, D00FECAF last (or both halfword-swapped). Once per block it scans a slice of internal
// and external memory for the first word, keeps the addresses whose word 255 is the matching last word, and writes into each:
// word 200 600DF00D, 216 and 217 the window peaks of input and output, 218 the knobs, 250 the window count, 251 the release
// coefficient over a window. Words 201..215, 219..249 and 252 are left alone.
//
// Every other core (other compressors, the 3-Band Comp's nine, the Busy One amps, the Sweep Echo) goes straight to the stock
// code: a preset near the DSP limit has no room for this wrapper's work on each of them (issue #84 froze the unit). With no
// metered core running nothing writes the tail, but the stock sender keeps sending the last words written, marker included: the
// M4 turns the meter off once word 250 has not changed for 1024 frames.

.equ MAGIC1,  0xFACEF00D
.equ MAGIC2,  0xF00DFACE
.equ TRAIL1,  0xD00FECAF
.equ TRAIL2,  0xECAFD00F
.equ PEYEN,   0x200000
.equ BDCST9,  0x400000
.equ SCAN_A,  0x80000                   // internal RAM, then the DDR2 the heaps use
.equ SCAN_B,  0x100000
.equ SCAN_C,  0x200000
.equ SCAN_D,  0x330000
.equ ORIG,    0x8d9c9                  // the stock process code of primitive 0x271a (Deluxe Comp, Rochester Comp)
.equ ORIG_2719, 0x8d342                 // and of 0x2719 (LA Studio Comp) and 0x2710 (Kinky Comp, Ampeg Opto Comp, Red Squeeze), which share it
.equ SLICE,   256                       // words looked at per call
.equ ORIG_CTRL_271A, 0x6100bd          // the stock control functions (compiled C, VISA code in DDR2)
.equ ORIG_CTRL_2719, 0x60cc71
.equ ORIG_CTRL_2710, 0x60cf8e
.equ N_FRAMES, 16                       // frames kept
.equ N_CORE,  16                        // cores kept
.equ CE,      6                         // a core's entry: state, Mtr Pos, Dir, Size, Release coefficient (0x2710), output in I1
.equ GR_PID,  100                       // patch_comp.py's GR Position, Direction and Thickness writers: pids 100..102, past every core's own
.equ GR_TAG,  0x6B000000
.equ WINDOW,  64                        // blocks per window peak: longer than a cycle of a low E; 1024 samples, as the Release power assumes

.section dm GR_DM_BASE
FP_SAVE:  .space 13
FP_CUR:   .space 1                      // the next address to look at (0: not started)
FP_N:     .space 1                      // frames found
FP_WA:    .space 1                      // the window peaks so far: A before, B after
FP_WB:    .space 1
FP_WN:    .space 1
FP_WC:    .space 1                      // windows so far
FP_KIND:  .space 1                      // the core being run: 0 Deluxe or Rochester Comp (0x271a), 1 LA Studio Comp (0x2719), 2 Kinky Comp, Ampeg Opto Comp or Red Squeeze (0x2710)
FP_R0:    .space 1
FP_R1:    .space 1
FP_I0:    .space 1                      // as called: the core's state, its buffers and its pm words
FP_I1:    .space 1
FP_I2:    .space 1
FP_I8:    .space 1
FP_A:     .space 1                      // this block's peaks: I1 before the call, I1 and I2 after it
FP_A1:    .space 1
FP_B:     .space 1
FP_WIN:   .space 4                      // the last window's A, B, count and Release coefficient: frame words 216, 217, 250, 251
FP_LIST:  .space 16                     // N_FRAMES frame addresses + 1
LA_REL:   .word 0x3F7FEED8              // the meter's fixed Release for the LA Studio Comp (500 ms), as a per-sample coefficient
GR_PACK:  .space 1
GR_CORE:  .space 1                      // the state (I0) of the core the meter shows: the last whose Mtr Size was set above Off
CORES:    .space 97                     // N_CORE entries of CE words, then the next entry to replace
FC_R3:    .space 1

.section pm GR_PM_BASE
ENTRY_271A:
    DM(FP_R0) = R0;
    R0 = 0;
    JUMP fp_entry;
ENTRY_2719:
    DM(FP_R0) = R0;
    R0 = 1;
    JUMP fp_entry;
ENTRY_2710:
    DM(FP_R0) = R0;
    R0 = 2;
fp_entry:
    DM(FP_KIND) = R0;
    DM(FP_R1) = R1;
    R0 = I0;
    R1 = DM(GR_CORE);
    COMP(R0, R1);
    R1 = DM(FP_R1);
    R0 = DM(FP_KIND);
    IF EQ JUMP fp_mine;
    R0 = PASS R0;
    R0 = DM(FP_R0);
    IF NE JUMP ORIG_2719;
    JUMP ORIG;
fp_mine:
    R0 = DM(FP_R0);
    DM(FP_I8) = I8;
    DM(FP_I1) = I1;                     // as called
    DM(FP_I2) = I2;
    DM(FP_I0) = I0;
    DM(FP_SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    NOP;
    DM(FP_SAVE + 1) = R0;
    DM(FP_SAVE + 2) = R1;
    DM(FP_SAVE + 9) = I4;
    I4 = DM(FP_I1);                     // the input's peak, before
    CALL fp_max;
    DM(FP_A) = R1;
    R0 = DM(FP_KIND);
    R0 = PASS R0;
    R0 = DM(FP_SAVE + 1);
    R1 = DM(FP_SAVE + 2);
    I4 = DM(FP_SAVE + 9);
    MODE1 = DM(FP_SAVE + 0);
    NOP;
    IF NE JUMP fp_la;
    CALL ORIG;
    JUMP fp_ran;
fp_la:
    CALL ORIG_2719;
fp_ran:
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

    I4 = DM(FP_I1);                     // and after
    CALL fp_max;
    DM(FP_A1) = R1;
    I4 = DM(FP_I2);
    CALL fp_max;
    DM(FP_B) = R1;
    R0 = DM(FP_I0);                     // the output is I2, or I1 for a core whose entry says so (patch_comp.py's pid GR_PID + 3)
    CALL fp_find;
    R2 = PASS R2;
    IF EQ JUMP fp_outb;
    R1 = DM(5, I4);
    R1 = PASS R1;
    IF EQ JUMP fp_outb;
    R0 = DM(FP_A1);
    DM(FP_B) = R0;
fp_outb:
    R0 = DM(FP_KIND);
    R0 = PASS R0;
    IF NE JUMP fp_peaks;
    I4 = DM(FP_I8);                     // the Deluxe core's gain, PM(1, I8) [verified offline]: as A = 1 / gain, B = 1, its reduction even on a pick's attack
    F1 = DM(1, I4);
    F1 = ABS F1;
    R0 = 0x358637BD;                    // 1e-6: -120 dB
    F1 = MAX(F0, F1);
    F0 = RECIPS F1;
    DM(FP_A) = R0;
    R0 = 0x3F800000;
    DM(FP_B) = R0;
fp_peaks:
    R0 = DM(FP_A);                      // window peaks: per-block peaks of input and output are taken at
    R1 = DM(FP_WA);                     // different points of the waveform when the core delays its output
    F1 = MAX(F0, F1);
    DM(FP_WA) = R1;
    R0 = DM(FP_B);
    R1 = DM(FP_WB);
    F1 = MAX(F0, F1);
    DM(FP_WB) = R1;
    R0 = DM(FP_WN);
    R0 = R0 + 1;
    R1 = WINDOW;
    COMP(R0, R1);
    IF LT JUMP fp_wkeep;
    R1 = DM(FP_WA);
    DM(FP_WIN + 0) = R1;
    R1 = DM(FP_WB);
    DM(FP_WIN + 1) = R1;
    R1 = DM(FP_WC);                     // a new window, for the M4 to tell apart from repeated frames
    R1 = R1 + 1;
    DM(FP_WC) = R1;
    DM(FP_WIN + 2) = R1;
    CALL fp_coef;                       // the comp's Release, a per-sample coefficient: to the power of a window's 1024 samples
    F1 = F1 * F1;
    F1 = F1 * F1;
    F1 = F1 * F1;
    F1 = F1 * F1;
    F1 = F1 * F1;
    F1 = F1 * F1;
    F1 = F1 * F1;
    F1 = F1 * F1;
    F1 = F1 * F1;
    F1 = F1 * F1;
    DM(FP_WIN + 3) = R1;
    R0 = 0;
    DM(FP_WA) = R0;
    DM(FP_WB) = R0;
fp_wkeep:
    DM(FP_WN) = R0;

fp_pack:
    R0 = DM(GR_CORE);                   // GR_TAG, Position, Direction, Thickness in bytes 3..0; 0 with no metered core
    R0 = PASS R0;
    IF EQ JUMP fp_bad;
    CALL fp_find;
    R2 = PASS R2;
    IF EQ JUMP fp_bad;
    R0 = 0;
    R1 = DM(1, I4);
    R2 = 4;
    CALL gr_inrange;
    R1 = DM(2, I4);
    R2 = 1;
    CALL gr_inrange;
    R1 = DM(3, I4);
    R2 = 20;
    CALL gr_inrange;
    R0 = PASS R0;
    IF NE JUMP fp_bad;
    R0 = DM(1, I4);
    R0 = LSHIFT R0 BY 16;
    R1 = DM(2, I4);
    R1 = LSHIFT R1 BY 8;
    R0 = R0 OR R1;
    R1 = DM(3, I4);
    R0 = R0 OR R1;
    R1 = GR_TAG;
    R0 = R0 OR R1;
    JUMP fp_nok;
fp_bad:
    R0 = 0;
fp_nok:
    DM(GR_PACK) = R0;

    // ---- look at the next slice, keeping each frame whose word 255 closes it
    R1 = DM(FP_CUR);
    R1 = PASS R1;
    IF NE JUMP fp_have;
    R1 = SCAN_A;
fp_have:
    R2 = SCAN_D;
    COMP(R1, R2);
    IF GE JUMP fp_write;                // all looked at
    I4 = R1;
    R3 = MAGIC1;
    R4 = MAGIC2;
    R2 = SLICE;
fp_scan:
    R5 = DM(I4, 1);
    R0 = TRAIL1;
    COMP(R5, R3);
    IF EQ JUMP fp_cand;
    R0 = TRAIL2;
    COMP(R5, R4);
    IF EQ JUMP fp_cand;
fp_next:
    R2 = R2 - 1;
    IF NE JUMP fp_scan;
    R1 = I4;
    R2 = SCAN_B;
    COMP(R1, R2);
    IF NE JUMP fp_cstore;
    R1 = SCAN_C;                        // internal RAM done: on to the DDR2
fp_cstore:
    DM(FP_CUR) = R1;
    JUMP fp_write;
fp_cand:                                // I4 is one past the first word
    R6 = DM(254, I4);
    COMP(R6, R0);
    IF NE JUMP fp_next;
    R0 = DM(FP_N);
    R6 = N_FRAMES;
    COMP(R0, R6);
    IF GE JUMP fp_next;
    R6 = FP_LIST;
    R6 = R6 + R0;
    I5 = R6;
    R6 = I4;
    DM(0, I5) = R6;
    R0 = R0 + 1;
    DM(FP_N) = R0;
    JUMP fp_next;

    // ---- the words the M4 reads, into every frame still whole
fp_write:
    R0 = DM(FP_N);
    R0 = PASS R0;
    IF EQ JUMP fp_out;
    I5 = FP_LIST;
fp_wr:
    R1 = DM(I5, 1);
    R1 = R1 - 1;
    I4 = R1;
    R2 = DM(I4, 0);
    R3 = MAGIC1;
    COMP(R2, R3);
    IF EQ JUMP fp_f1;
    R3 = MAGIC2;
    COMP(R2, R3);
    IF NE JUMP fp_skip;
    R3 = TRAIL2;
    R6 = 0xF00D600D;
    JUMP fp_chk;
fp_f1:
    R3 = TRAIL1;
    R6 = 0x600DF00D;
fp_chk:
    R2 = DM(255, I4);
    COMP(R2, R3);
    IF NE JUMP fp_skip;
    DM(200, I4) = R6;
    R2 = DM(FP_WIN + 0);
    DM(216, I4) = R2;
    R2 = DM(FP_WIN + 1);
    DM(217, I4) = R2;
    R2 = DM(GR_PACK);                   // in 218: a tag in word 253 never reached the M4
    DM(218, I4) = R2;
    R2 = DM(FP_WIN + 2);
    DM(250, I4) = R2;
    R2 = DM(FP_WIN + 3);
    DM(251, I4) = R2;
fp_skip:
    R0 = R0 - 1;
    IF NE JUMP fp_wr;

fp_out:
    R0 = DM(FP_SAVE + 1);
    R1 = DM(FP_SAVE + 2);
    R2 = DM(FP_SAVE + 3);
    R3 = DM(FP_SAVE + 4);
    R4 = DM(FP_SAVE + 5);
    R5 = DM(FP_SAVE + 6);
    R6 = DM(FP_SAVE + 7);
    R7 = DM(FP_SAVE + 8);
    I4 = DM(FP_SAVE + 9);
    I5 = DM(FP_SAVE + 10);
    L4 = DM(FP_SAVE + 11);
    L5 = DM(FP_SAVE + 12);
    MODE1 = DM(FP_SAVE + 0);
    NOP;
    RTS (LR);

gr_inrange:                             // R0 = 1 unless 0 <= R1 <= R2
    R1 = PASS R1;
    IF LT JUMP gr_bad;
    COMP(R1, R2);
    IF LE RTS;
gr_bad:
    R0 = 1;
    RTS;

fp_find:                                // I4 = the entry of state R0 and R2 = 1, or R2 = 0 when it has none; uses R1
    I4 = CORES;
    R2 = N_CORE;
ff_1:
    R1 = DM(0, I4);
    COMP(R1, R0);
    IF EQ JUMP ff_yes;
    MODIFY(I4, CE);
    R2 = R2 - 1;
    IF NE JUMP ff_1;
    RTS;
ff_yes:
    R2 = 1;
    RTS;

fp_coef:                                // R1 = the metered core's Release as a per-sample coefficient: the Deluxe's state word 3, a
    R0 = DM(FP_KIND);                   // Kinky's from its knob, else the LA Studio Comp's
    R0 = PASS R0;
    IF NE JUMP fp_cla;
    I4 = DM(FP_I0);
    R1 = DM(3, I4);
    RTS;
fp_cla:
    R1 = 2;
    COMP(R0, R1);
    IF NE JUMP fp_clr;
    R0 = DM(FP_I0);
    CALL fp_find;
    R2 = PASS R2;
    IF EQ JUMP fp_clr;
    R1 = DM(4, I4);
    R1 = PASS R1;
    IF NE RTS;
fp_clr:
    R1 = DM(LA_REL);
    RTS;

fp_max:                                 // R1 = the largest |sample| of the 16 words at I4
    R1 = 0;
    LCNTR = 16, DO fp_mx UNTIL LCE;
      F0 = DM(I4, 1);
      F0 = ABS F0;
fp_mx: F1 = MAX(F0, F1);
    RTS;

// The cores' control functions, called as (pid R4, pointer to the value R8, the core's state R12) [verified on unit]:
// pids GR_PID.. are the GR knobs, kept here for the frame; any other goes to the stock function untouched.
CTRL_271A:
    R2 = R4;
    R1 = GR_PID;
    COMP(R2, R1);
    IF LT JUMP ORIG_CTRL_271A;
    R1 = GR_PID + 3;
    COMP(R2, R1);
    IF GT JUMP ORIG_CTRL_271A;
    JUMP fc_take;
CTRL_2719:
    R2 = R4;
    R1 = GR_PID;
    COMP(R2, R1);
    IF LT JUMP ORIG_CTRL_2719;
    R1 = GR_PID + 3;
    COMP(R2, R1);
    IF GT JUMP ORIG_CTRL_2719;
    JUMP fc_take;
CTRL_2710:
    R2 = R4;
    R1 = 3;
    COMP(R2, R1);
    IF EQ JUMP fc_kk;
    R1 = GR_PID;
    COMP(R2, R1);
    IF LT JUMP ORIG_CTRL_2710;
    R1 = GR_PID + 3;
    COMP(R2, R1);
    IF GT JUMP ORIG_CTRL_2710;
fc_take:
    DM(FC_R3) = R3;
    I4 = R8;
    R1 = DM(0, I4);
    R2 = 0x1000;
    COMP(R1, R2);
    IF LT JUMP fc_int;                  // an integer as the input node has it, else a float
    R1 = FIX F1;
fc_int:
    I4 = R12;
    R0 = DM(0, I4);
    CALL fc_slot;
    R2 = GR_PID + 3;
    COMP(R4, R2);
    IF NE JUMP fc_kn;
    DM(5, I4) = R1;                     // pid GR_PID + 3: 1 when this core's output overwrites its first input I1
    JUMP fc_kn1;
fc_kn:
    R2 = GR_PID - 1;
    R2 = R4 - R2;
    M4 = R2;
    DM(M4, I4) = R1;
    R2 = GR_PID + 2;
    COMP(R4, R2);
    IF NE JUMP fc_kn1;
    R1 = PASS R1;
    IF EQ JUMP fc_koff;
    DM(GR_CORE) = R0;
    JUMP fc_kn1;
fc_koff:                                // the metered core's Mtr Size to Off: the meter goes to another core with one above Off, if any
    R2 = DM(GR_CORE);
    COMP(R2, R0);
    IF NE JUMP fc_kn1;
    I4 = CORES;
    R3 = N_CORE;
fc_ka:
    R2 = DM(3, I4);
    R2 = PASS R2;
    IF NE JUMP fc_kb;
    MODIFY(I4, CE);
    R3 = R3 - 1;
    IF NE JUMP fc_ka;
    JUMP fc_kn1;
fc_kb:
    R2 = DM(0, I4);
    DM(GR_CORE) = R2;
fc_kn1:
    R3 = DM(FC_R3);
fc_ret:
    I12 = DM(M7, I6);
    JUMP (M14, I12) (DB);
    NOP;
    RFRAME;

fc_kk:                                  // the Kinky Comp's Release (pid 3) in ms, kept for the meter as 1 - 2pi/(48 t), then passed on
    DM(FC_R3) = R3;
    I4 = R8;
    F0 = DM(0, I4);
    R2 = 0x3F800000;
    COMP(F0, F2);
    IF GE JUMP fc_k0;
    F0 = PASS F2;                       // at least 1 ms, where the coefficient's first-order form still holds
fc_k0:
    F1 = RECIPS F0;
    F3 = F0 * F1;
    F3 = F2 - F3;
    F3 = F1 * F3;
    F1 = F1 + F3;
    F3 = F0 * F1;
    F3 = F2 - F3;
    F3 = F1 * F3;
    F1 = F1 + F3;
    R3 = 0x3E060A92;                    // 2pi/48
    F1 = F1 * F3;
    F1 = F2 - F1;
    I4 = R12;
    R0 = DM(0, I4);
    CALL fc_slot;
    DM(4, I4) = R1;
    R3 = DM(FC_R3);
    JUMP ORIG_CTRL_2710;

fc_slot:                                // I4 = the entry of state R0 in CORES, taken and zeroed if new; uses R2, R3
    I4 = CORES;
    R3 = N_CORE;
fs_1:
    R2 = DM(0, I4);
    COMP(R2, R0);
    IF EQ RTS;
    MODIFY(I4, CE);
    R3 = R3 - 1;
    IF NE JUMP fs_1;
    I4 = CORES;
    R3 = N_CORE;
fs_2:
    R2 = DM(0, I4);
    R2 = PASS R2;
    IF EQ JUMP fs_new;
    MODIFY(I4, CE);
    R3 = R3 - 1;
    IF NE JUMP fs_2;
    R2 = DM(CORES + CE * N_CORE);       // full: replace entries in turn
    R3 = R2 + 1;
    R3 = BCLR R3 BY 4;
    DM(CORES + CE * N_CORE) = R3;
    R3 = LSHIFT R2 BY 1;                // CE = 6 words an entry
    R2 = LSHIFT R2 BY 2;
    R2 = R2 + R3;
    R3 = CORES;
    R2 = R2 + R3;
    I4 = R2;
fs_new:
    R2 = 0;
    DM(1, I4) = R2;
    DM(2, I4) = R2;
    DM(3, I4) = R2;
    DM(4, I4) = R2;
    DM(5, I4) = R2;
    DM(0, I4) = R0;
    RTS;
