@ tap_command.s - a Tap command in the Command Center: a footswitch whose slot holds it taps the tempo as the TAP footswitch does,
@ and its ring blinks the tempo as the TAP ring does. Kept in the preset as type 9, the CV Out the HX Stomp never offers, so stock
@ firmware reads such a preset as a command that does nothing. xl_tap_command.py installs the XL hooks.
.syntax unified
.thumb
.include "tap.inc"                  @ TAP_LED, TAP_LED_AGAIN: Tap LED Color's ring colour handlers, or 0 in a build without it
.equ TAP, 9                         @ the command type
.equ TAP_CHOICE, 7                  @ its place on the Command knob of an FS slot, after Hotkey
.equ FS_SLOT, 6                     @ the eight assignable footswitch slots are 6..13
.equ RINGS, 0x6
.equ CC, 0x28125340
.equ CC_TYPE, 0x74                  @ in it: each slot's command type
.equ FS_FUNCTIONS, 0x28128d6c
.equ STOMP, 2
.equ DEDICATED_TAP, 0x12
.equ FS_STATE, 0x28d98c0d
.equ FS_OBJ, 0x28d98c15
.equ FS_NODE, 0x28ddfba5
.equ NODE_ON, 0x20                  @ in a node: the command's on/off state, which the label and the ring show
.equ FOOTSWITCHES, 0x8
.equ FIRE, 0x28debb5d
.equ NODE_NAME, 0x28dde6f1
.equ NODE_LABEL, 0x24               @ in a node: its name, the label Home shows for a footswitch with no block
.equ STRCPY, 0x28dadced
.equ CHOICE, 0x28deb665
.equ STEP, 0x28dec4a1
.equ TAP_CORE, 0x28d9eed5
.equ GET_VALUE, 0x28e25c71
.equ TEMPO_SELECT, 14               @ 2 Global: the BPM is setting 15, else 16
.equ TAP_TEMPO_LED, 26
.equ EXT_CLOCK, 0x28d994cd
.equ LED_COLOUR, 0x28dbb309
.equ LED_MODE, 0x28dbb36d
.equ RED, 0x28e2e4f8
.equ BLUE, 0x28e2e4f4
.equ BEAT_PERIOD, 0x281cdd84
.equ BEAT_ON, 0x281cdd88

.thumb_func
.global tc_fire
tc_fire:                            @ the stomp toggle's fire (cc, slot, state, momentary): Tap taps, any other command fires as stock
    sub.w r12, r1, #FS_SLOT
    cmp r12, #FOOTSWITCHES - 1
    bhi fire_stock
    add.w r12, r0, r1
    ldrb.w r12, [r12, #CC_TYPE]
    cmp r12, #TAP
    beq 1f
fire_stock:
    ldr r12, =FIRE
    bx r12
1:  push {r4, lr}
    sub r4, r1, #FS_SLOT
    ldr r3, =TAP_CORE               @ through its entry, so the handlers chained there run
    blx r3
    mov r0, r4
    bl tc_lit                       @ the toggle flipped it before this call; the caller then lights the label from it
    bl tc_tempo
    pop {r4, pc}

tc_lit:                             @ (k): footswitch k's command shown on, as a Tap never toggles
    push {r4, lr}
    mov r4, r0
    ldr r3, =FS_OBJ
    blx r3
    mov r1, r4
    ldr r3, =FS_NODE
    blx r3
    cbz r0, 1f
    movs r1, #1
    strb r1, [r0, #NODE_ON]
1:  pop {r4, pc}

.thumb_func
.global tc_node
tc_node:                            @ the footswitch node insert's naming (node, type) -> 1 when the type has a node: Tap has one
    cmp r1, #TAP
    beq 1f
    ldr r12, =NODE_NAME
    bx r12
1:  push {r4, lr}
    adds r0, #NODE_LABEL
    adr.w r1, tc_name
    ldr r3, =STRCPY
    blx r3
    movs r0, #1
    pop {r4, pc}

.thumb_func
.global tc_choice
tc_choice:                          @ type -> place (cc, slot, type): on an FS slot Tap after Hotkey, Preset and the rest one later
    sub.w r12, r1, #FS_SLOT
    cmp r12, #FOOTSWITCHES - 1
    bhi 2f
    cmp r2, #TAP
    beq 1f
    push {r4, lr}
    ldr r3, =CHOICE
    blx r3
    cmp r0, #TAP_CHOICE
    it hs
    addhs r0, #1
    pop {r4, pc}
1:  movs r0, #TAP_CHOICE
    bx lr
2:  ldr r12, =CHOICE
    bx r12

.thumb_func
.global tc_step
tc_step:                            @ the Command knob's turn (cc, slot, type, turn) -> type: on an FS slot one place along tc_list
    sub.w r12, r1, #FS_SLOT
    cmp r12, #FOOTSWITCHES - 1
    bls 1f
    ldr r12, =STEP
    bx r12
1:  adr.w r1, tc_list
    movs r0, #0                     @ a type not on the list counts as None, as stock
2:  ldrb r12, [r1, r0]
    cmp r12, r2
    beq 3f
    adds r0, #1
    cmp r0, #LIST
    blo 2b
    movs r0, #0
3:  cmp r3, #0
    ble 4f
    cmp r0, #LIST - 1
    it lo
    addlo r0, #1
    b 5f
4:  cmp r0, #0                      @ a turn of 0 or less steps back, as stock
    it ne
    subne r0, #1
5:  ldrb r0, [r1, r0]
    bx lr

tc_active:                          @ -> r0 a bit for each ring whose footswitch is a Stomp switch with a Tap command
    ldr r1, =FS_FUNCTIONS
    ldr r2, =CC + CC_TYPE + FS_SLOT
    movs r0, #0
    movs r3, #RINGS - 1
1:  ldrb.w r12, [r1, r3, lsl #1]
    cmp r12, #STOMP
    bne 2f
    ldrb r12, [r2, r3]
    cmp r12, #TAP
    bne 2f
    movs r12, #1
    lsl.w r12, r12, r3
    orr.w r0, r0, r12
2:  subs r3, #1
    bpl 1b
    bx lr

.thumb_func
.global tc_running
tc_running:                         @ the stock beat's dedicated TAP check () -> state: one that says so too while a Tap ring is to blink
    push {r4, lr}
    ldr r3, =FS_STATE
    blx r3
    mov r4, r0
    ldrb r3, [r0, #DEDICATED_TAP]
    cmp r3, #1
    beq 1f
    bl tc_active
    cbz r0, 1f
    adr.w r4, tc_tap_state
1:  mov r0, r4
    pop {r4, pc}

.thumb_func
.global tc_on
tc_on:
    push {r4, lr}
    ldr r3, =FS_STATE
    blx r3
    mov r4, r0
    ldrb r3, [r0, #DEDICATED_TAP]
    cmp r3, #1
    beq on_return
    movs r0, #1
    bl tc_light_rings
on_return:
    mov r0, r4
    pop {r4, pc}

.thumb_func
.global tc_sync_on
tc_sync_on:
    push {r4, lr}
    ldr r3, =LED_MODE
    blx r3                       @ the dedicated ring's color is already set
    movs r0, #0
    bl tc_light_rings
    pop {r4, pc}

tc_light_rings:
    push {r4-r8, lr}
    mov r7, r0
    bl tc_active
    mov r5, r0
    movs r4, #0
1:  lsrs r5, r5, #1
    bcc 3f
    ldr r3, =EXT_CLOCK
    blx r3
    cbz r0, 2f
    ldr r1, =BLUE
    ldr r1, [r1]
    mov r0, r4
    ldr r3, =LED_COLOUR
    blx r3
    b 4f
2:  mov r0, r4
    ldr r1, =RED
    ldr r1, [r1]
    mov r2, r7
    bl tc_colour
    movs r7, #0
4:  mov r0, r4
    movs r1, #1
    ldr r3, =LED_MODE
    blx r3
3:  adds r4, #1
    cmp r5, #0
    bne 1b
    pop {r4, r5, r6, r7, r8, pc}

tc_colour:                          @ (led, red, next): the ring's colour; with next, Tap LED Color's next one, else the one it shows
.if TAP_LED
    cbz r2, 1f
    ldr r3, =TAP_LED
    bx r3
1:  ldr r3, =TAP_LED_AGAIN
    bx r3
.else
    ldr r3, =LED_COLOUR
    bx r3
.endif

.thumb_func
.global tc_off
tc_off:                             @ the beat's turn off (7, 0): dedicated TAP's ring when it is TAP, then each Tap ring
    push {r4, r5, r6, lr}
    ldr r3, =FS_STATE
    blx r3
    ldrb r3, [r0, #DEDICATED_TAP]
    cmp r3, #1
    bne 1f
    movs r0, #7
    movs r1, #0
    ldr r3, =LED_MODE
    blx r3
1:  bl tc_active
    mov r5, r0
    movs r4, #0
2:  lsrs r5, r5, #1
    bcc 3f
    mov r0, r4
    movs r1, #0
    ldr r3, =LED_MODE
    blx r3
3:  adds r4, #1
    cmp r5, #0
    bne 2b
    pop {r4, r5, r6, pc}

.thumb_func
.global tc_refresh
tc_refresh:                         @ the footswitch LED refresh's () -> state: Tap commands shown on, the beat set going for a Tap ring
    push {r0, r1, r4, lr}
    movs r4, #0
1:  ldr r1, =FS_FUNCTIONS
    ldrb.w r1, [r1, r4, lsl #1]
    cmp r1, #STOMP
    bne 2f
    ldr r1, =CC + CC_TYPE + FS_SLOT
    ldrb r1, [r1, r4]
    cmp r1, #TAP
    bne 2f
    mov r0, r4
    bl tc_lit
2:  adds r4, #1
    cmp r4, #FOOTSWITCHES
    blo 1b
    bl tc_tempo
    pop {r0, r1, r4, lr}
    ldr r12, =0x28dd8639
    bx r12

.thumb_func
.global tc_setting
tc_setting:
    cmp r4, #0                    @ the first switch in the stock tempo-change scan
    bne setting_stock
    push {r4, lr}
    bl tc_tempo
    pop {r4, lr}
setting_stock:
    ldr r12, =FS_STATE
    bx r12

tc_tempo:                           @ use the current BPM when no dedicated TAP function drives the beat
    push {r4, lr}
    ldr r3, =FS_FUNCTIONS
    ldrb r3, [r3, #14]
    cmp r3, #1
    beq 9f                          @ the stock TAP case keeps the beat
    bl tc_active
    cbz r0, 9f
    movs r0, #TAP_TEMPO_LED
    bl tc_get
    cmp r0, #0
    blt 9f                          @ unset: as stock, nothing
    beq 8f
    movs r0, #TEMPO_SELECT
    bl tc_get
    cmp r0, #2
    ite eq
    moveq r0, #15
    movne r0, #16
    bl tc_get
    ubfx r2, r0, #23, #8
    subs r2, #127
    cmp r2, #9
    bhi 9f                          @ not 1..1023 BPM: no tempo
    ubfx r1, r0, #0, #23
    orr r1, r1, #0x800000
    lsrs r1, r1, #8                 @ 16 bits of the BPM's mantissa
    rsb.w r2, r2, #15
    ldr r0, =60000
    lsls r0, r0, r2                 @ 60000 * 2^(15 - exponent), below 2^31
    udiv r0, r0, r1                 @ 60000 / BPM, whole ms, as stock works it out
    ldr r3, =BEAT_PERIOD
    str r0, [r3]
    ldr r3, =BEAT_ON
    movs r0, #1
    strb r0, [r3]
    b 9f
8:  ldr r3, =BEAT_ON                @ the beat stops, as the TAP case stops it; the refresh then paints the rings as stock
    movs r0, #0
    strb r0, [r3]
9:  pop {r4, pc}

tc_get:                             @ r0 a setting ID -> r0 its value as stored, -1 when it has none
    push {r4, lr}
    sub sp, #8
    mov r1, sp
    ldr r3, =GET_VALUE
    blx r3
    cmp r0, #0
    ldr r0, [sp, #4]
    it lt
    movlt r0, #-1
    add sp, #8
    pop {r4, pc}

.ltorg
.balignl 4, 0
tc_tap_state:                       @ footswitch state as the beat reads it while only a Tap command blinks: dedicated TAP reads TAP
    .space 18
    .byte 1
.balign 4
tc_name:
    .asciz "Tap"
.balignl 4, 0
tc_list:                            @ an FS slot's Command knob: None, MIDI CC, CC Toggle, Bank/PC, Note On, MMC, Hotkey, Tap, Preset,
    .byte 0, 1, 2, 4, 5, 6, 12, TAP, 14, 15, 16    @ Snapshot, Looper
.equ LIST, . - tc_list
