// fx_gate.asm - a noise gate on the FX Loop and Return blocks' returned signal, around their return reader (primitive 0x2618).
// The reader's process code fills the 16-sample buffer at I2 from its jack; this runs it, then gates that buffer in place.
// Its control function takes the blocks' Gate, Threshold and Decay knobs (tools/patch_gate.py's writers, pids GATE_PID..+2)
// into a table by reader instance (its state: I0 here, R12's first word there) and hands every other pid to the stock one.
// tools/patch_gate.py places it in Block 3 (GATE_DM_BASE, GATE_PM_BASE).

.equ PEYEN,   0x200000
.equ BDCST9,  0x400000
.equ ORIG,    0x8d872                   // the reader's stock process code
.equ ORIG_CTRL_2618, 0x60f99a           // and its stock control function (compiled C, VISA code in DDR2)
.equ GATE_PID, 100                      // Gate (0 or 1), Threshold (dB), Decay (s): past the reader's own pid 1
.equ N_INST,  8                         // readers tracked: four stereo blocks
.equ ENT,     6                         // an entry: state, on, threshold (linear), decay coefficient, envelope, gain
.equ BLOCK,   16                        // samples a call
.equ ONE,     0x3F800000
.equ REL,     0x3F7FBBE7                // the envelope's fall a sample: 20 ms at 48 kHz
.equ ATT,     0x3CA8F5C3                // the gain's rise towards 1 a sample when open: 1 ms (0.0206)
.equ DB2LOG2, 0x3E2A1499                // 1 / 6.0206: dB to powers of 2
.equ P1,      0x3F317218                // 2^f ~ 1 + f (P1 + f (P2 + f P3)) for -1 < f <= 0
.equ P2,      0x3E75FDF0
.equ P3,      0x3D635847
.equ K60,     0x3916E728                // ln 1000 / 48000: the decay coefficient is 1 - K60 / Decay (60 dB in Decay seconds)

.section dm GATE_DM_BASE
G_I0:     .space 1
G_I2:     .space 1
G_SAVE:   .space 13
G_TAB:    .space 48                     // N_INST entries of ENT words

.section pm GATE_PM_BASE
ENTRY_2618:
    DM(G_I0) = I0;
    DM(G_I2) = I2;
    CALL ORIG;
    DM(G_SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    NOP;
    DM(G_SAVE + 1) = R0;
    DM(G_SAVE + 2) = R1;
    DM(G_SAVE + 3) = R2;
    DM(G_SAVE + 4) = R3;
    DM(G_SAVE + 5) = R4;
    DM(G_SAVE + 6) = R5;
    DM(G_SAVE + 7) = R6;
    DM(G_SAVE + 8) = R7;
    DM(G_SAVE + 9) = R8;
    DM(G_SAVE + 10) = R9;
    DM(G_SAVE + 11) = I4;
    DM(G_SAVE + 12) = L4;
    L4 = 0;
    R0 = DM(G_I0);                      // this reader's entry
    I4 = G_TAB;
    R2 = N_INST;
g_find:
    R1 = DM(0, I4);
    COMP(R1, R0);
    IF EQ JUMP g_have;
    MODIFY(I4, ENT);
    R2 = R2 - 1;
    IF NE JUMP g_find;
    JUMP g_out;                         // no knobs seen for this reader: as stock
g_have:
    R1 = DM(1, I4);
    R1 = PASS R1;
    IF EQ JUMP g_out;                   // Gate Off
    F3 = DM(2, I4);                     // threshold
    F4 = DM(3, I4);                     // decay coefficient
    F5 = DM(4, I4);                     // envelope
    F6 = DM(5, I4);                     // gain
    R2 = I4;
    R7 = REL;
    R8 = ONE;
    R9 = ATT;
    I4 = DM(G_I2);
    LCNTR = BLOCK, DO g_l UNTIL LCE;
      F0 = DM(0, I4);
      F1 = ABS F0;
      F5 = F5 * F7;
      F5 = MAX(F5, F1);
      F1 = F8 - F6;                     // open: towards 1
      F1 = F1 * F9;
      F0 = F6 * F4;                     // closed: down by the decay coefficient
      F6 = F6 + F1;
      COMP(F5, F3);
      IF LT F6 = PASS F0;
      F0 = DM(0, I4);
      F0 = F0 * F6;
g_l:  DM(I4, 1) = F0;
    I4 = R2;
    DM(4, I4) = F5;
    DM(5, I4) = F6;
g_out:
    R0 = DM(G_SAVE + 1);
    R1 = DM(G_SAVE + 2);
    R2 = DM(G_SAVE + 3);
    R3 = DM(G_SAVE + 4);
    R4 = DM(G_SAVE + 5);
    R5 = DM(G_SAVE + 6);
    R6 = DM(G_SAVE + 7);
    R7 = DM(G_SAVE + 8);
    R8 = DM(G_SAVE + 9);
    R9 = DM(G_SAVE + 10);
    I4 = DM(G_SAVE + 11);
    L4 = DM(G_SAVE + 12);
    MODE1 = DM(G_SAVE + 0);
    NOP;
    RTS;

CTRL_2618:                              // (pid R4, the value at R8, the reader's state R12): a C function
    R2 = R4;
    R1 = GATE_PID;
    COMP(R2, R1);
    IF LT JUMP ORIG_CTRL_2618;
    R1 = GATE_PID + 2;
    COMP(R2, R1);
    IF GT JUMP ORIG_CTRL_2618;
    I4 = R8;
    R8 = DM(0, I4);                     // the value
    I4 = R12;
    R0 = DM(0, I4);
    I4 = G_TAB + ENT * (N_INST - 1);    // its entry, else the first free one (looking from the last), else the first
    R12 = G_TAB;
    R2 = N_INST;
gc_1:
    R1 = DM(0, I4);
    COMP(R1, R0);
    IF EQ JUMP gc_have;
    R1 = PASS R1;
    IF NE JUMP gc_2;
    R12 = I4;
gc_2:
    MODIFY(I4, -ENT);
    R2 = R2 - 1;
    IF NE JUMP gc_1;
    I4 = R12;
    DM(0, I4) = R0;
    R1 = 0;
    DM(1, I4) = R1;
    DM(4, I4) = R1;
    R1 = ONE;
    DM(2, I4) = R1;
    DM(5, I4) = R1;
    R1 = 0x3F7C0000;                    // a decay until one arrives
    DM(3, I4) = R1;
gc_have:
    R1 = R8;
    R2 = GATE_PID;
    COMP(R4, R2);
    IF NE JUMP gc_thr;
    DM(1, I4) = R1;                     // Gate: 0 or 1
    JUMP gc_ret;
gc_thr:
    R2 = GATE_PID + 1;
    COMP(R4, R2);
    IF NE JUMP gc_dec;
    R2 = DB2LOG2;                       // Threshold in dB -> 2^(dB / 6.0206)
    F1 = F1 * F2;
    R0 = TRUNC F1;                      // towards 0: n, and f = x - n in (-1, 0]
    F2 = FLOAT R0;
    F1 = F1 - F2;
    R2 = P3;
    F2 = F1 * F2;
    R12 = P2;
    F2 = F2 + F12;
    F2 = F1 * F2;
    R12 = P1;
    F2 = F2 + F12;
    F2 = F1 * F2;
    R12 = ONE;
    F2 = F2 + F12;
    F2 = SCALB F2 BY R0;
    DM(2, I4) = F2;
    JUMP gc_ret;
gc_dec:
    F12 = RECIPS F1;                    // Decay in s -> 1 - K60 / Decay
    R0 = 0x40000000;
    F2 = F1 * F12;
    F2 = F0 - F2;
    F12 = F12 * F2;
    F2 = F1 * F12;
    F2 = F0 - F2;
    F12 = F12 * F2;
    R2 = K60;
    F12 = F12 * F2;
    R2 = ONE;
    F2 = F2 - F12;
    DM(3, I4) = F2;
gc_ret:
    R0 = 0;
    I12 = DM(M7, I6);
    JUMP (M14, I12) (DB);
    NOP;
    RFRAME;
