"""Color feature settings and added block parameters on the XL."""
import struct

import m4asm
import patch_amp
import setting_ids
from xl_virtual_settings import WORK

CALLS = ((0x28dd4412, 0x28dc9594, "label_colour"), (0x28dc28f0, 0x28dc9510, "label_param"))


def model_counts(archive):
    entry = patch_amp.get_entry_swapped(archive, 3)
    return {model["name"]: len(model["params"])
            for model in patch_amp.parse_entry3_full(entry)["models"]}


def install(entry, segments, base, occupied, archive, previous_counts):
    def view(address, size):
        offset = patch_amp._e0_vaddr_to_foff(segments, address, size)
        return offset, bytes(entry[offset:offset + size])

    profile = patch_amp.e0_device(segments)
    _, pointer = view(profile.TAB1_BASE_PTRS[0], 4)
    table = struct.unpack("<I", pointer)[0]
    _, count_insn = view(profile.TAB1_CNT_INSN, 4)
    _, count = patch_amp._decode_thumb_movw(count_insn)
    _, table_data = view(table, count * 12)
    ids = {name: pid for name, pid, _, _ in struct.iter_unpack("<IHHI", table_data)}
    models = patch_amp.parse_entry3_full(patch_amp.get_entry_swapped(archive, 3))["models"]
    params = []
    for model in models:
        name, name_index = model["name"], model["words"][2]
        original = 0 if name in ("HD2_DistNAMLite", "HD2_ClickMetronomeMono") else previous_counts.get(name)
        if original is not None and original < len(model["params"]) and name_index in ids:
            params.append((ids[name_index], original))
    assert any(first == 0 for _, first in params)

    source = (WORK / "xl-label-color-upstream.s").read_text(encoding="ascii")
    source = source.replace("0x28dc6455", "0x28dc9595").replace("0x28dc63d1", "0x28dc9511")
    module = WORK / "xl_label_color.s"
    module.write_text(source, encoding="ascii")
    include = WORK / "xl-label-color-include"
    include.mkdir(exist_ok=True)
    lines = [f".equ VIRTUAL_FIRST, {setting_ids.VIRTUAL_IDS.start}",
             f".equ VIRTUAL_COUNT, {len(setting_ids.VIRTUAL_IDS)}",
             ".equ TEAL, 0x3cceb5", f".equ PARAMS, {len(params)}", ".macro PARAM_TABLE"]
    for pid, first in params:
        lines += [f"    .hword {pid}", f"    .byte {first}, 0"]
    (include / "label.inc").write_text("\n".join(lines + [".endm", ""]), encoding="ascii")
    code, symbols = m4asm.assemble_module(str(module), include=[str(include)])
    for site, stock, label in CALLS:
        offset, original = view(site, 4)
        assert original == patch_amp._thumb_bl(site, stock)
        region = set(range(offset, offset + 4))
        assert not occupied.intersection(region)
        occupied.update(region)
        entry[offset:offset + 4] = patch_amp._thumb_bl(site, base + symbols[label])
    print(f"Verified XL teal label hooks for {len(params)} model rows.")
    return code
