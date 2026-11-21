"""Install the XL USB editor's optional local control and screen-mirror commands."""
import re
import struct

import m4asm
import patch_amp
from xl_virtual_settings import WORK

BOOT_CALL, BOOT = 0x28d99780, 0x28e1ca44
REGISTER = 0x28e1ca18
POST, POST_STOCK = 0x28dbb958, bytes.fromhex("f8b50446")
INPUT = {
    "REGISTER": REGISTER | 1, "NO_PARAMS": 0x28e1f62d, "SEND": 0x28e1bf59,
    "PUT": 0x28dbba25, "QUEUE": 0x281f5e28, "ROOM": 0x28dbcbd9, "SLEEP": 0x28e2aee1,
}
MIRROR = {
    "REGISTER": REGISTER | 1, "NO_PARAMS": 0x28e1f62d,
    "FB0": 0x28d1f650, "WRITER": 0x28e1bbf1, "PREFIX_LEN": 0x28e1bc15,
    "PREFIX": 0x28e1bc39, "PREFIX_RESET": 0x28e1bc5d, "REPLY_HEAD": 0x28e1bca1,
    "LOCK": 0x28e2ae81, "UNLOCK": 0x28e2aef9, "CLOCK": 0x28da93ad,
    "SLEEP": 0x28e2aee1, "LED_COLOURS": 0x281f55f8, "LED_MODES": 0x281f561c, "LEDS": 8,
}

GUARD_EVENTS = """
    mov r0, r4
ui_check:
    ldrb r1, [r0]
    ldrb r2, [r0, #1]
    ldrb r3, [r0, #2]
    ldrb r12, [r0, #3]
    orrs r3, r12
    bne ui_bad
    ldrb r3, [r0, #4]
    ldrb r12, [r0, #5]
    orrs r3, r3, r12, lsl #8
    ldrb r12, [r0, #6]
    orrs r3, r3, r12, lsl #16
    ldrb r12, [r0, #7]
    orrs r3, r3, r12, lsl #24
    cmp r1, #1
    beq ui_key
    cmp r1, #2
    bne ui_bad
    cmp r2, #4
    bhi ui_bad
    adds r1, r3, #127
    cmp r1, #254
    bhi ui_bad
    cmp r3, #0
    beq ui_bad
    b ui_check_next
ui_key:
    cmp r2, #24
    bhi ui_bad
    cmp r3, #5
    bhi ui_bad
    cmp r3, #4
    beq ui_bad
    cmp r3, #0
    beq ui_bad
ui_check_next:
    adds r0, #EVENT
    cmp r0, r5
    blo ui_check
"""

FRAME_CHECK = """
    ldr r0, =FB0
    cmp r11, r0
    beq sm_frame_valid
    add.w r1, r0, #FB_BYTES
    cmp r11, r1
    beq sm_frame_valid
    add.w r1, r1, #FB_BYTES
    cmp r11, r1
    beq sm_frame_valid
    mov r11, r0
sm_frame_valid:
"""


def compile_feature(name, command, profile, *, gr_data=0):
    source = (WORK / f"xl-{name}-upstream.s").read_text(encoding="utf-8-sig")
    source = re.sub(r'(?m)^\.include "usb.inc".*$', f".equ CMD, {command:#x}", source)
    for key, value in profile.items():
        source, count = re.subn(rf"(?m)^\.equ {key},.*$", f".equ {key}, {value:#x}", source)
        assert count == 1, key
    if name == "usb-input":
        source = source.replace("ui_next:", GUARD_EVENTS + "ui_next:", 1)
        source = source.replace("cbz r5, ui_bad", "cmp r5, #0\n    beq.w ui_bad")
    else:
        start = source.index("    ldr r0, =FB0")
        end = source.index("    ldr r3, =CLOCK", start)
        source = source[:start] + FRAME_CHECK + source[end:]
        if gr_data:
            trace = """
    @ Append the GR trace before the stock three timing words.
    adr.w r1, sm_prev
    add.w r1, r1, #FB_BYTES
    add r1, r8
    ldr r2, =GR_DATA
"""
            for offset in (24, 28, 40, 48, 4):
                trace += f"""
    ldr r3, [r2, #{offset}]
    strh r3, [r1], #2
    lsrs r3, #16
    strh r3, [r1], #2
"""
            trace += "    add.w r8, r8, #20\n"
            trace = trace.replace("GR_DATA", f"{gr_data:#x}")
            source = source.replace("    add r8, r0\n", "    add r8, r0\n" + trace, 1)

    path = WORK / f"xl-{name}.s"
    path.write_text(source, encoding="utf-8")
    return m4asm.assemble_module(str(path))


def install(entry, segments, base, occupied, *, usb_input, mirror, gr_data=0):
    blob = bytearray()
    registration = []
    event = None

    def read(va, size):
        offset = patch_amp._e0_vaddr_to_foff(segments, va, size)
        return bytes(entry[offset:offset + size])

    def replace(site, original, changed):
        offset = patch_amp._e0_vaddr_to_foff(segments, site, len(original))
        assert read(site, len(original)) == original, hex(site)
        region = set(range(offset, offset + len(original)))
        assert not occupied.intersection(region)
        occupied.update(region)
        entry[offset:offset + len(original)] = changed

    assert read(REGISTER, 4) == bytes.fromhex("7b280dd8")
    stock = []
    for site in range(REGISTER - 0x8000, REGISTER + 0x10000, 2):
        if read(site, 4) == patch_amp._thumb_bl(site, REGISTER):
            stock.append(next(read(site - back, 2)[0] for back in range(2, 14, 2)
                              if read(site - back, 2)[1] == 0x20))
    assert len(stock) == 110 and set(stock).isdisjoint((0x51, 0x52))

    for enabled, name, command, profile, register in (
        (usb_input, "usb-input", 0x51, INPUT, "ui_register"),
        (mirror, "screen-mirror", 0x52, MIRROR, "sm_register"),
    ):
        if not enabled:
            continue
        blob.extend(b"\0" * (-len(blob) % 4))
        code, labels = compile_feature(name, command, profile, gr_data=gr_data if name == "screen-mirror" else 0)
        registration.append((base + len(blob) + labels[register]) | 1)
        if name == "screen-mirror":
            event = (base + len(blob) + labels["sm_event"]) | 1
        blob.extend(code)
    if usb_input:
        assert read(0x28dbbb38, 4) == struct.pack("<I", INPUT["QUEUE"])
        assert read(INPUT["PUT"] & ~1, 6) == bytes.fromhex("f0b505468bb0")
    if mirror:
        for va, value in ((0x28da292c, 0x40008000), (0x28dbb234, MIRROR["FB0"]),
                          (0x28dbb364, MIRROR["LED_COLOURS"]), (0x28dbb3f0, MIRROR["LED_MODES"])):
            assert read(va, 4) == struct.pack("<I", value)
    blob.extend(b"\0" * (-len(blob) % 4))
    wrappers_base = base + len(blob)
    wrappers = f"""
.syntax unified
.thumb
.thumb_func
usb_boot:
    push {{r4, lr}}
    ldr r12, ={BOOT | 1:#x}
    blx r12
    mov r4, r0
"""
    for target in registration:
        wrappers += f"    ldr r12, ={target:#x}\n    blx r12\n"
    wrappers += "    mov r0, r4\n    pop {r4, pc}\n"
    if event is not None:
        wrappers += f"""
.thumb_func
usb_event:
    push {{r0-r4, lr}}
    ldr r12, ={event:#x}
    blx r12
    pop {{r0-r4, lr}}
    .hword 0xb5f8, 0x4604
    ldr r12, ={(POST + 4) | 1:#x}
    bx r12
"""
    path = WORK / "xl-usb-hooks.s"
    path.write_text(wrappers + "\n.ltorg\n", encoding="ascii")
    code, labels = m4asm.assemble_module(str(path))
    blob.extend(code)
    replace(BOOT_CALL, patch_amp._thumb_bl(BOOT_CALL, BOOT),
            patch_amp._thumb_bl(BOOT_CALL, wrappers_base + labels["usb_boot"]))
    if event is not None:
        replace(POST, POST_STOCK, patch_amp.thumb_bw(POST, wrappers_base + labels["usb_event"]))
    return blob
