@ label_color.s - HXtra settings' and block parameters' labels in Teal, apart from the stock white ones.
.syntax unified
.thumb
.include "label.inc"                @ VIRTUAL_FIRST, VIRTUAL_COUNT, TEAL, PARAMS, PARAM_TABLE
.equ LABEL_COLOUR, 0x28dc6455       @ (slot, 0xRRGGBB): the slot's label colour
.equ LABEL_TEXT, 0x28dc63d1         @ (knob, text): the knob's label
.equ PARAM_INDEX, 0x6c              @ in the knob drawer's frame, as 0x28dbe830 leaves them
.equ SECOND_MODEL, 0x70

.thumb_func
.global label_colour
label_colour:                       @ the section paint's 0x28dc6454(slot, white), the slot's setting ID in r5
    sub.w r2, r5, #VIRTUAL_FIRST
    cmp r2, #VIRTUAL_COUNT
    bhs label_set
.thumb_func
.global label_any
label_any:                          @ (knob, colour) for a label that is always HXtra's: tuner.s's page
    ldr r1, =TEAL
label_set:
    ldr r3, =LABEL_COLOUR
    bx r3

.thumb_func
.global label_param
label_param:                        @ the knob drawer's 0x28dc63d0(knob, name), its block info in r5; page loops set white first
    push {r0, r1, r4, lr}
    ldrb r2, [sp, #16 + SECOND_MODEL]
    cmp r2, #0
    ite eq
    ldreq.w r3, [r5, #1]
    ldrne.w r3, [r5, #5]
    ldrb r2, [sp, #16 + PARAM_INDEX]
    adr.w r1, label_params
    add.w r4, r1, #4 * PARAMS
label_find:
    cmp r1, r4
    bhs label_param_text
    ldrh r12, [r1]
    cmp r12, r3
    bne label_find_next
    ldrb r12, [r1, #2]
    cmp r2, r12
    bhs label_hxtra
label_find_next:
    adds r1, #4
    b label_find
label_hxtra:
    ldr r1, =TEAL
    ldr r3, =LABEL_COLOUR
    blx r3
label_param_text:
    pop {r0, r1, r4, lr}
    ldr r3, =LABEL_TEXT
    bx r3

.ltorg
.balign 4
label_params:                       @ {preset ID, first HXtra parameter index}
    PARAM_TABLE
