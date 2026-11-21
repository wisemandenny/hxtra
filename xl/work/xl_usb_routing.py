"""Install the XL application's Path A Out sender and menu callbacks."""
import struct

import m4asm
import patch_amp
import patch_menu
import setting_ids
from features import usb_monitor
from xl_virtual_settings import WORK

SEND, CHANGED, PAGE = 0x28dfb884, 0x28dd45e0, 0x28dd4304


def compile_usb():
    source = (WORK / "xl-v12" / "usb_monitor.s").read_text(encoding="ascii")
    for original, xl in {
        0x28d92a99: 0x28d95249,
        0x28e03c69: 0x28e09d89,
        0x28df35a1: 0x28df96c5,
        0x28df35e9: 0x28df970d,
        0x28e1f845: 0x28e25c71,
    }.items():
        source = source.replace(f"{original:#x}", f"{xl:#x}")
    source = source.replace("    str r0, [sp, #12]", "    movs r1, #3\n    str r1, [sp, #12]")
    source += """
.balign 4
.thumb_func
xl_usb_send:
    adr.w r12, stock_send
    orr r12, #1
    b um_send
.thumb_func
stock_send:
    push {r4-r7, lr}
    sub sp, #0x14
    ldr r12, =0x28dfb889
    bx r12
.thumb_func
xl_usb_changed:
    push {r1, r4, r5, lr}
    bl stock_changed
    mov r4, r0
    ldr r1, [sp]
    bl um_changed
    mov r0, r4
    pop {r1, r4, r5, pc}
.thumb_func
stock_changed:
    push {r4-r6, lr}
    cmp r1, #0x10
    ldr r12, =0x28dd45e5
    bx r12
.thumb_func
xl_usb_page:
    push {r4, lr}
    bl stock_page
    mov r4, r0
    bl um_page
    mov r0, r4
    pop {r4, pc}
.thumb_func
stock_page:
    push.w {r4-r10, lr}
    ldr r12, =0x28dd4309
    bx r12
.ltorg
"""
    module = WORK / "xl_usb_routing.s"
    module.write_text(source, encoding="ascii")
    include = WORK / "xl-usb-include"
    include.mkdir(exist_ok=True)
    (include / "hxtra.inc").write_text(
        patch_menu.hxtra_inc([usb_monitor], setting_ids.by_name(), getter=0x28e25c70),
        encoding="ascii",
    )
    return m4asm.assemble_module(str(module), include=[str(include)])


def install(entry, segments, base, occupied):
    code, labels = compile_usb()
    offset = patch_amp._e0_vaddr_to_foff(segments, 0x28dfb8ce, 4)
    assert entry[offset:offset + 4] == bytes.fromhex("d6f8c81a")
    for site, original, label in (
        (SEND, "f0b585b0", "xl_usb_send"),
        (CHANGED, "70b51029", "xl_usb_changed"),
        (PAGE, "2de9f047", "xl_usb_page"),
    ):
        expected = bytes.fromhex(original)
        offset = patch_amp._e0_vaddr_to_foff(segments, site, 4)
        assert entry[offset:offset + 4] == expected
        claimed = set(range(offset, offset + 4))
        assert not occupied.intersection(claimed)
        occupied.update(claimed)
        entry[offset:offset + 4] = patch_amp.thumb_bw(site, base + labels[label])
    return code
