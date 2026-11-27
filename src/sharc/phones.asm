// phones.asm - Phones Monitor = HP Block (tools/features/phones_block.py): the phones carry only what Phones blocks (phones_send.asm)
// send them, through the Volume knob as stock; Main, Send and USB stay as they are. Two stock primitives are wrapped
// (tools/patch_phones.py):
//   the Level gain 0x80: its process notes each call's instance and input. The phones' two gains are the root graph's members 132
//   and 133 (0x80, in place on the buffers the phones' writers read), run just before the writers. While PH_MODE is on, the gain
//   whose instance is a phones gain gets the Phones bus for its channel in its buffer first, so the knob's gain applies to it.
//   Its control function takes the modes from USB Input Trim (pid 1 of the app's [99] and [105]): the M4 sends
//   trim + 1000 * K, K = U + 5 * H, U = USB monitoring's mode + 1 (1..4; 0 in a build without it) and H = HP Block + 1 (1, 2).
//   USB monitoring's alone sends K = U (src/m4/usb_monitor.s), the Phones block's alone K = 5 * H (src/m4/phones_block.s); with
//   both, usb_monitor.s sends the whole K. So a value above CODE_MIN with K 1..14 is ours: PH_MODE = H - 1 when H, USB
//   monitoring's mode word (@USB_MODE@, usb_monitor.asm's USB_MODE; a word of ours without it) = U - 1 when U, and the trim goes on
//   to the stock function. This replaces usb_monitor.asm's CTRL_80 in a build with both (tools/patch_usbmon.py leaves 0x80 alone).
//   the phones' writer 0x2aab: it learns its channel's gain instance (the 0x80 call of the last two whose output is its input).
//   The phones' gain empties its channel of the bus as it takes it (the blocks run after the writers in the root graph, so a
//   clear by the writer threw each block's send away before the gain saw it: verified on the unit, test14/15); the writer
//   empties it only while nobody takes it. It calls @NEXT_2AAB@: the stock writer, or in a build with USB monitoring
//   main_send.asm's ENTRY_2AAB, which calls the stock one (tools/patch_usbmon.py leaves 0x2aab to this wrapper).
// PH_DM_BASE, PH_PM_BASE: tools/patch_phones.py.
.equ PEYEN,   0x200000
.equ BDCST9,  0x400000
.equ ORIG_80, 0x8d7f5                   // the Level gain's stock process code
.equ ORIG_CTRL_80, 0x60f3e2             // and its control function (compiled C, VISA code in DDR2)
.equ NEXT_2AAB, @NEXT_2AAB@             // the phones' writer: its stock process code 0x8ce30 (port 7, SPORT6 A), or USB monitoring's wrapper
.equ GAIN_PID, 1
.equ CODE_MIN, 0x43FA0000               // 500.0: no Level or trim comes near it (usb_monitor.asm's)
.equ STEP_INV, 0x3A83126F               // 1 / 1000
.equ HALF, 0x3F000000
.equ STEP, 0x447A0000                   // 1000.0
.equ K_MAX, 14                          // U 4 + 5 * H 2
.equ H_STEP, 5
.equ BLOCK,   16

.section dm PH_DM_BASE
PH_MODE:  .space 1                      // 1: the phones carry the Phones bus
PH_GAIN:  .space 2                      // each phones channel's gain instance (its I0), 0 until learnt
G_LAST:   .space 4                      // the last two gain calls: I0, I2, then the one before
G_SAVE:   .space 12
W_I1:     .space 1
W_SAVE:   .space 12
C_K:      .space 1
C_SINK:   .space 1                      // USB monitoring's mode, in a build without it
PH_BUS:   .space 2 * BLOCK              // channel 0 then channel 1: what the Phones blocks send this block

.section pm PH_PM_BASE
ENTRY_80:                               // the Level gain's process: I0 its instance, I1 its input, I2 its output
    DM(G_SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    NOP;
    DM(G_SAVE + 1) = R0;
    DM(G_SAVE + 2) = R1;
    R0 = DM(G_LAST + 0);
    DM(G_LAST + 2) = R0;
    R0 = DM(G_LAST + 1);
    DM(G_LAST + 3) = R0;
    R0 = I0;
    DM(G_LAST + 0) = R0;
    R1 = I2;
    DM(G_LAST + 1) = R1;                // its output: what a writer reads
    R1 = DM(PH_MODE);
    R1 = PASS R1;
    IF EQ JUMP g_out;
    R1 = DM(PH_GAIN + 0);
    COMP(R0, R1);
    IF EQ JUMP g_ch0;
    R1 = DM(PH_GAIN + 1);
    COMP(R0, R1);
    IF NE JUMP g_out;
    R0 = PH_BUS + BLOCK;
    JUMP g_copy;
g_ch0:
    R0 = PH_BUS;
g_copy:
    DM(G_SAVE + 3) = I4;
    DM(G_SAVE + 4) = L4;
    DM(G_SAVE + 5) = I5;
    DM(G_SAVE + 6) = L5;
    I4 = R0;
    R1 = I1;
    I5 = R1;
    L4 = 0;
    L5 = 0;
    R1 = 0;
    LCNTR = BLOCK, DO g_l UNTIL LCE;    // the bus's channel taken, and emptied: whenever the blocks run in the graph
      R0 = DM(0, I4);                   // (after the writers, as the root list has them), what they sent since is here
      DM(I4, 1) = R1;
g_l:  DM(I5, 1) = R0;
    I4 = DM(G_SAVE + 3);
    L4 = DM(G_SAVE + 4);
    I5 = DM(G_SAVE + 5);
    L5 = DM(G_SAVE + 6);
g_out:
    R0 = DM(G_SAVE + 1);
    R1 = DM(G_SAVE + 2);
    MODE1 = DM(G_SAVE + 0);
    NOP;
    JUMP ORIG_80;

CTRL_80:                                // (pid R4, the value at R8, the gain's state R12): a C function. R0, R1, R2 and I4 only,
    R2 = GAIN_PID;                      // as the C runtime lets a callee change them; R4, R8 and R12 go on to the stock function
    COMP(R4, R2);
    IF NE JUMP ORIG_CTRL_80;
    I4 = R8;
    R0 = DM(0, I4);
    R2 = CODE_MIN;
    COMP(F0, F2);
    IF LE JUMP ORIG_CTRL_80;
    R2 = STEP_INV;
    F1 = F0 * F2;
    R2 = HALF;
    F1 = F1 + F2;
    R1 = TRUNC F1;                      // K
    R2 = K_MAX;
    COMPU(R1, R2);
    IF GT JUMP ORIG_CTRL_80;            // no code of ours: as it came
    DM(C_K) = R1;
    F2 = FLOAT R1;
    R1 = STEP;
    F2 = F2 * F1;
    F0 = F0 - F2;
    DM(0, I4) = R0;                     // the trim alone
    R1 = DM(C_K);
    R0 = H_STEP;
    COMP(R1, R0);
    IF LT JUMP c_usb;                   // H 0: USB monitoring's alone
    R1 = R1 - R0;
    R2 = 0;
    COMP(R1, R0);
    IF LT JUMP c_set;
    R1 = R1 - R0;
    R2 = 1;
c_set:
    DM(PH_MODE) = R2;                   // H - 1
c_usb:
    R1 = PASS R1;                       // U
    IF EQ JUMP ORIG_CTRL_80;
    R2 = 1;
    R1 = R1 - R2;
    DM(@USB_MODE@) = R1;
    JUMP ORIG_CTRL_80;

ENTRY_2AAB:                             // the phones' writer: I0 its instance (DM(0, I0) its channel), I1 its 16-sample input
    DM(W_I1) = I1;
    DM(W_SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    NOP;
    DM(W_SAVE + 1) = R0;
    DM(W_SAVE + 2) = R1;
    DM(W_SAVE + 3) = R2;
    DM(W_SAVE + 4) = I4;
    DM(W_SAVE + 5) = L4;
    R2 = DM(0, I0);
    R1 = 1;
    R2 = R2 AND R1;                     // the channel
    R0 = I1;
    R1 = DM(G_LAST + 1);
    COMP(R0, R1);
    IF NE JUMP w_older;
    R1 = DM(G_LAST + 0);
    JUMP w_keep;
w_older:
    R1 = DM(G_LAST + 3);
    COMP(R0, R1);
    IF NE JUMP w_call;
    R1 = DM(G_LAST + 2);
w_keep:
    R0 = PH_GAIN;
    R0 = R0 + R2;
    I4 = R0;
    L4 = 0;
    DM(0, I4) = R1;                     // this channel's gain
w_call:
    R0 = DM(W_SAVE + 1);
    R1 = DM(W_SAVE + 2);
    R2 = DM(W_SAVE + 3);
    I4 = DM(W_SAVE + 4);
    L4 = DM(W_SAVE + 5);
    MODE1 = DM(W_SAVE + 0);
    NOP;
    I1 = DM(W_I1);
    CALL NEXT_2AAB;
    DM(W_SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    NOP;
    DM(W_SAVE + 1) = R0;
    DM(W_SAVE + 2) = R1;
    DM(W_SAVE + 3) = R2;
    DM(W_SAVE + 4) = I4;
    DM(W_SAVE + 5) = L4;
    R0 = DM(0, I0);
    R1 = 1;
    R0 = R0 AND R1;
    R1 = DM(PH_MODE);                   // nobody takes the bus (mode off, or this channel's gain not found yet): empty it
    R1 = PASS R1;
    IF EQ JUMP w_clear;
    R1 = PH_GAIN;
    R1 = R1 + R0;
    I4 = R1;
    L4 = 0;
    R1 = DM(0, I4);
    R1 = PASS R1;
    IF NE JUMP w_kept;
w_clear:
    R0 = LSHIFT R0 BY 4;
    R1 = PH_BUS;
    R0 = R0 + R1;
    I4 = R0;
    L4 = 0;
    R1 = 0;
    LCNTR = BLOCK, DO w_z UNTIL LCE;
w_z:  DM(I4, 1) = R1;
w_kept:
    R0 = DM(W_SAVE + 1);
    R1 = DM(W_SAVE + 2);
    R2 = DM(W_SAVE + 3);
    I4 = DM(W_SAVE + 4);
    L4 = DM(W_SAVE + 5);
    MODE1 = DM(W_SAVE + 0);
    NOP;
    I1 = DM(W_I1);
    RTS;
