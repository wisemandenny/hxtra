"""XL breathing line over the native Edit divider, with a shared LED task tick."""
import struct

import m4asm
import patch_amp
from features import breathing_line
from xl_virtual_settings import WORK, REPO, xl_display_include

EDIT_PAINT_PTR = 0x28d99a38
EDIT_PAINT = 0x28dc5939
TICK_SITE = 0x28dbb0a6
TICK_STOCK = 0x28e2aee0
DIVIDER = 0x281f927c
FILL_PREFIX = bytes.fromhex("82b02de9f04383b002ad9df838400b93")

XL_STRIP = """
    ldr.w r11, =SEGMENTS + 0x1c
    bl bl_valid_divider
    cbnz r0, bl_divider_found
    ldr.w r11, =SEGMENTS
    bl bl_valid_divider
    cbz r0, bl_render_done
bl_divider_found:
    movs r5, #0
bl_strip:
"""

CHECK = """
@ XL draws two full-width rectangle widgets, a base and a foreground.
@ Restrict the overlay to the stock Edit divider geometry.
bl_valid_divider:
    ldrb r0, [r11, #0x15]
    cbz r0, bl_not_divider
    ldrb r0, [r11, #0x14]
    cmp r0, #6
    bne bl_not_divider
    ldr r0, [r11, #4]
    cbnz r0, bl_not_divider
    ldr r0, [r11, #8]
    cmp r0, #120
    bne bl_not_divider
    ldr r0, [r11, #0xc]
    cmp r0, #320
    bne bl_not_divider
    ldr r0, [r11, #0x10]
    subs r0, #1
    cmp r0, #1
    ite ls
    movls r0, #1
    movhi r0, #0
    bx lr
bl_not_divider:
    movs r0, #0
    bx lr
"""


def compile_line(prior_tick):
    stock = (REPO / "src" / "m4" / "breathing_line.s").read_text(encoding="utf-8")
    addresses = {
        0x2812a594: DIVIDER,
        0x28db8509: 0x28dbb631,
        0x28da6459: 0x28da93ad,
        0x28e24971: 0x28e2ad41,
        0x28e24ae9: 0x28e2adf1,
        0x28e1f845: 0x28e25c71,
    }
    for original, xl in addresses.items():
        stock = stock.replace(f"{original:#x}", f"{xl:#x}")
    stock = stock.replace('.include "gr.inc"', '@ XL meter state is published by the Edit paint wrapper.')
    start = stock.index(".if GR_SHOWN")
    end = stock.index(".endif", start) + len(".endif")
    stock = stock[:start] + """
    adr.w r1, xl_line_meter_middle
    ldr r1, [r1]
    cmp r1, #0
    it ne
    movne r6, #0
""" + stock[end:]
    start = stock.index("    movs r5, #0\nbl_strip:")
    end = stock.index("    mov r0, r6\n", start)
    stock = stock[:start] + XL_STRIP + stock[end:]
    marker = "    bne bl_strip\n    ldr r3,"
    assert stock.count(marker) == 1
    stock = stock.replace(marker, "    bne bl_strip\nbl_render_done:\n    ldr r3,")
    stock = stock.replace("    movs r1, #4\n    movs r2, #1\nbl_dirty:",
                          "    movs r1, #2\n    movs r2, #1\nbl_dirty:")
    stock = stock.replace(
        "    strb r2, [r3, #0x24]\n    adds r0, #0x1c",
        "    cbz r3, bl_next_node\n    strb r2, [r3, #0x24]\nbl_next_node:\n    adds r0, #0x1c",
    )
    stock += CHECK + f"""
.ltorg
.balign 4
.thumb_func
xl_line_edit_paint:
    push {{r4-r6, lr}}
    mov r4, r0
    ldr r3, ={EDIT_PAINT:#x}
    blx r3
    mov r5, r0
    mov r0, r4
    bl bl_paint
    mov r0, r5
    pop {{r4-r6, pc}}
.thumb_func
xl_line_tick:
    push {{r4, lr}}
    ldr r3, ={prior_tick | 1:#x}
    blx r3
    mov r4, r0
    bl bl_tick
    mov r0, r4
    pop {{r4, pc}}
.ltorg
.balign 4
xl_line_meter_middle:
    .word 0
"""
    module = WORK / "xl_breathing_line.s"
    module.write_text(stock, encoding="utf-8")
    include = WORK / "xl-breathing-include"
    include.mkdir(exist_ok=True)
    (include / "hxtra.inc").write_text(
        xl_display_include(breathing_line), encoding="utf-8"
    )
    return m4asm.assemble_module(str(module), include=[str(include)])


def apply_line(entry, segments, base, prior_tick, occupied):
    code, labels = compile_line(prior_tick)

    def replace(address, expected, replacement, shared=False):
        offset = patch_amp._e0_vaddr_to_foff(segments, address, len(expected))
        assert entry[offset:offset + len(expected)] == expected, hex(address)
        region = set(range(offset, offset + len(expected)))
        assert (region <= occupied) if shared else (not region.intersection(occupied))
        occupied.update(region)
        entry[offset:offset + len(expected)] = replacement

    fill = patch_amp._e0_vaddr_to_foff(segments, 0x100017e8, len(FILL_PREFIX))
    assert entry[fill:fill + len(FILL_PREFIX)] == FILL_PREFIX
    replace(EDIT_PAINT_PTR, struct.pack("<I", EDIT_PAINT), struct.pack("<I", (base + labels["xl_line_edit_paint"]) | 1))
    replace(TICK_SITE, patch_amp._thumb_bl(TICK_SITE, prior_tick),
            patch_amp._thumb_bl(TICK_SITE, base + labels["xl_line_tick"]), shared=prior_tick != TICK_STOCK)
    return code, labels
