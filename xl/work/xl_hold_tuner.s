.syntax unified
.thumb
.include "hxtra.inc"

.equ KEY_FIRST, 17
.equ TOUCH_FIRST, 9
.equ HOLD_SLOTS, 5
.equ STOCK_HANDLER, 0x28dd9c0d
.equ VIEW_IS, 0x28d98ce5
.equ REQUEST_VIEW, 0x28d98eed
.equ REQUEST_PANEL, 0x28d98f4d

.balign 4
.thumb_func
xl_hold_event:
    push {r4-r8, lr}
    sub sp, #8
    mov r4, r0
    mov r5, r1
    ldrb r2, [r4]
    cmp r2, #1
    bne pass
    ldrb r7, [r4, #1]
    adr.w r8, pending
    ldr r2, [r4, #4]
    subs r7, #KEY_FIRST
    cmp r7, #HOLD_SLOTS
    bhs touch
    bl eq_exit
    cmp r0, #0
    bne out
    ldr r2, [r4, #4]
    cmp r2, #1
    beq press
    cmp r2, #3
    beq click
    cmp r2, #5
    bne pass
    ldrb.w r2, [r8, r7]
    cmp r2, #0
    beq pass
    movs r2, #0
    strb.w r2, [r8, r7]
    bl eligible
    cmp r0, #0
    beq click_replay
    cmp r0, #1
    bne choose_switch
request_tuner:
    movs r0, #5
    ldr r3, =0x28d98ce5
    blx r3
    cmp r0, #0
    bne click_replay
    ldr r3, =0x28d9919d
    blx r3
    b held
choose_switch:
    cmp r0, #7
    blo virtual_hold
    @ Physical options follow VFS1..5 to preserve existing setting values.
    adds r0, #(KEY_FIRST + 3 - 7)
    lsls r0, #8
    orr r0, #1
    str r0, [sp]
    mov r0, sp
    bl replay_stock
    b held
virtual_hold:
    subs r0, #2
    mov r6, r0
    adr r0, function_ids
    ldrh.w r0, [r0, r6, lsl #1]
    movs r1, #12
    movs r2, #1
    bl hxtra_setting_get
    cmp r0, #0
    beq request_tuner
    cmp r0, #1
    bne virtual_snapshot
    mov r0, r6
    bl toggle_cc
    b held
virtual_snapshot:
    cmp r0, #4
    beq virtual_eq
    bhi virtual_preset
    adds r0, #6
    ldr r3, =XL_STEP_SNAPSHOT
    blx r3
    b held
virtual_preset:
    cmp r0, #7
    bhs virtual_bank
    bl step_preset
    b held
virtual_bank:
    cmp r0, #9
    beq virtual_bypass
    bhi virtual_exp
    bl step_bank
    b held
virtual_bypass:
    ldr r3, =0x28d994d9
    blx r3
    cmp r0, #0
    bne held
    movs r0, #1
    ldr r3, =0x28d99521
    blx r3
    b held
virtual_exp:
    cmp r0, #10
    bhi virtual_mode
    bl toggle_expression
    mov r0, r6
    bl toggle_cc
    b held
virtual_mode:
    bl step_mode
    b held
virtual_eq:
    movs r0, #8                  @ only open from the stock Home view
    ldr r3, =VIEW_IS
    blx r3
    cmp r0, #0
    beq click_replay
    movs r0, #5                  @ stock Global EQ menu shortcut
    ldr r3, =REQUEST_VIEW
    blx r3
    movs r0, #7
    ldr r3, =REQUEST_PANEL
    blx r3
held:
    adr.w r3, suppress_touch
    movs r2, #1
    strb r2, [r3, r7]
    b out
press:
    bl eligible
    strb.w r0, [r8, r7]
    cbz r0, pass
    b out
click:
    ldrb.w r2, [r8, r7]
    cbz r2, pass
    movs r2, #0
    strb.w r2, [r8, r7]
click_replay:
    ldr r0, [r4]
    str r0, [sp]
    mov r0, sp
    bl replay_stock
    b out
touch:
    adds r7, #(KEY_FIRST - TOUCH_FIRST)
    cmp r7, #HOLD_SLOTS
    bhs pass
    adr.w r3, suppress_touch
    cmp r2, #5
    beq touch_hold
    cmp r2, #1
    beq touch_reset
    cmp r2, #2
    bne pass
touch_reset:
    movs r2, #0
    strb r2, [r3, r7]
    b pass
touch_hold:
    ldrb.w r2, [r8, r7]
    cbnz r2, out
    ldrb r2, [r3, r7]
    cbnz r2, out
pass:
    mov r0, r4
    mov r1, r5
    bl stock
out:
    add sp, #8
    pop {r4-r8, pc}

.thumb_func
replay_stock:
    @ Send both events directly to stock so the target cannot start another hold.
    push {r4, lr}
    mov r4, r0
    movs r2, #1
    str r2, [r4, #4]
    mov r1, r5
    bl stock
    movs r2, #2
    str r2, [r4, #4]
    mov r0, r4
    mov r1, r5
    bl stock
    pop {r4, pc}

.thumb_func
stock:
    push.w {r4-r9, lr}
    ldr r12, =STOCK_HANDLER
    bx r12

.thumb_func
step_preset:
    push {r4, lr}
    sub sp, #8
    mov r4, r0
    mvn r1, #0
    str r1, [sp]
    movs r0, #0
    mov r1, sp
    movs r2, #0
    ldr r3, =0x28df6285
    blx r3
    ldr r1, [sp]
    cmp r1, #127
    bhi preset_done
    cmp r4, #5
    ite eq
    addeq r1, #1
    subne r1, #1
    and r1, r1, #127
    movs r0, #0
    ldr r3, =0x28df6339
    blx r3
    movs r0, #0
    str r0, [r5, #0x6c]
preset_done:
    add sp, #8
    pop {r4, pc}

.thumb_func
step_bank:
    @ Enter the XL's release cases after the physical pressed-state checks.
    @ The stock epilogue unwinds this frame and calls its own bank chooser.
    push {r4-r7, lr}
    sub sp, #0x1c
    mov r6, r5
    cmp r0, #7
    ite eq
    ldreq r3, =0x28dd9621
    ldrne r3, =0x28dd9687
    bx r3

.thumb_func
toggle_expression:
    push {r4, lr}
    ldr r3, =0x28d99509
    blx r3
    cmp r0, #2
    ite eq
    moveq r4, #1
    movne r4, #2
    mov r0, r4
    ldr r3, =0x28d99515
    blx r3
    ldr r3, =0x28d98c45
    blx r3
    cmp r4, #1
    ite eq
    ldreq r1, =0x28e42b90
    ldrne r1, =0x28e42b80
    ldr r3, =0x28dd5229
    blx r3
    ldr r3, =0x28d98c45
    blx r3
    movw r1, #500
    ldr r3, =0x28dd529d
    blx r3
    ldr r3, =0x28d9905d
    blx r3
    movs r0, #4
    ldr r3, =VIEW_IS
    blx r3
    cbnz r0, exp_done
    mov r0, r5
    movs r1, #1
    ldr r3, =0x28dd89cd
    blx r3
exp_done:
    pop {r4, pc}

.thumb_func
step_mode:
    push {r4, lr}
    sub sp, #8
    ldrb r4, [r5, #0x4d]
    cmp r4, #3
    bhi mode_done
    cmp r0, #11
    ite eq
    addeq r4, #1
    subne r4, #1
    and r4, r4, #3
    mov r0, r5
    mov r1, r4
    ldr r3, =0x28dd9301
    blx r3
    movs r0, #2
    str r0, [sp]
    str r4, [sp, #4]
    ldr r3, =0x28e0690d
    blx r3
    movs r1, #21
    mov r2, sp
    movs r3, #6
    ldr r12, =0x28e25d21
    blx r12
mode_done:
    add sp, #8
    pop {r4, pc}

.thumb_func
eq_exit:
    push {r4, lr}
    adr.w r4, eq_exiting
    add r4, r7
    ldrb r0, [r4]
    cbz r0, check_exit_press
    cmp r2, #2
    bne took_exit
    movs r0, #0
    strb r0, [r4]
    b took_exit
check_exit_press:
    cmp r2, #1
    bne pass_exit
    movs r0, #5
    ldr r3, =VIEW_IS
    blx r3
    cbz r0, pass_exit
    movs r0, #1
    strb r0, [r4]
    movs r2, #0
    strb.w r2, [r8, r7]
    adr.w r3, suppress_touch
    strb r0, [r3, r7]
    movs r0, #8                  @ stock Home shortcut
    ldr r3, =REQUEST_VIEW
    blx r3
    movs r0, #0
    ldr r3, =REQUEST_PANEL
    blx r3
took_exit:
    movs r0, #1
    pop {r4, pc}
pass_exit:
    movs r0, #0
    pop {r4, pc}

.thumb_func
eligible:
    push {r3, lr}
    sub sp, #16
    adr r0, hold_ids
    ldrh.w r0, [r0, r7, lsl #1]
    movs r1, #8
    movs r2, #0
    bl hxtra_setting_get
    cbz r0, disabled
    str r0, [sp]
    movs r0, #21
    add r1, sp, #4
    ldr r3, =0x28e25c71
    blx r3
    cmp r0, #0
    blt disabled
    ldr r0, [sp, #8]
    subs r0, #2
    cmp r0, #1
    bls disabled
    ldr r3, =0x28d98c0d
    blx r3
    add.w r0, r0, r7, lsl #1
    ldrb r0, [r0, #4]
    cmp r0, #2
    bne disabled
    ldr r3, =0x28d98c15
    blx r3
    mov r1, r7
    ldr r3, =0x28de05ad
    blx r3
    cmp r0, #0
    bne disabled
    ldr r0, [sp]
    b eligible_out
disabled:
    movs r0, #0
eligible_out:
    add sp, #16
    pop {r3, pc}

@ Scan the XL's live controller records under their stock mutex.
.thumb_func
toggle_cc:
    push {r4-r8, lr}
    sub sp, #8
    mov r8, r0
    add.w r4, r0, #20
    ldr r3, =0x28d98c1d
    blx r3
    mov r5, r0
    adds r0, #4
    ldr r3, =0x28e2ae81
    blx r3
    mvn r6, #0
    add.w r3, r5, #0xdc
    movs r2, #64
scan:
    ldrb r1, [r3, #0x44]
    cmp r1, #0x40
    beq next
    ldrb r1, [r3, #0x28]
    cmp r1, #2
    bne next
    ldrb r1, [r3, #0x10]
    cmp r1, #11
    bne next
    ldr r1, [r3, #0x14]
    cmp r1, r4
    bne next
    ldr r6, [r3, #0x2c]
    b scanned
next:
    adds r3, #0x48
    subs r2, #1
    bne scan
scanned:
    adds r0, r5, #4
    ldr r3, =0x28e2aef9
    blx r3
    movs r7, #0xff
    strb r7, [sp]
    adds r0, r6, #1
    beq latch
    ldr r3, =0x28d95249
    blx r3
    mov r1, r6
    mov r2, sp
    ldr r3, =0x28e0a825
    blx r3
    ldrb r7, [sp]
latch:
    adr.w r3, latched
    cmp r7, #0xff
    bne send
    ldrb.w r7, [r3, r8]
    eor r7, r7, #1
send:
    strb.w r7, [r3, r8]
    mov r0, r5
    movs r1, #11
    mov r2, r4
    movs r3, #0
    cmp r7, #0
    it ne
    movtne r3, #0x3f80
    ldr.w r12, =0x28de40d1
    blx r12
    add sp, #8
    pop {r4-r8, pc}

.thumb_func
vfs_cc_text:
    subs r2, r0, #20
    cmp r2, #4
    bhi ordinary_cc
    subs r1, #2
    movs r3, #'V'
    strb r3, [r1]
    movs r3, #'F'
    strb r3, [r1, #1]
    movs r3, #'S'
    strb r3, [r1, #2]
    adds r2, #'1'
    strb r2, [r1, #3]
    movs r3, #0
    strb r3, [r1, #4]
    bx lr
ordinary_cc:
    ldr r3, =0x28dadf09
    bx r3

.thumb_func
vfs_label_redraw:
    mov r2, r5
    b vfs_label
.thumb_func
vfs_label_refresh:
    mov r2, r4
vfs_label:
    cbz r2, ordinary_label
    ldr r2, [r2, #0x14]
    subs r2, #20
    cmp r2, #4
    bhi ordinary_label
    adr.w r1, vfs_label_text
ordinary_label:
    ldr r3, =0x28dc9511
    bx r3

HXTRA_SETTING_GET
.ltorg
.balign 4
vfs_label_text:
    .asciz "FootswIn"
.balign 4
hold_ids:
    .hword SETTING_LONG_PRESS_FS1, SETTING_LONG_PRESS_FS2, SETTING_LONG_PRESS_FS3, SETTING_LONG_PRESS_FS4, SETTING_LONG_PRESS_FS5
.balign 4
function_ids:
    .hword SETTING_LONG_PRESS_FS6_FUNCTION, SETTING_LONG_PRESS_FS7_FUNCTION, SETTING_LONG_PRESS_FS8_FUNCTION
    .hword SETTING_LONG_PRESS_FS9_FUNCTION, SETTING_LONG_PRESS_FS10_FUNCTION
.balign 4
pending:
    .space HOLD_SLOTS
.balign 4
suppress_touch:
    .space HOLD_SLOTS
.balign 4
latched:
    .space HOLD_SLOTS
.balign 4
eq_exiting:
    .space HOLD_SLOTS
.balign 4
