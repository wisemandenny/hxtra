@ usb_input.s - HX Edit's editor service gets one more command, CMD, whose parameter is a string of UI events, 8 bytes each
@ {class, code, 0, 0, u32 value}: the unit queues them with the key queue's put (0x28db88fc), as its footswitches, knobs and
@ buttons queue theirs, so its UI task posts them in turn and nothing can tell them from the real controls (tools/hx_input.py).
@ The reply is {0x66: seq, 0x67: 0, 0x68: nil}; a parameter that is not 1..MAX events gets the dispatcher's error reply, and so
@ does a queue that stays full (then the events before it are queued). tools/features/usb_input.py chains ui_register after the
@ editor's command registration at boot.
.syntax unified
.thumb
.include "usb.inc"                  @ CMD: this feature's line in tools/usb_commands.py
.equ REGISTER, 0x28e165f1           @ (command, {first, then, 0}): the editor's command table
.equ NO_PARAMS, 0x28e19205          @ returns 0: the second call, as the command replies in the first
.equ SEND, 0x28e15b31               @ (stream, seq, status, result, [sp] its bytes): a whole reply
.equ PUT, 0x28db88fd                @ (event): the key queue's put, under its lock; it wakes the UI task
.equ QUEUE, 0x281f3db0              @ the key queue: 8000 bytes
.equ ROOM, 0x28db9a59               @ (queue) -> its free bytes; the put stops the unit (bkpt) with fewer than 8
.equ SLEEP, 0x28e24c59              @ (µs)
.equ EVENT, 8
.equ MAX, 16                        @ events a request
.equ SPARE, 64                      @ free bytes the put needs before it: other controls put theirs between the check and the put
.equ WAIT_US, 1000
.equ WAITS, 200
.equ FIXSTR, 0xa0                   @ MessagePack heads: hx_ctl packs bytes as a string, fixstr then str16 (old-style, no str8)
.equ STR16, 0xda
.equ STR8, 0xd9
.equ BIN8, 0xc4

ui_register:                        @ after the editor registers its commands at boot: CMD too
    push {r4, lr}
    sub sp, #16
    adr.w r0, ui_cmd
    orr r0, r0, #1
    ldr r1, =NO_PARAMS
    movs r2, #0
    str r0, [sp, #4]
    str r1, [sp, #8]
    str r2, [sp, #12]
    movs r0, #CMD
    add r1, sp, #4
    ldr r3, =REGISTER
    blx r3
    add sp, #16
    pop {r4, pc}

ui_cmd:                             @ r0 the stream, r1 the request {its bytes, their count, the parameter's offset, seq} -> r0
    push {r4-r8, lr}                @ the reply's result, or negative for the dispatcher's error reply
    sub sp, #16                     @ [sp] SEND's stack argument, [sp, #8] the event, aligned
    mov r7, r0
    mov r8, r1
    ldr r2, [r1]
    ldr r3, [r1, #4]
    ldr r4, [r1, #8]
    cmp r4, r3
    bhs ui_bad
    ldrb r0, [r2, r4]
    adds r4, #1
    and r5, r0, #0xe0
    cmp r5, #FIXSTR
    bne ui_head8
    and r5, r0, #0x1f
    b ui_length
ui_head8:
    cmp r0, #STR16
    beq ui_head16
    cmp r0, #STR8
    it ne
    cmpne r0, #BIN8
    bne ui_bad
    cmp r4, r3
    bhs ui_bad
    ldrb r5, [r2, r4]
    adds r4, #1
    b ui_length
ui_head16:                          @ a big-endian count
    adds r0, r4, #2
    cmp r0, r3
    bhi ui_bad
    ldrb r5, [r2, r4]
    adds r4, #1
    ldrb r0, [r2, r4]
    adds r4, #1
    orr r5, r0, r5, lsl #8
ui_length:                          @ r5 the parameter's bytes, from r2 + r4
    cbz r5, ui_bad
    tst r5, #EVENT - 1
    bne ui_bad
    cmp r5, #EVENT * MAX
    bhi ui_bad
    adds r0, r4, r5
    cmp r0, r3
    bhi ui_bad
    add r4, r2
    add r5, r4
ui_next:
    movs r6, #WAITS
ui_wait:
    ldr r0, =QUEUE
    ldr r3, =ROOM
    blx r3
    cmp r0, #SPARE
    bhs ui_put
    subs r6, #1
    beq ui_busy
    ldr r0, =WAIT_US
    ldr r3, =SLEEP
    blx r3
    b ui_wait
ui_put:
    add r0, sp, #8
    movs r1, #0
ui_copy:                            @ bytewise: the parameter may be at any address
    ldrb r2, [r4, r1]
    strb r2, [r0, r1]
    adds r1, #1
    cmp r1, #EVENT
    blo ui_copy
    ldr r3, =PUT
    blx r3
    adds r4, #EVENT
    cmp r4, r5
    blo ui_next
    movs r0, #1
    str r0, [sp]
    mov r0, r7
    ldrh r1, [r8, #0xc]
    movs r2, #0
    adr.w r3, ui_nil
    ldr r12, =SEND
    blx r12
    b ui_done
ui_busy:
    mvn r0, #15                     @ -16
    b ui_done
ui_bad:
    mvn r0, #2                      @ -3, as the stock commands refuse a parameter
ui_done:
    add sp, #16
    pop {r4-r8, pc}

.ltorg
ui_nil:
    .byte 0xc0
.align 2
