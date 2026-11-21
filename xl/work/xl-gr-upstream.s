@ gr_meter.s - a ten-light gain-reduction meter on the Home divider or along an edge of the screen, for the Deluxe Comp.
@ Set by the compressor block's GR knobs, sent by the DSP in frame word 218 (tagged 0x6B): Mtr Size (Off, S, M, L, XL; Off, no knobs yet,
@ or no compressor heard from lately turns it off), GR Position (Middle, Top, Left, Bottom, Right) and GR Direction (Normal is
@ left to right or top to bottom, Reverse the other way). Middle, Top and Bottom are
@ 30 px lights at a 32 px pitch, Middle on the divider line in place of its four segments; Left and Right are 21 px lights at a 24 px
@ pitch, clear of the divider, which then stays stock.
@ The lights are A over B in dB, from 64-block window peaks (for the Deluxe Comp, A is 1 / the core's own gain), at 1 2 3 4 6 8 10 14
@ 19 25 dB. The measured gain already follows the comp's attack and release; in silence the lights decay at its Release.
@ Handlers on shared hooks (tools/features/gr.py): frame before the DSP stream's receive callback, construct after the Home view's
@ constructor, erase before and draw after its paint function, and edit_top and edit_params after the Edit view's two paints, which
@ draw the same lights straight into the framebuffer while the selected block is a compressor the meter measures (gr.inc).
@ Position independent, assembled by tools/m4asm.py at build time.
@ Integer maths only: the thread has no FPU context of its own.
.syntax unified
.thumb
.include "gr.inc"
.thumb_func
frame:                              @ r1 the frame
    push {r0-r7, lr}
    sub sp, #20
    mov r7, r1                      @ the frame
    adr.w r4, data
    ldr r0, [r7, #800]              @ the DSP's marker (600DF00D, halfwords swapped)
    ldr r1, =0xf00d600d
    subs r0, r0, r1
    str r0, [r4, #8]                @ 0: this frame carries the DSP's words
    bne nomark
    movs r1, #1
    str r1, [r4, #12]
    str r0, [r4, #4]                @ heard from the compressor just now
    ldr.w r1, [r7, #872]            @ word 218: the block's GR knobs, tagged 0x6B
    ror.w r1, r1, #16
    str r1, [r4, #32]
    b heard
nomark:
    ldr r1, [r4, #12]
    cmp r1, #0
    beq leave                       @ until the DSP has been heard from, the UI may not be up
    ldr r1, [r4, #4]
    adds r1, #1
    str r1, [r4, #4]
heard:
    ldr r0, [r4, #28]
    adds r0, #1
    str r0, [r4, #28]
    ldr r3, [r4, #32]
    lsrs r0, r3, #24
    cmp r0, #0x6b
    bne stock                       @ no knobs from the block yet
    uxtb r5, r3                     @ Thickness
    ubfx r0, r3, #16, #8
    cmp r0, #4
    it hi
    movhi r0, #4
    str r0, [sp, #12]               @ Position
    ubfx r0, r3, #8, #8
    str r0, [sp, #16]               @ Direction
    cmp r5, #4
    it hi
    movhi r5, #4
    add.w r5, r5, r5, lsl #2        @ Mtr Size Off, S, M, L, XL: 0, 5, 10, 15, 20 px
    ldr r0, [r4, #4]
    cmp.w r0, #1024
    it hs
    movhs r5, #0
    cmp r5, #0
    beq stock
    ldr r0, [r4, #20]
    cbnz r0, wasshown
    ldr r0, [r4, #28]               @ just shown: the stock layout runs again 64 frames on, in the paint
    adds r0, #64
    str r0, [r4, #36]
wasshown:
    movs r0, #1
    str r0, [r4, #20]               @ ours are shown
    str r5, [sp, #8]
    ldr r0, [r4, #8]
    cmp r0, #0
    bne grshow                      @ no measurement in this frame
    ldr.w r0, [r7, #1000]           @ word 250: the DSP's window count; frames repeat a window's values
    ldr r1, [r4, #24]
    cmp r0, r1
    beq grshow
    str r0, [r4, #24]
    ldr r0, [r7, #864]              @ word 216: the window peak of A before, the compressor's input
    ldr r1, [r7, #868]              @ word 217: that of B after, its output
    bl grdb
    cmp r2, #0
    blt silent
    lsls r5, r2, #16                @ as measured both ways: the reduction already has the comp's attack and release
    str r5, [r4, #0]
    b grshow
silent:                             @ nothing to measure: the comp's gain recovers at its Release
    ldr.w r0, [r7, #1004]           @ word 251: its coefficient over one window
    bl q16
    ldr r1, [r4, #0]
    umull r2, r3, r1, r0
    lsrs r2, r2, #16
    orr.w r2, r2, r3, lsl #16
    str r2, [r4, #0]
grshow:
    ldr r2, [r4, #0]
    lsrs r2, r2, #16
    adr.w r3, lights
    movs r5, #0                     @ the lights lit
light:
    ldrh.w r0, [r3, r5, lsl #1]
    cmp r2, r0
    blo lit
    adds r5, #1
    cmp r5, #10
    bne light
lit:                                @ the paint lays the lights out (layout): a setter on this thread could race it and lose its mark
    ldr r0, [sp, #12]
    orr.w r5, r5, r0, lsl #8        @ the layout: lights lit, Position, Direction, Thickness, and bit 31 for ours shown
    ldr r0, [sp, #16]
    orr.w r5, r5, r0, lsl #16
    ldr r0, [sp, #8]
    orr.w r5, r5, r0, lsl #24
    orr r5, r5, #0x80000000
    b post

stock:
    movs r0, #0
    str r0, [r4, #20]               @ ours are hidden
    movs r5, #0                     @ the layout: the stock divider
post:
    ldr r0, [r4, #40]
    cmp r0, r5
    beq repaint
    str r5, [r4, #40]
    movs r0, #1
    str r0, [r4, #16]
    b repaint


stockdiv:                           @ the stock divider: four 80 px segments, the selected one white and 2 px, the others grey and 1 px; leaves r7 want
    push {r4-r6, lr}
    adr.w r0, data
    ldr r5, [r0, #44]               @ the selected segment, as layout read it
    adr.w r7, want
    movs r0, #0x77
    str r0, [r7, #8]
    movs r0, #80
    str r0, [r7, #12]
    movs r6, #0
segment:
    cmp r6, r5
    ite eq
    moveq r0, #2
    movne r0, #1
    str r0, [r7, #16]
    cmp r6, r5
    ite eq
    mvneq r0, #0xff000000
    ldrne r0, =0x666666
    str r0, [r7, #0]
    movs r0, #80
    mul r0, r6, r0
    str r0, [r7, #4]
    mov r0, r6
    bl widget
    bl apply
    adds r6, #1
    cmp r6, #4
    bne segment
    pop {r4-r6, pc}

repaint:
    ldr r0, [r4, #16]               @ the setters only mark the canvas: ask the UI to repaint, at most every 16 frames
    cbz r0, leave
    ldr r0, [r4, #28]
    lsls r0, r0, #28
    bne leave
    movs r0, #0
    str r0, [r4, #16]
    movs r1, #1
    ldr r3, =0x28db8509             @ the redraw request the layout code ends with: (0, 1)
    blx r3
leave:
    add sp, #20
    pop {r0-r7, pc}

layout:                             @ from the paint, under the widget lock: the lights as the frame last set data + 40
    push {r4-r7, lr}
    sub sp, #20
    adr.w r4, data
    movs r0, #0x15                  @ the setting the stock layout selects a divider segment by, read before the lock
    mov r1, sp
    ldr r3, =0x28e1f845
    blx r3
    ldr r0, [sp, #4]
    str r0, [r4, #44]
    ldr r3, =0x28e24971             @ the widget lock, as the stock paint takes it
    blx r3
    ldr r5, [r4, #40]
    cmp r5, #0
    bne shown
    bl stockdiv
    movs r0, #0
    movs r1, #46
    bl park
    b laid
shown:
    ubfx r0, r5, #8, #8
    str r0, [sp, #12]               @ Position
    ubfx r0, r5, #16, #8
    str r0, [sp, #16]               @ Direction
    ubfx r0, r5, #24, #7
    str r0, [sp, #8]                @ Thickness
    uxtb r5, r5                     @ the lights lit
    adr.w r7, want                  @ slot j counts left to right or top to bottom; it shows light j, or 9 - j in Reverse
    ldr r0, [sp, #12]
    cmp r0, #0
    it ne
    blne stockdiv                   @ Middle uses the divider's own segments
    movs r6, #0
slot:
    ldr r2, [sp, #16]
    mov r0, r6
    cbz r2, forward
    rsb.w r0, r6, #9
forward:
    movs r1, #0
    cmp r0, r5
    bhs dark
    adr.w r3, colours
    ldr.w r1, [r3, r0, lsl #2]
dark:
    str r1, [r7, #0]
    ldr r0, [sp, #12]
    ldr r1, [sp, #8]
    cbz r0, middle
    subs r0, #1                     @ the edge: Top, Left, Bottom, Right
    lsls r2, r0, #31
    bne upright
    lsls r2, r6, #5
    str r2, [r7, #4]
    movs r2, #30
    str r2, [r7, #12]
    str r1, [r7, #16]
    cmp r0, #0
    ite eq
    moveq r2, #240                  @ y counts up from the screen's bottom edge [verified on unit]
    movne r2, r1
    str r2, [r7, #8]
    b place
upright:                            @ slots 4 and 5 leave rows 117..119 to the divider
    movs r2, #24
    mul r2, r6, r2
    rsb.w r2, r2, #237
    str r2, [r7, #8]
    str r1, [r7, #12]
    movs r2, #21
    str r2, [r7, #16]
    cmp r0, #1
    ite eq
    moveq r2, #0
    rsbne.w r2, r1, #320
    str r2, [r7, #4]
place:                              @ each position has its own widgets: a move would erase the box spanning both places
    movs r2, #10
    mla r0, r0, r2, r6
    bl own
    b fit
middle:                             @ centred on the stock divider line; slots 0..3 are its segments, 4..9 our widgets 40..45
    lsls r2, r6, #5
    str r2, [r7, #4]
    movs r2, #30
    str r2, [r7, #12]
    str r1, [r7, #16]
    adds r2, r1, #1
    lsrs r2, r2, #1
    adds r2, #0x76
    str r2, [r7, #8]
    mov r0, r6
    cmp r0, #4
    bhs midown
    bl widget
    b fit
midown:
    adds r0, #36
    bl own
fit:
    bl apply
    adds r6, #1
    cmp r6, #10
    bne slot
    ldr r0, [sp, #12]
    cmp r0, #0
    bne edgepark
    movs r1, #40
    bl park
    b laid
edgepark:
    subs r0, #1
    movs r1, #10
    muls r1, r0
    movs r0, #0
    bl park
    ldr r0, [sp, #12]
    subs r0, #1
    movs r1, #10
    mla r0, r0, r1, r1
    movs r1, #46
    bl park
    b laid
laid:
    ldr r3, =0x28e24ae9             @ the widget unlock
    blx r3
    add sp, #20
    pop {r4-r7, pc}

apply:                              @ r0 a widget: colour, place and size as `want` says, calling a setter only for a change
    push {r4-r6, lr}
    mov r5, r0
    adr.w r6, want
    adr.w r4, data
    ldr r1, [r6, #0]
    ldr r2, [r5, #0]
    cmp r1, r2
    beq coloured
    mov r0, r5
    ldr r3, =0x28e24b99             @ setColor
    blx r3
    movs r0, #1
    str r0, [r4, #16]
coloured:
    ldr r1, [r6, #4]
    ldr r2, [r6, #8]
    ldr r3, [r5, #4]
    cmp r1, r3
    bne move
    ldr r3, [r5, #8]
    cmp r2, r3
    beq placed
move:                               @ placed before it is sized: a first erase then covers only the divider row
    mov r0, r5
    ldr r3, =0x28e24af1             @ setPos
    blx r3
    movs r0, #1
    str r0, [r4, #16]
placed:
    ldr r1, [r6, #12]
    ldr r2, [r6, #16]
    ldr r3, [r5, #0xc]
    cmp r1, r3
    bne size
    ldr r3, [r5, #0x10]
    cmp r2, r3
    beq sized
size:
    mov r0, r5
    ldr r3, =0x28e24b29             @ setSize
    blx r3
    movs r0, #1
    str r0, [r4, #16]
sized:
    pop {r4-r6, pc}

widget:                             @ r0 a divider segment, 0..3 -> r0 its widget
    movs r2, #0x1c
    mul r0, r0, r2
    ldr r2, =0x2812a594             @ the Home view's four divider segments
    add r0, r2
    bx lr
own:                                @ r0 an index -> our widget; keeps r1, r3
    movs r2, #0x1c
    mul r0, r0, r2
    adr.w r2, widgets
    add r0, r2
    bx lr

park:                               @ our widgets r0 .. r1 - 1 shrink to nothing where they are, so their erase covers only where they were
    push {r4-r6, lr}
    mov r4, r0
    mov r5, r1
    adr.w r6, want
parkone:
    cmp r4, r5
    beq parked
    mov r0, r4
    bl own
    ldr r1, [r0, #4]
    str r1, [r6, #4]
    ldr r1, [r0, #8]
    str r1, [r6, #8]
    movs r1, #0
    str r1, [r6, #0]
    str r1, [r6, #12]
    str r1, [r6, #16]
    bl apply
    adds r4, #1
    b parkone
parked:
    pop {r4-r6, pc}

.thumb_func
construct:                          @ our 46 widgets, hidden until the meter shows
    push {r4-r7, lr}
    adr.w r5, widgets
    adr.w r6, nodes
    movs r7, #46
make:
    mov r0, r5
    mov r1, r6
    ldr r3, =0x28e24989             @ init(widget, node)
    blx r3
    mov r0, r5
    movs r1, #6
    ldr r3, =0x28e24a19             @ the layer the stock segments use
    blx r3
    adds r5, #0x1c
    adds r6, #0x28
    subs r7, #1
    bne make
    pop {r4-r7, pc}

.thumb_func
erase:                              @ r0 the framebuffer, r1 the Home view: like the stock paint, every erase before any draw
    push {r3-r7, lr}
    mov r4, r0
    mov r5, r1
    adr.w r0, data                  @ the meter's first draw leaves the footswitch labels blank until a relayout [verified on unit]
    ldr r1, [r0, #36]
    cbz r1, laidout
    ldr r2, [r0, #28]
    cmp r2, r1
    blo laidout
    movs r1, #0
    str r1, [r0, #36]
    mov r0, r5
    ldr r3, =0x28dc87cd             @ the Home view's divider and footswitch label layout, as the stock code calls it: (home, 0)
    blx r3
laidout:
    bl layout
    add.w r0, r5, #0x538
    ldrb r7, [r0, #0x15]            @ ours are shown while the stock divider is and the meter is on
    adr.w r0, data
    ldr r0, [r0, #20]
    cmp r0, #0
    it eq
    moveq r7, #0
    adr.w r6, widgets
    ldrb r0, [r6, #0x15]
    cmp r0, r7
    beq synced
hide:
    mov r0, r6
    mov r1, r7
    ldr r3, =0x28e24b01             @ setVisible
    blx r3
    adds r6, #0x1c
    adr.w r0, nodes                 @ the end of our widgets
    cmp r6, r0
    bne hide
synced:
    ldr r3, =0x28e24b41             @ erase(context, context, widget): the old place
    bl each
    pop {r3-r7, pc}

.thumb_func
draw:                               @ r0 the framebuffer
    push {r4, lr}
    mov r4, r0
    ldr r3, =0x28e24b59             @ draw(context, context, widget): in its colour
    bl each
    pop {r4, pc}

each:                               @ r3 a function (context, context, widget) for our 46 widgets, r4 the context
    push {r5-r7, lr}
    mov r7, r3
    ldr r3, =0x28e24971             @ the widget lock, as the stock paint takes it
    blx r3
    adr.w r6, widgets
    movs r5, #46
each6:
    mov r0, r4
    mov r1, r4
    mov r2, r6
    blx r7
    adds r6, #0x1c
    subs r5, #1
    bne each6
    ldr r3, =0x28e24ae9
    blx r3
    pop {r5-r7, pc}

q16:                                @ r0 a frame word, a float in 0..2 -> r0 in Q16; keeps r1, r5
    ror.w r0, r0, #16               @ the stream swaps halfwords
    lsrs r2, r0, #23
    rsb.w r2, r2, #134
    cmp r2, #32
    bhs q16zero
    ubfx r0, r0, #0, #23
    orr r0, r0, #0x800000
    lsr.w r0, r0, r2
    bx lr
q16zero:
    movs r0, #0
    bx lr

grdb:                               @ r0, r1 frame words: input and output peaks -> r2 the reduction in 1/256 octaves, 0..1500, or -1 in silence
    push {r4, r5, lr}
    mov r4, r1
    bl lg
    mov r5, r0
    mov r0, r4
    bl lg
    mov.w r2, #-1
    movw r1, #29440                 @ below -72 dB there is nothing to compare
    cmp r5, r1
    blo grout
    subs r2, r5, r0
    it lt
    movlt r2, #0
    movw r1, #1500
    cmp r2, r1
    it gt
    movgt r2, r1
grout:
    pop {r4, r5, pc}

lg:                                 @ r0 a frame word -> r0 log2 of its magnitude in 1/256 octaves, 1.0 = 32512
    ror.w r0, r0, #16               @ the stream swaps halfwords
    bic r0, r0, #0x80000000
    ubfx r1, r0, #15, #8
    lsrs r0, r0, #15
    rsb.w r3, r1, #256              @ log2(1 + m) ~ m + 0.346 m (1 - m): within 0.14 dB
    mul r3, r3, r1
    movs r2, #89
    mul r3, r3, r2
    add.w r0, r0, r3, lsr #16
    bx lr

.thumb_func
edit_params:                        @ r0 the framebuffer, r1 the view, after the generic paint of list A's views
    ldr r2, =0x28128270             @ the Edit view's bottom half
    cmp r1, r2
    beq edit
    bx lr
.thumb_func
edit_top:                           @ r0 the framebuffer, r1 the Edit view's top half, after its stock paint
edit:                               @ list B paints after list A into the same buffer, so whichever ran last leaves the lights on top
    push {r4-r6, r10, r11, lr}
    mov r11, r0
    adr.w r10, data
    ldr r4, [r10, #40]              @ the layout the frame last set
    cmp r4, #0
    beq ewant
    bl showing
    cbz r0, ehide
    bl selected
    cbnz r0, ewant
ehide:
    movs r4, #0
ewant:
    ldr r5, [r10, #48]              @ the layout drawn, 0 for none
    cbz r5, drawn
    eor.w r0, r4, r5
    ldr r1, =0x7f00ff00             @ Position and Thickness: the rectangles
    tst r0, r1
    beq drawn
    mov r0, r5
    movs r1, #0
    bl slots
    movs r5, #0
    str r5, [r10, #48]
drawn:
    cbz r4, edone
    mov r0, r4
    movs r1, #1
    bl slots
    str r4, [r10, #48]
edone:
    pop {r4-r6, r10, r11, pc}

slots:                              @ r0 a layout, r1 0 to take every light off, 1 to draw it; r11 the framebuffer
    push {r4-r9, lr}
    sub sp, #12
    mov r7, r0
    mov r8, r1
    movs r9, #0                     @ slot j, counting left to right or top to bottom
eslot:
    ubfx r0, r7, #8, #8             @ Position, as layout places it
    ubfx r1, r7, #24, #7            @ Thickness
    cbz r0, emid
    subs r0, #1
    lsls r2, r0, #31
    bne eupright
    lsl.w r4, r9, #5                @ x
    movs r6, #30                    @ w
    mov r5, r1                      @ h
    cmp r0, #0
    ite eq
    rsbeq.w r3, r1, #240            @ Top's bottom row; Bottom's is 0
    movne r3, #0
    b erect
eupright:
    movs r2, #24
    mul r3, r9, r2
    rsb.w r3, r3, #216
    mov r6, r1
    movs r5, #21
    cmp r0, #1
    ite eq
    moveq r4, #0
    rsbne.w r4, r1, #320
    b erect
emid:
    lsl.w r4, r9, #5
    movs r6, #30
    mov r5, r1
    adds r3, r1, #1
    lsrs r3, r3, #1
    adds r3, #0x76
    subs r3, r3, r1
erect:                              @ x r4, bottom row r3, w r6, h r5
    str r3, [sp, #0]
    mov r0, r9
    ubfx r2, r7, #16, #8
    cbz r2, eforward
    rsb.w r0, r9, #9
eforward:
    movs r1, #0                     @ an unlit light draws nothing: the text under it shows whole
    uxtb r2, r7
    cmp r0, r2
    bhs ecolour
    adr.w r3, colours               @ 0xRRGGBB to the screen's 5-6-5, blue high and red low
    ldr.w r3, [r3, r0, lsl #2]
    ubfx r1, r3, #3, #5
    lsls r1, r1, #11
    ubfx r2, r3, #10, #6
    orr.w r1, r1, r2, lsl #5
    ubfx r2, r3, #19, #5
    orrs r1, r2
ecolour:
    cmp r8, #0
    it eq
    moveq r1, #0
    str r1, [sp, #4]
    adr.w r0, eprev
    add.w r0, r0, r9, lsl #1
    ldrh r2, [r0]                   @ the colour this slot is drawn in, 0 for none
    strh r1, [r0]
    str r2, [sp, #8]
    orrs r1, r2
    beq eslotdone
    adr.w r12, esave                @ this slot's saved pixels: 600 for a 30 x 20 light at most
    mov.w r0, #1200
    mla r12, r9, r0, r12
ecol:                               @ the framebuffer is column-major and bottom-up: pixel (x, y) at fb + 2 * (240 x + y)
    ldr r3, [sp, #0]
    movs r0, #240
    mla r0, r4, r0, r3
    add.w r0, r11, r0, lsl #1
    mov lr, r5
epix:
    ldrh r1, [r0]
    ldr r2, [sp, #8]
    ldr r3, [sp, #4]
    cbnz r3, epaint
    cmp r1, r2                      @ restore only what is still ours: a stock paint may have drawn here since
    itt eq
    ldrheq r1, [r12]
    strheq r1, [r0]
    b enext
epaint:
    cbz r2, ekeep                   @ newly lit: save every pixel it covers
    cmp r1, r2
    beq ecover                      @ else only those a stock paint drew since
ekeep:
    strh r1, [r12]
ecover:
    strh r3, [r0]
enext:
    adds r0, #2
    add.w r12, r12, #2
    subs.w lr, lr, #1
    bne epix
    adds r4, #1
    subs r6, #1
    bne ecol
eslotdone:
    add.w r9, r9, #1
    cmp.w r9, #10
    bne eslot
    add sp, #12
    pop {r4-r9, pc}

showing:                            @ -> r0 nonzero while list A paints the Edit view and list B its top half, as the UI loop picks them
    push {r4, lr}
    ldr r0, =0x281f35b8             @ list A's head
    bl painted
    ldr r1, =0x28128270
    subs r4, r0, r1
    ldr r0, =0x281f3d2c             @ list B's head
    bl painted
    ldr r1, =0x281282f8
    subs r0, r0, r1
    orrs r0, r4
    ite eq
    moveq r0, #1
    movne r0, #0
    pop {r4, pc}
painted:                            @ r0 a view list's head -> r0 the view of its first active node, 0 for none or no paint
    ldr r0, [r0]
pnode:
    cbz r0, pdone
    ldr r1, [r0, #0]
    lsls r1, r1, #31
    bmi pactive
    ldr r0, [r0, #0x14]
    b pnode
pactive:
    ldr r1, [r0, #4]
    cmp r1, #0
    ite ne
    ldrne r0, [r0, #0xc]
    moveq r0, #0
pdone:
    bx lr

selected:                           @ -> r0 nonzero when the selected block is one of the compressors in gr.inc
    push {r4-r6, lr}
    sub sp, #8
    add r0, sp, #4
    ldr r3, =0x28df0281             @ the selected block's ID, as the Edit view's layout reads it; takes its own lock
    blx r3
    subs r4, r0, #1                 @ IDs 1..8 are block records 0..7, IDs 11..18 records 8..15, the second row (0x28e07328)
    cmp r4, #8
    blo eblock
    subs r4, r0, #3
    subs r0, r4, #8
    cmp r0, #8
    bhs enone
eblock:
    ldr r5, =0x28449e78             @ the DSP model: block records of 0x54 bytes
    ldr r5, [r5]
    cbz r5, enone
    movs r0, #0
    ldr r3, =0x28e07845             @ its lock, as dsp_meter.s takes it
    blx r3
    movs r6, #0
    movs r2, #0x54
    mla r0, r4, r2, r5
    ldr r0, [r0, #0x14]             @ the block's handle among the preset's nodes
    cmp r0, #0x4b
    bhi eunlock
    add.w r1, r5, #0x4400
    ldr r1, [r1]
    add.w r1, r1, r0, lsl #2
    ldr r1, [r1, #0x24]
    cbz r1, eunlock
    ldrb r2, [r1, #5]
    cmp r2, #1
    bne eunlock                     @ kind 1: a block object
    ldr r6, [r1, #0x54]             @ its model's name, an Entry 3 string index
eunlock:
    movs r0, #0
    ldr r3, =0x28e0785d
    blx r3
    adr.w r1, comps
    movs r2, #COMP_COUNT
ecomp:
    ldrh r0, [r1], #2
    cmp r0, r6
    beq eyes
    subs r2, #1
    bne ecomp
enone:
    movs r0, #0
    b eout
eyes:
    movs r0, #1
eout:
    add sp, #8
    pop {r4-r6, pc}

.ltorg
.balign 4
lights:                             @ a compressor pedal's GR lights, 1 2 3 4 6 8 10 14 19 25 dB, in 1/256 octaves
    .hword 43, 85, 128, 170, 255, 340, 425, 595, 808, 1063
colours:                            @ lights 1..10
    .word 0x00ff00, 0x66ff00, 0xb3ff00, 0xffff00, 0xffd000, 0xffa500, 0xff7f00, 0xff5500, 0xff2a00, 0xff0000
comps:                              @ the compressor models' names, from gr.inc
    COMP_NAMES
.balign 4
data:                               @ 0 shown reduction (Q16), 4 frames since the compressor, 8 marker, 12 latch, 16 repaint,
    .space 52                       @ 20 ours shown, 24 the last window seen, 28 frames, 32 the block's knobs (word 218), 36 relayout at frame, 40 layout,
                                    @ 44 the selected divider segment, 48 the layout the Edit view shows
want:                               @ colour, x, y, w, h
    .space 20
widgets:                            @ ten slots for each edge, Top, Left, Bottom, Right, then Middle's slots 4..9
    .space 46 * 0x1c
nodes:                              @ their backing nodes
    .space 46 * 0x28
eprev:                              @ the colour each Edit-view light was drawn in
    .space 20
esave:                              @ the pixels under each Edit-view light
    .space 10 * 1200
