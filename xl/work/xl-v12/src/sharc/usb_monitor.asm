// usb_monitor.asm - Path A Out's output modes in the DSP (issues #81, #93), around two stock primitives:
//   the Level gain 0x80's control function takes the mode from USB Input Trim (usbInGain0_1, pid 1 of the app's [99] and [105]):
//   the M4 sends trim + 1000 * (mode + 1) (src/m4/usb_monitor.s), so a value above CODE_MIN is the mode, kept in USB_MODE (0..3),
//   and the trim, handed on to the stock function; every other value and pid goes to the stock function as it came;
//   the Send jacks' writer 0x2aaa writes silence while USB_MODE is USB_ONLY, so path A on the Send bus reaches only USB 3/4.
// USB_MODE is the one mode word every output-writer wrapper reads (DECISIONS.md, "Output modes share one mode word").
// tools/patch_usbmon.py places it in Block 3 (UM_DM_BASE, UM_PM_BASE).
.equ PEYEN,   0x200000
.equ BDCST9,  0x400000
.equ ORIG_2AAA, 0x8ce36                 // the Send jacks' writer's stock process code (port 6, SPORT4 B)
.equ ORIG_CTRL_80, 0x60f3e2             // the Level gain's stock control function (compiled C, VISA code in DDR2)
.equ GAIN_PID, 1
.equ CODE_MIN, 0x43FA0000               // 500.0: no Level or trim comes near it
.equ THOUSANDTH, 0x3A83126F             // 0.001
.equ HALF, 0x3F000000                   // 0.5
.equ THOUSAND, 0x447A0000               // 1000.0
.equ MODE_MAX, 3                        // 0 Main L/R, 1 Send/USB, 2 USB Only, 3 Main+Snd
.equ USB_ONLY, 2
.equ BLOCK,   16                        // samples a call

.section dm UM_DM_BASE
USB_MODE: .space 1
U_I1:     .space 1
U_SAVE:   .space 3
U_ZERO:   .space BLOCK                  // a silent input

.section pm UM_PM_BASE
ENTRY_2AAA:                             // the Send jacks' writer: I0 its instance (DM(0, I0) the channel), I1 its 16-sample input
    DM(U_I1) = I1;
    DM(U_SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    NOP;
    DM(U_SAVE + 1) = R0;
    DM(U_SAVE + 2) = R1;
    R0 = DM(USB_MODE);
    R1 = USB_ONLY;
    COMP(R0, R1);
    IF NE JUMP s_call;
    I1 = U_ZERO;
s_call:
    R0 = DM(U_SAVE + 1);
    R1 = DM(U_SAVE + 2);
    MODE1 = DM(U_SAVE + 0);
    NOP;
    CALL ORIG_2AAA;
    I1 = DM(U_I1);
    RTS;

CTRL_80:                                // (pid R4, the value at R8, the gain's state R12): a C function
    R2 = GAIN_PID;
    COMP(R4, R2);
    IF NE JUMP ORIG_CTRL_80;
    I4 = R8;
    R0 = DM(0, I4);
    R2 = CODE_MIN;
    COMP(F0, F2);
    IF LE JUMP ORIG_CTRL_80;
    R2 = THOUSANDTH;
    F1 = F0 * F2;
    R2 = HALF;
    F1 = F1 + F2;
    R1 = TRUNC F1;                      // mode + 1
    R2 = 1;
    R1 = R1 - R2;
    R2 = MODE_MAX;
    COMPU(R1, R2);
    IF GT JUMP ORIG_CTRL_80;            // no mode of ours: as it came
    DM(USB_MODE) = R1;
    R2 = 1;
    R1 = R1 + R2;
    F1 = FLOAT R1;
    R2 = THOUSAND;
    F1 = F1 * F2;
    F0 = F0 - F1;
    DM(0, I4) = R0;                     // the trim alone
    JUMP ORIG_CTRL_80;
