"""Install HXtra Tap Command into the XL 3.80 Command Center."""
import struct

import m4asm
import patch_amp
from xl_virtual_settings import WORK

CALLS = (
    (0x28dd911a, 0x28debb5c, "tc_fire"),
    (0x28de0aba, 0x28dde6f0, "tc_node"),
    (0x28de0c52, 0x28dde6f0, "tc_node"),
    (0x28dc040a, 0x28deb664, "tc_choice"),
    (0x28dc057a, 0x28deb664, "tc_choice"),
    (0x28dc0ab6, 0x28deb664, "tc_choice"),
    (0x28dc0770, 0x28dec4a0, "tc_step"),
    (0x28d9ed6e, 0x28d98c0c, "tc_running"),
    (0x28d9ed80, 0x28d98c0c, "tc_running"),
    (0x28d9edc6, 0x28d98c0c, "tc_on"),
    (0x28d9ede4, 0x28dbb36c, "tc_sync_on"),
    (0x28d9edee, 0x28dbb36c, "tc_off"),
    (0x28dd89d6, 0x28dd8638, "tc_refresh"),
    (0x28ddafa6, 0x28d98c0c, "tc_setting"),
)


def compile_tap_command(tap_targets):
    include = WORK / "xl-tap-command-include"
    include.mkdir(exist_ok=True)
    (include / "tap.inc").write_text(
        f".equ TAP_LED, {tap_targets[0]:#x}\n.equ TAP_LED_AGAIN, {tap_targets[1]:#x}\n",
        encoding="ascii",
    )
    return m4asm.assemble_module(str(WORK / "xl_tap_command.s"), include=[str(include)])


def install(entry, segments, base, occupied, tap_targets):
    def read(address, size):
        offset = patch_amp._e0_vaddr_to_foff(segments, address, size)
        return bytes(entry[offset:offset + size])

    assert read(0x28d98c10, 4) == struct.pack("<I", 0x28128d68)
    assert read(0x28d98c28, 4) == struct.pack("<I", 0x28125340)
    assert read(0x28e438d9, 9) == bytes((1, 2, 4, 5, 6, 12, 14, 15, 16))
    code, symbols = compile_tap_command(tap_targets)
    edits = [
        (site, patch_amp._thumb_bl(site, target), patch_amp._thumb_bl(site, base + symbols[label]))
        for site, target, label in CALLS
    ]
    edits += [(0x28e42d18 + 4 * slot, struct.pack("<I", 10), struct.pack("<I", 11))
              for slot in range(6, 14)]
    edits += [(0x28e42da0, b"CV Out\0\0", b"Tap\0\0\0\0\0"), (0x28e42e11, b"\x02", b"\x01")]
    for site, expected, replacement in edits:
        start = patch_amp._e0_vaddr_to_foff(segments, site, len(expected))
        assert bytes(entry[start:start + len(expected)]) == expected, hex(site)
        region = set(range(start, start + len(expected)))
        assert not occupied.intersection(region), hex(site)
        occupied.update(region)
        entry[start:start + len(expected)] = replacement
    return code
