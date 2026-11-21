"""XL gain-reduction receive callback and Play overlay."""
import struct

import m4asm
import patch_amp
from xl_bpm import PLAY_PAINT, PLAY_PAINT_POINTER
from xl_breathing import EDIT_PAINT, EDIT_PAINT_PTR
from xl_virtual_settings import WORK

RX_PTR, RX = 0x28da90b4, 0x10001095


def compile_gr(prior_play, prior_edit, compressor_names, line_middle=0, *, diagnostic=False):
    original = (WORK / "xl-gr-upstream.s").read_text(encoding="ascii")

    def part(start, end):
        offset = original.index(start)
        return original[offset:original.index(end, offset + len(start))]

    source = ".syntax unified\n.thumb\n"
    source += ".thumb_func\n" + part("frame:", "stockdiv:")
    # XL has two independent display paint lists. Wake both so the active
    # list repaints even when the stock view has no input events to redraw it.
    source += part("repaint:", "layout: ").replace("0x28db8509", "0x28dbb631").replace(
        "lsls r0, r0, #28", "lsls r0, r0, #26"
    ).replace("movs r1, #1\n    ldr r3", "movs r0, #1\n    movs r1, #1\n    ldr r3")
    source = source.replace(
        "    ldr r1, [r4, #24]\n", "    ror.w r0, r0, #16\n    ldr r1, [r4, #24]\n", 1
    )
    source += part("q16:", "edit_params:").rsplit(".thumb_func", 1)[0]
    source += part("slots:", "showing:").rsplit(".thumb_func", 1)[0]
    selected = part("selected:", ".ltorg")
    for original_address, xl_address in {
        "0x28df0281": "0x28df62bd",
        "0x28449e78": "0x2844c5e8",
        "0x28e07845": "0x28e0db89",
        "0x28e0785d": "0x28e0dba1",
    }.items():
        selected = selected.replace(original_address, xl_address)
    source += selected.replace("#COMP_COUNT", f"#{len(compressor_names)}")
    source += ".ltorg\n.balign 4\n" + part("lights:", "comps:")
    source += "comps:\n    .hword " + ", ".join(map(str, compressor_names)) + "\n"
    source += """
.balign 4
data:
    .space 52
eprev:
    .space 20
.balign 4
.thumb_func
xl_gr_receive:
    push {r0-r2, lr}
    bl frame
    pop {r0-r2, lr}
    ldr r12, =0x10001095
    bx r12

.thumb_func
xl_gr_play:
    movs r2, #0
    ldr r3, =PRIOR_PLAY
    b paint
.thumb_func
xl_gr_edit:
    movs r2, #1
    ldr r3, =PRIOR_EDIT
paint:
    push {r4-r7, r11, lr}
    push {r2, r3}
    mov r11, r0
    mov r4, r1
    adr.w r5, data
    ldr r0, [r5, #48]
    cbz r0, gr_stock
    movs r1, #0
    bl slots
gr_stock:
    ldr r7, [r5, #40]
    ldr r0, [sp]
    cbz r0, gr_stock_paint
    cbz r7, gr_line_flag
    bl selected
    cmp r0, #0
    it eq
    moveq r7, #0
gr_line_flag:
    ldr r3, line_middle_address
    cbz r3, gr_stock_paint
    ubfx r2, r7, #8, #8
    cmp r2, #0
    ite eq
    lsreq r2, r7, #31
    movne r2, #0
    str r2, [r3]
gr_stock_paint:
    mov r0, r11
    mov r1, r4
    ldr r3, [sp, #4]
    blx r3
    mov r6, r0
    cbz r7, gr_end
    mov r0, r7
    movs r1, #1
    bl slots
gr_end:
    str r7, [r5, #48]
    mov r0, r6
    add sp, #8
    pop {r4-r7, r11, pc}
.ltorg
.balign 4
line_middle_address:
    .word LINE_MIDDLE
esave:
    .space 12000
""".replace("PRIOR_PLAY", f"{prior_play:#x}").replace("PRIOR_EDIT", f"{prior_edit:#x}").replace(
    "LINE_MIDDLE", f"{line_middle:#x}"
)
    if diagnostic:
        source = source.replace("post:\n", """post:
    ldr r0, [r4, #24]
    and r0, r0, #16
    adr.w r1, trace_last
    ldr r2, [r1]
    cmp r2, r0
    beq gr_trace_post
    str r0, [r1]
    movs r0, #1
    str r0, [r4, #16]
gr_trace_post:
""", 1)
        source = source.replace("    bl frame", """    adr.w r0, trace_receive
    movs r2, #1
    str r2, [r0]
    pop {r0-r2, lr}
    push {r0-r2, lr}
    bl frame""", 1)
        source = source.replace("    cbz r0, gr_stock_paint", """    cbnz r0, gr_trace_edit
    @ Diagnostic mode replaces the Play meter with a stage count at the top.
    movs r7, #1
    adr.w r3, trace_receive
    ldr r3, [r3]
    cbz r3, gr_trace_layout
    adds r7, #1
    ldr r3, [r5, #12]
    cbz r3, gr_trace_layout
    adds r7, #1
    ldr r3, [r5, #32]
    lsrs r2, r3, #24
    cmp r2, #0x6b
    bne gr_trace_layout
    uxtb r3, r3
    cbz r3, gr_trace_layout
    adds r7, #1
    ldr r3, [r5, #24]
    cbz r3, gr_trace_layout
    adds r7, #1
    ldr r3, [r5, #40]
    uxtb r3, r3
    cbz r3, gr_trace_heartbeat
    adds r7, #1
gr_trace_heartbeat:
    @ The window counter changes about once per 21 ms upstream.
    @ Bit 4 is slow enough to observe in a 15 fps mirror capture.
    ldr r3, [r5, #24]
    tst r3, #16
    it ne
    addne r7, #2
gr_trace_layout:
    ldr r3, =0x8a000100
    orrs r7, r3
    b gr_stock_paint
gr_trace_edit:""", 1)
        source = source.replace("esave:", "trace_receive:\n    .word 0\ntrace_last:\n    .word 0\nesave:", 1)
    path = WORK / "xl_gr_play.s"
    path.write_text(source, encoding="ascii")
    return m4asm.assemble_module(str(path))


def compressor_indices(archive):
    import patch_comp

    names = patch_comp.e3_strings(patch_comp.pa.get_entry_swapped(archive, 3))[3]
    return tuple(names[name] for name, _ in patch_comp.COMP_MODELS)


def install(entry, segments, base, occupied, prior_play, prior_edit, compressor_names, line_middle, *, diagnostic=False):
    code, symbols = compile_gr(prior_play, prior_edit, compressor_names, line_middle, diagnostic=diagnostic)
    for address, before, label, shared in (
        (RX_PTR, RX, "xl_gr_receive", False),
        (PLAY_PAINT_POINTER, prior_play, "xl_gr_play", prior_play != PLAY_PAINT),
        (EDIT_PAINT_PTR, prior_edit, "xl_gr_edit", prior_edit != EDIT_PAINT),
    ):
        offset = patch_amp._e0_vaddr_to_foff(segments, address, 4)
        assert entry[offset:offset + 4] == struct.pack("<I", before)
        patch = set(range(offset, offset + 4))
        assert (patch <= occupied) if shared else (not patch.intersection(occupied))
        occupied.update(patch)
        entry[offset:offset + 4] = struct.pack("<I", (base + symbols[label]) | 1)
    return code, base + symbols["data"]
