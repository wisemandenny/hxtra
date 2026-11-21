"""HXtra tuner pages and TAP activation port for stock XL 3.80."""
import re

import m4asm
import patch_amp
import patch_menu
import setting_ids
from features import tuner
from xl_virtual_settings import REPO, WORK

ROUTINES = {
    "GUARD": 0x28d98ce5,
    "REQUEST_TUNER": 0x28d9919d,
    "TAP_CORE": 0x28d9eed5,
    "TURN_FN_CONT": 0x28d93e91,
    "RESET_RET": 0x28d93f27,
    "PAINT": 0x28dd2515,
    "PAINT_TBH": 0x28dd2547,
    "PAINT_END": 0x28dd2619,
    "STEPS": 0x28e043fd,
    "SHOW": 0x28dc96d9,
    "VALUE_TEXT": 0x28dc968d,
    "POSITION": 0x28dc95cd,
    "LABEL": 0x28dc9511,
    "NEXT_CONT": 0x28d93f3d,
    "PREV_CONT": 0x28d93f7f,
    "STORE_CONT": 0x28d93f87,
    "DOTS_CONT": 0x28dd280b,
}
BRANCHES = (
    (0x28dd9676, "c5f72dbc", "tuner_tap"),
    (0x28d93e8c, "f8b54678", "tuner_turn_hook"),
    (0x28d93fb2, "91f87430", "tuner_reset2"),
    (0x28d93ff6, "91f87430", "tuner_reset1"),
    (0x28d9400c, "91f87430", "tuner_reset0"),
    (0x28dd2542, "032b68d8", "tuner_switch"),
    (0x28d93f38, "91f87430", "tuner_next_page"),
    (0x28d93f7a, "91f87430", "tuner_prev_page"),
    (0x28d93f82, "01252046", "tuner_store_page"),
    (0x28dd2806, "94f87400", "tuner_dots"),
)
IMMEDIATES = (
    (0x28d93f3c, "022b", "032b"),
    (0x28dd2520, "032b", "042b"),
    (0x28dd2a88, "032b", "042b"),
    (0x28dd2800, "0420", "0520"),
)


def compile_tuner(virtual_set, *, teal_labels=False):
    source = (REPO / "src" / "m4" / "tuner.s").read_text(encoding="utf-8")
    for key, value in ROUTINES.items():
        source, count = re.subn(rf"(?m)^\.equ {key}, [^@\r\n]+", f".equ {key}, {value:#x} ", source)
        assert count == 1, key
    for knob, address in ((0, 0x28d94011), (1, 0x28d93ffb), (2, 0x28d93fb7)):
        source, count = re.subn(rf"(?m)^RESET {knob}, 0x[0-9a-f]+", f"RESET {knob}, {address:#x}", source)
        assert count == 1, knob
    for original, _ in tuner.KNOB_COLOURS:
        source = source.replace(f"{original | 1:#x}", f"{(original + 0x3140) | 1:#x}")
    if teal_labels:
        source = source.replace(".word 0x28dc9595, 0xffffff", ".word 0x28dc9595, 0x3cceb5")
    module = WORK / "xl_tuner.s"
    module.write_text(source, encoding="utf-8")
    include = WORK / "xl-tuner-include"
    include.mkdir(exist_ok=True)
    (include / "hxtra.inc").write_text(
        patch_menu.hxtra_inc(
            [tuner], setting_ids.by_name(), virtual_set,
            getter=0x28e25c70, context=0x28e0690c, setter_fn=0x28e25d20,
        ), encoding="utf-8",
    )
    return m4asm.assemble_module(str(module), include=[str(include)])


def apply_tuner(entry, segments, base, virtual_set, occupied, *, teal_labels=False):
    code, symbols = compile_tuner(virtual_set, teal_labels=teal_labels)

    def replace(site, expected, data):
        offset = patch_amp._e0_vaddr_to_foff(segments, site, len(data))
        expected = bytes.fromhex(expected)
        assert len(expected) == len(data) and entry[offset:offset + len(data)] == expected, hex(site)
        region = set(range(offset, offset + len(data)))
        assert not occupied.intersection(region), hex(site)
        occupied.update(region)
        entry[offset:offset + len(data)] = data

    assert patch_amp.thumb_bw(BRANCHES[0][0], ROUTINES["TAP_CORE"] & ~1).hex() == BRANCHES[0][1]
    for site, expected, label in BRANCHES:
        replace(site, expected, patch_amp.thumb_bw(site, base + symbols[label]))
    for site, expected, value in IMMEDIATES:
        replace(site, expected, bytes.fromhex(value))
    return code
