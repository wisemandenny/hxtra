@ more_snapshots.s - snapshots 4 to 6: a second bank on the snapshot footswitches. Bank A (snapshots 1-3) and bank B (4-6) share
@ the snapshot manager's three 0x260-byte records; the other bank waits in snaps_shadow, and a cross swaps the two and recalls the
@ footswitch's snapshot through the stock select. Snapshot BankSel picks how the footswitches cross: Hold (the default) holds back
@ their presses and selects on the click, in the bank a 1 s hold of FS1 (A) or FS2 (B) points them at, which only a hold, their own
@ select and a preset load change; Tap flips on the lit one pressed again. tools/features/more_snapshots.py places the hooks.
@ A cross, and the reads that decide one, run under the DSP model's lock D, which stock select and HX Edit's Get edit buffer take
@ (the serializer in between), and so do every serializer here and key 0x64's writer: none interleaves with a cross, whichever task
@ runs it. A select under that D holds back its posts to the editor (snaps_quiet), so none waits for a free event block there.
.syntax unified
.thumb
.include "hxtra.inc"
.equ SELECT, 0x28de2f91             @ (manager, index): recalls a snapshot; its hook (snaps_selecting) runs first
.equ RESELECT, 103                  @ Reselect Snapshot: 0 the lit one recalls itself, else it goes back to PREV
.equ RECORD_INIT, 0x28de14b5        @ (manager, record, name): a record's defaults; takes the manager's lock itself
.equ LOCK, 0x28e24c01
.equ UNLOCK, 0x28e24bb1
.equ MEMCPY, 0x28e24c79
.equ MEMSET, 0x28e24b79
.equ REC, 0x260                     @ a snapshot record
.equ RECS, 0xc                      @ record 0, in the manager
.equ COLOUR, 0x254                  @ in a record: its colour, 0 the default
.equ NAME, 0x255                    @ its name
.equ RENAMED, 0x24c                 @ set once it has a name of its own: the label shows the name, not a camera
.equ CUR, 0x743                     @ the current snapshot
.equ PREV, 0x744                    @ the one before it
.equ BUSY, 0x9a9                    @ set while select must not run; select returns 0 then
.equ MANAGER, 0x2812c630
.equ CUR_GET, 0x28de3751            @ (manager) -> the current snapshot: the stock reads the layout hooks stand in for
.equ COLOUR_GET, 0x28de2f81         @ (manager, k) -> record k's colour
.equ NAME_GET, 0x28de3865           @ (manager, k) -> record k's name
.equ RENAMED_GET, 0x28de3875        @ (manager, k) -> 1 when record k is renamed
.equ ICON, 0x2812ade8               @ the top view's snapshot icon (image widget): a camera, its number in a circle
.equ LABELS, 0x2812a4bc             @ the Home view's footswitch labels in Snapshot mode: the same cameras, 0x24 bytes apart
.equ FS_FUNCTIONS, 0x28128a74       @ each footswitch's function, two bytes apart
.equ FN_SNAPSHOT, 14                @ snapshot k for footswitch k: Snapshot mode; other modes keep stale cameras in LABELS
.equ WIDGET_LOCK, 0x28e24971
.equ WIDGET_UNLOCK, 0x28e24ae9
.equ REDRAW, 0x28db8509             @ (full, partial): the UI repaints; the layout code ends with (0, 1)
.equ FILL, 0x100017e9               @ (fb, x, y, w, h, colour, anchor)
.equ TEXT, 0x28db7aa5               @ (fb, text, length, x, y, font, colour, anchor, mode): mode 1 draws only the glyphs' pixels
.equ CONTROLLERS, 0x741             @ snapshot controllers: 7-byte entries at a record's +0x28, keyed by their first byte
.equ SWITCHES, 0x742                @ footswitch entries: 9 bytes at +0x1e8, keyed by their first byte
.equ FILE_KEY, 0x64                 @ bank B's key in the preset file (src/m4/preset_keys.s); stock uses 0..12
.equ FILE_LEN, 8 + 3 * REC          @ its bin16: "HX6B", version, 3 spare, the three records
.equ DARK, 0x101010                 @ the digit on a lit camera's white circle; black would be the renderer's transparent
.equ SAVING, 2                      @ in snaps_data: a serializer has bank A in the manager while bank B is the one heard
.equ VIEW, 4                       @ in snaps_data: the bank the snapshot footswitches select in on Hold, 0 A or 1 B
.equ WRAP, 5                        @ in snaps_data: the select on its way is a next or previous past the bank's end
.equ VALUE, 2                       @ in WRAP instead: the select on its way is CC 69's value, 0..5
.equ STEP, 3                        @ in WRAP instead: a footswitch next or previous within the bank
.equ RELAYOUT, 7                    @ in snaps_data: the Home view's labels are to be laid out again; only ever stored whole
.equ PREV6, 8                       @ in snaps_data: the snapshot before the current one, bank * 3 + index, across the banks
.equ NONE, 0xff                     @ in PREV6: none since the preset loaded; from the layout's current snapshot reads: none lit
.equ SELECTED_BLOCK, 0x28df0281     @ the stock call the event hook stands in for: (out) -> the selected block
.equ PRESS, 1                       @ a key event's types
.equ CLICK, 3                       @ a release before a hold, posted after the release
.equ HOLD, 5                        @ after 1 s
.equ FS1_CODE, 12                   @ codes 12..14 are footswitches 1..3 (9..11 touches on their caps)
.equ PENDING, 0x4f                  @ the handler's object: a press waits for its 30-tick timer
.equ PENDING_FS, 0x50               @ the footswitch it is (a word)
.equ IMMEDIATE, 0x6d                @ set while MIDI CC 49..53 press a footswitch: the press dispatches at once
.equ PRESSED, 0x78                  @ footswitch k pressed at +0x78 + k
.equ LISTS_GET, 0x28d96085          @ () -> the footswitch lists
.equ FS_LEARNING, 0x28dd87a1        @ (lists) -> set while Bypass Assign's learn waits for a footswitch
.equ CONTROLLERS_GET, 0x28d9608d    @ () -> the controllers
.equ CC_LEARNING, 0x28dde9ed        @ (controllers) -> set while Bypass Assign's or Controller Assign's learn waits
.equ FS_MODE, 0x15                  @ setting 21, Footswitch Mode
.equ SNAPSHOT_MODE, 3
.equ HOLD_SEL, 0                    @ Snapshot BankSel's Hold; 1 is Tap
.equ VIEW_IS, 0x28d96135            @ (view) -> 1 when it is the current view
.equ HOME_VIEW, 0
.equ TUNER_VIEW, 5
.equ HOME_GET, 0x28d960f5           @ () -> the Home view
.equ LAYOUT, 0x28dc87cd             @ (Home, 0): its labels for the Footswitch Mode, as the stomp toggle lays them out from the key task
.equ ENGINE_GET, 0x28d92a99         @ () -> the DSP index D's calls take (0 on the unit), as select (0x28de2fc6) and Get edit buffer pass it
.equ DSP_LOCK, 0x28e07845           @ (engine): D, the recursive ROM mutex at [DSP_MODEL] + 8 (0x28e1c56a in Get edit buffer)
.equ DSP_UNLOCK, 0x28e0785d         @ (engine): D let go once (0x28e1c5be)
.equ DSP_MODEL, 0x28449e78          @ the DSP model, 0 until the boot makes it: D's lock would write at address 8 then
.equ DSP_HELD, 9                    @ in snaps_data: 1 while snaps_saving holds D for its serializer, for snaps_saved to let it go
.equ HELD, 10                       @ in snaps_data: how many times the module holds D; only the task holding D writes it
.equ REPOST, 11                     @ in snaps_data: a select under the module's D had its post of 0x2102 held back
.equ LEDS, 12                       @ in snaps_data: the footswitch rings are to be refreshed (snaps_tick); only ever stored whole
.equ QUIET, 0x28d99729              @ (1 or 0): one more or one less (not below 0) on stock's count 0x281caa8c, which while above 0
                                    @ drops the editor's event posts 0x28d99820 and 0x28d99888, the ones that wait for a free block
.equ SELECTED, 0x28d99889           @ (): the editor's event 0x2102, which select posts last, after it lets D go (0x28de32d8)
.equ LED_REFRESH, 0x28dd0b3d        @ (the handler's object, 0): the footswitch rings, as the handler's events call it (0x28dd26cc)

snaps_select:                       @ the footswitch functions' call of select (manager, index): snapshot k, next and previous
    adr.w r2, snaps_data
    ldrb r3, [r2, #WRAP]
    cmp r3, #STEP
    beq snaps_step
    cmp r3, #0
    bne snaps_wrap
    cmp r1, #2
    bhi snaps_stock
    push {r0, r1, r2, lr}
    bl snaps_hold_sel
    mov r3, r0
    pop {r0, r1, r2, lr}
    cbnz r3, snaps_held
    adr.w r12, snaps_tap            @ Tap: decided under D
    b snaps_locked
snaps_stock:
    ldr r12, =SELECT
    bx r12
snaps_held:                         @ Hold: snapshot k's press selects nothing; its click does (snaps_click)
    movs r0, #0
    bx lr

snaps_tap:                          @ (manager, index) on Tap, under D: the lit one flips the bank, another is stock select
    adr.w r2, snaps_data
    ldrb r3, [r2]                   @ the footswitches on the live bank, where a switch to Hold then finds them
    strb r3, [r2, #VIEW]
    ldrb.w r2, [r0, #CUR]
    cmp r2, r1
    bne snaps_quiet
    ldrb.w r2, [r0, #BUSY]
    cmp r2, #0
    beq snaps_flip
    b snaps_quiet

snaps_locked:                       @ (manager, index; r12 a routine of them ending in select or snaps_cross) -> its result: the
    push {r0, r1, r4, lr}           @ routine under D, so what it reads (bytes 0 and 1, CUR, BUSY) is no serializer's flip to
    bl snaps_dsp_lock               @ bank A, and what it decides runs before the next serializer
    mov r4, r0
    ldm sp, {r0, r1}
    orr r12, r12, #1
    blx r12
    str r0, [sp]
    mov r0, r4
    bl snaps_dsp_unlock_post
    pop {r0, r1, r4, pc}

snaps_dsp_lock:                     @ () -> r0 1 with D taken, 0 before the boot makes the DSP model (no lock); keeps r1-r3 and r12
    push {r1, r2, r3, r4, r12, lr}
    ldr r0, =DSP_MODEL
    ldr r0, [r0]
    cbz r0, snaps_dsp_lock_done
    ldr r3, =ENGINE_GET
    blx r3
    ldr r3, =DSP_LOCK
    blx r3
    adr.w r1, snaps_data
    ldrb r0, [r1, #HELD]
    adds r0, #1
    strb r0, [r1, #HELD]
    movs r0, #1
snaps_dsp_lock_done:
    pop {r1, r2, r3, r4, r12, pc}

snaps_dsp_unlock:                   @ (r0 what snaps_dsp_lock returned): D let go if it was taken; keeps r1-r3 and r12
    cbz r0, snaps_dsp_unlock_none
    push {r1, r2, r3, r4, r12, lr}
    adr.w r1, snaps_data
    ldrb r0, [r1, #HELD]
    subs r0, #1
    strb r0, [r1, #HELD]
    ldr r3, =ENGINE_GET
    blx r3
    ldr r3, =DSP_UNLOCK
    blx r3
    pop {r1, r2, r3, r4, r12, pc}
snaps_dsp_unlock_none:
    bx lr

snaps_dsp_unlock_post:              @ (r0 what snaps_dsp_lock returned): D let go, then the post of 0x2102 a select under it held
    push {r4, lr}                   @ back, so the editor hears of the select once, from outside D, as select itself posts it
    adr.w r3, snaps_data
    ldrb r4, [r3, #REPOST]
    movs r2, #0
    strb r2, [r3, #REPOST]
    bl snaps_dsp_unlock
    cbz r4, snaps_dsp_unlock_post_done
    ldr r3, =SELECTED
    blx r3
snaps_dsp_unlock_post_done:
    pop {r4, pc}

snaps_quiet:                        @ (manager, index) -> select's result: every select under the module's D, with stock's count
    adr.w r2, snaps_data            @ up around it (QUIET), as select puts it up around its own copy of an unused record
    ldrb r3, [r2, #HELD]            @ (0x28de3296..0x28de32c4): no post of select's waits for a free event block while the module
    cmp r3, #0                      @ holds D. Before the boot makes the DSP model the module holds none: stock select as is
    beq snaps_stock
    push {r4, r5, r6, lr}
    mov r4, r0
    mov r5, r1
    movs r0, #1
    ldr r3, =QUIET
    blx r3
    mov r0, r4
    mov r1, r5
    ldr r3, =SELECT
    blx r3
    mov r6, r0
    movs r0, #0
    ldr r3, =QUIET
    blx r3
    adr.w r2, snaps_data
    ldrb r3, [r2, #SAVING]
    cbnz r3, snaps_quiet_done       @ a serializer's flip, which the editor is not told of
    ldrb.w r3, [r4, #BUSY]
    cbnz r3, snaps_quiet_done       @ refused: only a load sets BUSY, under D, so select found it set
    cmp r6, #0
    blt snaps_quiet_done            @ failed before its post (0x28de3272, 0x28de36d0, 0x28de371a)
    movs r3, #1
    strb r3, [r2, #REPOST]
snaps_quiet_done:
    mov r0, r6
    pop {r4, r5, r6, pc}

snaps_step:                         @ (manager, index, snaps_data) a next or previous within the bank: stock
    movs r3, #0
    strb r3, [r2, #WRAP]
    b snaps_stock

snaps_action_select:                @ the snapshot action's call of select (manager, index): Hold, stock (the lit one does what
    push {r0, r1, r2, lr}           @ Reselect Snapshot says, within the bank); Tap, as a press
    bl snaps_hold_sel
    mov r3, r0
    pop {r0, r1, r2, lr}
    cmp r3, #0
    bne snaps_stock
    b snaps_select

snaps_cc_select:                    @ MIDI CC 69's call of select (manager, index): stock, bar a value 0..5 or a next or previous past the bank's end
    adr.w r2, snaps_data
    ldrb r3, [r2, #WRAP]
    cmp r3, #VALUE
    beq snaps_value
    cmp r3, #STEP
    beq snaps_step
    cmp r3, #0
    beq snaps_stock

snaps_wrap:                        @ (manager, index, snaps_data): the other bank's first or last, if this preset has a bank B
    movs r3, #0
    strb r3, [r2, #WRAP]
    adr.w r12, snaps_wrap_locked
    b snaps_locked
snaps_wrap_locked:                  @ (manager, index), under D
    adr.w r2, snaps_data
    ldrb r3, [r2, #1]
    cmp r3, #0
    beq snaps_quiet
    cmp r1, #2
    bhi snaps_quiet
snaps_cc_cross:
    ldrb.w r3, [r0, #BUSY]
    cmp r3, #0
    bne snaps_quiet
    ldrb.w r2, [r0, #CUR]
    b snaps_cross

snaps_value:                        @ (manager, value, snaps_data): 0..2 snapshots 1..3 and 3..5 snapshots 4..6, from either bank
    movs r3, #0
    strb r3, [r2, #WRAP]
    adr.w r12, snaps_value_locked
    b snaps_locked
snaps_value_locked:                 @ (manager, value), under D
    adr.w r2, snaps_data
    ldrb r3, [r2]
    cmp r1, #3
    itt hs
    subhs r1, #3
    eorhs r3, r3, #1                @ r3 set: the value's bank is not the live one
    cmp r3, #0
    beq snaps_quiet
    b snaps_cc_cross

snaps_next_cur:                    @ in place of footswitch next's read of the current snapshot (manager): marks a wrap past 3 or 6,
    ldrb.w r0, [r0, #CUR]           @ else a step, so snaps_select tells it from a press of snapshot k
    cmp r0, #2
    beq snaps_mark
    b snaps_mark_step

snaps_prev_cur:                     @ in place of footswitch previous's read: marks a wrap past 1 or 4, else a step
    ldrb.w r0, [r0, #CUR]
    cmp r0, #0
    beq snaps_mark
snaps_mark_step:
    movs r2, #STEP
    b snaps_mark_as

snaps_cc_value:                     @ in place of CC 69's manager getter before its select of the value: marks it
    ldr r0, =MANAGER
    movs r2, #VALUE
    b snaps_mark_as

snaps_cc_wrap:                      @ in place of CC 69's manager getter where next leaves 3 or previous leaves 1: marks the wrap
    ldr r0, =MANAGER
snaps_mark:
    movs r2, #1
snaps_mark_as:
    adr.w r1, snaps_data
    strb r2, [r1, #WRAP]
    bx lr

snaps_flip:                         @ the lit one again: the other bank, then select(index) from the record the sound came from
    mov r2, r1
snaps_cross:                        @ (manager, index, the index being left): under D from bank B's making to byte 0's flip, then
    push {r3-r11, lr}               @ the manager lock around the swaps, so D before it, as select takes them
    mov r4, r0
    mov r5, r1
    mov r11, r2
    bl snaps_dsp_lock
    mov r8, r0
    adr.w r6, snaps_data
    ldrb r0, [r6, #1]
    cbnz r0, snaps_ready
    adr.w r0, snaps_shadow          @ bank B since the preset loaded: three default records, which select fills from the sound
    movs r1, #0
    movw r2, #3 * REC
    ldr r3, =MEMSET
    blx r3
    movs r7, #0
snaps_init:
    adr.w r1, snaps_shadow
    mov.w r2, #REC
    mla r1, r2, r7, r1
    adr.w r2, snaps_names
    add.w r2, r2, r7, lsl #4
    mov r0, r4
    ldr r3, =RECORD_INIT
    blx r3
    adds r7, #1
    cmp r7, #3
    bne snaps_init
    movs r0, #1
    strb r0, [r6, #1]
snaps_ready:
    add.w r0, r4, #4
    ldr r3, =LOCK
    blx r3
    bl snaps_swap
    bl snaps_match
    cmp r5, #0                      @ j, another index: its record stands in for the old one while select runs
    ite eq
    moveq r7, #1
    movne r7, #0
    mov r0, r7
    bl snaps_record
    mov r9, r0
    adr.w r0, snaps_temp
    mov r1, r9
    bl snaps_copy
    adr.w r1, snaps_shadow          @ the record just swapped out holds the sound being left, with its edits
    mov.w r2, #REC
    mla r1, r2, r11, r1
    mov r0, r9
    bl snaps_copy
    strb.w r7, [r4, #CUR]           @ so select sees a change from j: it diffs, or copies into an unused record, from there
    add.w r0, r4, #4
    ldr r3, =UNLOCK
    blx r3
    mov r0, r4
    mov r1, r5
    bl snaps_quiet
    mov r10, r0
    add.w r0, r4, #4
    ldr r3, =LOCK
    blx r3
    mov r0, r9
    adr.w r1, snaps_temp
    bl snaps_copy
    strb.w r5, [r4, #PREV]          @ the previous snapshot is the new one: the one before it is in the other bank
    ldrb r0, [r6]
    add.w r1, r0, r0, lsl #1
    add r1, r11
    strb r1, [r6, #PREV6]           @ and PREV6 the snapshot left, where select's hook stored j
    eor r0, r0, #1
    strb r0, [r6]
    cbnz r0, snaps_flipped
    movs r1, #3
    strb r1, [r6, #3]               @ back in bank A: the top icon (bit 0) and the labels (bit 1) drawn again over bank B's numbers
snaps_flipped:
    add.w r0, r4, #4
    ldr r3, =UNLOCK
    blx r3
    mov r0, r8
    bl snaps_dsp_unlock
    bl snaps_hold_sel
    cbnz r0, snaps_crossed
    ldrb r0, [r6]                   @ Tap: the footswitches follow the live bank, where a switch to Hold then finds them
    strb r0, [r6, #VIEW]
snaps_crossed:
    movs r0, #1                     @ the rings and the labels again once the cross is whole (snaps_tick): select's own, from
    strb r0, [r6, #LEDS]            @ another task, may have read the records and banks halfway
    strb r0, [r6, #RELAYOUT]
    movs r0, #0
    movs r1, #1
    ldr r3, =REDRAW
    blx r3
    mov r0, r10
    pop {r3-r11, pc}

snaps_loaded:                       @ before the preset parser fills the records: bank A, and bank B from the file or anew; the
    push {r4, lr}                   @ footswitches on bank A, no previous snapshot
    adr.w r0, snaps_armed           @ a press made before the load selects nothing in it
    movs r1, #0
    str r1, [r0]
    adr.w r0, snaps_data
    ldrb r4, [r0, #VIEW]
    strb r1, [r0, #VIEW]
    movs r1, #NONE
    strb r1, [r0, #PREV6]
    ldrb r1, [r0]
    add.w r1, r1, r1, lsl #1
    lsls r1, r1, #24                @ bank B was live: the cameras must be drawn again (byte 3)
    str r1, [r0]
    ldrb r1, [r0, #6]
    cbz r1, snaps_loaded_done
    movs r2, #0                     @ the file's bank B, read with its section 10
    strb r2, [r0, #6]
    movs r2, #1
    strb r2, [r0, #1]
    adr.w r0, snaps_shadow
    add.w r1, r0, #3 * REC
    movw r2, #3 * REC
    ldr r3, =MEMCPY
    blx r3
snaps_loaded_done:                  @ stock lays the labels out after the load; the tick does too if Hold had them on bank B
    cbz r4, snaps_loaded_out
    bl snaps_hold_sel
    cbz r0, snaps_loaded_out
    adr.w r0, snaps_data
    movs r1, #1
    strb r1, [r0, #LEDS]
    strb r1, [r0, #RELAYOUT]
snaps_loaded_out:
    pop {r4, pc}

snaps_match:                        @ (r4 the manager) after a swap: the incoming bank's controller and footswitch entries as the
    push {r4-r8, lr}                @ outgoing bank's, which were live, wherever their keys differ (an assignment made meanwhile)
    add.w r4, r4, #RECS
    ldrb.w r7, [r4, #CONTROLLERS - RECS]
    cmp r7, #64
    it hi
    movhi r7, #64
    ldrb.w r8, [r4, #SWITCHES - RECS]
    cmp.w r8, #11
    it hi
    movhi.w r8, #11
    adr.w r5, snaps_shadow
    movs r6, #3
snaps_match_record:
    add.w r0, r4, #0x28
    add.w r1, r5, #0x28
    mov r2, r7
    movs r3, #7
    bl snaps_match_entries
    add.w r0, r4, #0x1e8
    add.w r1, r5, #0x1e8
    mov r2, r8
    movs r3, #9
    bl snaps_match_entries
    add.w r4, r4, #REC
    add.w r5, r5, #REC
    subs r6, #1
    bne snaps_match_record
    pop {r4-r8, pc}

snaps_match_entries:                @ (to, from, count, size): entry i from from where its first byte differs
    cbz r2, snaps_matched
    push {r4, r5}
snaps_match_entry:
    ldrb r4, [r0]
    ldrb r5, [r1]
    cmp r4, r5
    beq snaps_match_next
    movs r4, #0
snaps_match_byte:
    ldrb r5, [r1, r4]
    strb r5, [r0, r4]
    adds r4, #1
    cmp r4, r3
    bne snaps_match_byte
snaps_match_next:
    add r0, r3
    add r1, r3
    subs r2, #1
    bne snaps_match_entry
    pop {r4, r5}
snaps_matched:
    bx lr

.thumb_func
.global snaps_key_write
snaps_key_write:                    @ preset_keys.s's writer (stream): bank B after the map, as key 0x64; -> the keys written. Under
    push {r4, r5, r6, r7, r8, lr}   @ D from its read of byte 0 to its last write: the serializer before it has let D go, and a
    mov r4, r0                      @ cross must not swap the records it copies
    bl snaps_dsp_lock
    mov r8, r0
    movs r7, #0
    ldr r5, =MANAGER + RECS         @ bank B live: the manager's records
    adr.w r6, snaps_data
    ldrb r0, [r6]
    cbnz r0, snaps_key_put
    ldrb r0, [r6, #1]
    cbz r0, snaps_key_written       @ no bank B for this preset: a stock file
    adr.w r5, snaps_shadow
snaps_key_put:
    adr.w r1, snaps_file_head
    movs r2, #12
    bl snaps_file_put
    mov r1, r5
    movw r2, #3 * REC
    bl snaps_file_put
    movs r7, #1
snaps_key_written:
    mov r0, r8
    bl snaps_dsp_unlock
    mov r0, r7
    pop {r4, r5, r6, r7, r8, pc}

snaps_file_put:                     @ (r4 the stream, r1 bytes, r2 length): the stream's write(context, bytes, length)
    ldr r0, [r4]
    ldr r3, [r4, #4]
    bx r3

.thumb_func
.global snaps_key_found
snaps_key_found:                    @ preset_keys.s's finder (key, data, length): key 0x64, "HX6B", version 1, into snaps_staged
    adr.w r3, snaps_data
    cmp r0, #FILE_KEY
    beq snaps_key_ours
    cmn r0, #1                      @ START: a file is being read
    itt eq
    moveq r0, #0
    strbeq r0, [r3, #6]
    bx lr
snaps_key_ours:
    movw r0, #FILE_LEN
    cmp r2, r0
    it ne
    bxne lr
    push {r4, r5, r6, lr}
    mov r6, r3
    adr.w r4, snaps_file_head + 4
    movs r3, #0
snaps_key_head_byte:
    ldrb r2, [r1, r3]
    ldrb r5, [r4, r3]
    cmp r2, r5
    bne snaps_key_none
    adds r3, #1
    cmp r3, #5
    bne snaps_key_head_byte
    adds r1, #8
    adr.w r0, snaps_shadow
    add.w r0, r0, #3 * REC
    movw r2, #3 * REC
    ldr r3, =MEMCPY
    blx r3
    movs r1, #1
    strb r1, [r6, #6]
snaps_key_none:
    pop {r4, r5, r6, pc}

snaps_paint:                        @ after the top view's paint (framebuffer, view): the live bank B's number over its snapshot icon's
    movs r1, #1
    adr.w r2, snaps_top
    adr.w r3, snaps_data
    ldrb r3, [r3]
    b snaps_cameras_paint

snaps_home_paint:                   @ after the Home view's paint (framebuffer, view): over its footswitch labels', for the bank shown
    ldr r3, =FS_FUNCTIONS
    ldrb r3, [r3]
    cmp r3, #FN_SNAPSHOT
    it ne
    bxne lr
    mov r12, lr
    bl snaps_viewed
    mov lr, r12
    adr.w r2, snaps_data
    ldrb r2, [r2]
    cmp r3, #0
    it ne
    eorne r2, r2, #1                @ the other bank
    mov r3, r2
    movs r1, #2
    adr.w r2, snaps_labels

snaps_cameras_paint:                @ r0 the framebuffer, r1 this paint's bit in byte 3, r2 its cameras, ending in 0, r3 1 for bank B
    push {r3-r9, lr}
    mov r4, r0
    mov r5, r1
    mov r6, r2
    mov r9, r3
    adr.w r7, snaps_data
    ldrb r1, [r7, #3]
    tst r1, r5
    it eq
    cmpeq r9, #0
    beq snaps_cameras_done
    ldr r3, =WIDGET_LOCK
    blx r3
    movs r8, #0
    ldrb r0, [r7, #3]
    tst r0, r5
    beq snaps_cameras_draw
    bic r0, r0, r5
    strb r0, [r7, #3]
    movs r8, #1
    mov r0, r6
snaps_cameras_dirty:
    ldr r1, [r0], #4
    cbz r1, snaps_cameras_draw
    ldrb r2, [r1, #0x1d]            @ a hidden one is a renamed snapshot's: its erase would black out the name over it
    cmp r2, #0
    beq snaps_cameras_dirty
    ldr r1, [r1, #0x20]             @ its node: the paint draws it only while the node's byte 0x24 is set
    movs r2, #1
    strb.w r2, [r1, #0x24]
    b snaps_cameras_dirty
snaps_cameras_draw:
    cmp.w r9, #0
    beq snaps_cameras_unlock
snaps_cameras_each:
    ldr r0, [r6], #4
    cbz r0, snaps_cameras_unlock
    bl snaps_camera
    b snaps_cameras_each
snaps_cameras_unlock:
    ldr r3, =WIDGET_UNLOCK
    blx r3
    cmp.w r8, #0
    beq snaps_cameras_done
    movs r0, #0                     @ the stock cameras are drawn on the next paint
    movs r1, #1
    ldr r3, =REDRAW
    blx r3
snaps_cameras_done:
    pop {r3-r9, pc}

snaps_camera:                       @ (camera, r4 the framebuffer): 4..6 over a visible stock camera's 1..3, where its image puts it
    push {r4-r7, lr}
    sub sp, #28                     @ 0..16 the stack arguments, 20 the digit
    mov r5, r0
    ldrb r0, [r5, #0x1d]            @ visible
    cmp r0, #0
    beq snaps_camera_done
    ldr r0, [r5]                    @ its image
    adr.w r1, snaps_images
    movs r6, #0
snaps_camera_find:
    ldrh.w r2, [r1, r6, lsl #1]
    cmp r2, r0
    beq snaps_camera_found
    adds r6, #1
    cmp r6, #9
    bne snaps_camera_find
    b snaps_camera_done
snaps_camera_found:
    movs r1, #3
    udiv r7, r6, r1                 @ its style: 0 white, 1 red, 2 lit
    mls r6, r7, r1, r6
    adds r6, #'4'
    strh r6, [sp, #20]              @ with its NUL: the renderer draws to the NUL, using the length only to spot 0 or 1
    ldrb r0, [r5, #0x1c]            @ the anchor: column (x at the left, centre, right) and row (y at the bottom, middle, top)
    udiv r2, r0, r1
    mls r1, r2, r1, r0
    ldr r3, [r5, #0x14]
    mul r1, r1, r3
    ldr r0, [r5, #0xc]
    sub.w r6, r0, r1, lsr #1        @ the camera's left
    ldr r3, [r5, #0x18]
    mul r2, r2, r3
    ldr r0, [r5, #0x10]
    sub.w r5, r0, r2, lsr #1        @ and bottom; its digit's rows are 6..26, inside the circle at 16..42 across [verified offline]
    movs r0, #22
    str r0, [sp]
    movs r0, #0
    cmp r7, #2
    it eq
    mvneq r0, #0xff000000           @ a lit camera's circle is white
    str r0, [sp, #4]
    movs r0, #0
    str r0, [sp, #8]                @ anchor 0: x, y the bottom left corner
    mov r0, r4
    add.w r1, r6, #22
    add.w r2, r5, #6
    movs r3, #16
    ldr r12, =FILL
    blx r12
    adds r0, r5, #1                 @ hx28_boldFont's digits ink rows 5..25 of the cell
    str r0, [sp]
    movs r0, #2
    str r0, [sp, #4]
    ldr r0, =DARK
    cmp r7, #2
    it ne
    mvnne r0, #0xff000000
    str r0, [sp, #8]
    movs r0, #1                     @ anchor 1: x the centre, y the bottom; mode 1: the glyphs' pixels only
    str r0, [sp, #12]
    str r0, [sp, #16]
    mov r0, r4
    add r1, sp, #20
    movs r2, #1
    add.w r3, r6, #29
    ldr r12, =TEXT
    blx r12
snaps_camera_done:
    add sp, #28
    pop {r4-r7, pc}

snaps_saving:                       @ before a preset serializer: D until snaps_saved, so no cross runs while it reads the records;
    push {r3, lr}                   @ in bank B, bank A live, as a load takes the blocks' live values for its snapshot, and SAVING
    bl snaps_dsp_lock               @ from before this flip until after the flip back
    adr.w r1, snaps_data
    strb r0, [r1, #DSP_HELD]
    ldrb r2, [r1]
    cbz r2, snaps_saving_done
    movs r2, #1
    strb r2, [r1, #SAVING]
    ldr r0, =MANAGER
    bl snaps_flip_now
snaps_saving_done:
    pop {r3, pc}

snaps_saved:                        @ after it: bank B again, then D let go; keeps r4 and r5, the serializer's result in its chain
    push {r3, lr}
    adr.w r1, snaps_data
    ldrb r2, [r1, #SAVING]
    cbz r2, snaps_saved_done
    ldr r0, =MANAGER
    bl snaps_flip_now
    adr.w r1, snaps_data
    movs r2, #0
    strb r2, [r1, #SAVING]
snaps_saved_done:
    ldrb r0, [r1, #DSP_HELD]
    movs r2, #0
    strb r2, [r1, #DSP_HELD]
    bl snaps_dsp_unlock
    pop {r3, pc}

snaps_flip_now:                    @ (manager): a flip on the current snapshot; select allowed for it, as the load path allows its own
    push {r3-r7, lr}
    mov r4, r0
    ldrb.w r6, [r4, #BUSY]
    ldrb.w r5, [r4, #PREV]
    adr.w r7, snaps_data
    ldrb r7, [r7, #PREV6]
    movs r1, #0
    strb.w r1, [r4, #BUSY]
    ldrb.w r1, [r4, #CUR]
    bl snaps_flip
    strb.w r5, [r4, #PREV]          @ the save's two flips leave the previous snapshot as it was, in both forms
    adr.w r0, snaps_data
    strb r7, [r0, #PREV6]
    strb.w r6, [r4, #BUSY]
    pop {r3-r7, pc}

snaps_swap:                         @ the manager's three records and snaps_shadow trade places (r4 the manager)
    push {r4-r6, lr}
    add.w r4, r4, #RECS
    adr.w r5, snaps_shadow
    movs r6, #3
snaps_swap1:
    adr.w r0, snaps_temp
    mov r1, r4
    bl snaps_copy
    mov r0, r4
    mov r1, r5
    bl snaps_copy
    mov r0, r5
    adr.w r1, snaps_temp
    bl snaps_copy
    add.w r4, r4, #REC
    add.w r5, r5, #REC
    subs r6, #1
    bne snaps_swap1
    pop {r4-r6, pc}

snaps_record:                       @ (index) -> its record in the manager (r4)
    mov.w r1, #REC
    mla r0, r0, r1, r4
    adds r0, #RECS
    bx lr

snaps_copy:                         @ (to, from): a record
    mov.w r2, #REC
    ldr r3, =MEMCPY
    bx r3

snaps_event:                        @ in place of the footswitch event handler's call of the selected block's getter (out), which every
    push {r3-r7, lr}                @ event reaches, r4 the event {1 key, code, -, -, type} and r5 the handler's object: the getter's
    ldr r3, =SELECTED_BLOCK         @ result, after FS1..3's presses, clicks and holds
    blx r3
    mov r6, r0
    ldrb r0, [r4]
    cmp r0, #1
    bne snaps_event_done
    ldrb r7, [r4, #1]
    subs r7, #FS1_CODE
    cmp r7, #3
    bhs snaps_event_done            @ footswitch k (r7)
    ldr r0, [r4, #4]
    cmp r0, #PRESS
    beq snaps_press
    cmp r0, #CLICK
    it ne
    cmpne r0, #HOLD
    bne snaps_event_done
    adr.w r1, snaps_armed
    ldrb r0, [r1, r7]
    cmp r0, #0
    beq snaps_event_done
    movs r0, #0
    strb r0, [r1, r7]
    mov r0, r7
    bl snaps_gate
    cmp r0, #0
    beq snaps_event_done
    ldr r1, [r4, #4]
    mov r0, r7
    cmp r1, #HOLD
    beq snaps_key_hold
    bl snaps_click
    b snaps_event_done
snaps_key_hold:
    bl snaps_hold
    b snaps_event_done
snaps_press:                        @ armed while it is a lone press, as stock reads the same state next (0x28dd1a24..0x28dd1a5a)
    adr.w r1, snaps_armed
    movs r0, #0
    strb r0, [r1, r7]
    mov r0, r7
    bl snaps_gate
    cmp r0, #0
    beq snaps_event_done
    bl snaps_learning
    cmp r0, #0
    bne snaps_event_done
    ldrb r0, [r5, #IMMEDIATE]
    cbnz r0, snaps_press_now
    ldrb r0, [r5, #PENDING]
    cbz r0, snaps_arm
    ldr r0, [r5, #PENDING_FS]
    cmp r0, r7
    beq snaps_arm                   @ the same switch again inside its window: stock dispatches it once, while held
    cmp r0, #3
    bhs snaps_arm
    adds r1, r5, r0
    ldrb r1, [r1, #PRESSED]
    cbz r1, snaps_arm               @ the other was let go inside its window and selected on its click: this is no combo
    adr.w r1, snaps_armed           @ another switch held inside its window: stock switches to Preset mode (FS1+FS2, FS2+FS3)
    movs r2, #0                     @ or drops both (FS1+FS3), so neither selects
    strb r2, [r1, r0]
    b snaps_event_done
snaps_arm:
    adr.w r1, snaps_armed
    movs r0, #1
    strb r0, [r1, r7]
    b snaps_event_done
snaps_press_now:                    @ MIDI CC 49..51: a tap on the press, when stock dispatches it, whatever posts its release
    mov r0, r7
    bl snaps_click
snaps_event_done:
    mov r0, r6
    pop {r3-r7, pc}

snaps_learning:                     @ () -> r0 non-zero while a learn waits: the dispatch then gives the press to it and selects
    push {r3, lr}                   @ nothing (0x28dd14a8..0x28dd14be)
    ldr r3, =LISTS_GET
    blx r3
    ldr r3, =FS_LEARNING
    blx r3
    cbnz r0, snaps_learning_done
    ldr r3, =CONTROLLERS_GET
    blx r3
    ldr r3, =CC_LEARNING
    blx r3
snaps_learning_done:
    pop {r3, pc}

snaps_gate:                         @ (k) -> r0 1 when footswitch k selects snapshot k (Snapshot mode), Snapshot BankSel is Hold, and
    push {r4, lr}                   @ the tuner is not open (a press there only leaves it)
    ldr r1, =FS_FUNCTIONS
    ldrb.w r1, [r1, r0, lsl #1]
    cmp r1, #FN_SNAPSHOT
    bne snaps_gate_no
    movs r0, #TUNER_VIEW
    ldr r3, =VIEW_IS
    blx r3
    cmp r0, #0
    bne snaps_gate_no
    movs r0, #FS_MODE
    movs r1, #SNAPSHOT_MODE
    movs r2, #0
    bl hxtra_setting_get
    cmp r0, #SNAPSHOT_MODE
    bne snaps_gate_no
    bl snaps_hold_sel
    pop {r4, pc}
snaps_gate_no:
    movs r0, #0
    pop {r4, pc}

snaps_hold_sel:                     @ () -> r0 1 when Snapshot BankSel is Hold, which a unit that never stored it reads
    push {r3, lr}
    movs r0, #SETTING_MORE_SNAPSHOTS_BANK_SWITCH
    movs r1, #SETTING_MORE_SNAPSHOTS_BANK_SWITCH_MAX
    movs r2, #SETTING_MORE_SNAPSHOTS_BANK_SWITCH_DEFAULT
    bl hxtra_setting_get
    cmp r0, #HOLD_SEL
    ite eq
    moveq r0, #1
    movne r0, #0
    pop {r3, pc}

snaps_click:                        @ (k) a click of footswitch k in Hold mode: snapshot k of the bank the footswitches select in; in
    push {r4, r5, r6, lr}           @ the live bank stock select, bar the lit one going back to the other bank; then the footswitches
    mov r5, r0                      @ select in the bank now live. Under D throughout: a serializer waits for it, and it for one
    bl snaps_dsp_lock
    mov r6, r0
    adr.w r0, snaps_data
    ldrb r0, [r0, #SAVING]
    cmp r0, #0
    bne snaps_click_shown           @ a serializer's flip: byte 0 is not the bank heard, and the records are the ones it reads
    ldr r4, =MANAGER
    ldrb.w r0, [r4, #BUSY]
    cbnz r0, snaps_click_stock      @ select refuses it
    bl snaps_viewed
    mov r1, r5
    cbnz r3, snaps_click_cross
    ldrb.w r0, [r4, #CUR]
    cmp r0, r5
    bne snaps_click_stock
    bl snaps_back
    cbz r0, snaps_click_stock
snaps_click_cross:                  @ r1 the index in the other bank
    mov r0, r4
    ldrb.w r2, [r4, #CUR]
    bl snaps_cross
    b snaps_click_done
snaps_click_stock:
    mov r0, r4
    mov r1, r5
    bl snaps_quiet
snaps_click_done:
    adr.w r0, snaps_data
    ldrb r1, [r0]
    ldrb r2, [r0, #VIEW]
    cmp r1, r2
    beq snaps_click_shown
    strb r1, [r0, #VIEW]
    movs r1, #1                     @ refreshed and laid out by snaps_tick, in the key task: CC 49..51 click from the request task
    strb r1, [r0, #LEDS]
    strb r1, [r0, #RELAYOUT]
snaps_click_shown:
    mov r0, r6
    bl snaps_dsp_unlock_post
    pop {r4, r5, r6, pc}

snaps_back:                         @ -> r0 1 and r1 its index when Reselect Snapshot goes back and the previous snapshot is in the
    push {r3, lr}                   @ other bank, else r0 0 (stock select goes back within the bank, to PREV)
    movs r0, #RESELECT
    mvn r1, #0
    movs r2, #0
    bl hxtra_setting_get
    cbz r0, snaps_back_done
    adr.w r2, snaps_data
    ldrb r1, [r2, #PREV6]
    movs r0, #0
    cmp r1, #5
    bhi snaps_back_done             @ none since the preset loaded
    cmp r1, #3
    itt hs
    subhs r1, #3
    movhs r0, #1                    @ its bank
    ldrb r3, [r2]
    eors r0, r3
snaps_back_done:
    pop {r3, pc}

snaps_hold:                         @ (k) a 1 s hold of footswitch k in Hold mode: FS1 points the footswitches at bank A, FS2 at
    cmp r0, #2                      @ bank B, FS3 at nothing; the labels and the rings (on the next tick) show that bank, none lit
    it hs                           @ unless it is the live one
    bxhs lr
    adr.w r1, snaps_data
    ldrb r2, [r1, #VIEW]
    cmp r0, r2
    it eq
    bxeq lr
    strb r0, [r1, #VIEW]
    movs r2, #1
    strb r2, [r1, #LEDS]
    b snaps_relayout

snaps_viewed:                       @ -> r3 0 while the footswitches select in the live bank (on Tap, which ignores VIEW, or VIEW the
    push {r0, r1, r12, lr}          @ live bank), else 1 with the other bank's records in snaps_shadow, 2 with no bank B yet (its
    bl snaps_hold_sel               @ defaults); keeps r0, r1 and r12
    movs r3, #0
    cbz r0, snaps_viewed_done
    adr.w r2, snaps_data
    ldrb r0, [r2, #VIEW]
    ldrb r1, [r2]
    cmp r0, r1
    beq snaps_viewed_done
    movs r3, #1
    cbnz r1, snaps_viewed_done      @ bank B live: bank A waits in snaps_shadow
    ldrb r1, [r2, #1]
    cbnz r1, snaps_viewed_done
    movs r3, #2
snaps_viewed_done:
    pop {r0, r1, r12, pc}

snaps_tick:                         @ after the footswitch tick (event, the handler's object), in the key task: a refresh of the
    push {r4, lr}                   @ rings and a layout that are due; both wait between a serializer's flips, whose flip back asks
    mov r4, r1                      @ again, and the rings while the tuner is open, as stock's refreshes do (0x28dd26be)
    adr.w r0, snaps_data
    ldrb r1, [r0, #SAVING]
    cbnz r1, snaps_tick_done
    ldrb r0, [r0, #LEDS]
    cbz r0, snaps_tick_labels
    movs r0, #TUNER_VIEW
    ldr r3, =VIEW_IS
    blx r3
    cbnz r0, snaps_tick_labels
    adr.w r1, snaps_data
    strb r0, [r1, #LEDS]            @ cleared before the refresh reads the banks, so a change during it refreshes again
    mov r0, r4
    movs r1, #0
    ldr r3, =LED_REFRESH
    blx r3
snaps_tick_labels:
    adr.w r0, snaps_data
    ldrb r0, [r0, #RELAYOUT]
    cbz r0, snaps_tick_done
    bl snaps_relayout
snaps_tick_done:
    pop {r4, pc}

snaps_relayout:                     @ the Home view's labels laid out again: at once when it is the current view, else by snaps_tick
    push {r4, lr}
    adr.w r4, snaps_data
    movs r0, #HOME_VIEW
    ldr r3, =VIEW_IS
    blx r3
    eor r0, r0, #1
    strb r0, [r4, #RELAYOUT]        @ cleared before the layout reads the banks, so a change during it lays out again
    cbnz r0, snaps_relayout_done
    ldr r3, =HOME_GET
    blx r3
    movs r1, #0
    ldr r3, =LAYOUT
    blx r3
snaps_relayout_done:
    pop {r4, pc}

snaps_selecting:                    @ before every select (manager, index), in any task: the snapshot it leaves, as PREV6, when it
    ldrb.w r2, [r0, #BUSY]          @ leaves one (snaps_cross puts its own after its select)
    cmp r1, #2
    it ls
    cmpls r2, #0
    bne snaps_selecting_done        @ select refuses it, or does nothing for an index above 2
    ldrb.w r2, [r0, #CUR]
    cmp r2, r1
    bne snaps_left
    ldrb.w r3, [r0, #PREV]
    cmp r3, r2
    beq snaps_selecting_done        @ the lit one, with no other to go back to
    push {r2, lr}
    movs r0, #RESELECT
    mvn r1, #0
    movs r2, #0
    bl hxtra_setting_get
    mov r3, r0
    pop {r2, lr}
    cbz r3, snaps_selecting_done    @ Reselect Snapshot: it recalls itself
snaps_left:
    adr.w r0, snaps_data
    ldrb r1, [r0]
    ldrb r3, [r0, #SAVING]
    orrs r1, r3                     @ bank B heard, while a serializer has bank A in the manager
    add.w r1, r1, r1, lsl #1
    add r1, r2
    strb r1, [r0, #PREV6]
snaps_selecting_done:
    bx lr

snaps_layout_cur:                   @ in place of the Snapshot-mode label layout's and ring refresh's reads of the current snapshot
    mov r12, lr                     @ (manager): none lit while the footswitches select in the other bank
    bl snaps_viewed
    mov lr, r12
    cbnz r3, snaps_layout_none
    ldr r3, =CUR_GET
    bx r3
snaps_layout_none:
    movs r0, #NONE
    bx lr

snaps_layout_colour:                @ in place of their reads of snapshot k's colour (manager, k): the other bank's, if the
    mov r12, lr                     @ footswitches select in it; the default for a bank B not made yet
    bl snaps_viewed
    mov lr, r12
    cbnz r3, snaps_layout_colour_other
    ldr r3, =COLOUR_GET
    bx r3
snaps_layout_colour_other:
    movs r0, #0
    cmp r3, #1
    it ne
    bxne lr
    bl snaps_shadow_record
    mov lr, r12
    ldrb.w r0, [r0, #COLOUR]
    bx lr

snaps_layout_name:                  @ in place of its read of snapshot k's name (manager, k): the other bank's, SNAPSHOT 4..6 for a
    mov r12, lr                     @ bank B not made yet
    bl snaps_viewed
    mov lr, r12
    cbnz r3, snaps_layout_name_other
    ldr r3, =NAME_GET
    bx r3
snaps_layout_name_other:
    cmp r3, #1
    bne snaps_layout_name_default
    bl snaps_shadow_record
    mov lr, r12
    addw r0, r0, #NAME
    bx lr
snaps_layout_name_default:
    adr.w r0, snaps_names
    add.w r0, r0, r1, lsl #4
    bx lr

snaps_layout_renamed:               @ in place of its test for a renamed snapshot k (manager, k): the other bank's, none for a bank B
    mov r12, lr                     @ not made yet
    bl snaps_viewed
    mov lr, r12
    cbnz r3, snaps_layout_renamed_other
    ldr r3, =RENAMED_GET
    bx r3
snaps_layout_renamed_other:
    movs r0, #0
    cmp r3, #1
    it ne
    bxne lr
    bl snaps_shadow_record
    mov lr, r12
    ldrb.w r0, [r0, #RENAMED]
    cmp r0, #0
    it ne
    movne r0, #1
    bx lr

snaps_shadow_record:                @ (-, k) -> r0 record k of snaps_shadow; keeps r1 and r12
    adr.w r0, snaps_shadow
    mov.w r2, #REC
    mla r0, r1, r2, r0
    bx lr

HXTRA_SETTING_GET

.ltorg
.balign 4
snaps_top:
    .word ICON, 0
snaps_labels:
    .word LABELS, LABELS + 0x24, LABELS + 0x48, 0
snaps_images:                       @ the stock cameras by style, then number: Icon_Snapshot1..3, 1Red..3Red, 1Sel..3Sel
    .hword 0x1a0, 0x71, 0x10f, 0x156, 0x105, 0x4f, 0x13, 0x202, 0x12a
.balign 4
snaps_names:                        @ bank B's default names, 16 bytes apart
    .ascii "SNAPSHOT 4"
    .space 6
    .ascii "SNAPSHOT 5"
    .space 6
    .ascii "SNAPSHOT 6"
    .space 6
snaps_file_head:                    @ key 0x64, bin16 of FILE_LEN (big-endian), "HX6B", version 1, 3 spare
    .byte FILE_KEY, 0xc5, FILE_LEN >> 8, FILE_LEN & 0xff, 'H', 'X', '6', 'B', 1, 0, 0, 0
snaps_data:                         @ 0 bank B live, 1 snaps_shadow holds bank B, 2 SAVING, 3 cameras to redraw, 4 VIEW,
    .byte 0, 0, 0, 0, 0, 0, 0, 0    @ 5 WRAP, 6 bank B read from a file, 7 RELAYOUT, 8 PREV6, 9 DSP_HELD, 10 HELD, 11 REPOST,
    .byte NONE, 0, 0, 0, 0, 0, 0, 0 @ 12 LEDS, 13..15 spare
snaps_armed:                        @ per footswitch 0..2: a lone press made in Snapshot mode on Hold, its click or hold still to come
    .space 4
snaps_temp:
    .space REC
snaps_shadow:                       @ the bank not live: three records as the manager's
    .space 3 * REC
snaps_staged:                       @ bank B as read from a preset file, until the preset's snapshots are parsed
    .space 3 * REC
