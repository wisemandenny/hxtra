// midi_thru.asm - the MIDI block's kernel: the input to the output, unchanged. The block's knobs (pids 5..9:
// Channel, Type, Number, On Value, Off Value) reach DM(5..9, I0) and are not used here: the M4 reads them
// from the preset and sends the MIDI message (src/m4/midi_block.s). Called once per 16-sample block with
// I0 the instance's DM block, I1 the input and I2 the output.

.equ C_SAVE,   20                       // the caller's registers

.equ PEYEN,    0x200000
.equ BDCST9,   0x400000

.section pm KIT_PM_BASE

CUSTOM_AMP_ENTRY:
    DM(C_SAVE + 0, I0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    DM(C_SAVE + 1, I0) = R0;
    R0 = I4;                            // (a DAG1 register cannot be stored through I0)
    DM(C_SAVE + 2, I0) = R0;
    R0 = L4;
    DM(C_SAVE + 3, I0) = R0;
    R0 = I5;
    DM(C_SAVE + 4, I0) = R0;
    R0 = L5;
    DM(C_SAVE + 5, I0) = R0;
    L4 = 0;
    L5 = 0;
    I4 = I1;
    I5 = I2;

    LCNTR = 16, DO m_last UNTIL LCE;
      F0 = DM(I4, 1);
m_last: DM(I5, 1) = F0;

    R0 = DM(C_SAVE + 2, I0);
    I4 = R0;
    R0 = DM(C_SAVE + 3, I0);
    L4 = R0;
    R0 = DM(C_SAVE + 4, I0);
    I5 = R0;
    R0 = DM(C_SAVE + 5, I0);
    L5 = R0;
    R0 = DM(C_SAVE + 1, I0);
    MODE1 = DM(C_SAVE + 0, I0);
    NOP;
    RTS (LR);
