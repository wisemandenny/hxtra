"""XL Global Settings menu extension. Keeps the native category strip and adds pages."""
import struct

import patch_amp
import patch_menu
import setting_ids
from features import bpm, breathing_line, dsp_meter, long_press, preset_color, tap_color, usb_monitor
from xl_virtual_settings import hold_tuner_settings, xl_feature_settings

CATEGORY_SHIFT = 0x5ab0
SITES = {
    name: (address + CATEGORY_SHIFT, reg, page, table,
           tbb + CATEGORY_SHIFT, exit_ + CATEGORY_SHIFT, generic + CATEGORY_SHIFT)
    for name, (address, reg, page, table, tbb, exit_, generic) in patch_menu.SITES.items()
}
PAGES = 0x28e41c2c
PAGE_REFS = (0x28dd444c, 0x28dd4eb8)
TEXT_ENTRY = 0x28d9a44c
CATEGORIES = {
    2: (0x28e41c44, (0x51, 0x49, 0x41, 0x5f, 0x60, 0x44, 0x45, 0x1b, 0x67), (long_press,)),
    5: (0x28e41bdc, (0x19, 0x1a, 0x17e), (bpm, breathing_line, tap_color)),
}


def apply_menu(entry, segments, cave, setting_targets, occupied, *, hold_tuner=False, usb_routing=False, preset_color_enabled=False, dsp_options=False):
    def read(address, count):
        offset = patch_amp._e0_vaddr_to_foff(segments, address, count)
        return bytes(entry[offset:offset + count])

    def replace(address, original, changed):
        assert len(original) == len(changed)
        assert read(address, len(original)) == original, hex(address)
        offset = patch_amp._e0_vaddr_to_foff(segments, address, len(original))
        region = set(range(offset, offset + len(original)))
        assert not occupied.intersection(region), hex(address)
        occupied.update(region)
        entry[offset:offset + len(changed)] = changed

    pages = list(struct.unpack("<6I", read(PAGES, 24)))
    assert pages == [3, 4, 3, 1, 4, 1]
    setting_ids_by_name = setting_ids.by_name()
    value_tables = {}
    category_tables = {}

    categories = dict(CATEGORIES)
    if preset_color_enabled:
        table, native, features = categories[5]
        categories[5] = (table, native, features + (preset_color,))
    if dsp_options:
        table, native, features = categories[5]
        categories[5] = (table, native, features + (dsp_meter,))
    if usb_routing:
        categories[0] = (0x28e41c00, (0x1f, 0x5e, 2, 3, 0x9a, 0x99, 0x9e, 0x9c, 0x17e), (usb_monitor,))
    for category, (table, native, features) in categories.items():
        assert read(table, len(native) * 2) == struct.pack(f"<{len(native)}H", *native)
        ids = list(native)
        while ids[-1] == patch_menu.EMPTY_SLOT:
            ids.pop()
        for feature in features:
            settings = hold_tuner_settings() if hold_tuner and feature is long_press else xl_feature_settings(feature)
            for setting in settings:
                pid = setting_ids_by_name[f"{feature.__name__.split('.')[-1]}.{setting.key}"]
                ids.append(pid)
                value_tables[pid] = (
                    cave.add(b"".join(patch_menu.padded(value) for value in setting.values)),
                    setting.max,
                    setting.default,
                )
        ids += [patch_menu.EMPTY_SLOT] * (-len(ids) % 3)
        pages[category] = len(ids) // 3
        category_tables[category] = cave.add(struct.pack(f"<{len(ids)}H", *ids))

    page_table = cave.add(struct.pack("<6I", *pages))
    for literal in PAGE_REFS:
        replace(literal, struct.pack("<I", PAGES), struct.pack("<I", page_table))
    for name, site in SITES.items():
        address, reg, _, _, _, _, _ = site
        original = read(address, 4)
        expected = bytes((5, 0x2b if reg == 3 else 0x2c))
        assert original[:2] == expected and original[3] == 0xd8, name
        target = cave.add(patch_menu.dispatch_cave(cave.next(), site, category_tables, setting_targets.get(name)))
        replace(address, original, patch_amp.thumb_bw(address, target))
    target = cave.add(patch_menu.text_cave(
        cave.next(), value_tables, continuation=TEXT_ENTRY + 4, copy_text=0x28e2af78
    ))
    replace(TEXT_ENTRY, bytes.fromhex("30b585b0"), patch_amp.thumb_bw(TEXT_ENTRY, target))
    return pages, category_tables
