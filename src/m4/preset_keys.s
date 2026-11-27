@ preset_keys.s - the preset file's extra keys: each feature's data after the stock map, under a key of its own. tools/patch_menu.py
@ add_preset_keys() owns the three sites and lists the features' handlers in preset_keys.inc, in ORDER. A writer (stream) writes its
@ key with the stream's write and returns how many keys it wrote; a finder (key, data, length) gets every key read back, and first
@ START, before each read of a file.
.syntax unified
.thumb
.include "preset_keys.inc"          @ PK_WRITERS, PK_FINDERS
.equ NAMES, 12                      @ the last stock key, an array of strings: section 10 starts with it when there
.equ START, -1

.thumb_func
.global pk_serialize
pk_serialize:                       @ in place of the preset file's serializer call (stream, toc): then each feature's keys
    push {r3-r7, lr}
    mov r4, r0
    PK_BEFORE
    ldr r3, =SERIALIZE
    blx r3
    mov r6, r0
    PK_AFTER
    movs r5, #0
    adr.w r7, pk_writers
pk_serialize_each:
    adr.w r3, pk_writers_end
    cmp r7, r3
    beq pk_serialize_done
    ldr r3, [r7], #4
    mov r0, r4
    blx r3
    add r5, r0
    b pk_serialize_each
pk_serialize_done:
    adr.w r0, pk_count
    strb r5, [r0]
    mov r0, r6
    pop {r3-r7, pc}

.thumb_func
.global pk_toc
pk_toc:                             @ in place of the TOC's second write (stream, toc): then the map's count, counting our keys
    push {r3-r7, lr}
    mov r4, r0
    ldr r3, =TOC_WRITE
    blx r3
    mov r6, r0
    adr.w r5, pk_count
    ldrb r7, [r5]
    cbz r7, pk_toc_done
    movs r0, #0
    strb r0, [r5]
    ldr r3, =PRESET
    blx r3
    movs r1, #1
    ldr r3, =PRESET_FLAG
    blx r3
    adds r0, #9                     @ as the serializer counts its keys (0x28dead0e)
    orr r0, r0, #0x80
    add r0, r7
    strb r0, [r5, #1]
    adds r1, r5, #1
    movs r2, #1
    ldr r0, [r4]
    ldr r3, [r4, #4]
    blx r3
pk_toc_done:
    mov r0, r6
    pop {r3-r7, pc}

.thumb_func
.global pk_section
pk_section:                         @ in place of the load's read of section 10 (file, 10, 0, buffer, max on the stack)
    push {r3-r7, lr}
    sub sp, #8
    ldr r12, [sp, #32]
    str.w r12, [sp]
    mov r4, r3
    ldr r12, =SECTION_READ
    blx r12
    mov r5, r0
    mov.w r0, #START
    bl pk_found
    cmp r5, #0
    ble pk_section_done
    mov r6, r4
    add.w r7, r4, r5
    ldrb r2, [r6]
    cmp r2, #NAMES
    bne pk_section_keys
    ldrb r2, [r6, #1]               @ key 12: an array of strings
    cmp r2, #0xdc
    bne pk_section_fixarray
    ldrb r3, [r6, #2]
    ldrb r2, [r6, #3]
    orr.w r3, r2, r3, lsl #8
    adds r6, #4
    b pk_section_names
pk_section_fixarray:
    and r3, r2, #0xf0
    cmp r3, #0x90
    bne pk_section_done
    and r3, r2, #0x0f
    adds r6, #2
pk_section_names:
    cbz r3, pk_section_keys
    cmp r6, r7
    bhs pk_section_done
    ldrb r2, [r6]
    and r1, r2, #0xe0
    cmp r1, #0xa0
    bne pk_section_str8
    and r2, r2, #0x1f
    adds r6, #1
    add r6, r2
    b pk_section_name_done
pk_section_str8:
    cmp r2, #0xd9
    bne pk_section_str16
    ldrb r2, [r6, #1]
    adds r6, #2
    add r6, r2
    b pk_section_name_done
pk_section_str16:
    cmp r2, #0xda
    bne pk_section_nil
    ldrb r2, [r6, #1]
    ldrb r1, [r6, #2]
    orr.w r2, r1, r2, lsl #8
    adds r6, #3
    add r6, r2
    b pk_section_name_done
pk_section_nil:
    cmp r2, #0xc0
    bne pk_section_done
    adds r6, #1
pk_section_name_done:
    subs r3, #1
    b pk_section_names
pk_section_keys:                    @ each key a positive fixint with a bin8 or bin16, to the end or the first that is not
    adds r1, r6, #3
    cmp r1, r7
    bhi pk_section_done
    ldrb r0, [r6]
    cmp r0, #0x80
    bhs pk_section_done
    ldrb r2, [r6, #1]
    cmp r2, #0xc4
    bne pk_section_bin16
    ldrb r2, [r6, #2]
    b pk_section_key
pk_section_bin16:
    cmp r2, #0xc5
    bne pk_section_done
    adds r1, r6, #4
    cmp r1, r7
    bhi pk_section_done
    ldrb r2, [r6, #2]
    ldrb r3, [r6, #3]
    orr.w r2, r3, r2, lsl #8
pk_section_key:                     @ r0 the key, r1 its data, r2 its length
    adds r6, r1, r2
    cmp r6, r7
    bhi pk_section_done
    bl pk_found
    b pk_section_keys
pk_section_done:
    mov r0, r5
    add sp, #8
    pop {r3-r7, pc}

pk_found:                           @ (key, data, length) to each feature's finder
    push {r4-r8, lr}
    mov r4, r0
    mov r5, r1
    mov r6, r2
    adr.w r7, pk_finders
pk_found_each:
    adr.w r3, pk_finders_end
    cmp r7, r3
    beq pk_found_done
    ldr r3, [r7], #4
    mov r0, r4
    mov r1, r5
    mov r2, r6
    blx r3
    b pk_found_each
pk_found_done:
    pop {r4-r8, pc}

.ltorg
.balign 4
pk_writers:
    PK_WRITERS
pk_writers_end:
pk_finders:
    PK_FINDERS
pk_finders_end:
pk_count:                           @ 0 the keys the last serialize wrote, until the TOC counts them; 1 the map's new count
    .word 0
