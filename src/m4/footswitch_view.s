@ footswitch_view.s - Footswitch View: a Footswitches screen, as the HX Stomp XL shows its switches: the preset, then two rows of three tiles,
@ FS6 FS7 FS8 (the virtual footswitches, MIDI CC 20..22) above FS1 FS2 FS3. Each tile is lit in its block's category colour,
@ dimmed while the block is off, with the block's name (FS1..FS3: the Play view's own footswitch labels).
@ VIEW cycles Play -> Edit -> Footswitches -> Play. The screen is drawn over the Play view, which stays the active view under it,
@ so the footswitches and knobs work as they do in Play. Leaving it reactivates the Play view, which redraws it whole.
@ A block's name and category come from the firmware's own model tables as they are at run time (Table 1: name index -> preset model
@ ID; Table 2: name and category), so a model a later build step adds (the Metronome, the MIDI and Phones blocks) has its tile too,
@ and a renamed one (Real block names) its new name. footswitch_view.inc (generated) gives the tables' pointer literals and the
@ movw instructions that hold their row counts, which every add-model step keeps up to date.
.syntax unified
.thumb
.include "footswitch_view.inc"

.equ SCREEN, 0x28128260             @ the screen shown: 0 Play, 1 Edit, ...
.equ TOP, 0x2812aae0                @ the Play view's top half: +0x30 preset number, +0x8c preset name (text widgets)
.equ HOME, 0x2812a05c               @ the Play view's bottom half: footswitch k's label lines at +0x64 + 0x30k, +0xf4 + 0x30k
.equ TOP_HANDLER, 0x28dca555        @ (msg 0, active, view): the views' show/hide handlers
.equ HOME_HANDLER, 0x28dc9129
.equ VIEW_KEY, 5
.equ NO_KEY, 0xff                   @ a key code no listener handles
.equ FONTS, 0x28d1aa7c
.equ TILE_FONT, 1                   @ hx21_regularFont
.equ TILE_W, 104
.equ TILE_H, 80
.equ ROW_TOP, 166                   @ the top row's top edge (widget y counts up from the bottom), screen 74..153
.equ ROW_BOTTOM, 82                 @ the bottom row's, screen 158..237
.equ VIRTUAL_CC, 20

.macro CALL fn
    ldr r12, =(\fn) | 1
    blx r12
.endm

@ ---------------------------------------------------------------- VIEW
@ Before the key events' post (a chain other features share): r0 the event {class, code, -, -, type}. A press this feature
@ takes is turned into a key no listener knows (NO_KEY), so the stock post passes it by.
.thumb_func
footswitch_view_post:
    ldr r2, =SCREEN                 @ any event while another screen is up (the tuner, the Menu, Edit): the Footswitches screen is
    ldrb r2, [r2]                   @ off, so a return to Play shows Play (the UI task's 100 Hz ticks come this way too)
    cbz r2, post_event
    adr.w r3, state
    movs r1, #0
    strb r1, [r3, #1]
post_event:
    ldrb r1, [r0]
    cmp r1, #1
    bne post_on
    ldrb r1, [r0, #1]
    cmp r1, #VIEW_KEY
    bne post_on
    adr.w r2, state
    ldr r1, [r0, #4]                @ the type: 1 press, 2 release, 3 release before a hold, 5 hold
    ldrb r3, [r2, #3]               @ swallowing VIEW until its release
    cbz r3, post_view
    cmp r1, #2                      @ its release ends it
    itt eq
    moveq r3, #0
    strbeq r3, [r2, #3]
    movs r1, #NO_KEY
    strb r1, [r0, #1]
    bx lr
post_view:
    cmp r1, #1
    bne post_on
    ldr r3, =SCREEN
    ldrb r3, [r3]
    cmp r3, #1
    bne post_play
    movs r1, #1                     @ in Edit: the stock goes to Play, and the Footswitches screen goes over it
    strb r1, [r2]                   @ armed
    b post_on
post_play:
    cbnz r3, post_on
    ldrb r1, [r2, #1]
    cbz r1, post_on
    movs r1, #0                     @ on the Footswitches screen: back to Play, the press kept from the Play view
    strb r1, [r2, #1]
    movs r1, #1
    strb r1, [r2, #2]               @ the Play view to be reactivated, by the view controller
    strb r1, [r2, #3]
    movs r1, #NO_KEY
    strb r1, [r0, #1]
    push {r0, lr}
    movs r0, #0
    CALL 0x28d96320                 @ request the Play view: runs the controller
    pop {r0, pc}
post_on:
    bx lr

.thumb_func
footswitch_view_controller:                  @ the view controller's entry: the Play view reactivated, as a switch to it does
    adr.w r0, state
    ldrb r1, [r0, #2]
    cbz r1, controller_done
    movs r1, #0
    strb r1, [r0, #2]
    push {r4, lr}
    ldr r0, =0x281f3d30             @ the views' lock, as the activation 0x28db865c holds it around a handler
    CALL 0x28e249a0
    movs r0, #0
    movs r1, #0
    ldr r2, =TOP
    CALL TOP_HANDLER
    movs r0, #0
    movs r1, #0
    ldr r2, =HOME
    CALL HOME_HANDLER
    movs r0, #0
    movs r1, #1
    ldr r2, =TOP
    CALL TOP_HANDLER
    movs r0, #0
    movs r1, #1
    ldr r2, =HOME
    CALL HOME_HANDLER
    ldr r0, =0x281f3d30
    CALL 0x28e24a30
    movs r0, #1
    movs r1, #1
    CALL 0x28db8508                 @ a full repaint
    pop {r4, pc}
controller_done:
    bx lr

@ ---------------------------------------------------------------- the screen
.thumb_func
footswitch_view_paint:                           @ r0 framebuffer: after the Play view's top or bottom half paints
    push {r4-r11, lr}
    sub sp, #0xa0
    mov r11, r0
    adr.w r4, state
    ldr r0, =SCREEN
    ldrb r0, [r0]
    ldrb r1, [r4]
    cbz r1, fs_armed_done
    cmp r0, #1
    beq fs_armed_done               @ still in Edit
    movs r1, #0
    strb r1, [r4]
    cbnz r0, fs_armed_done          @ somewhere else: no screen
    movs r1, #1
    strb r1, [r4, #1]
fs_armed_done:
    cmp r0, #0
    bne fs_out
    ldrb r1, [r4, #1]
    cmp r1, #0
    beq fs_out

    @ the virtual footswitches' tiles first: their blocks are read under the DSP model's lock, never with the widget lock held
    movs r5, #0
fs_virtual:
    mov r0, r5
    add r1, sp, #0x40
    add.w r1, r1, r5, lsl #5        @ tile r5's record (32 bytes): name 16, colour, text colour, present
    bl virtual_tile
    adds r5, #1
    cmp r5, #3
    blt fs_virtual

    CALL 0x28e24970                 @ the widget lock
    mov r0, r11                     @ black, the whole screen
    movs r1, #0
    movs r2, #0
    mov r3, #320
    movs r4, #240
    str r4, [sp]
    movs r4, #0
    str r4, [sp, #4]
    str r4, [sp, #8]
    CALL 0x100017e8

    ldr r0, =TOP + 0x30             @ the preset number and name, as the Play view has them
    movs r1, #4
    movs r2, #238
    bl header_line
    ldr r0, =TOP + 0x8c
    movs r1, #3
    movs r2, #202
    bl header_line

    movs r5, #0
fs_tiles:
    cmp r5, #3
    bge fs_real
    add r6, sp, #0x40
    add.w r6, r6, r5, lsl #5
    ldr r0, [r6, #0x1c]
    cbz r0, fs_empty
    mov r0, r5
    ldr r1, [r6, #0x10]
    bl tile_fill
    mov r7, r0
    mov r0, r6                      @ the name, on one line or two
    bl name_lines
    b fs_tile_next
fs_real:
    subs r0, r5, #3                 @ footswitch 0..2: the Play view's label lines
    add.w r0, r0, r0, lsl #1
    lsls r0, r0, #4
    ldr r6, =HOME + 0x64
    add r6, r0
    ldrb r1, [r6, #0x2a]            @ visible
    cbz r1, fs_empty
    mov r0, r5
    ldr r1, [r6, #0x1c]             @ the label's colour: lit or dimmed, as the block is
    bl tile_fill
    mov r7, r0                      @ the text colour
    ldr r0, [r6]
    bl strlen16
    mov r8, r0                      @ line 1's length
    add.w r4, r6, #0x90             @ its second line
    ldrb r1, [r4, #0x2a]
    cbz r1, fs_real_one
    ldr r0, [r4]
    bl strlen16
    cbz r0, fs_real_one
    mov r3, r0
    ldr r2, [r4]
    ldr r0, [r6]
    mov r1, r8
    bl two_lines
    b fs_tile_next
fs_real_one:
    ldr r0, [r6]
    mov r1, r8
    movs r2, #0
    movs r3, #0
    bl two_lines
    b fs_tile_next
fs_empty:
    mov r0, r5
    ldr r1, =0x262626
    bl tile_fill
fs_tile_next:
    adds r5, #1
    cmp r5, #6
    blt fs_tiles
    CALL 0x28e24ae8
fs_out:
    add sp, #0xa0
    pop {r4-r11, pc}

@ r0 a text widget, r1 its font, r2 the top edge: its text centred there in white
header_line:
    push {r4, r5, r6, lr}
    sub sp, #24
    mov r4, r0
    mov r5, r1
    mov r6, r2
    ldr r0, [r4]
    cbz r0, header_done
    bl strlen16
    cbz r0, header_done
    mov r2, r0
    str r6, [sp]                    @ y
    str r5, [sp, #4]                @ font
    mvn r0, #0xff000000
    str r0, [sp, #8]                @ colour
    movs r0, #7                     @ anchor: the top edge's centre
    str r0, [sp, #12]
    movs r0, #1                     @ glyphs without their boxes
    str r0, [sp, #16]
    ldr r1, [r4]
    mov r3, #160
    mov r0, r11
    CALL 0x28db7aa4
header_done:
    add sp, #24
    pop {r4, r5, r6, pc}

@ r0 tile 0..5, r1 its colour; r11 the framebuffer: fills it; -> r0 its text colour; leaves r9 its centre x, r10 its centre y
tile_fill:
    push {r4, r5, lr}
    sub sp, #12
    mov r5, r1
    movs r2, #ROW_TOP - TILE_H
    cmp r0, #3
    itt ge
    subge r0, #3
    movge r2, #ROW_BOTTOM - TILE_H
    movs r1, #TILE_W + 4
    muls r1, r0, r1
    adds r1, #2                     @ x: 2, 110, 218
    add.w r9, r1, #TILE_W / 2
    add.w r10, r2, #TILE_H / 2
    movs r0, #TILE_H
    str r0, [sp]
    str r5, [sp, #4]
    movs r0, #0                     @ anchor: bottom left
    str r0, [sp, #8]
    mov r0, r11
    movs r3, #TILE_W
    CALL 0x100017e8
    ubfx r0, r5, #16, #8            @ dark text on a bright tile, light on a dim one
    ubfx r1, r5, #8, #8
    add r0, r0, r1, lsl #1
    uxtb r1, r5
    add r0, r1
    cmp r0, #300
    ite ge
    ldrge r0, =0x141414
    ldrlt r0, =0xe0e0e0
    add sp, #12
    pop {r4, r5, pc}

@ r0 text 1, r1 its length, r2 text 2 (or 0), r3 its length; r7 colour, r9/r10 the centre: one line centred, or two
two_lines:
    push {r4-r6, lr}
    sub sp, #24
    mov r4, r2
    mov r5, r3
    mov r6, r10
    cbz r4, two_one
    adds r6, #11                    @ two lines: 11 px above and below the centre
two_one:
    mov r2, r1
    mov r1, r0
    bl text_at
    cbz r4, two_done
    sub r6, r10, #11
    mov r1, r4
    mov r2, r5
    bl text_at
two_done:
    add sp, #24
    pop {r4-r6, pc}

text_at:                            @ r1 text, r2 length, r6 its centre y; r7 colour, r9 centre x, r11 framebuffer (sp: 24 free)
    push {lr}
    sub sp, #20
    str r6, [sp]
    movs r0, #TILE_FONT
    str r0, [sp, #4]
    str r7, [sp, #8]
    movs r0, #4                     @ anchor: centred
    str r0, [sp, #12]
    movs r0, #1
    str r0, [sp, #16]
    mov r3, r9
    mov r0, r11
    CALL 0x28db7aa4
    add sp, #20
    pop {pc}

@ r0 a tile record (name, 16 bytes): its name centred, split into two lines if it is wider than the tile
name_lines:
    push {r4-r8, lr}
    sub sp, #40                     @ 0 line 1, 20 line 2: each NUL-terminated (the renderer draws to the NUL)
    mov r1, r0
    mov r4, sp
    movs r3, #0
name_copy:
    ldrb r2, [r1, r3]
    strb r2, [r4, r3]
    cbz r2, name_copied
    adds r3, #1
    cmp r3, #16
    blt name_copy
    movs r2, #0
    strb r2, [r4, r3]
name_copied:
    mov r5, r3                      @ its length
    cbz r5, name_done
    ldr r6, =FONTS + 0x604 * TILE_FONT
    mov r0, r4
    mov r1, r5
    bl width
    cmp r0, #TILE_W - 6
    bgt name_split
    mov r0, r4
    mov r1, r5
    movs r2, #0
    movs r3, #0
    bl two_lines
    b name_done
name_split:                         @ at the space nearest the middle, else the middle
    lsrs r8, r5, #1                 @ the cut
    movs r6, #0xff                  @ its distance from the middle
    movs r3, #1
name_space:
    cmp r3, r5
    bge name_cut
    ldrb r0, [r4, r3]
    cmp r0, #' '
    bne name_space_next
    lsrs r1, r5, #1
    subs r0, r3, r1
    it mi
    rsbmi r0, r0, #0
    cmp r0, r6
    bge name_space_next
    mov r6, r0
    mov r8, r3
name_space_next:
    adds r3, #1
    b name_space
name_cut:
    ldrb r0, [r4, r8]
    mov r3, r8                      @ line 2 starts after the space, or at the cut
    cmp r0, #' '
    it eq
    addeq r3, #1
    add r1, sp, #20                 @ line 2, copied out
    movs r2, #0
name_copy2:
    ldrb r0, [r4, r3]
    strb r0, [r1, r2]
    cbz r0, name_copied2
    adds r3, #1
    adds r2, #1
    b name_copy2
name_copied2:
    movs r0, #0
    strb r0, [r4, r8]               @ line 1 ends at the cut
    mov r3, r2
    add r2, sp, #20
    mov r0, r4
    mov r1, r8
    bl two_lines
name_done:
    add sp, #40
    pop {r4-r8, pc}

width:                              @ r0 text, r1 length, r6 font -> r0 its width (glyphs and the spacing between them)
    push {r4, lr}
    movs r2, #0
    cbz r1, width_done
    mov r4, r0
    ldr r12, [r6]
    sub r2, r12                     @ one spacing fewer than glyphs
width_next:
    ldrb r0, [r4], #1
    and r0, r0, #0x7f
    add r0, r0, r0, lsl #1
    add r0, r6, r0, lsl #2
    ldr r0, [r0, #8]
    add r2, r0
    add r2, r12
    subs r1, #1
    bne width_next
width_done:
    mov r0, r2
    pop {r4, pc}

strlen16:                           @ r0 a text -> r0 its length, at most 16
    mov r1, r0
    movs r0, #0
strlen_next:
    ldrb r2, [r1, r0]
    cbz r2, strlen_done
    adds r0, #1
    cmp r0, #16
    blt strlen_next
strlen_done:
    bx lr

    .ltorg

@ r0 virtual footswitch 0..2, r1 its tile record: the first block on MIDI CC 20 + r0, its name, colour, and whether there is one
virtual_tile:
    push {r4-r8, lr}
    sub sp, #0x80                   @ 0 bypass, 4 the block (0x34), 0x40 its category (0x2c)
    mov r8, r1
    add.w r7, r0, #VIRTUAL_CC
    movs r0, #0
    str r0, [r8, #0x1c]
    CALL 0x28d9608c                 @ the parameter controllers
    mov r5, r0
    adds r0, r5, #4
    CALL 0x28e24c00                 @ their lock
    mvn r6, #0
    add.w r3, r5, #0xac
    movs r2, #64
vt_scan:
    ldrb r1, [r3, #0x44]
    cmp r1, #0x40
    beq vt_next
    ldrb r1, [r3, #0x28]
    cmp r1, #2
    bne vt_next
    ldrb r1, [r3, #0x10]
    cmp r1, #8
    bne vt_next
    ldr r1, [r3, #0x14]
    cmp r1, r7
    bne vt_next
    ldr r6, [r3, #0x2c]
    b vt_found
vt_next:
    adds r3, #0x48
    subs r2, #1
    bne vt_scan
vt_found:
    adds r0, r5, #4
    CALL 0x28e24bb0
    adds r0, r6, #1
    beq vt_done
    CALL 0x28d92a98
    mov r1, r6
    add r2, sp, #4
    CALL 0x28e0fe94                 @ the block: its model's preset ID at +1
    cmp r0, #0
    blt vt_done
    ldrb r0, [sp, #5]
    ldrb r1, [sp, #6]
    orr r0, r0, r1, lsl #8
    bl model_row                    @ its Table 2 row: the name at +4 (16 bytes), the category at +0x15
    cbz r0, vt_done
    adds r4, r0, #4
    ldrb r0, [r4]
    cbz r0, vt_done
    ldr r0, [r4]                    @ the name, word by word: a row is 4-aligned
    ldr r1, [r4, #4]
    ldr r2, [r4, #8]
    ldr r3, [r4, #12]
    stmia r8, {r0-r3}
    movs r0, #0xff
    strb r0, [sp]
    CALL 0x28d92a98
    mov r1, r6
    mov r2, sp
    CALL 0x28e04514                 @ bypassed: 1
    ldrb r0, [r4, #0x11]
    add r1, sp, #0x40
    CALL 0x28d9e01c                 @ the category's colours: lit +0x1c, dimmed +0x20
    ldrb r0, [sp]
    cmp r0, #1
    ite eq
    ldreq r0, [sp, #0x40 + 0x20]
    ldrne r0, [sp, #0x40 + 0x1c]
    str r0, [r8, #0x10]
    movs r0, #1
    str r0, [r8, #0x1c]
vt_done:
    add sp, #0x80
    pop {r4-r8, pc}

    .ltorg

@ r0 a preset model ID -> r0 its Table 2 row, or 0: Table 1 {name index, preset ID +4 (16 bits), -, cost} maps the ID to a name
@ index, Table 2 {name index, name +4, ..., category +0x15} has the row
model_row:
    push {r4-r7, lr}
    mov r7, r0
    ldr r0, =TAB1_CNT_INSN
    bl movw_imm
    mov r5, r0
    ldr r4, =TAB1_BASE_PTR
    ldr r4, [r4]
mr_t1:
    cbz r5, mr_none
    ldrh r0, [r4, #4]
    cmp r0, r7
    beq mr_t2
    adds r4, #12
    subs r5, #1
    b mr_t1
mr_t2:
    ldr r6, [r4]                    @ its name index
    ldr r0, =TAB2_CNT_INSN
    bl movw_imm
    mov r5, r0
    ldr r4, =TAB2_BASE_PTR
    ldr r4, [r4]
mr_t2_scan:
    cbz r5, mr_none
    ldr r0, [r4]
    cmp r0, r6
    beq mr_found
    adds r4, #44
    subs r5, #1
    b mr_t2_scan
mr_found:
    mov r0, r4
    pop {r4-r7, pc}
mr_none:
    movs r0, #0
    pop {r4-r7, pc}

@ r0 the address of a Thumb-2 movw -> r0 its 16-bit immediate (imm4:i:imm3:imm8)
movw_imm:
    ldrh r1, [r0]
    ldrh r2, [r0, #2]
    and r0, r1, #0xf
    lsl r0, r0, #12
    ubfx r3, r1, #10, #1
    orr r0, r0, r3, lsl #11
    ubfx r3, r2, #12, #3
    orr r0, r0, r3, lsl #8
    uxtb r3, r2
    orr r0, r0, r3
    bx lr

    .ltorg
.balign 4
state: .byte 0, 0, 0, 0             @ armed (VIEW pressed in Edit), shown, Play to be reactivated, swallowing VIEW
