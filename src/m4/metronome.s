@ metronome.s - the Metronome block in the signal flow: Volume/Pan's teal pictures, with on/off, instead of Looper's grey ones;
@ and a plain effect, not a looper, wherever the firmware tests a block's browser category for Looper.
.syntax unified
.thumb
.equ PRESET_ID, 181                 @ tools/patch_click.py PRESET_ID
.equ TEAL, 0x10                     @ Volume/Pan's browser category
.equ NOT_LOOPER, 5                  @ Modulation, the Tremolo it is copied from: no Looper test site treats it specially

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
