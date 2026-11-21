// main_send.asm - Path A Out's Main+Snd (issue #93): while USB_MODE is MAIN_SEND, the Main jacks' writer 0x2aa8 (SP4A) keeps a
// copy of its 16 samples a channel, and the phones' writer 0x2aab (SP6A), which runs after the Send writer 0x2aaa (SP4B) in every
// block, adds that copy into the Send words of its own side: Main reaches the Send jacks at 0 dB, whatever the Volume knob does to
// the phones. The Send words are 32-bit fixed (FIX by 31), stride 2, Send ch 0 is L. USB out's writer 0x2aac runs before Main's in
// a block, so it adds its own USB 1/2 input (Main as the computer gets it) to USB 3/4 in the same block: USB 3/4 carries what the
// Send jacks do, as stock, in step with USB 1/2.
// tools/patch_usbmon.py appends it to usb_monitor.asm, whose USB_MODE and .equs it uses, with its data and code right after
// usb_monitor.asm's (SM_DM_BASE, SM_PM_BASE).
.equ ORIG_2AA8, 0x8ce33                 // Main's writer: stock process code
.equ ORIG_2AAB, 0x8ce30                 // the phones' writer: stock process code
.equ ORIG_2AAC, 0x8ce11                 // USB out's writer: stock process code
.equ USB3, 2                            // USB out's channel for USB 3
.equ SEND_BUF, 0xc5b50                  // DM word holding SP4B's buffer this block (the SPORT driver's port 6)
.equ MAIN_SEND, 3
.equ MAIN_FLIP, 1                       // Send ch s takes Main ch s XOR MAIN_FLIP: Main's ch 1 is L [verified on unit]

.section dm SM_DM_BASE
S_I1:     .space 1
S_SAVE:   .space 11
S_MAIN:   .space 32                     // Main's samples this block, ch 0 then ch 1
S_IN:     .space 1                      // the input USB out's writer gets
S_USB:    .space 17                     // USB 3 or 4 with Main added (the stock writer reads one word past its 16)
S_USB12:  .space 32                     // USB 1 and 2's input this block

.section pm SM_PM_BASE
ENTRY_2AA8:                             // I0 the instance (DM(0, I0) its channel), I1 its 16-sample input
    DM(S_I1) = I1;
    DM(S_SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    NOP;
    DM(S_SAVE + 1) = R0;
    DM(S_SAVE + 2) = R1;
    DM(S_SAVE + 5) = I4;
    DM(S_SAVE + 6) = L4;
    R0 = DM(USB_MODE);
    R1 = MAIN_SEND;
    COMP(R0, R1);
    IF NE JUMP m_call;
    R0 = DM(0, I0);
    R1 = 1;
    R0 = R0 AND R1;
    R0 = LSHIFT R0 BY 4;
    R1 = S_MAIN;
    R0 = R0 + R1;
    I4 = R0;                            // this channel's copy
    L4 = 0;
    L1 = 0;
    LCNTR = 16, DO m_l UNTIL LCE;
      R0 = DM(I1, 1);
m_l:  DM(I4, 1) = R0;
m_call:
    R0 = DM(S_SAVE + 1);
    R1 = DM(S_SAVE + 2);
    I4 = DM(S_SAVE + 5);
    L4 = DM(S_SAVE + 6);
    MODE1 = DM(S_SAVE + 0);
    NOP;
    I1 = DM(S_I1);
    CALL ORIG_2AA8;
    I1 = DM(S_I1);
    RTS;

ENTRY_2AAB:                             // I0 the instance (DM(0, I0) its channel), I1 its 16-sample input
    DM(S_I1) = I1;
    CALL ORIG_2AAB;
    DM(S_SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    NOP;
    DM(S_SAVE + 1) = R0;
    DM(S_SAVE + 2) = R1;
    DM(S_SAVE + 3) = R2;
    DM(S_SAVE + 4) = R3;
    DM(S_SAVE + 5) = I4;
    DM(S_SAVE + 6) = L4;
    DM(S_SAVE + 7) = I5;
    DM(S_SAVE + 8) = L5;
    DM(S_SAVE + 9) = M5;
    DM(S_SAVE + 10) = R4;
    R0 = DM(USB_MODE);
    R1 = MAIN_SEND;
    COMP(R0, R1);
    IF NE JUMP s_out;
    R0 = DM(0, I0);
    R1 = 1;
    R0 = R0 AND R1;                     // the Send side this instance fills
    R1 = DM(SEND_BUF);
    R1 = R0 + R1;
    I5 = R1;                            // Send's first word for this side
    R1 = MAIN_FLIP;
    R0 = R0 XOR R1;
    R0 = LSHIFT R0 BY 4;
    R1 = S_MAIN;
    R0 = R0 + R1;
    I4 = R0;                            // Main's copy for this side
    L4 = 0;
    L5 = 0;
    M5 = 2;
    R2 = -31;
    R3 = 31;
    F4 = 0.99999988;                    // the writers' clip, 0x3f7ffffe
    LCNTR = 16, DO s_l UNTIL LCE;
      R1 = DM(0, I5);
      F1 = FLOAT R1 BY R2;              // Send's word as a float
      F0 = DM(I4, 1);
      F1 = F1 + F0;
      F1 = CLIP F1 BY F4;
      R1 = FIX F1 BY R3;
s_l:  DM(I5, M5) = R1;
s_out:
    R0 = DM(S_SAVE + 1);
    R1 = DM(S_SAVE + 2);
    R2 = DM(S_SAVE + 3);
    R3 = DM(S_SAVE + 4);
    I4 = DM(S_SAVE + 5);
    L4 = DM(S_SAVE + 6);
    I5 = DM(S_SAVE + 7);
    L5 = DM(S_SAVE + 8);
    M5 = DM(S_SAVE + 9);
    R4 = DM(S_SAVE + 10);
    MODE1 = DM(S_SAVE + 0);
    NOP;
    I1 = DM(S_I1);
    RTS;

ENTRY_2AAC:                             // I0 the instance (DM(0, I0) its channel: USB n is n - 1), I1 its 16-sample input
    DM(S_I1) = I1;
    DM(S_IN) = I1;
    DM(S_SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    NOP;
    DM(S_SAVE + 1) = R0;
    DM(S_SAVE + 2) = R1;
    DM(S_SAVE + 5) = I4;
    DM(S_SAVE + 6) = L4;
    DM(S_SAVE + 7) = I5;
    DM(S_SAVE + 8) = L5;
    R0 = DM(USB_MODE);
    R1 = MAIN_SEND;
    COMP(R0, R1);
    IF NE JUMP u_call;
    L1 = 0;
    L4 = 0;
    L5 = 0;
    R0 = DM(0, I0);
    R1 = 1;
    COMPU(R0, R1);
    IF GT JUMP u_add;
    R0 = LSHIFT R0 BY 4;                // USB 1 or 2: keep it
    R1 = S_USB12;
    R0 = R0 + R1;
    I4 = R0;
    LCNTR = 16, DO u_k UNTIL LCE;
      R0 = DM(I1, 1);
u_k:  DM(I4, 1) = R0;
    JUMP u_call;
u_add:
    R1 = USB3;
    R0 = R0 - R1;                       // 0 USB 3, 1 USB 4
    R1 = 1;
    COMPU(R0, R1);
    IF GT JUMP u_call;
    R0 = LSHIFT R0 BY 4;
    R1 = S_USB12;
    R0 = R0 + R1;
    I4 = R0;                            // USB 1 for USB 3, USB 2 for USB 4
    I5 = S_USB;
    LCNTR = 16, DO u_l UNTIL LCE;
      F0 = DM(I1, 1);
      F1 = DM(I4, 1);
      F0 = F0 + F1;
u_l:  DM(I5, 1) = F0;
    R0 = S_USB;
    DM(S_IN) = R0;
u_call:
    R0 = DM(S_SAVE + 1);
    R1 = DM(S_SAVE + 2);
    I4 = DM(S_SAVE + 5);
    L4 = DM(S_SAVE + 6);
    I5 = DM(S_SAVE + 7);
    L5 = DM(S_SAVE + 8);
    MODE1 = DM(S_SAVE + 0);
    NOP;
    I1 = DM(S_IN);
    CALL ORIG_2AAC;
    I1 = DM(S_I1);
    RTS;
