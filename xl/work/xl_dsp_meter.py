"""Relocate the DSP meter to the XL Edit and model-browser painters."""
import struct

import m4asm
import patch_amp
import patch_menu
import setting_ids
from features import dsp_meter
from xl_bpm import RELOCATIONS
from xl_breathing import EDIT_PAINT, EDIT_PAINT_PTR
from xl_virtual_settings import WORK

BROWSER_PAINT_PTR = 0x28d99ab4
BROWSER_PAINT = 0x28dc7f11
NAMES_X = 0x28d93722
DSP_MODEL = 0x2844c5e8
SLOT_MODEL = 0x2812d3cc


def compile_meter(prior_edit_paint):
    source = (WORK / "xl-dsp-meter-upstream.s").read_text(encoding="utf-8")
    addresses = {
        **RELOCATIONS,
        0x28449e78: DSP_MODEL,
        0x2812c590: SLOT_MODEL,
        0x28e07845: 0x28e0db89,
        0x28e0785d: 0x28e0dba1,
        0x28df0281: 0x28df62bd,
        0x28e0edcd: 0x28e151f5,
        0x28e01205: 0x28e07325,
        0x28e01d51: 0x28e07e71,
    }
    for original, xl in addresses.items():
        source = source.replace(f"{original:#x}", f"{xl:#x}")
    source += "\n.balign 4\n"
    for view, painter, overlay in (
        ("edit", prior_edit_paint, "dsp_paint"),
        ("browser", BROWSER_PAINT, "dsp_browser"),
    ):
        source += f"""
.thumb_func
xl_dsp_{view}_paint:
    push {{r4-r6, lr}}
    mov r4, r0
    mov r5, r1
    ldr r3, ={painter:#x}
    blx r3
    mov r6, r0
    mov r0, r4
    mov r1, r5
    bl {overlay}
    mov r0, r6
    pop {{r4-r6, pc}}
"""
    source += ".ltorg\n"
    module = WORK / "xl_dsp_meter.s"
    module.write_text(source, encoding="utf-8")
    include = WORK / "xl-dsp-meter-include"
    include.mkdir(exist_ok=True)
    (include / "hxtra.inc").write_text(
        patch_menu.hxtra_inc([dsp_meter], setting_ids.by_name(), getter=0x28e25c70),
        encoding="utf-8",
    )
    return m4asm.assemble_module(str(module), include=[str(include)])


def apply_meter(entry, segments, base, prior_edit_paint, occupied):
    code, labels = compile_meter(prior_edit_paint)

    def verify(address, expected):
        offset = patch_amp._e0_vaddr_to_foff(segments, address, len(expected))
        assert entry[offset:offset + len(expected)] == expected, hex(address)
        return offset

    def replace(address, expected, replacement, shared=False):
        offset = verify(address, expected)
        region = set(range(offset, offset + len(expected)))
        assert (region <= occupied) if shared else (not region.intersection(occupied))
        occupied.update(region)
        entry[offset:offset + len(expected)] = replacement

    verify(0x28e0db9c, struct.pack("<I", DSP_MODEL))
    verify(0x28d98c40, struct.pack("<I", SLOT_MODEL))
    verify(0x28e0f394, bytes.fromhex("00f587407c30"))
    verify(0x28e0f3c0, bytes.fromhex("4ff0540c0cfb01335969"))
    verify(0x28e00988, bytes.fromhex("4b294368"))
    verify(0x28e00506, bytes.fromhex("40f2dc53"))
    verify(0x28e07fa8, bytes.fromhex("42f22830"))
    replace(EDIT_PAINT_PTR, struct.pack("<I", prior_edit_paint),
            struct.pack("<I", (base + labels["xl_dsp_edit_paint"]) | 1),
            shared=prior_edit_paint != EDIT_PAINT)
    replace(BROWSER_PAINT_PTR, struct.pack("<I", BROWSER_PAINT),
            struct.pack("<I", (base + labels["xl_dsp_browser_paint"]) | 1))
    replace(NAMES_X, b"\x2c\x23", b"\x3c\x23")
    return code, labels
