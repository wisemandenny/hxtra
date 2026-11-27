.syntax unified
.thumb

.thumb_func
.global xl_page_event
xl_page_event:
    push {r4-r8, lr}
    sub sp, #8
    mov r4, r0
    ldrb r0, [r4]
    cmp r0, #1
    bne page_done
    adr.w r5, page_state
    ldrb r7, [r4, #1]
    cmp r7, #5
    bne page_check_view
    ldr r0, [r4, #4]
    cmp r0, #1
    bne page_done
    movs r0, #0
    str r0, [r5]
    b page_done
page_check_view:
    movs r0, #8
    ldr r3, =0x28d98ce5
    blx r3
    cbnz r0, page_in_play
    movs r0, #0
    str r0, [r5]
    b page_done
page_in_play:
    subs r0, r7, #7
    cmp r0, #1
    bhi page_done
    movs r6, #1
    lsl.w r6, r6, r0
    ldr r8, [r4, #4]
    cmp r8, #1
    beq page_press
    cmp r8, #2
    beq page_release
    cmp r8, #3
    beq page_click
    cmp r8, #5
    beq page_disarm
    b page_done

page_press:
    ldrb r0, [r5, #2]
    bic r0, r0, r6
    strb r0, [r5, #2]
    ldrb r0, [r5]
    tst r0, r6
    bne page_done
    cbz r0, page_arm
    orr r0, r0, r6
    strb r0, [r5]
    movs r0, #3
    strb r0, [r5, #2]
    movs r0, #0
    strb r0, [r5, #1]
    b page_done
page_arm:
    strb r6, [r5]
    ldrb r0, [r5, #1]
    orr r0, r0, r6
    strb r0, [r5, #1]
    b page_done
page_release:
    ldrb r0, [r5]
    bic r0, r0, r6
    strb r0, [r5]
    b page_done
page_disarm:
    ldrb r0, [r5, #1]
    bic r0, r0, r6
    strb r0, [r5, #1]
    b page_done
page_click:
    ldrb r0, [r5, #2]
    tst r0, r6
    beq page_check_armed
    bic r0, r0, r6
    strb r0, [r5, #2]
    b page_disarm
page_check_armed:
    ldrb r0, [r5, #1]
    tst r0, r6
    beq page_done
    bic r0, r0, r6
    strb r0, [r5, #1]
    ldr r3, =0x28d98cb5
    blx r3
    mov r4, r0
    ldrb.w r6, [r4, #0x4d]
    cmp r6, #3
    bhi page_done
    cmp r7, #8
    ite eq
    addeq r6, #1
    subne r6, #1
    and r6, r6, #3
    mov r0, r4
    mov r1, r6
    ldr r3, =0x28dd9301
    blx r3
    movs r0, #2
    str r0, [sp]
    str r6, [sp, #4]
    ldr r3, =0x28e0690d
    blx r3
    movs r1, #21
    mov r2, sp
    movs r3, #6
    ldr r12, =0x28e25d21
    blx r12
page_done:
    add sp, #8
    pop {r4-r8, pc}

.ltorg
.balign 4
page_state:
    .word 0
