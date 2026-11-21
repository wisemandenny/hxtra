// phones_send.asm - the Phones block's kernel: its input, at Level, added to both channels of the Phones bus (phones.asm), and its
// input at Dry Thru to its output. A primitive called once per 16-sample block with I0 the instance's DM block, I1 the input and
// I2 the output (the mono FX host). Knobs (the generic store puts pid p in DM(p, I0)): DM(5) Level dB, DM(6) Dry Thru dB; at
// their bottom (-60 dB) each is off. @PH_BUS@ is phones.asm's bus, filled in by tools/patch_phones.py.
.equ PEYEN,    0x200000
.equ BDCST9,   0x400000
.equ BUS,      @PH_BUS@
.equ C_SAVE,   100

.section pm KIT_PM_BASE

CUSTOM_AMP_ENTRY:
    DM(C_SAVE + 0, I0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    DM(C_SAVE + 1, I0) = R0;
    DM(C_SAVE + 2, I0) = R1;
    DM(C_SAVE + 3, I0) = R2;
    DM(C_SAVE + 14, I0) = R3;
    DM(C_SAVE + 4, I0) = R6;
    DM(C_SAVE + 5, I0) = R7;
    DM(C_SAVE + 6, I0) = R8;
    DM(C_SAVE + 7, I0) = R9;
    DM(C_SAVE + 8, I0) = R10;
    DM(C_SAVE + 9, I0) = R11;
    R0 = I4;
    DM(C_SAVE + 10, I0) = R0;
    R0 = L4;
    DM(C_SAVE + 11, I0) = R0;
    R0 = I5;
    DM(C_SAVE + 12, I0) = R0;
    R0 = L5;
    DM(C_SAVE + 13, I0) = R0;
    L4 = 0;
    L5 = 0;

    F8 = DM(5, I0);
    CALL p_gain;
    F7 = PASS F6;                       // the send
    F8 = DM(6, I0);
    CALL p_gain;                        // F6 the dry thru

    I4 = I1;
    I5 = BUS;
    LCNTR = 16, DO p_l UNTIL LCE;
      F0 = DM(I4, 1);
      F0 = F0 * F7;
      F1 = DM(0, I5);
      F1 = F1 + F0;
p_l:  DM(I5, 1) = F1;
    I4 = I1;
    I5 = BUS + 16;
    LCNTR = 16, DO p_r UNTIL LCE;
      F0 = DM(I4, 1);
      F0 = F0 * F7;
      F1 = DM(0, I5);
      F1 = F1 + F0;
p_r:  DM(I5, 1) = F1;
    I4 = I1;
    I5 = I2;
    LCNTR = 16, DO p_o UNTIL LCE;
      F0 = DM(I4, 1);
      F0 = F0 * F6;
p_o:  DM(I5, 1) = F0;

    R0 = DM(C_SAVE + 10, I0);
    I4 = R0;
    R0 = DM(C_SAVE + 11, I0);
    L4 = R0;
    R0 = DM(C_SAVE + 12, I0);
    I5 = R0;
    R0 = DM(C_SAVE + 13, I0);
    L5 = R0;
    R0 = DM(C_SAVE + 1, I0);
    R1 = DM(C_SAVE + 2, I0);
    R2 = DM(C_SAVE + 3, I0);
    R3 = DM(C_SAVE + 14, I0);
    R6 = DM(C_SAVE + 4, I0);
    R7 = DM(C_SAVE + 5, I0);
    R8 = DM(C_SAVE + 6, I0);
    R9 = DM(C_SAVE + 7, I0);
    R10 = DM(C_SAVE + 8, I0);
    R11 = DM(C_SAVE + 9, I0);
    MODE1 = DM(C_SAVE + 0, I0);
    NOP;
    RTS (LR);

// F8 dB -> F6 its gain, 0 at -59.9 dB and under: 2^(dB / 20 log2 10), 2^f by a cubic (click.asm's)
p_gain:
    F9 = -59.9;
    COMP(F8, F9);
    IF GT JUMP p_on;
    F6 = 0.0;
    RTS;
p_on:
    F9 = 0.16609640474;
    F8 = F8 * F9;
    F9 = 16.0;                          // (+16 keeps it positive for TRUNC)
    F8 = F8 + F9;
    R10 = TRUNC F8;
    F11 = FLOAT R10;
    F8 = F8 - F11;
    F6 = 0.0781633;
    F6 = F6 * F8;
    F9 = 0.2261586;
    F6 = F6 + F9;
    F6 = F6 * F8;
    F9 = 0.6951786;
    F6 = F6 + F9;
    F6 = F6 * F8;
    F9 = 1.0;
    F6 = F6 + F9;
    R9 = 16;
    R10 = R10 - R9;
    F6 = SCALB F6 BY R10;
    RTS;
