@ metronome.s - the Metronome block in the signal flow: Volume/Pan's teal pictures, with on/off, instead of Looper's grey ones;
@ and a plain effect, not a looper, wherever the firmware tests a block's browser category for Looper.
.syntax unified
.thumb
.equ PRESET_ID, 181                 @ tools/patch_click.py PRESET_ID
.equ TEAL, 0x10                     @ Volume/Pan's browser category
.equ NOT_LOOPER, 5                  @ Modulation, the Tremolo it is copied from: no Looper test site treats it specially
.equ BLOCK_CATEGORY, 0x28e1548d     @ (model, preset ID, &category) -> <0 on error; 0x19 for a model without Entry 3's category
.equ VOLUME, 0x0e                   @ Volume's block category, teal like the Metronome's
.equ METRONOME, 0x19                @ the Metronome's block category: tools/features/metronome.py METRONOME

metronome_slot:                     @ at 0x28dd3042, for ldrb.w r2, [sp, #0x10]: the block info at sp+4 has its preset model ID at +1
    ldrb.w r2, [sp, #0x10]
    ldrb.w r12, [sp, #6]            @ flags and r12 are free at the site
    cmp r12, #0
    bne 1f
    ldrb.w r12, [sp, #5]
    cmp r12, #PRESET_ID
    it eq
    moveq r2, #TEAL
1:  bx lr

@ In place of a site's ldrb.w reg, [sp, #off] of the block info's category (+0xc); the preset model ID is at info+1, so sp+off-0xb.
.macro category_load name, reg, off
\name:
    ldr.w \reg, [sp, #(\off - 0xb)]
    cmp \reg, #PRESET_ID            @ every site's next instruction sets the flags or leaves them unread
    ldrb.w \reg, [sp, #\off]
    it eq
    moveq \reg, #NOT_LOOPER
    bx lr
.endm

category_load metronome_cat_r3_20, r3, 0x20
category_load metronome_cat_r3_28, r3, 0x28
category_load metronome_cat_r3_38, r3, 0x38
category_load metronome_cat_r3_48, r3, 0x48
category_load metronome_cat_r2_34, r2, 0x34

@ The footswitch assign clears a block of category None or Unknown (0x18, 0x19) instead, and the Metronome's block category is 0x19.
metronome_assign_cat:               @ in place of its call of BLOCK_CATEGORY at 0x28dd84d8
    push {r1, r2, r4, lr}
    ldr r4, =BLOCK_CATEGORY
    blx r4
    pop {r1, r2}
    cmp r1, #PRESET_ID
    itt eq
    moveq r1, #VOLUME
    strbeq r1, [r2]
    pop {r4, pc}

@ Its footswitch's LED would be white at every other call, preset load among them: the colour lookup has no colour for 0x19.
metronome_led_colour:               @ owns the colour lookup (r0 block category, r1 on); r12 its stock code
    cmp r0, #METRONOME
    it eq
    moveq r0, #VOLUME
    bx r12


.thumb_func
xl_metronome_led:
    adr.w r12, stock_led
    orr r12, #1
    b metronome_led_colour
.thumb_func
stock_led:
    subs r0, #4
    cmp r0, #0x12
    ldr r12, =0x28dbaf19
    bx r12
.ltorg
