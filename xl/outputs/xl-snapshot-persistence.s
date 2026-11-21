.syntax unified
.cpu cortex-m4
.thumb
.text

.equ MAP_OFFSET, 61
.equ RECORD_BYTES, 0x278
.equ HEADER_BYTES, 12
.equ EXTRA_BYTES, HEADER_BYTES + 2 * RECORD_BYTES
.equ XL_PRESET_LIMIT, 0xffff
.equ XL_STREAM_CONTEXT, 0x28232048
.equ XL_STORAGE_BACKEND, 0x28231d80
.equ XL_STREAM_WRITE, 0x28df6b7d
.equ XL_BACKEND_WRITE, 0x28df6d01
.equ XL_TOC_WRITE, 0x28df0c1d
.equ XL_SECTION_READ, 0x28df59e1
.equ XL_RECORDS_OFFSET, 0xc
.equ XL_SNAPSHOT_BUSY, 0xc81
.equ XL_SNAPSHOT_CURRENT, 0xa03
.equ XL_SNAPSHOT_PREVIOUS, 0xa04
.equ XL_SNAPSHOT_SELECT, 0x28de8dcd
.equ XL_SNAPSHOT_MANAGER, 0x28d98c35
.equ XL_SETTING_GET, 0x28e25c71
.equ XL_CC_DIRECT, 0x28d9e4e7
.equ XL_CC_REMAINDER, 0x28d9e397
.equ XL_CC_DONE, 0x28d9e055
.equ XL_SERIALIZE_COMPACT, 0x28df0905
.equ XL_SERIALIZE_ALTERNATE, 0x28df0d35
.equ XL_PRESET_GET, 0x28d95249
.equ XL_PRESET_FLAG, 0x28e08811
.equ XL_RECORD_INIT, 0x28de718d
.equ XL_CURRENT_GET, 0x28de958d
.equ XL_FS_PREV_CONTINUE, 0x28dd975f
.equ XL_FS_NEXT_CONTINUE, 0x28dd992f
.equ XL_IMAGE_SET, 0x28e2ade1
.equ XL_EXTRA_PLAY_FIRST, 577

.global xl_save_append
.thumb_func
@ r0 = fresh stock preset, r1 = current length, r2 = buffer capacity,
@ r3 = disjoint buffer holding two records. Returns new length or zero.
@ Call this on the completed stock serialization, before any bytes are committed.
xl_save_append:
    push    {r4-r7, lr}
    cmp     r1, #MAP_OFFSET + 1
    blo     save_invalid
    movw    r4, #XL_PRESET_LIMIT - EXTRA_BYTES
    cmp     r1, r4
    bhi     save_invalid
    addw    r4, r1, #EXTRA_BYTES
    cmp     r4, r2
    bhi     save_invalid
    cmp     r3, #0
    beq     save_invalid

    ldrb    r7, [r0, #MAP_OFFSET]
    subs    r2, r7, #0x80
    cmp     r2, #14
    bhi     save_invalid
    ldr.w   r2, [r0, #13]
    cmp     r2, #MAP_OFFSET
    bne     save_invalid
    ldr.w   r2, [r0, #53]
    cmp     r2, r1
    bne     save_invalid
    ldr.w   r2, [r0, #57]
    cmp     r2, r1
    bne     save_invalid

    add     r5, r0, r1
    adr.w   r6, extension_header
    movs    r2, #HEADER_BYTES
save_header:
    ldrb    r7, [r6], #1
    strb    r7, [r5], #1
    subs    r2, #1
    bne     save_header

    movw    r2, #2 * RECORD_BYTES
save_records:
    ldrb    r7, [r3], #1
    strb    r7, [r5], #1
    subs    r2, #1
    bne     save_records

    @ The tail entries mark the beginning of section 10. Preserve them so
    @ stock reads can see both optional names and the appended extension.
    ldrb    r7, [r0, #MAP_OFFSET]
    adds    r7, #1
    strb    r7, [r0, #MAP_OFFSET]
    mov     r0, r4
    pop     {r4-r7, pc}
save_invalid:
    movs    r0, #0
    pop     {r4-r7, pc}

.global xl_append_to_stream
.thumb_func
@ r0 = stock stream {context, write}, r1 reserved,
@ r2 = contiguous extra records, r3 = stock map byte.
@ Returns the new map byte or zero. A zero after an attempted write requires
@ the caller to abandon the temporary file. The stock TOC stays intact.
xl_append_to_stream:
.Lappend_to_stream:
    push    {r4-r11, lr}
    sub     sp, #4
    mov     r4, r0
    mov     r6, r2
    mov     r7, r3
    subs    r3, #0x80
    cmp     r3, #14
    bhi     stream_invalid
    cbz     r6, stream_invalid
    ldr     r8, [r4]
    ldr     r9, [r4, #4]
    ldr     r10, [r8]
    movw    r3, #XL_PRESET_LIMIT - EXTRA_BYTES
    cmp     r10, r3
    bhi     stream_invalid
    addw    r11, r10, #EXTRA_BYTES

    mov     r0, r8
    adr.w   r1, extension_header
    movs    r2, #HEADER_BYTES
    blx     r9
    cmp     r0, #0
    blt     stream_write_failed
    ldr     r3, [r8]
    add.w   r2, r10, #HEADER_BYTES
    cmp     r3, r2
    bne     stream_write_failed
    mov     r0, r8
    mov     r1, r6
    movw    r2, #2 * RECORD_BYTES
    blx     r9
    cmp     r0, #0
    blt     stream_write_failed
    ldr     r3, [r8]
    cmp     r3, r11
    bne     stream_write_failed

    adds    r0, r7, #1
    b       stream_return
stream_write_failed:
    mov     r0, r4
    bl      .Lcancel_stock_save
stream_invalid:
    movs    r0, #0
stream_return:
    add     sp, #4
    pop     {r4-r11, pc}

.global xl_finish_stream_save
.thumb_func
@ r0 = stream, r1 = stock TOC, r2 = new map byte or 0 to preserve 0x81.
@ The stock caller must already have sought to the TOC. Returns 0 on success,
@ -1 on failure. Counter deltas are used because seeking moves the file cursor
@ independently of the outer stream's write counter.
xl_finish_stream_save:
.Lfinish_stream_save:
    push    {r4-r8, lr}
    sub     sp, #8
    mov     r4, r0
    strb    r2, [sp]
    ldrd    r5, r6, [r4]
    ldr     r7, [r5]
    ldr     r3, =XL_TOC_WRITE
    blx     r3
    ldr     r3, [r5]
    adds    r7, #51
    cmp     r3, r7
    bne     finish_failed
    ldrb    r3, [sp]
    cbz     r3, finish_ok
    mov     r0, r5
    mov     r1, sp
    movs    r2, #1
    blx     r6
    cmp     r0, #0
    blt     finish_failed
    ldr     r3, [r5]
    adds    r7, #1
    cmp     r3, r7
    bne     finish_failed
finish_ok:
    movs    r0, #0
    b       finish_return
finish_failed:
    mov     r0, r4
    bl      .Lcancel_stock_save
    mov.w   r0, #-1
finish_return:
    add     sp, #8
    pop     {r4-r8, pc}

.global xl_hook_save_compact
.thumb_func
xl_hook_save_compact:
    ldr     r2, =XL_SERIALIZE_COMPACT
    movs    r3, #0
    b       save_with_snapshots

.global xl_hook_save_alternate
.thumb_func
xl_hook_save_alternate:
    ldr     r2, =XL_SERIALIZE_ALTERNATE
    movs    r3, #1
    b       save_with_snapshots

.global xl_hook_usb_export
.thumb_func
xl_hook_usb_export:
    ldr     r2, =XL_SERIALIZE_ALTERNATE
    movs    r3, #2
    b       save_with_snapshots

save_with_snapshots:
    push    {r4-r11, lr}
    sub     sp, #12
    mov     r4, r0
    mov     r5, r1
    mov     r6, r2
    mov     r7, r3
    adr.w   r8, active_snapshot_state
    adr.w   r9, save_stream_state
    movs    r0, #0
    str     r0, [r9]
    str     r0, [r9, #4]
    movs    r10, #0
    movs    r11, #0
    ldrb    r0, [r8, #1]
    cbz     r0, save_call_stock
    ldr     r3, =XL_SNAPSHOT_MANAGER
    blx     r3
    mov     r10, r0
    ldrb.w  r11, [r10, #XL_SNAPSHOT_CURRENT]
    cmp     r11, #1
    bhi     save_cancel
    ldrb.w  r0, [r10, #XL_SNAPSHOT_PREVIOUS]
    str     r0, [sp, #4]
    cmp     r7, #2
    beq     save_usb_park
    mov     r0, r10
    movs    r1, #0
    bl      .Lrecall_logical_snapshot
    cmp     r0, #0
    blt     save_cancel
    movs    r0, #1
    str     r0, [sp, #8]
    b       save_serialize
save_usb_park:
    @ HX Edit reads the preset while connected. Present the native records
    @ to the serializer without recalling a sound or applying its bypass.
    mov     r0, r10
    adr.w   r1, active_snapshot_records
    bl      .Lexchange_extra_bank
    cmp     r0, #0
    beq     save_cancel
    movs    r0, #0
    strb    r0, [r8, #1]
    movs    r0, #2
    str     r0, [sp, #8]
    b       save_serialize
save_call_stock:
    movs    r0, #0
    str     r0, [sp, #8]
save_serialize:
    mov     r0, r4
    mov     r1, r5
    blx     r6
    str     r0, [sp]
    cmp     r0, #0
    blt     save_cancel_restore
    adr.w   r2, active_preset_color
    ldrb    r2, [r2]
    ldrb    r0, [r8]
    orrs    r0, r2
    beq     save_restore
    cmp     r7, #2
    bne     save_map
    @ XL USB writer context is {position, buffer, capacity}.
    movs    r3, #0
    cbz     r2, save_usb_snapshot_size
    movs    r3, #8
save_usb_snapshot_size:
    ldrb    r0, [r8]
    cbz     r0, save_usb_bounds
    addw    r3, r3, #EXTRA_BYTES
save_usb_bounds:
    ldr     r0, [r4]
    ldr     r1, [r0]
    ldr     r2, [r0, #8]
    subs    r1, r2, r1
    blo     save_cancel_restore
    cmp     r1, r3
    blo     save_cancel_restore
save_map:
    movs    r3, #0x81
    cbz     r7, save_append_extra
    ldr     r3, =XL_PRESET_GET
    blx     r3
    movs    r1, #1
    ldr     r3, =XL_PRESET_FLAG
    blx     r3
    cmp     r0, #1
    bhi     save_cancel_restore
    add.w   r3, r0, #0x89
save_append_extra:
    ldrb    r0, [r8]
    cbz     r0, save_color_without_extra
    mov     r0, r4
    mov     r1, r5
    adr.w   r2, active_snapshot_records
    bl      .Lappend_to_stream
    cbz     r0, save_cancel_restore
    mov     r3, r0
save_color_without_extra:
    adr.w   r2, active_preset_color
    ldrb    r2, [r2]
    mov     r0, r3
    cbz     r2, save_extensions_done
    mov     r0, r4
    bl      .Lappend_preset_color
    cbz     r0, save_cancel_restore
save_extensions_done:
    cmp     r7, #0
    it      eq
    moveq   r0, #0
    strb    r0, [r9, #4]
    str     r4, [r9]
    b       save_restore
save_cancel:
    movs    r0, #0
    str     r0, [sp, #8]
save_cancel_restore:
    mov     r0, r4
    bl      .Lcancel_stock_save
    str     r4, [r9]
    movs    r0, #1
    strb    r0, [r9, #5]
    mov.w   r0, #-1
    str     r0, [sp]
save_restore:
    ldr     r0, [sp, #8]
    cmp     r0, #0
    beq     save_return
    cmp     r0, #2
    beq     save_usb_unpark
    mov     r0, r10
    add.w   r1, r11, #4
    bl      .Lrecall_logical_snapshot
    cmp     r0, #0
    blt     save_restore_failed
    ldr     r0, [sp, #4]
    strb.w  r0, [r10, #XL_SNAPSHOT_PREVIOUS]
    b       save_return
save_usb_unpark:
    mov     r0, r10
    adr.w   r1, active_snapshot_records
    bl      .Lexchange_extra_bank_unchecked
    movs    r0, #1
    strb    r0, [r8, #1]
    b       save_return
save_restore_failed:
    mov     r0, r4
    bl      .Lcancel_stock_save
    str     r4, [r9]
    movs    r0, #1
    strb    r0, [r9, #5]
    mov.w   r0, #-1
    str     r0, [sp]
save_return:
    ldr     r0, [sp]
    add     sp, #12
    pop     {r4-r11, pc}

.global xl_append_preset_color
.thumb_func
@ r0 = stream, r2 = color 1..10, r3 = map byte before appending HXPC.
@ Returns the incremented map byte, or zero for the caller to cancel.
xl_append_preset_color:
.Lappend_preset_color:
    push    {r4-r6, lr}
    sub     sp, #8
    mov     r4, r3
    subs    r3, #0x80
    cmp     r3, #14
    bhi     color_write_failed
    subs    r3, r2, #1
    cmp     r3, #9
    bhi     color_write_failed
    strb    r2, [sp, #7]
    ldr     r3, =0x4805c465
    str     r3, [sp]
    ldr     r3, =0x00435058
    strh    r3, [sp, #4]
    lsrs    r3, #16
    strb    r3, [sp, #6]
    ldrd    r5, r3, [r0]
    ldr     r6, [r5]
    movw    r2, #XL_PRESET_LIMIT - 8
    cmp     r6, r2
    bhi     color_write_failed
    mov     r0, r5
    mov     r1, sp
    movs    r2, #8
    blx     r3
    cmp     r0, #0
    blt     color_write_failed
    ldr     r3, [r5]
    adds    r6, #8
    cmp     r3, r6
    bne     color_write_failed
    adds    r0, r4, #1
    b       color_write_return
color_write_failed:
    movs    r0, #0
color_write_return:
    add     sp, #8
    pop     {r4-r6, pc}
    .ltorg

save_stream_state:
    .space 8  @ stream pointer, map byte, cancelled flag

.global xl_active_preset_color
xl_active_preset_color:
active_preset_color:
    .word 0

.global xl_hook_save_toc
.thumb_func
@ Called in place of the post-serializer TOC write at either save site.
xl_hook_save_toc:
.Lhook_save_toc:
    adr.w   r3, save_stream_state
    ldr     r2, [r3]
    cmp     r2, r0
    bne     save_toc_stock
    movs    r2, #0
    str     r2, [r3]
    ldrb    r2, [r3, #5]
    cbnz    r2, save_toc_aborted
    ldrb    r2, [r3, #4]
    b       .Lfinish_stream_save
save_toc_stock:
    ldr     r3, =XL_TOC_WRITE
    bx      r3
save_toc_aborted:
    mov.w   r0, #-1
    bx      lr
    .ltorg

.global xl_hook_device_save_toc
.thumb_func
xl_hook_device_save_toc:
    push    {r4, lr}
    bl      .Lhook_save_toc
    cmp     r0, #0
    it      lt
    movlt   r6, r0              @ both callers return the status in r6
    pop     {r4, pc}

.global xl_hook_native_snapshot
.thumb_func
xl_hook_native_snapshot:
    cmp     r1, #3
    bhi     native_snapshot_stock
    adr.w   r2, active_snapshot_state
    ldrb    r2, [r2, #1]
    cmp     r2, #0
    bne.w   .Lrecall_logical_snapshot
native_snapshot_stock:
    ldr     r12, =XL_SNAPSHOT_SELECT
    bx      r12
    .ltorg

.global xl_hook_usb_export_toc
.thumb_func
xl_hook_usb_export_toc:
    push    {r4, lr}
    bl      .Lhook_save_toc
    cmp     r0, #0
    pop     {r4, lr}
    it      ge
    bxge    lr
    mov     r4, r0
    ldr     r12, =0x28e22a0b      @ stock USB export cleanup on serializer error
    bx      r12
    .ltorg

.global xl_cancel_stock_save
.thumb_func
@ r0 = outer stream. Return 1 only for the known stock preset save backend.
xl_cancel_stock_save:
.Lcancel_stock_save:
    cbz     r0, cancel_unknown
    ldr     r1, [r0, #4]
    ldr     r2, =XL_STREAM_WRITE
    cmp     r1, r2
    bne     cancel_unknown
    ldr     r1, [r0]
    ldr     r2, =XL_STREAM_CONTEXT
    cmp     r1, r2
    bne     cancel_unknown
    ldr     r2, [r1, #0x18]
    ldr     r3, =XL_BACKEND_WRITE
    cmp     r2, r3
    bne     cancel_unknown
    ldr     r2, [r1, #0x1c]
    cbnz    r2, cancel_unknown
    ldr     r0, [r1, #8]
    ldr     r2, =XL_STORAGE_BACKEND
    cmp     r0, r2
    bne     cancel_unknown
    movs    r1, #0
    strb    r1, [r0, #0xd]
    movs    r0, #1
    bx      lr
cancel_unknown:
    movs    r0, #0
    bx      lr
    .ltorg

.global xl_load_extension
.thumb_func
@ r0 = pointer to validated top-level key 0x64, r1 = length of that entry,
@ r2 = disjoint destination for two records. Returns 1 or 0; on failure the
@ destination is untouched. The caller owns MessagePack key traversal.
xl_load_extension:
.Lload_extension:
    push    {r4, r5, r6, lr}
    movw    r3, #EXTRA_BYTES
    cmp     r1, r3
    bne     load_invalid
    cmp     r2, #0
    beq     load_invalid
    adr.w   r3, extension_header
    movs    r1, #HEADER_BYTES
load_header:
    ldrb    r4, [r0], #1
    ldrb    r12, [r3], #1
    cmp     r4, r12
    bne     load_invalid
    subs    r1, #1
    bne     load_header
    @ Validate both records before modifying the destination. The XL recall
    @ loop indexes 72-byte controller entries from these selectors; 0x40
    @ is the stock unassigned selector.
    mov     r6, r0
    movs    r5, #2
load_validate_record:
    add.w   r3, r6, #0x28
    movs    r1, #64
load_validate_controller:
    ldrb    r4, [r3], #7
    cmp     r4, #0x40
    bhi     load_invalid
    subs    r1, #1
    bne     load_validate_controller
    @ The snapshot label occupies the final 11 bytes of the record.
    addw    r3, r6, #0x26d
    movs    r1, #11
load_validate_name:
    ldrb    r4, [r3], #1
    cbz     r4, load_record_valid
    subs    r1, #1
    bne     load_validate_name
    b       load_invalid
load_record_valid:
    addw    r6, r6, #RECORD_BYTES
    subs    r5, #1
    bne     load_validate_record
    movw    r1, #2 * RECORD_BYTES
load_records:
    ldrb    r4, [r0], #1
    strb    r4, [r2], #1
    subs    r1, #1
    bne     load_records
    movs    r0, #1
    pop     {r4, r5, r6, pc}
load_invalid:
    movs    r0, #0
    pop     {r4, r5, r6, pc}

.global xl_read_section_10
.thumb_func
@ The first five arguments match the stock section reader. The sixth is
@ the staging buffer for two records. Returns stock result in r0 and a
@ validated-extension flag in r1.
xl_read_section_10:
.Lread_section_10:
    push    {r4-r6, lr}
    sub     sp, #8
    ldr     r4, [sp, #24]
    str     r4, [sp]
    ldr     r6, [sp, #28]
    mov     r5, r3
    ldr     r12, =XL_SECTION_READ
    blx     r12
    mov     r4, r0
    movs    r1, #0
    movs    r2, #0
    cmp     r4, #0
    blt     section_done
    mov     r0, r5
    mov     r1, r4
    mov     r2, r6
    bl      .Lload_section_tail
    mov     r2, r1
    mov     r1, r0
section_done:
    mov     r0, r4
    add     sp, #8
    pop     {r4-r6, pc}
    .ltorg

.global xl_hook_read_section_10
.thumb_func
@ Drop-in BL target for XL v3.80 section 10 read site 0x28df157c.
@ The parser must consume the staged flag only after a successful preset load.
xl_hook_read_section_10:
    push    {r4, lr}
    sub     sp, #8
    ldr     r4, [sp, #16]
    str     r4, [sp]
    adr.w   r4, staged_snapshot_records
    str     r4, [sp, #4]
    bl      .Lread_section_10
    adr.w   r4, staged_snapshot_valid
    strb    r1, [r4]
    strb    r2, [r4, #1]
    add     sp, #8
    pop     {r4, pc}

.global xl_hook_finish_preset_load
.thumb_func
@ Replaces each stock pop.w {r4-r8,pc} after the load result is in r0.
@ Keep the prior extra-bank state on failed loads and consume staging once.
xl_hook_finish_preset_load:
    adr.w   r2, staged_snapshot_valid
    ldrb    r1, [r2]
    ldrb    r3, [r2, #1]
    movs    r4, #0
    strh    r4, [r2]
    mov     r2, r3
    adr.w   r3, staged_snapshot_records
    bl      .Lcommit_loaded_bank
    pop.w   {r4-r8, pc}

.global xl_hook_usb_import
.thumb_func
@ USB edit-buffer import while the stock preset mutex is held.
xl_hook_usb_import:
    push    {r4-r8, lr}
    mov     r4, r0
    mov     r5, r1
    movs    r6, #0
    movs    r7, #0
    cmp     r5, #62
    blo     usb_import_stock
    movw    r2, #0x5000
    cmp     r5, r2
    bhi     usb_import_stock
    ldr     r2, [r4]
    ldr     r3, =0x2d366ca9
    cmp     r2, r3
    bne     usb_import_stock
    ldr     r2, [r4, #4]
    ldr     r3, =0x696c6568
    cmp     r2, r3
    bne     usb_import_stock
    ldr     r2, [r4, #8]
    ldr     r3, =0x00da0078
    cmp     r2, r3
    bne     usb_import_stock
    ldrb    r2, [r4, #12]
    cmp     r2, #48
    bne     usb_import_stock
    ldrb    r2, [r4, #61]
    cmp     r2, #0x89
    blo     usb_import_stock
    cmp     r2, #0x8c
    bhi     usb_import_stock
    ldr     r2, [r4, #56]
    lsrs    r2, #8
    ldrb    r3, [r4, #60]
    orr     r2, r2, r3, lsl #24
    cmp     r2, #62
    blo     usb_import_stock
    cmp     r2, r5
    bhi     usb_import_stock
    add     r0, r4, r2
    sub     r1, r5, r2
    adr.w   r2, active_snapshot_records
    ldr     r12, =(usb_snapshot_records - active_snapshot_records)
    add     r2, r12
    bl      .Lload_section_tail
    mov     r6, r0
    mov     r7, r1
usb_import_stock:
    mov     r0, r4
    mov     r1, r5
    ldr     r12, =0x28df80b9
    blx     r12
    mov     r1, r6
    mov     r2, r7
    adr.w   r3, active_snapshot_records
    ldr     r12, =(usb_snapshot_records - active_snapshot_records)
    add     r3, r12
    bl      .Lcommit_loaded_bank
    pop     {r4-r8, pc}
    .ltorg

.thumb_func
.Lcommit_loaded_bank:
    @ r0 = stock result, r1 = valid bank, r2 = color, r3 = staged records.
    cmp     r0, #0
    it      lt
    bxlt    lr
    push    {r4-r6, lr}
    adr.w   r4, active_preset_color
    strb    r2, [r4]
    adr.w   r4, active_snapshot_state
    movs    r2, #0
    strb    r1, [r4]
    strb    r2, [r4, #1]
    strb    r2, [r4, #3]
    cbz     r1, preset_load_return
    adr.w   r5, active_snapshot_records
    movw    r6, #(2 * RECORD_BYTES) / 4
activate_records:
    ldr     r4, [r3], #4
    str     r4, [r5], #4
    subs    r6, #1
    bne     activate_records
preset_load_return:
    pop     {r4-r6, pc}

.global xl_load_section_tail
.thumb_func
@ r0 = section 10 bytes, r1 = size, r2 = record staging buffer.
@ Section 10 begins after the stock snapshot array. Returns the snapshot
@ validity flag in r0 and a validated HXPC palette index (or zero) in r1.
xl_load_section_tail:
.Lload_section_tail:
    push    {r4-r8, lr}
    mov     r8, r2
    adds    r5, r0, r1
    bcs     tail_invalid
    cmp     r0, r5
    beq     tail_invalid
    ldrb    r3, [r0]
    cmp     r3, #12
    bne     tail_array_end
    adds    r0, #1
    cmp     r0, r5
    bhs     tail_invalid
    ldrb    r3, [r0], #1
    cmp     r3, #0xdc
    beq     tail_array16
    and     r6, r3, #0xf0
    cmp     r6, #0x90
    bne     tail_invalid
    and     r4, r3, #15
    b       tail_name
tail_array16:
    subs    r3, r5, r0
    cmp     r3, #2
    blo     tail_invalid
    ldrb    r4, [r0], #1
    ldrb    r3, [r0], #1
    orr     r4, r3, r4, lsl #8
tail_name:
    cmp     r4, #0
    beq     tail_array_end
    cmp     r0, r5
    bhs     tail_invalid
    ldrb    r3, [r0], #1
    cmp     r3, #0xc0
    beq     tail_name_done
    cmp     r3, #0xd9
    beq     tail_str8
    cmp     r3, #0xda
    beq     tail_str16
    and     r6, r3, #0xe0
    cmp     r6, #0xa0
    bne     tail_invalid
    and     r3, #31
    b       tail_skip
tail_str8:
    cmp     r0, r5
    bhs     tail_invalid
    ldrb    r3, [r0], #1
    b       tail_skip
tail_str16:
    subs    r3, r5, r0
    cmp     r3, #2
    blo     tail_invalid
    ldrb    r3, [r0], #1
    ldrb    r6, [r0], #1
    orr     r3, r6, r3, lsl #8
tail_skip:
    subs    r6, r5, r0
    cmp     r3, r6
    bhi     tail_invalid
    add     r0, r3
tail_name_done:
    subs    r4, #1
    b       tail_name
tail_array_end:
    movs    r4, #0                  @ pending HX6B entry
    movs    r7, #0                  @ pending HXPC entry
tail_key:
    cmp     r0, r5
    beq     tail_apply
    subs    r3, r5, r0
    cmp     r3, #3
    blo     tail_invalid
    ldrb    r6, [r0]
    cmp     r6, #0x64
    beq     tail_snapshot
    cmp     r6, #0x65
    bne     tail_invalid
    cmp     r7, #0
    bne     tail_invalid
    cmp     r3, #8
    blo     tail_invalid
    ldrb    r6, [r0, #1]
    cmp     r6, #0xc4
    bne     tail_invalid
    ldrb    r6, [r0, #2]
    cmp     r6, #5
    bne     tail_invalid
    mov     r7, r0
    adds    r0, #8
    b       tail_key
tail_snapshot:
    cmp     r4, #0
    bne     tail_invalid
    movw    r6, #EXTRA_BYTES
    cmp     r3, r6
    blo     tail_invalid
    ldrb    r3, [r0, #1]
    cmp     r3, #0xc5
    bne     tail_invalid
    ldrb    r3, [r0, #2]
    ldrb    r4, [r0, #3]
    orr     r3, r4, r3, lsl #8
    adds    r3, #4
    cmp     r3, r6
    bne     tail_invalid
    mov     r4, r0
    add     r0, r6
    b       tail_key
tail_apply:
    movs    r5, #0
    cbz     r7, tail_apply_snapshot
    ldrb    r0, [r7, #3]
    cmp     r0, #'H'
    bne     tail_apply_snapshot
    ldrb    r0, [r7, #4]
    cmp     r0, #'X'
    bne     tail_apply_snapshot
    ldrb    r0, [r7, #5]
    cmp     r0, #'P'
    bne     tail_apply_snapshot
    ldrb    r0, [r7, #6]
    cmp     r0, #'C'
    bne     tail_apply_snapshot
    ldrb    r6, [r7, #7]
    cmp     r6, #10
    it      ls
    movls   r5, r6
tail_apply_snapshot:
    movs    r0, #0
    cbz     r4, tail_done
    mov     r0, r4
    movw    r1, #EXTRA_BYTES
    mov     r2, r8
    bl      .Lload_extension
tail_done:
    mov     r1, r5
    pop     {r4-r8, pc}
tail_invalid:
    movs    r0, #0
    movs    r1, #0
    pop     {r4-r8, pc}

.global xl_exchange_extra_bank
.thumb_func
@ r0 = XL manager; r1 = disjoint, word-aligned buffer for two parked records.
@ Caller owns the snapshot-manager lock and tracks the bank. Exchange only
@ physical slots 0 and 1. Slots 2 and 3 remain native in both banks.
xl_exchange_extra_bank:
.Lexchange_extra_bank:
    cbz     r0, exchange_blocked
    cbz     r1, exchange_blocked
    ldrb.w  r2, [r0, #XL_SNAPSHOT_BUSY]
    cbnz    r2, exchange_blocked
.Lexchange_extra_bank_unchecked:
    push    {r4, lr}
    adds    r0, #XL_RECORDS_OFFSET
    movw    r2, #(2 * RECORD_BYTES) / 4
exchange_word:
    ldr     r3, [r0]
    ldr     r4, [r1]
    str     r4, [r0], #4
    str     r3, [r1], #4
    subs    r2, #1
    bne     exchange_word
    movs    r0, #1
    pop     {r4, pc}
exchange_blocked:
    movs    r0, #0
    bx      lr

.global xl_recall_logical_snapshot
.thumb_func
@ r0 = manager, r1 = logical index 0..5. Caller serializes recall against
@ preset load/save. Existing extra records must have been staged already.
@ r0 returns the result of stock recall, or -1 when a request is refused.
xl_recall_logical_snapshot:
.Lrecall_logical_snapshot:
    push    {r4-r11, lr}
    sub     sp, #12
    mov     r4, r0
    mov     r5, r1
    cmp     r5, #5
    bhi     recall_refused
    ldrb.w  r0, [r4, #XL_SNAPSHOT_BUSY]
    cmp     r0, #0
    bne     recall_refused
    adr.w   r6, active_snapshot_state
    ldrb    r7, [r6, #1]
    movs    r8, #0
    cmp     r5, #4
    blo     recall_bank_known
    ldrb    r0, [r6]
    cmp     r0, #0
    beq     recall_refused
    subs    r5, #4
    movs    r8, #1
recall_bank_known:
    cmp     r7, r8
    bne     recall_cross
    mov     r0, r4
    mov     r1, r5
    ldr     r3, =XL_SNAPSHOT_SELECT
    blx     r3
    b       recall_return
recall_cross:
    ldrb.w  r9, [r4, #XL_SNAPSHOT_CURRENT]
    ldrb.w  r0, [r4, #XL_SNAPSHOT_PREVIOUS]
    str     r0, [sp, #4]
    cmp     r9, #3
    bhi     recall_refused
    movs    r10, #0
    cmp     r9, #2
    bhs     recall_exchange
    @ Copy the outgoing sound to a spare physical slot so stock recall
    @ can diff against it after slots 0 and 1 have been exchanged.
    movs    r10, #2
    cmp     r5, #2
    it      eq
    moveq   r10, #3
    movw    r2, #RECORD_BYTES
    mla     r11, r10, r2, r4
    add.w   r11, r11, #XL_RECORDS_OFFSET
    adr.w   r0, recall_scratch
    mov     r1, r11
    bl      copy_one_record
    movw    r2, #RECORD_BYTES
    mla     r1, r9, r2, r4
    add.w   r1, r1, #XL_RECORDS_OFFSET
    mov     r0, r11
    bl      copy_one_record
    strb.w  r10, [r4, #XL_SNAPSHOT_CURRENT]
recall_exchange:
    mov     r0, r4
    adr.w   r1, active_snapshot_records
    bl      .Lexchange_extra_bank
    cbz     r0, recall_restore_refused
    strb.w  r8, [r6, #1]
    mov     r0, r4
    mov     r1, r5
    ldr     r3, =XL_SNAPSHOT_SELECT
    blx     r3
    str     r0, [sp]
    cmp     r0, #0
    bge     recall_cross_ok
    mov     r0, r4
    adr.w   r1, active_snapshot_records
    bl      .Lexchange_extra_bank
    cbz     r0, recall_cross_ok
    strb    r7, [r6, #1]
    strb.w  r9, [r4, #XL_SNAPSHOT_CURRENT]
    ldr     r0, [sp, #4]
    strb.w  r0, [r4, #XL_SNAPSHOT_PREVIOUS]
    cmp     r10, #0
    beq     recall_result
    mov     r0, r11
    adr.w   r1, recall_scratch
    bl      copy_one_record
    b       recall_result
recall_cross_ok:
    cmp     r10, #0
    beq     recall_result
    mov     r0, r11
    adr.w   r1, recall_scratch
    bl      copy_one_record
    strb.w  r9, [r4, #XL_SNAPSHOT_PREVIOUS]
recall_result:
    ldr     r0, [sp]
    b       recall_return
recall_restore_refused:
    cmp     r10, #0
    beq     recall_refused
    mov     r0, r11
    adr.w   r1, recall_scratch
    bl      copy_one_record
    strb.w  r9, [r4, #XL_SNAPSHOT_CURRENT]
recall_refused:
    mov.w   r0, #-1
recall_return:
    add     sp, #12
    pop     {r4-r11, pc}

copy_one_record:
    movw    r2, #RECORD_BYTES / 4
copy_record_word:
    ldr     r3, [r1], #4
    str     r3, [r0], #4
    subs    r2, #1
    bne     copy_record_word
    bx      lr
    .ltorg

.balign 4
extension_header:
    .byte 0x64, 0xc5, 0x04, 0xf8, 'H', 'X', '6', 'B', 2, 0, 0, 0
snapshot_five_name:
    .asciz "SNAPSHOT 5"
.balign 4
snapshot_six_name:
    .asciz "SNAPSHOT 6"
.balign 4

.global xl_staged_snapshot_valid
xl_staged_snapshot_valid:
staged_snapshot_valid:
    .word 0 @ snapshot flag at byte 0, staged preset color at byte 1
.global xl_staged_snapshot_records
xl_staged_snapshot_records:
staged_snapshot_records:
    .space 2 * RECORD_BYTES
.global xl_active_snapshot_state
xl_active_snapshot_state:
active_snapshot_state:
    .word 0  @ bytes: has extras, live bank, previous logical slot, previous valid
.global xl_active_snapshot_records
xl_active_snapshot_records:
active_snapshot_records:
    .space RECORD_BYTES
second_active_snapshot_record:
    .space RECORD_BYTES
recall_scratch:
    .space RECORD_BYTES

.global xl_resolve_midi_snapshot
.thumb_func
@ r0 = CC 69 value, r1 = current logical slot, r2 = previous logical slot,
@ r3 bit 0 = extras exist and bit 1 = toggle previous on reselection.
@ Returns logical slot in r0 and extras-exist flag in r1.
xl_resolve_midi_snapshot:
.Lresolve_midi_snapshot:
    tst     r3, #1
    ite     eq
    moveq   r12, #4
    movne   r12, #6
    cmp     r0, #5
    bls     midi_direct
    cmp     r0, #8
    beq     midi_next
    cmp     r0, #9
    bne     midi_ignore
    cbz     r1, midi_prev_wrap
    subs    r0, r1, #1
    b       midi_done
midi_prev_wrap:
    sub.w   r0, r12, #1
    b       midi_done
midi_next:
    adds    r0, r1, #1
    cmp     r0, r12
    it      hs
    movhs   r0, #0
    b       midi_done
midi_direct:
    cmp     r0, #4
    it      hs
    orrhs   r3, r3, #1
    cmp     r0, r1
    bne     midi_done
    tst     r3, #2
    it      ne
    movne   r0, r2
    b       midi_done
midi_ignore:
    mov     r0, r1
midi_done:
    and     r1, r3, #1
    bx      lr

.global xl_hook_cc69
.thumb_func
@ Replaces cmp r1,#3 and bls.w at 0x28d9e390. Keep the original
@ dispatch for presets without an extra bank.
xl_hook_cc69:
    push    {r0-r7, lr}
    sub     sp, #12
    adr.w   r7, active_snapshot_state
    ldrb    r2, [r7]
    cbnz    r2, cc_has_bank
    cmp     r1, #4
    blo     cc_stock
    cmp     r1, #5
    bhi     cc_stock
    b       cc_resolve
cc_has_bank:
    cmp     r1, #5
    bls     cc_resolve
    cmp     r1, #8
    beq     cc_resolve
    cmp     r1, #9
    bne     cc_stock
cc_resolve:
    mov     r4, r1
    ldr     r3, =XL_SNAPSHOT_MANAGER
    blx     r3
    mov     r5, r0
    ldrb    r2, [r7]
    cbnz    r2, cc_bank_ready
    bl      initialize_extra_bank
    cmp     r0, #0
    beq     cc_done
cc_bank_ready:
    ldrb.w  r6, [r5, #XL_SNAPSHOT_CURRENT]
    ldrb    r0, [r7, #1]
    cbz     r0, cc_current_known
    cmp     r6, #2
    it      lo
    addlo   r6, #4
cc_current_known:
    movs    r0, #0
    str     r0, [sp, #4]
    movs    r0, #103
    mov     r1, sp
    ldr     r3, =XL_SETTING_GET
    blx     r3
    ldr     r3, [sp, #4]
    cmp     r3, #0
    ite     eq
    moveq   r3, #1
    movne   r3, #3
    ldrb    r2, [r7, #3]
    cbz     r2, cc_no_previous
    ldrb    r2, [r7, #2]
    b       cc_previous_known
cc_no_previous:
    mov     r2, r6
cc_previous_known:
    str     r3, [sp, #8]
    mov     r0, r4
    mov     r1, r6
    bl      .Lresolve_midi_snapshot
    cmp     r0, r6
    bne     cc_do_recall
    ldr     r3, [sp, #8]
    cmp     r3, #3
    beq     cc_done
cc_do_recall:
    mov     r1, r0
    mov     r0, r5
    bl      .Lrecall_logical_snapshot
    cmp     r0, #0
    blt     cc_done
    strb    r6, [r7, #2]
    movs    r0, #1
    strb    r0, [r7, #3]
cc_done:
    add     sp, #12
    pop     {r0-r7, lr}
    ldr     r12, =XL_CC_DONE
    bx      r12
cc_stock:
    add     sp, #12
    pop     {r0-r7, lr}
    cmp     r1, #3
    ite     ls
    ldrls   r12, =XL_CC_DIRECT
    ldrhi   r12, =XL_CC_REMAINDER
    bx      r12
    .ltorg

.global xl_hook_snapshot_button
.thumb_func
@ Called where Snapshot mode converts the physical button to index 0..3.
@ A repeat on the lit switch toggles banks. Buttons 0 and 1 select the two
@ extras in bank B; buttons 2 and 3 return directly to native slots 2 and 3.
xl_hook_snapshot_button:
    push    {r4-r7, lr}
    sub     sp, #4
    mov     r4, r0
    mov     r5, r1
    adr.w   r7, active_snapshot_state
    cmp     r5, #3
    bhi     button_stock
    ldrb.w  r6, [r4, #XL_SNAPSHOT_CURRENT]
    ldrb    r3, [r7, #1]
    cbnz    r3, button_extra_live
    cmp     r5, r6
    bne     button_native_target
    ldrb    r3, [r7]
    cbnz    r3, button_enter_extras
    bl      initialize_extra_bank
    cbz     r0, button_refused
button_enter_extras:
    and     r5, r5, #1
    adds    r5, #4
    b       button_recall
button_native_target:
    ldrb    r3, [r7]
    cbz     r3, button_stock
    b       button_recall
button_extra_live:
    cmp     r6, #2
    it      lo
    addlo   r6, #4
    cmp     r5, #2
    bhs     button_recall
    add.w   r3, r5, #4
    cmp     r3, r6
    beq     button_recall
    mov     r5, r3
button_recall:
    mov     r0, r4
    mov     r1, r5
    bl      .Lrecall_logical_snapshot
    cmp     r0, #0
    blt     button_return
    strb    r6, [r7, #2]
    movs    r2, #1
    strb    r2, [r7, #3]
    b       button_return
button_stock:
    mov     r0, r4
    mov     r1, r5
    ldr     r3, =XL_SNAPSHOT_SELECT
    blx     r3
    b       button_return
button_refused:
    mov.w   r0, #-1
button_return:
    add     sp, #4
    pop     {r4-r7, pc}

initialize_extra_bank:
    push    {r4, lr}
    mov     r4, r0
    ldrb.w  r2, [r4, #XL_SNAPSHOT_BUSY]
    cbnz    r2, initialize_busy
    adr.w   r1, active_snapshot_records
    adr.w   r2, snapshot_five_name
    ldr     r3, =XL_RECORD_INIT
    blx     r3
    mov     r0, r4
    adr.w   r1, second_active_snapshot_record
    adr.w   r2, snapshot_six_name
    ldr     r3, =XL_RECORD_INIT
    blx     r3
    adr.w   r3, active_snapshot_state
    movs    r0, #1
    strb    r0, [r3]
    pop     {r4, pc}
initialize_busy:
    movs    r0, #0
    pop     {r4, pc}
    .ltorg

.global xl_hook_footswitch_previous
.thumb_func
xl_hook_footswitch_previous:
    movs    r1, #9
    ldr     r12, =XL_FS_PREV_CONTINUE
    b       footswitch_step

.global xl_hook_footswitch_next
.thumb_func
xl_hook_footswitch_next:
    movs    r1, #8
    ldr     r12, =XL_FS_NEXT_CONTINUE
footswitch_step:
    adr.w   r3, active_snapshot_state
    ldrb    r2, [r3]
    cbz     r2, footswitch_step_stock
    @ The dispatcher's prologue leaves its stack aligned after local storage.
    bl      resolve_footswitch_step
    add     sp, #0x1c
    pop.w   {r4-r7, pc}
footswitch_step_stock:
    push    {r4, lr}
    mov     r4, r12
    ldr     r3, =XL_CURRENT_GET
    blx     r3
    mov     r12, r4
    pop     {r4, lr}
    bx      r12

resolve_footswitch_step:
    push    {r4-r6, lr}
    mov     r4, r0
    adr.w   r5, active_snapshot_state
    mov     r0, r1
    ldrb.w  r6, [r4, #XL_SNAPSHOT_CURRENT]
    ldrb    r2, [r5, #1]
    cbz     r2, fs_current_known
    cmp     r6, #2
    it      lo
    addlo   r6, #4
fs_current_known:
    mov     r1, r6
    mov     r2, r6
    ldrb    r3, [r5]
    bl      .Lresolve_midi_snapshot
    mov     r1, r0
    mov     r0, r4
    bl      .Lrecall_logical_snapshot
    cmp     r0, #0
    blt     fs_step_done
    strb    r6, [r5, #2]
    movs    r2, #1
    strb    r2, [r5, #3]
fs_step_done:
    pop     {r4-r6, pc}
    .ltorg

.global xl_step_logical_snapshot
.thumb_func
@ r0 = 8 for next or 9 for previous. Use the existing bank if present.
xl_step_logical_snapshot:
    push    {r4, lr}
    mov     r4, r0
    ldr     r3, =XL_SNAPSHOT_MANAGER
    blx     r3
    mov     r1, r4
    bl      resolve_footswitch_step
    pop     {r4, pc}
    .ltorg

.global xl_hook_play_snapshot_set
.thumb_func
@ Stock Play snapshot tile setter: widget in r0 and original image in r1.
xl_hook_play_snapshot_set:
    push    {r2, lr}
    bl      play_extra_image
    pop     {r2, lr}
    ldr     r12, =XL_IMAGE_SET
    bx      r12

.global xl_hook_play_snapshot_lookup
.thumb_func
@ Replaces ldr.w r1,[r3,r6,lsl #2] before stock dirty-image comparison.
xl_hook_play_snapshot_lookup:
    ldr.w   r1, [r3, r6, lsl #2]
    push    {r0, r2, r3, r12, lr}
    sub     sp, #4
    bl      play_extra_image
    add     sp, #4
    pop     {r0, r2, r3, r12, pc}

play_extra_image:
    adr.w   r2, active_snapshot_state
    ldrb    r2, [r2, #1]
    cbz     r2, play_extra_done
    adr.w   r2, play_snapshot_originals
    movs    r3, #0
play_extra_search:
    ldrh.w  r12, [r2, r3, lsl #1]
    cmp     r1, r12
    beq     play_extra_match
    adds    r3, #1
    cmp     r3, #12
    bne     play_extra_search
play_extra_done:
    bx      lr
play_extra_match:
    addw    r1, r3, #XL_EXTRA_PLAY_FIRST
    bx      lr
    .ltorg
.balign 4
play_snapshot_originals:
    .hword 0x13d, 0x165, 0x05, 0x139, 0x31, 0x41, 0xb1, 0x1cc, 0x1a0, 0x71, 0x156, 0x105


.balign 4
usb_snapshot_records:
    .space 2 * RECORD_BYTES
