.syntax unified
.cpu cortex-m4
.thumb

.macro call_stock target
    ldr r12, =\target
    blx r12
.endm

.thumb_func
.global preset_ring_dim
preset_ring_dim:
    @ The replaced BNE followed the comparison with the selected preset.
    it eq
    bxeq lr
    ldrb r1, [sp, #2]
    push {r4, r5, r6, lr}
    mov r4, r0
    mov r0, r1
    bl .Lfile_color
    cbz r0, ring_off
    subs r0, #1
    adr r1, dim_leds
    ldr r5, [r1, r0, lsl #2]
    mov r0, r4
    mov r1, r5
    call_stock 0x28dbb309
    movs r1, #1
    b ring_mode
ring_off:
    movs r1, #0
ring_mode:
    mov r0, r4
    call_stock 0x28dbb36d
    pop {r4, r5, r6, lr}
    ldr r12, =0x28dd8a59
    bx r12

.thumb_func
.global preset_icon_dim
preset_icon_dim:
    @ r7 is the absolute preset slot supplied to the XL tile builder.
    push {r0, r1, r4, lr}
    mov r0, r7
    bl .Lfile_color
    cbz r0, dim_icon_ready
    adr r1, dim_icons
    ldr r2, [sp, #4]
    movw r3, #0x152
    cmp r2, r3
    it eq
    addeq r1, #20
    subs r0, #1
    ldrh.w r1, [r1, r0, lsl #1]
    str r1, [sp, #4]
dim_icon_ready:
    pop {r0, r1, r4, lr}
    ldr r12, =0x28e2ade1
    bx r12

.thumb_func
.global preset_file_color
preset_file_color:
.Lfile_color:
    cmp r0, #127
    bhi invalid_slot
    push {r4-r6, lr}
    sub sp, #0x1c8
    mov r4, r0
    mov r0, sp
    call_stock 0x28df6289
    str r4, [sp, #4]
    mov r0, sp
    add r1, sp, #8
    call_stock 0x28df6671
    add r6, sp, #0x40
    ldr r0, [sp, #8]
    add r1, sp, #12
    mov r2, r6
    call_stock 0x28df57ed
    movs r5, #0
    mov r0, r6
    call_stock 0x28df60a5
    cmp r0, #0
    blt file_done
    add.w r0, r6, #0x18
    call_stock 0x28dad345
    cmp r0, #70
    blt file_close
    subs r1, r0, #8
    add.w r0, r6, #0x18
    movs r2, #0
    call_stock 0x28dad231
    cmp r0, #0
    blt file_close
    add.w r0, r6, #0x18
    add r1, sp, #0x2c
    movs r2, #8
    call_stock 0x28dad1c1
    cmp r0, #8
    bne file_close
    ldr r0, [sp, #0x2c]
    ldr r1, =0x4805c465
    cmp r0, r1
    bne file_close
    ldr r0, [sp, #0x30]
    bic r1, r0, #0xff000000
    ldr r2, =0x00435058
    cmp r1, r2
    bne file_close
    lsrs r0, r0, #24
    cmp r0, #10
    it ls
    movls r5, r0
file_close:
    mov r0, r6
    call_stock 0x28df5e19
file_done:
    mov r0, r5
    add sp, #0x1c8
    pop {r4-r6, pc}
invalid_slot:
    movs r0, #0
    bx lr

.ltorg
.balign 4
dim_leds:
    .word 0x02000c, 0x000410, 0x000608, 0x000c08, 0x000901
    .word 0x060d00, 0x0d0400, 0x0b0003, 0x07000b, 0x0c1007
dim_icons:
    XL_DIM_ICON_IDS

.thumb_func
.global preset_color_paint
preset_color_paint:
    push {r0-r4, lr}
    mov r0, r1
    bl refresh_selected
    pop {r0-r4, lr}
    ldr r12, =PRIOR_PLAY
    bx r12

.thumb_func
refresh_selected:
    push {r4-r10, lr}
    mov r4, r0
    ldrb r0, [r4, #3]
    cmp r0, #0                    @ stock paint hides the switch tiles
    bne paint_done
    bl color
    mov r8, r0
    adr r1, painted_color
    ldrb r0, [r1]
    cmp r0, r8
    beq paint_done
    strb r8, [r1]
    call_stock 0x28d98c0d
    add r6, r0, #4
    adr r9, icons
    add r5, r4, #0x60
    movs r7, #0
    mov.w r10, #0
    call_stock 0x28e2ad41
paint_switch:
    ldrb r0, [r6, r7, lsl #1]
    cmp r0, #13
    bne paint_next
    ldr r3, [r5]                 @ this image widget's selected tile
    movs r2, #0
paint_find:
    ldrh.w r1, [r9, r2, lsl #1]
    cmp r3, r1
    beq paint_match
    adds r2, #1
    cmp r2, #20
    blo paint_find
    b paint_next
paint_match:
    cmp r2, #10
    ite lo
    movlo r2, r8
    addhs r2, r8, #10
    mov r0, r5
    ldrh.w r1, [r9, r2, lsl #1]
    call_stock 0x28e2ade1
    movs r0, #1
    lsl.w r0, r0, r7
    orr r10, r0
paint_next:
    adds r5, #0x24
    adds r7, #1
    cmp r7, #6
    blo paint_switch
    call_stock 0x28e2adf1
    movs r7, #0
paint_ring:
    lsrs.w r10, r10, #1
    bcc paint_ring_next
    ldr r1, =0x281f561c
    ldrb r1, [r1, r7]
    cmp r1, #1                    @ preserve off, blink, and tuner modes
    bne paint_ring_next
    adr r1, ring_colors
    ldr r1, [r1, r8, lsl #2]
    mov r0, r7
    call_stock 0x28dbb309
paint_ring_next:
    adds r7, #1
    cmp r10, #0
    bne paint_ring
paint_done:
    pop {r4-r10, pc}

.ltorg
.balign 4
painted_color:
    .word 0xff
