"""Preset Mode colors for selected and unselected XL rings and Play tiles."""
import struct

import image_store
import m4asm
import patch_amp
from features import tap_color
from xl_virtual_settings import WORK
from xl_bpm import PLAY_PAINT, PLAY_PAINT_POINTER

RING = 0x28dd8c02
ICON_CALLS = (0x28dcb93a, 0x28dcba24)
STOCK_ICONS = (0x196, 0x221)
DIM_RING = 0x28dd8bf2
DIM_ICON_CALLS = (0x28dcb7ca, 0x28dcb90c)
DIM_STOCK_ICONS = (0x1ae, 0x152)


def install(entry, segments, base, occupied, index, pixels, active_color):
    def offset(address, size=4):
        return patch_amp._e0_vaddr_to_foff(segments, address, size)

    def read_word(address):
        return struct.unpack_from("<I", entry, offset(address))[0]

    assert read_word(0x28dd8cec) == 0x28e42bcc
    assert read_word(0x28e42bcc) == tap_color.LEDS[0]
    assert entry[offset(0x28dd8bfc):offset(0x28dd8bfc) + 4] == bytes.fromhex("daf80010")
    table = offset(0x28dd8a28, 20)
    assert 0x28dd8a28 + 2 * entry[table + 12] == 0x28dd8a3c
    assert image_store.names(index)[0x196] == b"Play_PresetSel"
    assert image_store.names(index)[0x221] == b"Play_PresetHXSelMedium"
    records = []
    items = []
    first_record = struct.unpack_from("<I", index, 24)[0]
    first_item = struct.unpack_from("<I", pixels, 8)[0]
    rows = []
    dim_rows = []
    for icon, label in zip(DIM_STOCK_ICONS, (b"Play_Preset", b"Play_PresetHXMedium")):
        assert image_store.names(index)[icon] == label
    for icon in (*STOCK_ICONS, *DIM_STOCK_ICONS):
        source = image_store.image_at(index, pixels, icon)
        assert source.bpp == 16 and source.length == 2 * source.width * source.height
        original = struct.unpack_from(f"<{source.width * source.height}H", pixels, source.offset)
        first = first_record + len(records)
        if icon in STOCK_ICONS:
            assert set(original) == {0, 19017, 33840, 48631, 61309, 63422, 65535}
            rows.append((icon, *range(first, first + 9)))
            colors = tap_color.TEXTS[1:]
        else:
            assert set(original) == {0, 6339, 10565, 14791, 19017}
            dim_rows.extend(range(first, first + 10))
            colors = (*tap_color.TEXTS[:9], 0xffffff)
        for color in colors:
            red, green, blue = (color >> 16) & 255, (color >> 8) & 255, color & 255
            palette = {
                shade: ((shade & 31) * red // 255)
                | ((((shade >> 5) & 63) * green // 255) << 5)
                | ((((shade >> 11) & 31) * blue // 255) << 11)
                for shade in set(original)
            }
            items.append(struct.pack(f"<{len(original)}H", *(palette[shade] for shade in original)))
            start = image_store.record_at(index, icon)
            record = bytearray(index[start:start + image_store.RECORD])
            for word in (2, 3, 9):
                struct.pack_into("<I", record, word * 4, first_item + len(records))
            records.append(record)

    prior_play = read_word(PLAY_PAINT_POINTER)
    assert prior_play == PLAY_PAINT or (0x28e50000 <= prior_play < base and prior_play & 1)
    assert read_word(0x28dbb3f0) == 0x281f561c
    source = f".equ ACTIVE_COLOR, {active_color:#x}\n.equ PRIOR_PLAY, {prior_play:#x}\n" + """
.syntax unified
.cpu cortex-m4
.thumb
.thumb_func
.global preset_ring
preset_ring:
    push {r0, r1, r4, lr}
    bl color
    cbz r0, ring_default
    adr r1, ring_colors
    ldr r1, [r1, r0, lsl #2]
    str r1, [sp, #4]
ring_default:
    pop {r0, r1, r4, lr}
    ldr r12, =0x28dbb309
    bx r12

.thumb_func
.global preset_icon
preset_icon:
    push {r0, r1, r4, lr}
    bl color
    adr r1, icons
    ldr r2, [sp, #4]
    movw r3, #0x221
    cmp r2, r3
    it eq
    addeq r1, #20
    ldrh.w r1, [r1, r0, lsl #1]
    str r1, [sp, #4]
    pop {r0, r1, r4, lr}
    ldr r12, =0x28e2ade1
    bx r12

.thumb_func
color:
    ldr r0, =ACTIVE_COLOR
    ldrb r0, [r0]
    subs r0, #1
    cmp r0, #9
    it ls
    bxls lr
    push {r4, lr}
    sub sp, #8
    movs r0, #0
    str r0, [sp, #4]
    movs r0, #0xe1
    mov r1, sp
    ldr r3, =0x28e25c71
    blx r3
    cmp r0, #0
    ite ge
    ldrge r0, [sp, #4]
    movlt r0, #0
    cmp r0, #9
    it hi
    movhi r0, #0
    add sp, #8
    pop {r4, pc}
.ltorg
.balign 4
ring_colors:
    .word """ + ", ".join(map(str, tap_color.LEDS)) + """
icons:
    .hword """ + ", ".join(str(value) for row in rows for value in row) + "\n"
    dim_source = (WORK / "xl_preset_dim.s").read_text(encoding="ascii")
    source += dim_source.replace("XL_DIM_ICON_IDS", ".hword " + ", ".join(map(str, dim_rows)))
    assembly = WORK / "xl_preset_color.s"
    assembly.write_text(source, encoding="ascii")
    code, symbols = m4asm.assemble_module(str(assembly))
    calls = ((RING, 0x28dbb308, "preset_ring"),
             *((site, 0x28e2ade0, "preset_icon") for site in ICON_CALLS),
             *((site, 0x28e2ade0, "preset_icon_dim") for site in DIM_ICON_CALLS))
    edits = [(site, patch_amp._thumb_bl(site, target), patch_amp._thumb_bl(site, base + symbols[symbol]))
             for site, target, symbol in calls]
    edits += [
        (DIM_RING, bytes.fromhex("7ff42eaf"), patch_amp._thumb_bl(DIM_RING, base + symbols["preset_ring_dim"])),
        (0x28dcb7b2, bytes.fromhex("00f02d81"), bytes.fromhex("00bf00bf")),
    ]
    for site, original, replacement in edits:
        pos = offset(site)
        assert entry[pos:pos + 4] == original
        region = set(range(pos, pos + 4))
        assert not occupied.intersection(region)
        occupied.update(region)
        entry[pos:pos + 4] = replacement
    pos = offset(PLAY_PAINT_POINTER)
    region = set(range(pos, pos + 4))
    assert (occupied.intersection(region) == region) == (prior_play != PLAY_PAINT)
    occupied.update(region)
    struct.pack_into("<I", entry, pos, (base + symbols["preset_color_paint"]) | 1)
    return code, image_store.append_records(index, records), image_store.append_items(pixels, items)
