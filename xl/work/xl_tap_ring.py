"""Port HXtra Tap LED's ring handlers to the XL, independent of the Home label UI."""
import struct

import m4asm
import patch_amp
from features import tap_color
from xl_virtual_settings import REPO, WORK

CALLS = ((0x28d9eddc, "1cf094fa", "tap_led"),
         (0x28d9ee84, "1cf040fa", "tap_led_again"))
LED_DRIVER = 0x28dbb309
SETTING_GET = 0x28e25c71


def compile_tap_ring():
    stock = (REPO / "src" / "m4" / "tap_color.s").read_text(encoding="utf-8")
    ring = stock[stock.index(".thumb_func\n.global tap_led"):stock.index(".thumb_func\n.global tap_text")]
    palette = stock[stock.index("tap_leds:"):stock.index("tap_icons:")]
    rainbow = stock[stock.index("tap_rainbow_leds:"):stock.index("tap_shown:")]
    helpers = f"""
.thumb_func
tap_setting:
    push {{r4, lr}}
    sub sp, #8
    movs r0, #0
    str r0, [sp, #4]
    movs r0, #0xdf
    mov r1, sp
    ldr r3, ={SETTING_GET:#x}
    blx r3
    cmp r0, #0
    ite ge
    ldrge r0, [sp, #4]
    movlt r0, #0
    cmp r0, #11
    it hi
    movhi r0, #0
    add sp, #8
    pop {{r4, pc}}
    .ltorg
    .balign 4
"""
    source = (
        ".syntax unified\n.cpu cortex-m4\n.thumb\n"
        f".equ LED_COLOUR, {LED_DRIVER:#x}\n"
        ".equ CLOCK, 0x28da93ad\n.equ COLOURS, 10\n.equ RAINBOW, 10\n.equ RANDOM, 11\n"
        + tap_color.rainbow_inc() + "\n" + ring + helpers + palette + rainbow
    )
    path = WORK / "xl_tap_ring.s"
    path.write_text(source, encoding="utf-8")
    return m4asm.assemble_module(str(path))


def apply_tap_ring(entry, segments, base, occupied):
    def read(va):
        offset = patch_amp._e0_vaddr_to_foff(segments, va, 4)
        return bytes(entry[offset:offset + 4])

    for literal in (0x28d9ee14, 0x28d9eeb0):
        red, = struct.unpack("<I", read(literal))
        assert struct.unpack("<I", read(red))[0] == 0xc0000000 | tap_color.LEDS[0]
    code, symbols = compile_tap_ring()
    for site, original, symbol in CALLS:
        offset = patch_amp._e0_vaddr_to_foff(segments, site, 4)
        assert read(site) == bytes.fromhex(original)
        assert read(site) == patch_amp._thumb_bl(site, LED_DRIVER & ~1)
        region = set(range(offset, offset + 4))
        assert not occupied.intersection(region)
        occupied.update(region)
        entry[offset:offset + 4] = patch_amp._thumb_bl(site, base + symbols[symbol])
    return code, symbols
