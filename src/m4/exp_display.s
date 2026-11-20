@ exp_display.s - EXP 1 and EXP 2 on the Home screen: tools/features/exp_display.py, docs/research/features/exp-display.md.
.syntax unified
.thumb
.include "hxtra.inc"
.include "exp.inc"

.equ LEARN, 0x281281e8
.equ JACKS, 0x281f5d88
.equ TIP_PEDAL, 0x22
.equ RING_PEDAL, 0x36
.equ PEDALS, 0x281f5d98
.equ TOGGLE, 0x28128a6c
.equ LIST_A, 0x281f35b8
.equ LIST_B, 0x281f3d2c
.equ HOME, 0x2812a05c
.equ TOP, 0x2812aae0
.equ BANK, 9
.equ REDRAW, 0x28db8509
.equ RELAYOUT, 0x28dc87cd
.equ FILL, 0x100017e9
.equ TEXT, 0x28db7aa5
.equ WIDGET_LOCK, 0x28e24971
.equ WIDGET_UNLOCK, 0x28e24ae9
.equ LINES, 0x64                    @ the Home view's footswitch labels: two text lines and a preset number each, 0x30 apart,
.equ NUMBERS, 0x1ec
.equ IMAGES, 0x2b0                  @ and 18 images, 0x24 apart
.equ EXP1_POSITION, 0x42
.equ EXP2_POSITION, 0x47

.equ RECENT_MS, 3000
.equ REQUEST_MS, 25
.equ LIVE, 0
.equ FROZEN, 1
.equ ABSENT, 2
.equ STALE, 3
.equ GLOBAL, 2
.equ RED, 0xff0000
.equ GREEN, 0x43ff40
.equ GREY, 0x666666
.equ TRACK, 0x2b2b2b
.equ TICK, 0x505050
.equ BAR_W, 6
.equ LABEL_TOP, LABEL_ROW + 9
.equ FONT_SPACING, 11
.equ FONT_NUMBER, 12
.equ FONT_Y, 13
.equ FONT_ROW, 14

.equ MS, 0
.equ DIRTY, 4
.equ LASTREQ, 8
.equ STATE, 12
.equ RECENT, 16
.equ SIDES, 20
.equ VAL, 24
.equ STAMP, 32
.equ SEED, 40
.equ WANT, 48
.equ DRAWN, 64
.equ SHOWING, 80
.equ CONTENT, 84
.equ TOGGLED, 92
.equ CHANGED, 96
.equ POSITION, 104

exp_event:
    ldrb r1, [r0, #1]
    cmp r1, #1
    bhi 1f
    ldr r2, =LEARN
    ldrb r2, [r2]
    cbnz r2, 1f
    ldr r3, [r0, #4]
    adr.w r0, exp_data
    ldr r2, [r0, #MS]
    b 2f
exp_redrive:
    subs r1, #1
    cmp r1, #1
    bhi 1f
    adr.w r0, exp_data
    ldr r2, [r0, #MS]
    subw r2, r2, #RECENT_MS         @ a re-drive is no event: stamped stale, it makes no side live
2:  add.w r12, r0, r1, lsl #2
    str.w r2, [r12, #STAMP]
    orr r3, r3, #0x80000000         @ bit 31 says a value came: the stores stay single words, and -0.0 reads as 0
    str.w r3, [r12, #VAL]
    movs r2, #0
    str.w r2, [r12, #CHANGED]
    movs r2, #1
    str r2, [r0, #DIRTY]
1:  bx lr

exp_loaded:
    movs r1, #CHANGED
    b 1f
exp_recalled:
    movs r1, #(CHANGED + 1)
1:  adr.w r0, exp_data
    movs r2, #1
    strb r2, [r0, r1]
    adds r1, #4
    strb r2, [r0, r1]
    str r2, [r0, #DIRTY]
    bx lr

exp_tick:
    push {r4, r5, r6, lr}
    adr.w r4, exp_data
    ldr r0, [r4, #MS]
    adds r0, #1
    str r0, [r4, #MS]
    ldr r3, =JACKS
    ldrh r5, [r3]
    ldrb r0, [r3, #TIP_PEDAL]
    orr.w r5, r5, r0, lsl #16
    ldrb r0, [r3, #RING_PEDAL]
    orr.w r5, r5, r0, lsl #24
    ldr r0, [r4, #STATE]
    cmp r0, r5
    beq 1f
    str r5, [r4, #STATE]
    movs r0, #1
    str r0, [r4, #DIRTY]
1:  ldr r3, =TOGGLE
    ldrb r5, [r3]
    movs r0, #0
    mov r1, r4
    bl fresh
    orr.w r5, r5, r0, lsl #8
    movs r0, #1
    mov r1, r4
    bl fresh
    orr.w r5, r5, r0, lsl #9
    ldr r0, [r4, #RECENT]
    cmp r0, r5
    beq 2f
    str r5, [r4, #RECENT]
    eors r0, r5
    tst r0, #0xff
    itt ne
    ldrne r0, [r4, #MS]
    strne r0, [r4, #TOGGLED]
    movs r0, #1
    str r0, [r4, #DIRTY]
2:  ldr r0, [r4, #DIRTY]
    cbz r0, 3f
    ldr r0, [r4, #SIDES]
    cbz r0, 3f
    ldr r1, [r4, #MS]
    ldr r0, [r4, #LASTREQ]
    subs r0, r1, r0
    cmp r0, #REQUEST_MS
    blo 3f
    str r1, [r4, #LASTREQ]
    movs r0, #0
    str r0, [r4, #DIRTY]
    movs r1, #1
    ldr r3, =REDRAW
    blx r3
3:  pop {r4, r5, r6, pc}

fresh:
    add.w r2, r1, r0, lsl #2
    ldr r3, [r2, #VAL]
    cmp r3, #0
    bge 1f
    ldr r3, [r2, #STAMP]
    ldr r0, [r1, #MS]
    subs r0, r0, r3
    movw r3, #RECENT_MS
    cmp r0, r3
    bhs 1f
    movs r0, #1
    bx lr
1:  movs r0, #0
    bx lr

exp_home_before:
    movs r2, #0
    b exp_before
exp_top_before:
    movs r2, #1
exp_before:
    push {r3-r11, lr}
    mov r4, r0
    mov r9, r1
    mov r8, r2
    adr.w r5, exp_data
    bl sides
    str r0, [r5, #SIDES]
    bl positions
    str r0, [r5, #POSITION]
    bl showing
    str r0, [r5, #SHOWING]
    bl geometry
    mov r10, r0
    mov.w r11, #0
    movs r6, #0
1:  add.w r7, r5, r6, lsl #2
    ldr r0, [r7, #DRAWN]
    cbz r0, 3f
    and r2, r6, #1
    cmp.w r8, #0
    beq 4f
    cbz r2, 3f                      @ a top view paint leaves the bars to the Home paint, which moves them and lays the labels out again
    b 2f                            @ and wipes the readouts, which lie in its area, before each of its paints, even under the bank view
4:  ldr r1, [r5, #SHOWING]
    cbz r1, 3f
    tst r1, #2
    it eq
    cmpeq r2, #1
    beq 3f                          @ under the bank view a readout is left to the top view paint, which wipes it
    ldr r1, [r7, #WANT]
    cmp r0, r1
    beq 3f
    cbnz r2, 2f
    cbz r1, 2f
    eors r1, r0
    ubfx r1, r1, #0, #9
    cbz r1, 2f
    mov.w r11, #1
2:  and r1, r6, #1
    bl wipe
    movs r0, #0
    str r0, [r7, #DRAWN]
3:  adds r6, #1
    cmp r6, #4
    bne 1b
    cmp.w r11, #0
    beq 9f
    cmp.w r10, #0
    bne 8f
    mov r0, r9
    movs r1, #0
    ldr r3, =RELAYOUT
    blx r3
    b 9f
8:  bl labels                       @ not the layout, which puts back as stock the divider's segments the meter at Middle lights
9:  pop {r3-r11, pc}

labels:                             @ r9 the Home view: each shown widget of its footswitch labels dirty, so the stock paint redraws it
    push {r4-r6, lr}
    ldr r3, =WIDGET_LOCK
    blx r3
    add.w r4, r9, #LINES
    movs r5, #6
    bl texts
    add.w r4, r9, #NUMBERS
    movs r5, #3
    bl texts
    add.w r4, r9, #IMAGES
    movs r5, #18
1:  ldrb r0, [r4, #0x1d]            @ visible: a hidden one's erase would black out what lies over it
    ldr r1, [r4, #0x20]             @ its node
    cbz r0, 2f
    cbz r1, 2f
    movs r0, #1
    strb r0, [r1, #0x24]
2:  adds r4, #0x24
    subs r5, #1
    bne 1b
    ldr r3, =WIDGET_UNLOCK
    blx r3
    pop {r4-r6, pc}

texts:                              @ r4 the first of r5 text widgets, 0x30 apart
    ldrb r0, [r4, #0x2a]            @ visible
    ldr r1, [r4, #0x2c]             @ its node
    cbz r0, 1f
    cbz r1, 1f
    movs r0, #1
    strb r0, [r1, #0x24]
1:  adds r4, #0x30
    subs r5, #1
    bne texts
    bx lr

exp_home_after:
    movs r2, #0
    b exp_after
exp_top_after:
    movs r2, #1
exp_after:
    push {r3-r11, lr}
    sub sp, #40
    str r2, [sp, #32]
    adr.w r5, exp_data
    ldr r1, [r5, #SHOWING]
    cmp r1, #0
    beq 5f
    mov r4, r0
    movs r6, #0
1:  add.w r7, r5, r6, lsl #3
    ldr r0, [r7, #WANT]
    cmp r0, #0
    beq 4f
    ldr r0, [r5, #SIDES]
    lsls r1, r6, #3
    lsrs r0, r1
    uxtb r0, r0
    subs.w r8, r0, #1
    mov r0, r8
    bl state
    mov r9, r0
    mov r0, r1
    bl percent
    mov r10, r0
    ldr.w r11, =GREY
    cmp.w r9, #FROZEN
    beq 2f
    cmp.w r9, #ABSENT
    beq 2f
    ldr.w r11, =RED
    cmp.w r8, #0
    it ne
    ldrne.w r11, =GREEN
2:  ldr r1, [sp, #32]
    ldr r0, [r7, #WANT]
    cbz r1, 3f
    ldr r0, [r7, #DRAWN]
    cbz r0, 6f
3:  mov r1, r9
    mov r2, r10
    mov r3, r11
    bl bar
    ldr r1, [sp, #32]
    cbnz r1, 6f
    ldr r0, [r7, #WANT]
    str r0, [r7, #DRAWN]
6:  ldr r0, [r5, #SHOWING]
    tst r0, #2
    beq 4f                          @ the bank view: the readouts' boxes are its
    cmp.w r9, #STALE
    ite eq
    moveq r0, #LIVE
    movne r0, r9
    orr.w r0, r10, r0, lsl #8
    orr.w r0, r0, r8, lsl #16
    orr r0, r0, #0x80000000
    add.w r1, r5, r6, lsl #2
    ldr r2, [r1, #CONTENT]
    str r0, [r1, #CONTENT]
    cmp r0, r2
    bne 7f
    ldr r0, [r7, #WANT + 4]
    ldr r1, [r7, #DRAWN + 4]
    cmp r0, r1
    beq 8f                          @ the same readout in place: drawn again over itself, as a wipe first could show for a frame
7:  ldr r0, [r7, #WANT + 4]
    movs r1, #1
    bl wipe
8:  ldr r0, [r7, #WANT + 4]
    ubfx r1, r0, #9, #1
    adr.w r2, exp_fonts
    add.w r2, r2, r1, lsl #4
    str r2, [sp, #36]
    ubfx r0, r0, #0, #9
    str r0, [sp, #24]
    cmp r6, #0
    it ne
    addne r0, #(BOX_W - LABEL_W)
    mov r1, r8
    mov r2, r11
    bl label
    cmp.w r9, #ABSENT
    bne 3f
    movw r0, #0x2d2d
    str r0, [sp, #20]
    movs r0, #2
    b 6f
3:  mov r0, r10
    add r1, sp, #20
    bl decimal
6:  mov r9, r0
    add r0, sp, #20
    mov r1, r9
    ldr r2, [sp, #36]
    bl width
    ldr r3, [sp, #24]
    cmp r6, #0
    itt ne
    addne r3, #BOX_W
    subne r3, r3, r0
    str r3, [sp, #28]
    ldr r3, =WIDGET_LOCK
    blx r3
    ldr r2, [sp, #36]
    ldrb r0, [r2, #FONT_Y]
    str r0, [sp]
    ldrb r0, [r2, #FONT_NUMBER]
    str r0, [sp, #4]
    str.w r11, [sp, #8]
    movs r0, #0
    str r0, [sp, #12]
    movs r0, #1
    str r0, [sp, #16]
    mov r0, r4
    add r1, sp, #20
    mov r2, r9
    ldr r3, [sp, #28]
    ldr.w r12, =TEXT
    blx r12
    ldr r3, =WIDGET_UNLOCK
    blx r3
    ldr r0, [r7, #WANT + 4]
    str r0, [r7, #DRAWN + 4]
4:  adds r6, #1
    cmp r6, #2
    bne 1b
5:  add sp, #40
    pop {r3-r11, pc}

sides:
    push {r4, lr}
    movs r0, #SETTING_EXP_DISPLAY_LEFT
    movs r1, #SETTING_EXP_DISPLAY_LEFT_MAX
    movs r2, #SETTING_EXP_DISPLAY_LEFT_DEFAULT
    bl hxtra_setting_get
    mov r4, r0
    movs r0, #SETTING_EXP_DISPLAY_RIGHT
    movs r1, #SETTING_EXP_DISPLAY_RIGHT_MAX
    movs r2, #SETTING_EXP_DISPLAY_RIGHT_DEFAULT
    bl hxtra_setting_get
    orr.w r0, r4, r0, lsl #8
    pop {r4, pc}

positions:
    push {r4, lr}
    movs r0, #EXP1_POSITION
    movs r1, #GLOBAL
    movs r2, #GLOBAL
    bl hxtra_setting_get
    mov r4, r0
    movs r0, #EXP2_POSITION
    movs r1, #GLOBAL
    movs r2, #GLOBAL
    bl hxtra_setting_get
    orr.w r0, r4, r0, lsl #8
    pop {r4, pc}

showing:                            @ -> 3 Home under the top view, 1 under its bank view (the bars only), 0 otherwise
    push {r4, lr}
    ldr r0, =LIST_A
    bl painted
    ldr r1, =HOME
    subs r4, r0, r1
    ldr r0, =LIST_B
    bl painted
    ldr r1, =TOP
    subs r0, r0, r1
    orrs r0, r4
    bne 1f
    ldrb r0, [r1, #BANK]
    cmp r0, #0
    ite eq
    moveq r0, #3
    movne r0, #1
    pop {r4, pc}
1:  movs r0, #0
    pop {r4, pc}

painted:
    ldr r0, [r0]
1:  cbz r0, 3f
    ldr r1, [r0, #0]
    lsls r1, r1, #31
    bmi 2f
    ldr r0, [r0, #0x14]
    b 1b
2:  ldr r1, [r0, #4]
    cmp r1, #0
    ite ne
    ldrne r0, [r0, #0xc]
    moveq r0, #0
3:  bx lr

geometry:
    push {r4, r6-r9, lr}
    movs r4, #0
    movs r0, #0
    str r0, [r5, #WANT]
    str r0, [r5, #WANT + 4]
    str r0, [r5, #WANT + 8]
    str r0, [r5, #WANT + 12]
    ldr r0, [r5, #SHOWING]
    cmp r0, #0
    beq 9f
    movs r6, #0
    movs r7, #116
    movs.w r8, #0
    movw r9, #314
    movs r2, #1
    movw r3, #318
.if GR_SHOWN
    ldr r0, =GR_SHOWN
    ldr r0, [r0]
    cbz r0, 5f
    ldr r0, =GR_LAYOUT
    ldr r0, [r0]
    ubfx r1, r0, #24, #7
    ubfx r0, r0, #8, #8
    cmp r0, #0
    bne 1f
    movs r4, #1
    sub.w r7, r7, r1, lsr #1
    cmp r1, #SMALL_FROM
    it hs
    movhs r4, #3
    b 5f
1:  cmp r0, #2
    bne 2f
    add.w r8, r1, #1
    add.w r2, r1, #2
    b 5f
2:  cmp r0, #3
    bne 3f
    adds r6, r1, #1
    b 5f
3:  cmp r0, #4
    bne 5f
    movw r9, #313
    sub.w r9, r9, r1
    movw r3, #317
    subs r3, r3, r1
.endif
5:  lsl.w r12, r6, #9
    orr.w r12, r12, r7, lsl #17
    orr r12, r12, #0x80000000
    and lr, r4, #2
    lsl.w lr, lr, #8
    orr lr, lr, #0x80000000
    ldr r0, [r5, #SIDES]
    tst r0, #0xff
    beq 6f
    orr.w r1, r12, r8
    str r1, [r5, #WANT]
    orr.w r1, r2, lr
    str r1, [r5, #WANT + 4]
6:  tst r0, #0xff00
    beq 9f
    orr.w r1, r12, r9
    str r1, [r5, #WANT + 8]
    sub.w r1, r3, #(BOX_W - 1)
    orr.w r1, r1, lr
    str r1, [r5, #WANT + 12]
9:  mov r0, r4
    pop {r4, r6-r9, pc}

state:
    push {r4-r8, lr}
    mov r4, r0
    ldr r3, =JACKS
    ldrb r6, [r3, #1]
    ldrb r0, [r3, #TIP_PEDAL]
    cmp r6, #0
    ite eq
    moveq r6, r0
    movne r6, #0
    ldrb r7, [r3]
    ldrb r0, [r3, #RING_PEDAL]
    cmp r7, #0
    ite eq
    moveq r7, r0
    movne r7, #0
    ldr r3, =TOGGLE
    ldrb.w r8, [r3]
    movs r2, #0
    cmp.w r8, #2
    bne 1f
    cmp r7, #0
    it eq
    moveq r2, #1
1:  movs r0, #0
    cmp r4, r2
    it eq
    moveq r0, r6
    cmp r4, #1
    it eq
    orreq r0, r7
    add.w r12, r5, r4, lsl #2
    ldr.w r1, [r12, #VAL]
    cmp r1, #0
    blt 3f
    ldr.w r1, [r12, #SEED]
    cmp r1, #0
    blt 3f
    cbz r0, 3f
    movs r3, #0
    cmp r4, #1
    bne 2f
    cmp r7, #0
    it ne
    movne r3, #1
2:  ldr r1, =PEDALS
    movs r2, #0x14
    mla r1, r3, r2, r1
    ldr r1, [r1, #8]
    orr r1, r1, #0x80000000
    str.w r1, [r12, #SEED]
3:  cbnz r0, 7f
    cmp r1, #0
    bge 6f
    movs r7, #0
    cmp.w r8, #0
    beq 4f
    cmp r4, r2
    it ne
    movne r7, r6                    @ only a pedal on the tip can have left it
4:  mov r6, r1
    mov r0, r4
    mov r1, r5
    bl fresh
    mov r1, r6
    cbz r0, 8f
    cbz r7, 7f
    add.w r12, r5, r4, lsl #2
    ldr.w r0, [r12, #STAMP]
    ldr r3, [r5, #TOGGLED]
    subs r0, r0, r3
    cmp r0, #0
    bgt 7f
5:  movs r0, #FROZEN
    pop {r4-r8, pc}
8:  cmp r7, #0
    bne 5b
6:  movs r0, #ABSENT
    movs r1, #0
    pop {r4-r8, pc}
7:  add.w r12, r5, r4, lsl #2
    ldr.w r0, [r12, #CHANGED]
    ldr r3, [r5, #POSITION]
    lsls r2, r4, #3
    lsrs r3, r2
    uxtb r3, r3
    cmp r3, #1
    it eq
    uxtbeq r0, r0                   @ under Preset a snapshot recall leaves the parameters alone (0x28de33f0, 0x28de3348)
    cmp r3, #GLOBAL
    it eq
    moveq r0, #0
    cmp r0, #0
    ite eq
    moveq r0, #LIVE
    movne r0, #STALE
    pop {r4-r8, pc}

percent:
    ubfx r1, r0, #23, #8
    ubfx r0, r0, #0, #23
    orr r0, r0, #0x800000
    movs r2, #100
    muls r0, r2, r0
    rsb.w r1, r1, #150
    cmp r1, #23
    blt 1f
    cmp r1, #32
    bge 2f
    subs r2, r1, #1
    movs r3, #1
    lsls r3, r2
    add r0, r3
    lsrs r0, r1
    cmp r0, #100
    it ls
    bxls lr
1:  movs r0, #100
    bx lr
2:  movs r0, #0
    bx lr

decimal:
    movs r3, #1
    cmp r0, #10
    it hs
    movhs r3, #2
    cmp r0, #100
    it hs
    movhs r3, #3
    add r2, r1, r3
    movs r1, #0
    strb r1, [r2]
    movs r1, #10
1:  udiv r12, r0, r1
    mls r0, r12, r1, r0
    adds r0, #'0'
    strb r0, [r2, #-1]!
    movs r0, r12
    bne 1b
    mov r0, r3
    bx lr

width:
    movs r3, #0
1:  ldrb r12, [r0], #1
    cmp.w r12, #'-'
    ite eq
    moveq.w r12, #10
    subne.w r12, r12, #'0'
    ldrb.w r12, [r2, r12]
    add r3, r12
    ldrb.w r12, [r2, #FONT_SPACING]
    add r3, r12
    subs r1, #1
    bne 1b
    subs r0, r3, r12
    bx lr

bar:
    push {r4-r10, lr}
    ubfx r6, r0, #0, #9
    ubfx r7, r0, #9, #8
    ubfx r8, r0, #17, #8
    sub.w r8, r8, r7
    add.w r8, r8, #1
    mov r10, r3
    cmp r1, #ABSENT
    bhs 3f
    mov r0, r2
    mov r1, r8
    bl rows
    movs r9, r0
    beq 1f
    mov r3, r0
    mov r0, r6
    mov r1, r7
    movs r2, #BAR_W
    mov r12, r10
    bl rect
1:  movs r5, #25
2:  mov r0, r5
    mov r1, r8
    bl rows
    cmp r0, r9
    blo 5f
    mov r10, r0
    subs r3, r0, r9
    beq 4f
    adds r1, r7, r9
    mov r0, r6
    movs r2, #BAR_W
    ldr.w r12, =TRACK
    bl rect
4:  adds r1, r7, r10
    mov r0, r6
    movs r2, #BAR_W
    movs r3, #1
    ldr.w r12, =TICK
    bl rect
    add.w r9, r10, #1
5:  adds r5, #25
    cmp r5, #100
    bne 2b
    subs r3, r8, r9
    beq 9f
    adds r1, r7, r9
    mov r0, r6
    movs r2, #BAR_W
    ldr.w r12, =TRACK
    bl rect
    b 9f
3:  mov r0, r6
    mov r1, r7
    movs r2, #BAR_W
    movs r3, #1
    mov r12, r10
    bl rect
    mov r0, r6
    add.w r1, r7, r8
    subs r1, #1
    movs r2, #BAR_W
    movs r3, #1
    mov r12, r10
    bl rect
    sub.w r9, r8, #2
    adds r7, #1
    mov r0, r6
    mov r1, r7
    movs r2, #1
    mov r3, r9
    mov r12, r10
    bl rect
    adds r0, r6, #(BAR_W - 1)
    mov r1, r7
    movs r2, #1
    mov r3, r9
    mov r12, r10
    bl rect
    adds r0, r6, #1
    mov r1, r7
    movs r2, #(BAR_W - 2)
    mov r3, r9
    mov.w r12, #0
    bl rect
9:  pop {r4-r10, pc}

rows:
    muls r0, r1, r0
    adds r0, #50
    movs r1, #100
    udiv r0, r0, r1
    bx lr

label:
    push {r3-r11, lr}
    mov r5, r0
    mov r10, r2
    adds r6, r1, #3
    movs r7, #0
1:  cmp r7, #3
    ite eq
    moveq r0, r6
    movne r0, r7
    adr.w r1, exp_glyphs
    ldrh.w r8, [r1, r0, lsl #1]
    movs.w r9, #(LABEL_TOP - 1)
2:  movs.w r11, #0
3:  tst r8, #0x4000
    beq 4f
    add.w r0, r5, r11, lsl #1
    mov r1, r9
    movs r2, #2
    movs r3, #2
    mov r12, r10
    bl rect
4:  lsl.w r8, r8, #1
    adds.w r11, r11, #1
    cmp.w r11, #3
    bne 3b
    subs.w r9, r9, #2
    cmp.w r9, #(LABEL_ROW - 2)
    bne 2b
    adds r5, #8
    adds r7, #1
    cmp r7, #4
    bne 1b
    pop {r3-r11, pc}

wipe:
    mov.w r12, #0
    cbnz r1, 1f
    ubfx r3, r0, #17, #8
    ubfx r1, r0, #9, #8
    subs r3, r3, r1
    adds r3, #1
    ubfx r0, r0, #0, #9
    movs r2, #BAR_W
    b rect
1:  ubfx r1, r0, #9, #1
    adr.w r2, exp_fonts
    add.w r2, r2, r1, lsl #4
    ldrb r1, [r2, #FONT_ROW]
    ubfx r0, r0, #0, #9
    rsb.w r3, r1, #(LABEL_TOP + 1)
    movs r2, #BOX_W

rect:
    push {lr}
    sub sp, #12
    str r3, [sp]
    str.w r12, [sp, #4]
    movs r3, #0
    str r3, [sp, #8]
    mov r3, r2
    mov r2, r1
    mov r1, r0
    mov r0, r4
    ldr.w r12, =FILL
    blx r12
    add sp, #12
    pop {pc}

HXTRA_SETTING_GET

.ltorg
.balign 4
exp_data:
    .space 108
exp_glyphs:                         @ 3x5, bit 14 the top left pixel, rows of 3 bits: E, X, P, 1, 2, -
    .hword 0b111100110100111, 0b101101010101101, 0b110101110100100, 0b010110010010111, 0b111001111100111, 0b000000111000000
exp_fonts:
    FONTS
