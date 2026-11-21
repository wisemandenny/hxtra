@ looper.s - the 1 Switch Looper's footswitch. With Looper Stop>Ply on Release, a press on a stopped loop opens the double-press
@ window as stock does but holds its play back: the release plays the loop as the stock press would have, and a 1 s hold instead
@ stops and clears it as the stock hold does after a double press, so nothing plays. With Looper DblPress on Release, a release
@ that finds the loop playing (not that of the press that stopped) sets the double-press window to the 21 ticks the stock release
@ gives the overdub it arms, so the window closes in the very tick that posts the overdub, and a second press before it stops.
@ Every other event, and every event with both settings on their stock values, goes to the stock state machine unchanged.
@ tools/features/looper.py owns the state machine 0x28d92490(switch, event) and enters looper_event with it in r2. The footswitch
@ handler sends it a release or a hold only for the switch whose press it latched, so one pending flag is that switch's.
.syntax unified
.thumb
.include "hxtra.inc"
.equ PRESS, 1
.equ RELEASE, 2
.equ HOLD, 5
.equ TAIL, 0                        @ an event none of its cases takes: it runs only its common tail, which starts the DSP listener
.equ RELEASE_PLAYS, 1               @ Stop>Ply's Release
.equ FROM_RELEASE, 0                @ DblPress's Release
.equ LOOPER, 0x28d9609d             @ () -> the looper object
.equ PLAY, 0x28de7c35               @ (looper): the Play verb, as the stock press calls it on a stopped loop
.equ STATE, 0x56                    @ the looper's state: 0 stopped, 1 playing, 2 recording, 3 overdubbing, 5 and 6 play once
.equ PLAYING, 1
.equ LOOP, 0x60                     @ a loop is recorded
.equ ACTED, 0x66                    @ halfword: the press started playback (a hold then clears) and acted (its release arms no overdub)
.equ SECOND, 0x68                   @ the second press of a double press is held: a hold while stopped stops and clears
.equ WINDOW, 0x74                   @ the double-press window in ticks, which a press opens
.equ WINDOW_TICKS, 20
.equ OVERDUB_TICKS, 21              @ the stock release's deferred overdub countdown; the tick counts the window down first

.thumb_func
looper_event:                       @ r0 the switch, r1 the event, r2 the stock state machine
    push {r3-r7, lr}
    mov r4, r0
    mov r5, r1
    mov r6, r2
    ldr r3, =LOOPER
    blx r3
    mov r7, r0
    adr r2, pending
    ldrb r0, [r2]
    movs r3, #0
    strb r3, [r2]                   @ any event ends a held-back play
    ldrb r1, [r7, #STATE]
    cmp r5, #PRESS
    beq press
    cmp r5, #RELEASE
    beq release
    cbz r0, stock
    cmp r5, #HOLD
    bne stock
    cbnz r1, stock                  @ playing since (MIDI, a Command Center command): the stock hold clears, as ACTED says
    ldrb r3, [r7, #LOOP]
    cbz r3, stock                   @ cleared since (as on a preset change): the stock hold does nothing
    movs r3, #1
    strb r3, [r7, #SECOND]
    b stock
release:
    cbz r0, window
    cbnz r1, window
    ldrb r3, [r7, #LOOP]
    cbz r3, window
    mov r0, r7
    ldr r3, =PLAY
    blx r3
window:
    ldrb r3, [r7, #SECOND]
    cbnz r3, stock                  @ the release of the press that stopped, even after MIDI's Play: the stock release clears SECOND
    ldrb r3, [r7, #STATE]           @ not r1: the held-back Play has changed the state since
    cmp r3, #PLAYING
    bne stock
    movs r0, #SETTING_LOOPER_DBL_PRESS
    movs r1, #SETTING_LOOPER_DBL_PRESS_MAX
    movs r2, #SETTING_LOOPER_DBL_PRESS_DEFAULT
    bl hxtra_setting_get
    cmp r0, #FROM_RELEASE
    bne stock
    movs r3, #OVERDUB_TICKS
    str r3, [r7, #WINDOW]
    b stock
press:
    ldr r3, [r7, #WINDOW]
    cbnz r3, stock                  @ a second press: the stock press stops
    ldrb r3, [r7, #LOOP]
    cbz r3, stock                   @ no loop: it records
    cbnz r1, stock                  @ not stopped: it closes the loop, ends the overdub or does nothing
    movs r0, #SETTING_LOOPER_STOP_PLAY
    movs r1, #SETTING_LOOPER_STOP_PLAY_MAX
    movs r2, #SETTING_LOOPER_STOP_PLAY_DEFAULT
    bl hxtra_setting_get
    cmp r0, #RELEASE_PLAYS
    bne stock
    movs r3, #WINDOW_TICKS
    str r3, [r7, #WINDOW]
    movw r3, #0x101
    strh r3, [r7, #ACTED]           @ as the stock press leaves it after its play
    adr r2, pending
    movs r3, #1
    strb r3, [r2]
    movs r5, #TAIL
stock:                              @ a tail call: the stock state machine returns to the caller
    mov r0, r4
    mov r1, r5
    mov r12, r6
    pop {r3-r7, lr}
    bx r12

.ltorg
.balign 4
pending:                            @ 1 while a press holds its play back for its release
    .space 4

HXTRA_SETTING_GET
