"""XL Metronome category, LEDs and assignment hooks."""
import struct

import image_store
import m4asm
import patch_amp
from features.metronome import UNKNOWN_STOCK
from xl_virtual_settings import WORK

CALLS = (
    (0x28ddba8a, "9df81020", "metronome_slot"),
    (0x28dbe3de, "9df84830", "metronome_cat_r3_48"),
    (0x28dbe6d0, "9df84830", "metronome_cat_r3_48"),
    (0x28dbed08, "9df82030", "metronome_cat_r3_20"),
    (0x28dbf22a, "9df82030", "metronome_cat_r3_20"),
    (0x28dbf2a4, "9df82030", "metronome_cat_r3_20"),
    (0x28dbf2f4, "9df82030", "metronome_cat_r3_20"),
    (0x28dd8ff6, "9df82830", "metronome_cat_r3_28"),
    (0x28de5114, "9df83830", "metronome_cat_r3_38"),
    (0x28de5fd4, "9df83420", "metronome_cat_r2_34"),
    (0x28de06c0, "34f0e4fe", "metronome_assign_cat"),
)
LED, CATEGORY = 0x28dbaf14, 0x28e2e9f4


def install(entry, segments, base, occupied, icons, pixels):
    code, symbols = m4asm.assemble_module(str(WORK / "xl_metronome.s"))

    def replace(site, old, new):
        offset = patch_amp._e0_vaddr_to_foff(segments, site, len(old))
        assert len(old) == len(new) and entry[offset:offset + len(old)] == old, hex(site)
        claimed = set(range(offset, offset + len(old)))
        assert not occupied.intersection(claimed)
        occupied.update(claimed)
        entry[offset:offset + len(old)] = new

    for site, expected, symbol in CALLS:
        replace(site, bytes.fromhex(expected), patch_amp._thumb_bl(site, base + symbols[symbol]))
    replace(LED, bytes.fromhex("04381228"), patch_amp.thumb_bw(LED, base + symbols["xl_metronome_led"]))

    icon = image_store.names(icons).index(b"Icon_Tempo")
    picture = image_store.image_at(icons, pixels, icon)
    pixels_off = image_store.scaled(pixels[picture.offset:picture.offset + picture.length], 0.39)
    source = image_store.record_at(icons, icon)
    record = bytearray(icons[source:source + image_store.RECORD])
    item_count, = struct.unpack_from("<I", pixels, 8)
    off_id, = struct.unpack_from("<I", icons, 24)
    for word in (2, 3, 9):
        struct.pack_into("<I", record, word * 4, item_count)
    icons = image_store.append_records(icons, [record])
    pixels = image_store.append_items(pixels, [pixels_off])
    name = b"Metronome"
    category = name.ljust(17, b"\0") + name.ljust(11, b"\0") + struct.pack("<4I", 0x3cceb5, 0x21665d, icon, off_id)
    replace(CATEGORY, UNKNOWN_STOCK, category)
    return code, icons, pixels
