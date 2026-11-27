@ phones_block.s - Global Settings > Ins/Outs > Phones Monitor with a third value, HP Block: the phones carry only what the Phones
@ blocks send them (tools/patch_phones.py, src/sharc/phones.asm). This Phones Monitor is a virtual setting in the stock one's slot
@ (tools/features/phones_block.py REPLACES): Main L/R and Send set the stock Phones Monitor as its knob would, HP Block sets it to
@ Main L/R (what the phones play if the DSP never hears of the mode) and turns the mode on. The mode rides to the DSP inside USB
@ Input Trim (USB In 1/2 Trim, I/O setting 0x99) as trim + 1000 * K, K = U + 5 * H: H = HP Block + 1, U = USB monitoring's
@ mode + 1, or 0 in a build without it. With USB monitoring, src/m4/usb_monitor.s sends the whole K after each send of path A's
@ destination, and a turn here asks it to send again (UM_RESEND). Alone, this module sends K = 5 * H with the context and app the
@ stock send of a path's destination (0x28df5760) has: after each such send (the boot, a preset load) and at each turn of the
@ setting [verified on unit: the trim's handle is found only with these].
.syntax unified
.thumb
.include "hxtra.inc"
.include "phones_block.inc"            @ UM_RESEND in a build with USB monitoring
.equ PHONES_ID, 0x9e                @ the stock Phones Monitor: 1 Main L/R, 2 Send
.equ STOCK_MAIN, 1
.equ STOCK_SEND, 2
.equ SEND_V, 1                      @ this setting: 0 Main L/R, 1 Send, 2 HP Block
.equ HP_BLOCK, 2
.equ UNSEEN, 0xff
.equ GET_VALUE, 0x28e1f845          @ (ID, &{type, value}): a Global Setting, < 0 when it has none
.equ SETTER_CONTEXT, 0x28e007ed     @ () -> the setter's context
.equ SETTER, 0x28e1f8f5             @ (context, ID, record {type, -, -, -, value}, source)
.equ PARAM_FIND, 0x28df35a1         @ (ctx, instance, name's Entry 3 string, &handle): an app parameter's handle, < 0 when it has none
.equ PARAM_SEND, 0x28df35e9         @ (ctx, instance, handle, &{u8 type, u32 value}): an app parameter to the DSP
.equ TRIM_NAME, 4209                @ usbInGain0_1, USB Input Trim
.equ TRIM_ID, 0x99                  @ its Global Setting, USB In 1/2 Trim (an I/O setting): GET_VALUE gives what the stock last sent
.equ CODE_STEP, 1000
.equ H_STEP, 5                      @ K = U + 5 * H (src/sharc/phones.asm): H = HP Block + 1, U = USB monitoring's mode + 1 or 0

.thumb_func
phones_block_dest_before:                     @ before 0x28df5760(ctx, app, path, value): its context and app, for the mode's sends
    adr r12, ph_ctx
    strd r0, r1, [r12]
    bx lr

.thumb_func
phones_block_dest_after:                      @ after it: the mode, so a rebuilt app (the boot, a preset) has it
    push {r3, lr}
    bl ph_mode
    pop {r3, pc}

.thumb_func
phones_block_changed:                         @ after the Global Settings slot repaint (view, ID): a turn of this setting
    cmp r1, #SETTING_PHONES_BLOCK_MONITOR
    it ne
    bxne lr
    b ph_sync

.thumb_func
phones_block_page:                            @ after the Global Settings page repaint: a click's reset to the default comes this way
    b ph_sync

ph_sync:                            @ the stock Phones Monitor kept in step. A turn of this one sets it; otherwise it sets this one (the
    push {r4, r5, r6, lr}           @ first paint, a change from HX Edit): Send is Send, Main L/R is Main L/R unless this is HP Block
    sub sp, #8
    bl ph_setting
    mov r4, r0
    movs r0, #PHONES_ID
    mov r1, sp
    ldr r3, =GET_VALUE
    blx r3
    cmp r0, #0
    blt ph_sync_done                @ no value: nothing to keep in step
    ldr r5, [sp, #4]
    adr r6, ph_seen
    ldrb r0, [r6]
    cmp r0, #UNSEEN
    beq ph_sync_stock
    cmp r0, r4
    beq ph_sync_stock
    cmp r4, #SEND_V                 @ this one turned: the stock follows
    ite eq
    moveq r1, #STOCK_SEND
    movne r1, #STOCK_MAIN
    cmp r1, r5
    beq ph_sync_mode
    str r1, [sp, #4]
    bl ph_set_stock
    b ph_sync_mode
ph_sync_stock:                      @ the stock decides
    mov r1, r4
    cmp r5, #STOCK_SEND
    bne 1f
    movs r1, #SEND_V
    b 2f
1:  cmp r4, #SEND_V
    it eq
    moveq r1, #0
2:  cmp r1, r4
    beq ph_sync_mode
    mov r4, r1
    movs r0, #SETTING_PHONES_BLOCK_MONITOR
    bl hxtra_setting_set
    strb r4, [r6]                   @ changed here: the DSP has the old value, sent with the boot's destination sends
    bl ph_mode
    b ph_sync_done
ph_sync_mode:
    ldrb r0, [r6]
    strb r4, [r6]
    cmp r0, #UNSEEN
    beq ph_sync_done                @ the first paint, in step: the boot's destination sends carried it
    cmp r0, r4
    it ne
    blne ph_mode
ph_sync_done:
    add sp, #8
    pop {r4, r5, r6, pc}

ph_set_stock:                       @ (-, -; the record {type, value} at the caller's sp): the stock Phones Monitor, as its knob writes it
    push {r4, lr}
    add r4, sp, #8                  @ the caller's record: past this push
    ldr r3, =SETTER_CONTEXT
    blx r3
    movs r1, #PHONES_ID
    mov r2, r4
    movs r3, #1
    ldr r12, =SETTER
    blx r12
    pop {r4, pc}

ph_setting:                         @ -> r0 this setting, 0..its max
    movs r0, #SETTING_PHONES_BLOCK_MONITOR
    movs r1, #SETTING_PHONES_BLOCK_MONITOR_MAX
    movs r2, #SETTING_PHONES_BLOCK_MONITOR_DEFAULT
    b hxtra_setting_get

ph_mode:                            @ the mode (H 2 for HP Block, else 1) to the DSP inside USB Input Trim
.ifdef UM_RESEND
    ldr r3, =UM_RESEND              @ USB monitoring sends the code word for both (usb_monitor.s um_resend): K = U + 5 * H
    bx r3
.endif
    push {r4-r7, lr}                @ alone: K = 5 * H, with the last destination send's ctx and app
    sub sp, #20                     @ the value {type, value} at sp, the handle at sp + 8, the trim {type, value} at sp + 12
    adr r0, ph_ctx
    ldrd r4, r5, [r0]
    cmp r4, #0
    beq ph_mode_done                @ none yet: the boot's destination sends will carry it
    ldr r4, [r4, #0xc]
    adds r4, #4                     @ the parameter context, as 0x28df5760 takes it
    ldr.w r5, [r5, #0xac8]          @ the app's instance
    mov r0, r4
    mov r1, r5
    movw r2, #TRIM_NAME
    add r3, sp, #8
    ldr r6, =PARAM_FIND
    blx r6                          @ looked up each time: a rebuilt app gets new handles
    cmp r0, #0
    blt ph_mode_done
    movs r0, #TRIM_ID
    add r1, sp, #12
    ldr r6, =GET_VALUE
    blx r6
    cmp r0, #0
    bge 1f
    movs r0, #0                     @ no trim stored: 0 dB, a float 0
    str r0, [sp, #12]
    str r0, [sp, #16]
1:  bl ph_code
    movw r1, #CODE_STEP
    muls r0, r1, r0
    vmov s0, r0
    vcvt.f32.s32 s0, s0
    vldr s1, [sp, #16]
    vadd.f32 s0, s0, s1
    vstr s0, [sp, #4]
    ldr r1, [sp, #12]
    strb r1, [sp]                   @ the trim's own type, as USB monitoring sends it
    mov r0, r4
    mov r1, r5
    ldr r2, [sp, #8]
    mov r3, sp
    ldr r6, =PARAM_SEND
    blx r6
ph_mode_done:
    add sp, #20
    pop {r4-r7, pc}

ph_code:                            @ -> r0 5 * H: 10 for HP Block, else 5
    push {r3, lr}
    bl ph_setting
    cmp r0, #HP_BLOCK
    ite eq
    moveq r0, #2 * H_STEP
    movne r0, #H_STEP
    pop {r3, pc}

HXTRA_SETTING_GET
HXTRA_SETTING_SET
.ltorg
.balign 4
ph_ctx:                             @ the last destination send's ctx and app
    .word 0, 0
ph_seen:                            @ this setting as last kept in step
    .byte UNSEEN
.balign 4
