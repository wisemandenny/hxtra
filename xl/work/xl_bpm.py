"""Relocate HXtra's BPM overlay to the XL Play view."""
import struct

import m4asm
import patch_amp
from features import bpm
from xl_virtual_settings import REPO, WORK, xl_display_include

RELOCATIONS = {
    0x28128a74: 0x28128d7a,
    0x28db8509: 0x28dbb631,
    0x281c90a4: 0x281ca1cc,
    0x28d98f79: 0x28d9bc69,
    0x28da6459: 0x28da93ad,
    0x281cd074: 0x281cdd84,
    0x28e249d1: 0x28e2b009,  # text init
    0x28e24a69: 0x28e2af01,  # text position
    0x28e24ac9: 0x28e2ade9,  # text anchor
    0x28e249e9: 0x28e2ae41,  # text font
    0x28e24bc1: 0x28e2adc9,  # text buffer
    0x28e24bc9: 0x28e2ae89,  # text visible
    0x28e24989: 0x28e2aea1,  # rectangle init
    0x28e24a19: 0x28e2afd1,  # rectangle anchor
    0x28e24b01: 0x28e2afc1,  # rectangle visible
    0x28e24a29: 0x28e2ae79,  # text colour
    0x28e24af1: 0x28e2aeb9,  # rectangle position
    0x28e24b29: 0x28e2aed1,  # rectangle size
    0x28e24b99: 0x28e2ad91,  # rectangle colour
    0x28e24c91: 0x28e2aef1,  # text erase
    0x28e24b41: 0x28e2ad99,  # rectangle erase
    0x28e24c31: 0x28e2ae39,  # text paint
    0x28e24b59: 0x28e2ae11,  # rectangle paint
    0x28e24971: 0x28e2ad41,  # graphics lock
    0x28e24ae9: 0x28e2adf1,  # graphics unlock
    0x28e1f845: 0x28e25c71,
    0x28d9685d: 0x28d994cd,
}
PLAY_PAINT_POINTER = 0x28d99a44
PLAY_PAINT = 0x28dcc98d
CALLS = (
    (0x28d99834, 0x28dccb98, "xl_bpm_construct"),
    (0x28dbb0a6, 0x28e2aee0, "xl_bpm_tick"),
    (0x28e258be, 0x28e25504, "xl_bpm_written"),
    (0x28e25d62, 0x28e25504, "xl_bpm_written"),
    (0x28e25ffa, 0x28e25504, "xl_bpm_written"),
    (0x28d9f044, 0x28e25c70, "xl_bpm_tap_led_option"),
    (0x28dd7cca, 0x28e25c70, "xl_bpm_tap_led_option"),
)

WRAPPERS = """
.balign 4
.thumb_func
xl_bpm_construct:
    push {r4, lr}
    ldr r3, =0x28dccb99
    blx r3
    mov r4, r0
    bl bpm_construct
    mov r0, r4
    pop {r4, pc}
.thumb_func
xl_bpm_paint:
    push {r0, r1, r4, lr}
    bl bpm_before
    ldrd r0, r1, [sp]
    ldr r3, =0x28dcc98d
    blx r3
    mov r4, r0
    ldr r0, [sp]
    bl bpm_after
    mov r0, r4
    add sp, #8
    pop {r4, pc}
.thumb_func
xl_bpm_tick:
    push {r4, lr}
    ldr r3, =0x28e2aee1
    blx r3
    mov r4, r0
    bl bpm_tick
    mov r0, r4
    pop {r4, pc}
.thumb_func
xl_bpm_written:
    push {r0, r4, r5, lr}
    ldr r12, =0x28e25505
    blx r12
    mov r4, r0
    ldr r0, [sp]
    bl bpm_written
    mov r0, r4
    add sp, #4
    pop {r4, r5, pc}
.thumb_func
xl_bpm_tap_led_option:
    push {r4, r5, r6, lr}
    mov r4, r1
    ldr r3, =0x28e25c71
    blx r3
    mov r5, r0
    cmp r0, #0
    blt bpm_option_done
    ldrb r3, [r4]
    cmp r3, #1
    bne bpm_option_done
    mov r1, r4
    bl bpm_tapled
bpm_option_done:
    mov r0, r5
    pop {r4, r5, r6, pc}
.thumb_func
xl_bpm_tap:
    push {r0-r4, lr}
    bl bpm_tap
    pop {r0-r4, lr}
    push {r4, lr}
    sub sp, #0x18
    ldr r12, =0x28d9eed9
    bx r12
.ltorg
"""


def compile_bpm(tap_now):
    source = (REPO / "src" / "m4" / "bpm.s").read_text(encoding="utf-8")
    for previous, address in RELOCATIONS.items():
        source = source.replace(f"{previous:#x}", f"{address:#x}")
    # XL has two independent paint queues. Mark both on beat transitions.
    redraw = "    movs r0, #0\n    movs r1, #1\n    ldr r3, =0x28dbb631"
    assert source.count(redraw) == 1
    source = source.replace(redraw, redraw.replace("movs r0, #0", "movs r0, #1"))
    source = source.replace("cmp r0, #2\n    bhi bpm_sent", "cmp r0, #7\n    bne bpm_sent")
    source = source.replace("strb r2, [r3, r0]", "strb r2, [r3]")
    source = source.replace("ldrb.w r2, [r3, r0, lsl #1]", "ldrb r2, [r3]")
    start, end = source.index("bpm_booted:"), source.index("    ldr r0, [r4, #16]")
    source = source[:start] + """bpm_booted:
    ldr r1, =FS_FUNCTIONS
    ldrb r0, [r1]
    movs r2, #0
    cmp r0, #1
    beq bpm_tapring
""" + source[end:]
    path = WORK / "xl_bpm.s"
    path.write_text(source + WRAPPERS, encoding="utf-8")
    include = WORK / "xl-bpm-include"
    include.mkdir(exist_ok=True)
    (include / "tap.inc").write_text(f".equ TAP_NOW, {tap_now:#x}\n", encoding="utf-8")
    (include / "hxtra.inc").write_text(
        xl_display_include(bpm), encoding="utf-8"
    )
    return m4asm.assemble_module(str(path), include=[str(include)])


def apply_bpm(entry, segments, base, tap_now, occupied):
    code, symbols = compile_bpm(tap_now)

    def read(address, size):
        offset = patch_amp._e0_vaddr_to_foff(segments, address, size)
        return bytes(entry[offset:offset + size])

    def replace(address, expected, changed):
        assert len(expected) == len(changed) and read(address, len(expected)) == expected, hex(address)
        offset = patch_amp._e0_vaddr_to_foff(segments, address, len(expected))
        region = set(range(offset, offset + len(expected)))
        assert not region.intersection(occupied), hex(address)
        occupied.update(region)
        entry[offset:offset + len(expected)] = changed

    for site, target, label in CALLS:
        replace(site, patch_amp._thumb_bl(site, target), patch_amp._thumb_bl(site, base + symbols[label]))
    replace(PLAY_PAINT_POINTER, struct.pack("<I", PLAY_PAINT),
            struct.pack("<I", (base + symbols["xl_bpm_paint"]) | 1))
    assert read(0x28d9bcf4, 4) == struct.pack("<I", 0x281ca1cc)
    replace(0x28d9bc64, bytes.fromhex("00b5234b"), patch_amp.thumb_bw(0x28d9bc64, base + symbols["bpm_ledsend"]))
    replace(0x28d9eed4, bytes.fromhex("10b586b0"), patch_amp.thumb_bw(0x28d9eed4, base + symbols["xl_bpm_tap"]))
    return code, symbols
