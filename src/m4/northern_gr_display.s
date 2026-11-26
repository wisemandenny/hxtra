@ SPDX-License-Identifier: GPL-3.0-or-later
@ Reference renderer extracted from Northern Audio Live 1.0's GR meter.
@ Derived from HXtra's Edit-view framebuffer overlay (Denny Wiseman / HXtra contributors).
@ Not connected to HXtra's live hooks. Caller owns view gating, locking and telemetry.
@ northern_gr_paint(r0 = framebuffer, r1 = unsigned GR in whole dB or 0xffffffff
@ for invalid, r2 = show (0 erase, nonzero draw)). Saturates at 24 dB.
@ northern_gr_forget() discards overlay history on framebuffer/view replacement.
@ Single caller only; do not call forget while the old overlay still needs erasing.
.syntax unified
.thumb
.thumb_func
northern_gr_paint:
    push {r4, r11, lr}
    sub sp, #4
    mov r11, r0
    mov r0, r1
    cmn r0, #1
    bne clamp_gr
    movs r0, #0x80
    b paint_gr
clamp_gr:
    cmp r0, #24
    it hi
    movhi r0, #24
paint_gr:
    mov r1, r2
    bl slots
    add sp, #4
    pop {r4, r11, pc}

.thumb_func
northern_gr_forget:
    adr.w r0, eprev
    movs r1, #0
    movs r2, #50
forget_loop:
    str r1, [r0], #4
    subs r2, #1
    bne forget_loop
    bx lr

slots:                              @ r0 a layout, r1 0 to take every light off, 1 to draw it; r11 the framebuffer
    push {r4-r9, lr}
    sub sp, #12
    mov r7, r0
    mov r8, r1
    movs r9, #0                     @ slot j, counting left to right or top to bottom
eslot:
    cmp r9, #24
    bhs eglyph
    @ 24 slots, x 8..253, top 8 pixels. Extra gaps mark 3/6/12/18 dB.
    movs r0, #10
    mul r4, r9, r0
    adds r4, #8
    cmp r9, #3
    it hs
    addhs r4, #2
    cmp r9, #6
    it hs
    addhs r4, #2
    cmp r9, #12
    it hs
    addhs r4, #2
    cmp r9, #18
    it hs
    addhs r4, #2
    movs r3, #232
    movs r6, #8
    movs r5, #8
    movw r1, #0x2945              @ dim unlit slot, nonzero for restore bookkeeping
    and r2, r7, #0x1f
    cmp r9, r2
    bhs ecolour
    adr.w r0, colours
    ldrh.w r1, [r0, r9, lsl #1]
    b ecolour
eglyph:
    @ Five 3x5 glyphs, each pixel 2x2; slots 24..98. -NNdB or --dB.
    sub.w r1, r9, #24
    movs r2, #15
    udiv r0, r1, r2               @ character index
    mls r1, r0, r2, r1            @ glyph pixel index (row-major)
    movs r3, #3
    udiv r2, r1, r3               @ pixel row
    mls r3, r2, r3, r1            @ pixel column
    lsl.w r4, r0, #3
    add.w r4, r4, #264
    add.w r4, r4, r3, lsl #1
    rsb.w r3, r2, #119            @ y = 238 - 2*row
    lsls r3, r3, #1
    movs r5, #2
    movs r6, #2
    str r3, [sp, #0]              @ preserve rectangle y while selecting glyph
    cmp r0, #3
    beq eglyph_d
    cmp r0, #4
    beq eglyph_b
    and r2, r7, #0x1f
    tst r7, #0x80
    bne eglyph_invalid
    cbz r0, eglyph_sign
    movs r3, #10
    cmp r0, #1
    beq eglyph_tens
    udiv r0, r2, r3
    mls r0, r0, r3, r2            @ ones
    b eglyph_lookup
eglyph_tens:
    udiv r0, r2, r3
    b eglyph_lookup
eglyph_sign:
    movs r0, #11                  @ blank at zero
    cbz r2, eglyph_lookup
    movs r0, #10                  @ minus at nonzero GR
    b eglyph_lookup
eglyph_invalid:
    cmp r0, #0
    ite eq
    moveq r0, #11
    movne r0, #10
    b eglyph_lookup
eglyph_d:
    movs r0, #12
    b eglyph_lookup
eglyph_b:
    movs r0, #13
eglyph_lookup:
    adr.w r3, glyphs
    ldrh.w r0, [r3, r0, lsl #1]
    lsr.w r0, r0, r1
    tst r0, #1
    ite ne
    movwne r1, #0xffff
    movweq r1, #0x0841            @ dark glyph background
    ldr r3, [sp, #0]
ecolour:
    str r3, [sp, #0]
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
    adr.w r12, esave
    cmp r9, #24
    bhs esave_glyph
    add.w r12, r12, r9, lsl #7    @ 128 bytes per 8x8 bar slot
    b ecol
esave_glyph:
    add.w r12, r12, #3072
    sub.w r0, r9, #24
    add.w r12, r12, r0, lsl #3    @ 8 bytes per 2x2 glyph pixel
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
    cmp.w r9, #99
    bne eslot
    add sp, #12
    pop {r4-r9, pc}

.balign 4
colours:                            @ BGR565, 24-slot green/yellow/orange/red gradient
    .hword 0x26e3, 0x26e5, 0x26e7, 0x26e9, 0x26ec, 0x26ee, 0xef2, 0xef4, 0xef6, 0xef8, 0xefb, 0xefd, 0x67f, 0x5bf, 0x4ff, 0x45f, 0x39f, 0x2df, 0x21f, 0x1bf, 0x15f, 0x11f, 0xbf, 0x5f
glyphs:                             @ 0..9, minus, blank, d, B; 15 row-major bits
    .hword 0x7b6f, 0x749a, 0x73e7, 0x79e7, 0x49ed, 0x79cf, 0x7bcf, 0x24a7, 0x7bef, 0x79ef, 0x1c0, 0x0, 0x7be4, 0x3aeb
.balign 4
eprev:
    .space 200
esave:
    .space 24 * 128 + 75 * 8
