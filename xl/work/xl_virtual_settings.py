"""Assemble the shared XL virtual settings engine for offline tests."""
from pathlib import Path
from dataclasses import replace
import re
import struct
import sys
from types import SimpleNamespace

WORK = Path(__file__).resolve().parent
REPO = WORK / "hxtra"
sys.path.insert(0, str(REPO / "tools"))
import m4asm
import patch_amp
import patch_menu
import setting_ids
from features import bpm, breathing_line, dsp_meter, long_press, preset_color, tap_color, tuner, usb_monitor

BASE = 0x28e54000
PROFILE = {
    "RECORDS": 0x28461654,
    "STORE_LOCK": 0x28461640,
    "DIRTY": 0x2846164d,
    "MUTEX_LOCK": 0x28e2ae81,
    "MUTEX_UNLOCK": 0x28e2aef9,
    "MEMCPY": 0x28e2af79,
    "SETTINGS_CTX": 0x28e0690d,
    "STEP_MATH": 0x28e047c9,
    "CHANGED": 0x28dd45e1,
    "CLASS_ABOVE": 0x28e26681,
    "CLASS_BELOW": 0x28e2668d,
    "TURN_STUB": 0x28dd4a47,
    "TURN_EXIT": 0x28dd4a3f,
    "CLICK_STUB": 0x28dd492b,
    "CLICK_DONE": 0x28dd495b,
}
SITES = {
    "get": (0x28e25c70, "b0f5bf7f"),
    "limits": (0x28e266ac, "cb2808b5"),
    "class": (0x28e2667c, "cb2805d9"),
    "label": (0x28d9a324, "f0b5bd28"),
}


def hold_tuner_settings():
    values = (b"Off", b"Tuner", b"VFS1", b"VFS2", b"VFS3", b"VFS4", b"VFS5", b"FS4", b"FS5")
    holds = tuple(replace(item, values=values, default=0) for item in long_press.HOLDS)
    functions = tuple(
        replace(item, label=f"Function\nVFS{index}".encode(),
                values=(b"Tuner", b"Stomp", b"SnpshtUp", b"SnpshtDn", b"GlobalEQ",
                        b"PresetUp", b"PresetDn", b"Bank Up", b"Bank Dn", b"AllBypas", b"TogglEXP",
                        b"FS Mode>", b"<FS Mode"))
        for index, item in enumerate(long_press.FUNCTIONS, start=1)
    )
    return holds + functions


DISPLAY_SETTINGS = {
    bpm: {
        "font": {"label": b"Size\nBPM"},
        "color": {"label": b"Color\nBPM"},
        "dot": {"label": b"Beat Dot", "default": 3},
    },
    breathing_line: {
        "color": {"label": b"Color\nLine"},
        "motion": {"label": b"Motion\nLine", "default": 0},
        "speed": {"label": b"Speed\nLine"},
    },
}


def xl_feature_settings(module):
    overrides = DISPLAY_SETTINGS.get(module, {})
    return tuple(replace(item, **overrides.get(item.key, {})) for item in module.SETTINGS)


def xl_display_include(module):
    profile = SimpleNamespace(__name__=module.__name__, SETTINGS=xl_feature_settings(module))
    return patch_menu.hxtra_inc([profile], setting_ids.by_name(), getter=0x28e25c70)


def compile_settings(entry, base=BASE, *, hold_tuner=False, usb_routing=False, active_preset_color=0, dsp_options=False):
    segments = patch_amp._parse_e0_segments(entry)
    assert segments[-1][3] == 0x28d92230

    def read(va, n):
        offset = patch_amp._e0_vaddr_to_foff(segments, va, n)
        return entry[offset:offset + n]

    for site, original in SITES.values():
        assert read(site, 4) == bytes.fromhex(original)
    for site, target in ((0x28e25d0c, PROFILE["STORE_LOCK"]), (0x28e25d18, PROFILE["RECORDS"]),
                         (0x28e25334, PROFILE["DIRTY"] - 5)):
        assert struct.unpack("<I", read(site, 4))[0] == target

    # Follow the actual switch-table entries. The range must still be
    # rejected from ordinary stock writes before it can store virtual bits.
    table = 0x28e25520
    offsets = [struct.unpack("<H", read(table + index * 2, 2))[0] for index in range(105, 117)]
    assert offsets == [0xa2] * 12
    assert read(table + 2 * offsets[0], 4) == bytes.fromhex("6ff01407")

    source = (REPO / "src" / "m4" / "virtual_settings.s").read_text(encoding="utf-8")
    for key, value in PROFILE.items():
        source, count = re.subn(rf"(?m)^\.equ {key}, [^@\r\n]+", f".equ {key}, {value:#x} ", source)
        assert count == 1, key

    if active_preset_color:
        source = f".equ XL_ACTIVE_COLOR, {active_preset_color:#x}\n" + source
        value = """    ldrh r2, [r0]
    cmp r2, #0xe2
    bne xl_global_value
    ldr r0, =XL_ACTIVE_COLOR
    ldrb r0, [r0]
    bx lr
xl_global_value:
"""
        store = """    ldrh r2, [r0]
    cmp r2, #0xe2
    bne xl_global_store
    ldr r2, =XL_ACTIVE_COLOR
    strb r1, [r2]
    bx lr
xl_global_store:
"""
        for label, insert in (("value", value), ("store", store)):
            position = source.index("\n", source.index(f"\n{label}:") + 1) + 1
            source = source[:position] + insert + source[position:]

    for name in ("get", "limits", "label"):
        site, prologue = SITES[name]
        words = struct.unpack("<2H", bytes.fromhex(prologue))
        source += (
            f"\n.balign 4\n.thumb_func\nxl_stock_{name}:\n"
            f"    .hword {words[0]:#x}, {words[1]:#x}\n"
            f"    ldr r12, ={(site + 4) | 1:#x}\n    bx r12\n    .ltorg\n"
        )
    destination = WORK / "xl_virtual_settings.s"
    destination.write_text(source, encoding="utf-8")

    ids = setting_ids.by_name()
    modules = (bpm, breathing_line, long_press, tap_color, tuner)
    if usb_routing:
        modules += (usb_monitor,)
    if active_preset_color:
        modules += (preset_color,)
    if dsp_options:
        modules += (dsp_meter,)
    settings = sorted(
        (ids[f"{module.__name__.split('.')[-1]}.{item.key}"], item)
        for module in modules
        for item in (hold_tuner_settings() if hold_tuner and module is long_press else xl_feature_settings(module))
    )
    packing = setting_ids.packing()
    include = WORK / "xl-settings-include"
    include.mkdir(exist_ok=True)

    def assemble(stock):
        (include / "virtual.inc").write_text(
            patch_menu.virtual_inc(settings, packing, stock), encoding="utf-8"
        )
        return m4asm.assemble_module(str(destination), include=[str(include)])

    names = ("get", "limits", "label")
    _, initial = assemble({name: base + 4 * i for i, name in enumerate(names)})
    code, symbols = assemble({name: base + initial[f"xl_stock_{name}"] for name in names})
    assert all(initial[f"xl_stock_{name}"] == symbols[f"xl_stock_{name}"] for name in names)
    return code, symbols, settings


if __name__ == "__main__":
    baseline = (WORK / "nam-xl-baseline.l6ia").read_bytes()
    entry = patch_amp.get_entry_swapped(baseline, 0)
    code, symbols, settings = compile_settings(entry)
    print(f"Assembled {len(settings)} XL virtual settings ({len(code)} bytes).")
