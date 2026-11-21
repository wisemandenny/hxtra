// gate_sc.asm - Input Sidechain on the Noise Gate block: its gate keyed by the input, as the Input block's gate hears it (#131).
// The Noise Gate runs the gate core, primitive 0x2720, which gates the 16 samples at I1 by the key at I1 + 16 into I2.
// The Input block's jack reader, primitive 0x2a94 (only in the Input block, ahead of its meters), arms SC_ARM: the next two
// meters, primitive 0x2390, are the Input block's on L and R, and leave (L + R) / 2 in SC_CAP, whether the Input gate runs or
// not. The core's control function takes the Noise Gate's Input Sidechain knob (tools/patch_sidechain.py's writers, pid
// SC_PID) into a table by core instance (its state: I0 here, R12's first word there); a core with the knob On gets SC_CAP as
// its key, if a capture came since its last block (else its own key, as stock). Every other core and meter runs as stock.
// tools/patch_sidechain.py places it in Block 3 (SC_DM_BASE, SC_PM_BASE).

.equ PEYEN,   0x200000
.equ BDCST9,  0x400000
.equ ORIG,    0x8e8f2                   // the gate core's stock process code
.equ ORIG_2A94, 0x8cdbb                 // the jack reader's
.equ ORIG_2390, 0x8da6a                 // the meter's
.equ HALF,    0x3F000000
.equ ORIG_CTRL_2720, 0x614b8b           // and its stock control function (compiled C, VISA code in DDR2)
.equ SC_PID,  100                       // Input Sidechain (0 or 1)
.equ N_INST,  16                        // cores tracked: eight stereo Noise Gates
.equ ENT,     4                         // an entry: state, Input Sidechain, last call's tick, captures seen
.equ BLOCK,   16                        // samples a call

.section dm SC_DM_BASE
SC_SAVE:  .space 9
SC_ARM:   .space 1                      // the Input block's meters still to come: 2 (L), 1 (R)
SC_TICK:  .space 1                      // calls of any tracked core: entries' ages, for reuse
SC_SEQ:   .space 1                      // captures so far
SC_CTMP:  .space 1
SC_CAP:   .space 16
SC_TAB:   .space 64                     // N_INST entries of ENT words
SC_END:   .space 5                      // the search's sentinel entry, and the word it reads past it

.section pm SC_PM_BASE
ENTRY_2720:
    DM(SC_SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    NOP;
    DM(SC_SAVE + 1) = R0;
    DM(SC_SAVE + 2) = R1;
    DM(SC_SAVE + 3) = R2;
    DM(SC_SAVE + 4) = I4;
    DM(SC_SAVE + 5) = I5;
    DM(SC_SAVE + 6) = M4;
    DM(SC_SAVE + 7) = L4;
    DM(SC_SAVE + 8) = L5;
    L4 = 0;
    R0 = I0;
    DM(SC_END) = R0;
    I4 = SC_TAB;
    M4 = ENT;
    R1 = DM(I4, M4);
s_find:
    COMP(R1, R0), R1 = DM(I4, M4);
    IF NE JUMP s_find;
    MODIFY(I4, -2 * ENT);
    R1 = I4;
    R2 = SC_END;
    COMP(R1, R2);
    IF EQ JUMP s_out;                   // no knob writes seen: as stock
    R1 = 0;                             // a Noise Gate: meters still armed for didn't run
    DM(SC_ARM) = R1;
    R1 = DM(SC_TICK);
    R1 = R1 + 1;
    DM(SC_TICK) = R1;
    DM(2, I4) = R1;
    R1 = DM(1, I4);
    R1 = PASS R1;
    IF EQ JUMP s_out;                   // Input Sidechain Off
    R1 = DM(SC_SEQ);
    R2 = DM(3, I4);
    COMP(R1, R2);
    IF EQ JUMP s_out;                   // nothing captured since its last block: its own key
    DM(3, I4) = R1;
    I4 = SC_CAP;
    I5 = I1;
    L5 = 0;
    MODIFY(I5, BLOCK);
s_copy:
    LCNTR = BLOCK, DO s_c UNTIL LCE;
      R1 = DM(I4, 1);
s_c:  DM(I5, 1) = R1;
s_out:
    R0 = DM(SC_SAVE + 1);
    R1 = DM(SC_SAVE + 2);
    R2 = DM(SC_SAVE + 3);
    I4 = DM(SC_SAVE + 4);
    I5 = DM(SC_SAVE + 5);
    M4 = DM(SC_SAVE + 6);
    L4 = DM(SC_SAVE + 7);
    L5 = DM(SC_SAVE + 8);
    MODE1 = DM(SC_SAVE + 0);
    NOP;
    JUMP ORIG;

ENTRY_2A94:                             // its stock code sets R0 first
    R0 = 2;
    DM(SC_ARM) = R0;
    JUMP ORIG_2A94;

ENTRY_2390:                             // its stock code sets R1..R4 before it reads them
    R2 = DM(SC_ARM);
    R2 = PASS R2;
    IF EQ JUMP ORIG_2390;
    DM(SC_SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    NOP;
    DM(SC_SAVE + 4) = I4;
    DM(SC_SAVE + 5) = I5;
    DM(SC_SAVE + 7) = L4;
    DM(SC_SAVE + 8) = L5;
    L4 = 0;
    L5 = 0;
    R1 = R2 - 1;
    DM(SC_ARM) = R1;
    I4 = I1;
    I5 = SC_CAP;
    R3 = HALF;
    R1 = 1;
    COMP(R2, R1);
    IF EQ JUMP m_r;
    LCNTR = BLOCK, DO m_l UNTIL LCE;    // L: half of it
      F1 = DM(I4, 1);
      F1 = F1 * F3;
m_l:  DM(I5, 1) = F1;
    JUMP m_out;
m_r:
    LCNTR = BLOCK, DO m_rl UNTIL LCE;   // R: plus half of it, and the capture is whole
      F1 = DM(I4, 1);
      F1 = F1 * F3;
      F2 = DM(0, I5);
      F1 = F1 + F2;
m_rl: DM(I5, 1) = F1;
    R1 = DM(SC_SEQ);
    R1 = R1 + 1;
    DM(SC_SEQ) = R1;
m_out:
    I4 = DM(SC_SAVE + 4);
    I5 = DM(SC_SAVE + 5);
    L4 = DM(SC_SAVE + 7);
    L5 = DM(SC_SAVE + 8);
    MODE1 = DM(SC_SAVE + 0);
    NOP;
    JUMP ORIG_2390;

CTRL_2720:                              // (pid R4, the value at R8, the core's state R12): a C function
    R2 = R4;
    R1 = SC_PID;
    COMP(R2, R1);
    IF NE JUMP ORIG_CTRL_2720;
    I4 = R8;
    R1 = 1;
    R8 = DM(0, I4);
    R8 = PASS R8;
    IF NE R8 = PASS R1;
    I4 = R12;
    R0 = DM(0, I4);
    I4 = SC_TAB;
    R2 = N_INST;
sc_find:                                // counted, as the process code may move the sentinel under it
    R1 = DM(0, I4);
    COMP(R1, R0);
    IF EQ JUMP sc_set;
    MODIFY(I4, ENT);
    R2 = R2 - 1;
    IF NE JUMP sc_find;
    DM(SC_CTMP) = R0;                   // a new core: the entry idle longest
    R0 = DM(SC_TICK);
    R4 = 0;
    I4 = SC_TAB;
    R12 = I4;
    R2 = N_INST;
sc_old:
    R1 = DM(0, I4);
    R1 = PASS R1;
    IF EQ JUMP sc_new;                  // a free one
    R1 = DM(2, I4);
    R1 = R0 - R1;
    COMPU(R1, R4);
    IF LE JUMP sc_next;
    R4 = PASS R1;
    R12 = I4;
sc_next:
    MODIFY(I4, ENT);
    R2 = R2 - 1;
    IF NE JUMP sc_old;
    I4 = R12;
sc_new:
    R1 = DM(SC_CTMP);
    DM(0, I4) = R1;
    DM(2, I4) = R0;
    R1 = DM(SC_SEQ);
    DM(3, I4) = R1;
sc_set:
    DM(1, I4) = R8;
    R0 = 0;
    I12 = DM(M7, I6);
    JUMP (M14, I12) (DB);
    NOP;
    RFRAME;
