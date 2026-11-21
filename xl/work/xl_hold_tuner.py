"""Assemble and install the XL hold-to-tuner prototype in an offline archive."""
import struct

from xl_virtual_settings import WORK
import m4asm
import patch_amp
import patch_menu
import setting_ids
from features import long_press

HANDLER = 0x28dd9c08
LISTENER = 0x28ddb358
MIDI_IN_FIRST = 0x28dbf358
PROLOGUE = bytes.fromhex("2de9f043")
ASSIGNMENT_CALLS = {
    0x28dbe73e: (0x28dadf08, "vfs_cc_text"),
    0x28dbed7a: (0x28dadf08, "vfs_cc_text"),
    0x28d926fc: (0x28dadf08, "vfs_cc_text"),
    0x28dbe74e: (0x28dc9510, "vfs_label_redraw"),
    0x28dbed8a: (0x28dc9510, "vfs_label_refresh"),
}


def compile_hold(snapshot_step):
    include = WORK / "xl-hold-include"
    include.mkdir(exist_ok=True)
    (include / "hxtra.inc").write_text(
        patch_menu.hxtra_inc([long_press], setting_ids.by_name(), getter=0x28e25c70)
        + f"\n.equ XL_STEP_SNAPSHOT, {snapshot_step | 1:#x}\n",
        encoding="utf-8",
    )
    return m4asm.assemble_module(str(WORK / "xl_hold_tuner.s"), include=[str(include)])


def apply_hold(entry, segments, base, occupied, snapshot_step):
    code, symbols = compile_hold(snapshot_step)
    for site, expected in (
        (0x28dd3fbe, "0520c4f794ff072002b0bde81040c4f7bebf"),
        (0x28dd54ca, "0820c3f70efdbde808400020c3f739bd"),
        (0x28dd96e6, "1cf0cdfd0499013100208029"),
        (0x28dd98f4, "1cf0c6fc049b013b"),
        (0x28dd9620, "96f84d10012914d0"),
        (0x28dd9686, "96f84d30012b00f0e181"),
        (0x28dd970c, "bff7e4fe00287ff40caf0120"),
        (0x28dd9a14, "bff778fd02283ad00220"),
        (0x28dd9ab8, "802be428902be428"),
        (0x28dd9300, "10b580f84d10"),
        (0x28dd99ac, "062302aa15214cf0b5f9"),
    ):
        raw = bytes.fromhex(expected)
        offset = patch_amp._e0_vaddr_to_foff(segments, site, len(raw))
        assert entry[offset:offset + len(raw)] == raw
    listener = patch_amp._e0_vaddr_to_foff(segments, LISTENER, 4)
    assert entry[listener:listener + 4] == struct.pack("<I", HANDLER | 1)
    offset = patch_amp._e0_vaddr_to_foff(segments, HANDLER, len(PROLOGUE))
    assert entry[offset:offset + 4] == PROLOGUE
    claimed = set(range(offset, offset + 4))
    assert not occupied.intersection(claimed)
    occupied.update(claimed)
    entry[offset:offset + 4] = patch_amp.thumb_bw(HANDLER, base + symbols["xl_hold_event"])
    for site, (stock, name) in ASSIGNMENT_CALLS.items():
        offset = patch_amp._e0_vaddr_to_foff(segments, site, 4)
        assert entry[offset:offset + 4] == patch_amp._thumb_bl(site, stock)
        claimed = set(range(offset, offset + 4))
        assert not occupied.intersection(claimed)
        occupied.update(claimed)
        entry[offset:offset + 4] = patch_amp._thumb_bl(site, base + symbols[name])
    offset = patch_amp._e0_vaddr_to_foff(segments, MIDI_IN_FIRST, 6)
    assert entry[offset:offset + 6] == bytes.fromhex("042225f0c5fe")
    region = set(range(offset, offset + 2))
    assert not occupied.intersection(region)
    occupied.update(region)
    entry[offset:offset + 2] = bytes.fromhex("1422")
    return code
