@ midi_block.s - the MIDI block's messages (tools/features/midi_block.py): 20 times a second, from the UI task's tick, every block
@ of the current preset whose model is the MIDI block (preset ID MIDI_PID, tools/patch_midi.py) is looked at: when one turns on or
@ off, or a preset loads with it, it sends what its knobs say on its channel (All: channels 1..16): a CC with On Value or Off Value,
@ or a PC of Number on turning on. The messages go out where the stock sends MIDI: the MIDI Out jack and USB.
@ What the preset is comes from the Play view's preset number and name texts: the current-preset call (0x28df024c) froze the unit
@ when called from this task [verified on unit].
.syntax unified
.thumb
.include "midi_block.inc"

.equ TICKS, 5                       @ 20 looks a second
.equ SLOTS, 40                      @ the block positions looked at: path A's and B's grids (path A's Output is 9)
.equ SENDER, 0x281252f0             @ the Command Center + 0x38: the MIDI sender's object
.equ KIND_CC, 3
.equ KIND_PC, 5
.equ UNKNOWN, 0xff

.macro CALL fn
    ldr r12, =(\fn) | 1
    blx r12
.endm


@ midi_block_post(event): before the key events' post (0x28db8830); its class-3 events are the UI task's 100 Hz tick
.thumb_func
midi_block_post:
    ldrb r1, [r0]
    cmp r1, #3
    it ne
    bxne lr
    push {r0, lr}
    bl midi_tick
    pop {r0, pc}

@ midi_tick(): from the UI task, 100 times a second
.thumb_func
midi_tick:
    adr.w r0, md_data
    ldrb r1, [r0]
    adds r1, #1
    cmp r1, #TICKS
    itt lo
    strblo r1, [r0]
    bxlo lr
    movs r1, #0
    strb r1, [r0]
    push {r3-r11, lr}               @ (r3 too: the stack stays 8-byte aligned for the calls)
    sub sp, #0x70                   @ +0 the bypass byte, +8 the preset ref, +0x10 the block info (0x34), +0x50 the message (16)
    adr.w r11, md_data
    ldr r0, =0x2812aae0 + 0x30      @ the Play view's preset number text, then its name: what the preset is, read without a lock
    add r1, sp, #8
    bl md_text4
    ldr r0, =0x2812aae0 + 0x8c
    add r1, sp, #12
    bl md_text4
    ldr r0, [sp, #8]
    ldr r1, [sp, #12]
    ldr r2, [r11, #4]
    ldr r3, [r11, #8]
    cmp r0, r2
    it eq
    cmpeq r1, r3
    beq md_same
    str r0, [r11, #4]               @ another preset: every block's message again
    str r1, [r11, #8]
    add r2, r11, #12
    movs r3, #UNKNOWN
    movs r1, #SLOTS
1:  strb r3, [r2], #1
    subs r1, #1
    bne 1b
md_same:
    movs r4, #0                     @ the slot
md_slot:
    mov r5, r4                      @ its block position (0x28df0280's kind): every one, 0..SLOTS-1
    add r6, r11, #12
    add r6, r4                      @ its last state: 0 off, 1 on, UNKNOWN
    add r0, sp, #0x10
    movs r1, #0
    movs r2, #0x34
    CALL 0x28e24b78
    CALL 0x28d92a98
    mov r1, r5
    add r2, sp, #0x10
    CALL 0x28e0fe94                 @ the block: its model's preset ID at +1
    cmp r0, #0
    blt md_none
    ldrb r0, [sp, #0x11]
    ldrb r1, [sp, #0x12]
    orr r0, r0, r1, lsl #8
    movw r1, #MIDI_PID
    cmp r0, r1
    bne md_none
    movs r0, #UNKNOWN
    strb r0, [sp]
    CALL 0x28d92a98
    mov r1, r5
    mov r2, sp
    CALL 0x28e04514                 @ bypassed: 1; unwritten for an unknown block
    ldrb r7, [sp]
    cmp r7, #UNKNOWN
    beq md_next
    eor r7, r7, #1                  @ on: 1
    ldrb r0, [r6]
    cmp r0, r7
    beq md_next
    strb r7, [r6]
    mov r0, r5
    movs r1, #0
    bl md_param
    mov r8, r0                      @ Channel
    mov r0, r5
    movs r1, #1
    bl md_param
    mov r9, r0                      @ Type: 0 CC, 1 PC
    mov r0, r5
    movs r1, #2
    bl md_param
    mov r10, r0                     @ Number
    mov r0, r5
    cmp r7, #0
    ite ne
    movne r1, #3                    @ On Value
    moveq r1, #4                    @ Off Value
    bl md_param
    and r3, r0, #0x7f               @ the value
    str r3, [sp, #4]
    and r10, r10, #0x7f
    cmp r9, #0
    bne md_pc
    movs r9, #KIND_CC
    b md_kind
md_pc:
    cmp r7, #0
    beq md_next                     @ PC: nothing when the block turns off
    movs r9, #KIND_PC
md_kind:
    subs r8, #1                     @ the channel, 0..15; -1: All
    cmp r8, #15
    it gt
    movgt r8, #15
    cmp r8, #0
    ite lt
    movlt r5, #15                   @ All: channels 1..16, one message each
    movge r5, r8
    it lt
    movlt r8, #0
md_ch:
    add r0, sp, #0x50
    movs r1, #0
    str r1, [r0]
    str r1, [r0, #4]
    str r1, [r0, #8]
    str r1, [r0, #12]
    strb r9, [r0]
    strb r8, [r0, #8]
    strb r10, [r0, #9]
    ldr r3, [sp, #4]
    strb r3, [r0, #10]
    mov r1, r0
    ldr r0, =SENDER
    CALL 0x28dacf6c
    adds r8, #1
    cmp r8, r5
    ble md_ch
    b md_next
md_none:
    movs r0, #UNKNOWN               @ no MIDI block here: when one comes, its message
    strb r0, [r6]
md_next:
    adds r4, #1
    cmp r4, #SLOTS
    blo md_slot
md_end:
    add sp, #0x70
    pop {r3-r11, pc}

@ md_text4(text widget, out): the first 4 bytes of its text (0 past its end, or with no text)
md_text4:
    ldr r0, [r0]
    movs r2, #0
    str r2, [r1]
    cbz r0, 2f
1:  ldrb r3, [r0, r2]
    cbz r3, 2f
    strb r3, [r1, r2]
    adds r2, #1
    cmp r2, #4
    blo 1b
2:  bx lr

@ md_param(code, index) -> the block's parameter index as a whole number (0 when it cannot be read)
md_param:
    push {r4-r6, lr}
    sub sp, #0x48                   @ +0, +4 the call's stack arguments; +8 the request (0x30); +0x38 the value {type, u32}
    mov r4, r0
    mov r5, r1
    add r0, sp, #8
    movs r1, #0
    movs r2, #0x40
    CALL 0x28e24b78
    movs r0, #0
    str r0, [sp]
    str r0, [sp, #4]
    mvn r0, #1                      @ -2: a parameter by its index
    str r0, [sp, #8]
    str r5, [sp, #12]
    CALL 0x28d92a98
    mov r1, r4
    add r2, sp, #8
    add r3, sp, #0x38
    CALL 0x28e11338
    cmp r0, #0
    blt md_param_none
    add r3, sp, #0x39               @ the value, unaligned
    ldrb r0, [r3]
    ldrb r1, [r3, #1]
    orr r0, r0, r1, lsl #8
    ldrb r1, [r3, #2]
    orr r0, r0, r1, lsl #16
    ldrb r1, [r3, #3]
    orr r0, r0, r1, lsl #24
    cmp r0, #0x10000
    blo md_param_done               @ a whole number
    lsrs r1, r0, #23                @ a float: rounded to a whole number (none here is negative or over 127)
    and r1, r1, #0xff
    rsbs r1, r1, #150               @ the shift
    ble md_param_none
    cmp r1, #24
    bgt md_param_none
    ubfx r2, r0, #0, #23
    orr r2, r2, #0x800000
    subs r1, #1
    movs r3, #1
    lsls r3, r1
    add r2, r3
    adds r1, #1
    lsr r0, r2, r1
    b md_param_done
md_param_none:
    movs r0, #0
md_param_done:
    add sp, #0x48
    pop {r4-r6, pc}

.ltorg
.align 2
md_data:                            @ +0 the tick count, +4 the preset seen (its number and name's first 4 bytes), +12 each slot's last state
    .word 0, 0xffffffff, 0xffffffff
    .space SLOTS
