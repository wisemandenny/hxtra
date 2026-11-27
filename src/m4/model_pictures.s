@ Optional picture previews. Stock and feature painters keep their widgets and coordinates.
@ The framebuffer is copied between paints, so remove our previous pixels before the next paint.
.syntax unified
.thumb
.include "hxtra.inc"
.include "model_pictures.inc"

.equ SCREEN, 0x28128260
.equ PANEL, 0x28128258
.equ EDIT_VIEW, 0x281282f8
.equ PARAM_VIEW, 0x28128270
.equ BROWSER_VIEW, 0x281299d0
.equ WIDGET_LOCK, 0x28e24971
.equ WIDGET_UNLOCK, 0x28e24ae9
.equ STRIDE, 480                    @ 240 RGB565 pixels per column, bottom first

.thumb_func
model_pictures_params:             @ generic list A paint, shared with nine other views
    ldr r2, =SCREEN
    ldrb r2, [r2]
    cmp r2, #2
    beq 1f
    ldr r2, =PARAM_VIEW
    cmp r1, r2
    bne 3f
    ldr r1, =EDIT_VIEW
    b model_pictures_edit
1:
    ldr r2, =0x281f3d2c             @ list B's first active view must be the browser
    ldr r2, [r2]
2:
    cbz r2, 3f
    ldr r3, [r2]
    lsls r3, r3, #31
    bmi 4f
    ldr r2, [r2, #0x14]
    b 2b
3:
    bx lr
4:
    ldr r1, [r2, #0xc]
    b model_pictures_browser

.thumb_func
model_pictures_edit:
    ldr r2, =EDIT_VIEW
    cmp r1, r2
    bne edit_return
    ldr r2, =SCREEN
    ldrb r2, [r2]
    cmp r2, #1
    bne edit_return
    ldr r2, =PANEL
    ldrb r2, [r2]
    cmp r2, #2
    bne edit_return
    push {r4-r8, lr}
    sub sp, #0x80
    mov r4, r0
    bl enabled
    cbz r0, edit_done
    movs r0, #0
    strb r0, [sp]
    mov r0, sp
    ldr r3, =0x28df0281             @ selected block ID and path, takes the DSP-model lock
    blx r3
    cmn r0, #1
    beq edit_done
    mov r5, r0
    ldr r3, =0x28d92a99             @ current DSP context
    blx r3
    mov r1, r5
    mov r2, sp
    movs r3, #0xff
    strb r3, [r2, #1]
    strb r3, [r2, #2]
    ldr r3, =0x28e0fe95             @ selected block info: preset ID at +1, little endian
    blx r3
    cmp r0, #0
    blt edit_done
    ldrb r0, [sp, #1]
    ldrb r1, [sp, #2]
    orr.w r0, r0, r1, lsl #8
    movs r1, #2                     @ preset ID and Edit resource in each table row
    bl picture
    cbz r0, edit_done
    mov r5, r0
    ldr r3, =WIDGET_LOCK
    blx r3
    movs r6, #123                   @ centred between the vertical GR positions
    movs r7, #129                   @ above the middle GR lights, just below the unsplit path
    movs r8, #EDIT_HEIGHT
    bl blank
    cbnz r0, edit_draw
    movs r7, #187                   @ alternative above the unsplit path, before the top title
    bl blank
    cbz r0, edit_unlock
edit_draw:
    bl draw
edit_unlock:
    ldr r3, =WIDGET_UNLOCK
    blx r3
edit_done:
    add sp, #0x80
    pop {r4-r8, pc}
edit_return:
    bx lr

.thumb_func
model_pictures_browser:
    ldr r2, =BROWSER_VIEW
    cmp r1, r2
    bne browser_return
    ldrb r2, [r1, #0x40]
    cmp r2, #2                      @ models, as opposed to categories or favourites
    bne browser_return
    push {r4-r10, lr}
    sub sp, #8
    mov r4, r0
    mov r5, r1
    bl enabled
    cmp r0, #0
    beq browser_done
    movs r0, #0
    str r0, [sp]
    str r0, [sp, #4]
    mov r0, sp
    ldr r3, =0x28df0281
    blx r3
    ldrb r0, [sp]
    cmp r0, #1
    bhi browser_done
    add r6, r5, r0
    addw r1, r5, #0x574
    ldr.w r7, [r1, r0, lsl #2]       @ highlighted item
    ldrb.w r0, [r6, #0x56e]
    ldrb.w r1, [r6, #0x570]
    ldr r3, =0x28e0edcd             @ length of this list
    blx r3
    cmp r0, #0
    ble browser_done
    cmp r7, r0
    bhs browser_done
    ldrb.w r9, [r5, #0x569]         @ first visible item
    subs.w r9, r7, r9
    cmp r9, #4
    bhi browser_done
    ldrb.w r0, [r6, #0x56e]
    ldrb.w r1, [r6, #0x570]
    mov r2, r7
    add r3, sp, #4
    ldr r12, =0x28e01205            @ item descriptor, model index at +4
    blx r12
    cmp r0, #0
    blt browser_done
    ldr r0, [sp, #4]
    cmp r0, #0
    beq browser_done
    ldr r0, [r0, #4]
    movs r1, #0                     @ model index and browser resource in each table row
    bl picture
    cmp r0, #0
    beq browser_done
    mov r5, r0
    ldr r3, =WIDGET_LOCK
    blx r3
    movs r6, #234                   @ stop before the scrollbar at x310
    movs r8, #BROWSER_HEIGHT
    movs r10, #5
browser_row:
    movs r0, #40
    mul r7, r9, r0
    rsb.w r7, r7, #161              @ inside the row, below its top at y194 - 40*row
    bl blank
    cbnz r0, browser_draw
    adds r9, #1                     @ long labels can use all of the selected row
    cmp r9, #5
    it eq
    moveq r9, #0
    subs r10, #1
    bne browser_row
    b browser_unlock
browser_draw:
    bl draw
browser_unlock:
    ldr r3, =WIDGET_UNLOCK
    blx r3
browser_done:
    add sp, #8
    pop {r4-r10, pc}
browser_return:
    bx lr

.thumb_func
model_pictures_erase:
    adr.w r3, state
    ldr r2, [r3, #8]
    cbz r2, erase_return
    push {r4-r8, lr}
    mov r4, r0
    ldm r3, {r6-r8}
    ldr r3, =WIDGET_LOCK
    blx r3
    adr.w r0, state
    movs r1, #0
    str r1, [r0, #8]
    movs r3, #2
    bl pixels                       @ erase only matching nonzero pixels
    ldr r3, =WIDGET_UNLOCK
    blx r3
    pop {r4-r8, pc}
erase_return:
    bx lr

.thumb_func
enabled:
    movs r0, #SETTING_MODEL_PICTURES_ENABLED
    movs r1, #SETTING_MODEL_PICTURES_ENABLED_MAX
    movs r2, #SETTING_MODEL_PICTURES_ENABLED_DEFAULT
    push {r4, lr}
    bl hxtra_setting_get
    eor r0, #1                     @ On is stored as 0, Off as 1
    pop {r4, pc}

.thumb_func
picture:                            @ r0 ID, r1 key offset (0 browser, 2 Edit) -> resource index or 0
    adr.w r2, saved
    movw r3, #(2 * PICTURE_WIDTH * BROWSER_HEIGHT)
    add r2, r3
    add r2, r1
    movw r3, #PICTURE_COUNT
1:
    ldrh r12, [r2]
    cmp r0, r12
    beq 2f
    adds r2, #8
    subs r3, #1
    bne 1b
    movs r0, #0
    bx lr
2:
    cmp r1, #0
    ite eq
    ldrheq r0, [r2, #6]             @ browser key is at row+0, resource at row+6
    ldrhne r0, [r2, #2]             @ Edit key is at row+2, resource at row+4
    bx lr

.thumb_func
blank:
    movs r3, #0
    b pixels

.thumb_func
draw:                               @ r4 framebuffer, r5 resource, r6 x, r7 y, r8 height, under the widget lock
    push {r9, lr}
    adr.w r0, state
    stmia r0, {r6-r8}
    adr.w r9, image
    ldr r0, [r9, #-4]
    cbnz r0, 1f
    movs r0, #1
    str r0, [r9, #-4]
    mov r0, r9
    movs r1, #0
    ldr r3, =0x28e24ab1             @ initialise an image widget with no node
    blx r3
1:
    mov r0, r9
    movs r1, #0                     @ bottom-left anchor
    ldr r3, =0x28e24aa9
    blx r3
    mov r0, r9
    mov r1, r5
    ldr r3, =0x28e24c19             @ resource index
    blx r3
    mov r0, r9
    mov r1, r6
    mov r2, r7
    ldr r3, =0x28e24c69             @ position
    blx r3
    mov r0, r9
    movs r1, #1
    ldr r3, =0x28e24a99             @ visible
    blx r3
    mov r0, r4
    mov r1, r4
    mov r2, r9
    ldr r3, =0x28e24a01             @ paint image
    blx r3
    movs r3, #1
    bl pixels                       @ remember which pixels we actually put in the blank rectangle
    pop {r9, pc}

.thumb_func
pixels:                             @ r3: 0 check for blank, 1 remember, 2 erase; rectangle in r6-r8
    push {r5-r7, r9-r11, lr}
    movw r0, #STRIDE
    mla r5, r6, r0, r4
    add.w r5, r5, r7, lsl #1
    adr.w r6, saved
    movs r7, #PICTURE_WIDTH
    movs r11, #0
pixel_column:
    mov r0, r5
    mov r1, r8
pixel_row:
    ldrh r2, [r0]
    cbz r3, pixel_check
    cmp r3, #1
    beq pixel_save
    ldrh r9, [r6]
    cbz r2, pixel_next
    cmp r2, r9
    it eq
    strheq r11, [r0]
    b pixel_next
pixel_save:
    strh r2, [r6]
    b pixel_next
pixel_check:
    cbnz r2, pixel_busy
pixel_next:
    adds r6, #2
    adds r0, #2
    subs r1, #1
    bne pixel_row
    addw r5, r5, #STRIDE
    subs r7, #1
    bne pixel_column
    movs r0, #1
    pop {r5-r7, r9-r11, pc}
pixel_busy:
    movs r0, #0
    pop {r5-r7, r9-r11, pc}

HXTRA_SETTING_GET
.ltorg
.balign 4
state:
    .space 12                       @ x, y, height (zero when no picture is drawn)
    .word 0                         @ image widget initialised
image:
    .space 36
saved:
    .space 2 * PICTURE_WIDTH * BROWSER_HEIGHT
pictures:
    PICTURE_TABLE
