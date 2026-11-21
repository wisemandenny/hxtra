"""Create XL Play snapshot 5/6 icons using the stock camera styles and LCD font."""
import io
import struct

from PIL import Image
import numpy as np
import image_store as store

ICON_STYLES = (
    ((0x13d, 0x165), 19017, 65535),
    ((0x05, 0x139), 19017, 65535),
    ((0x31, 0x41), 65535, 0),
    ((0xb1, 0x1cc), 65535, 0),
    ((0x1a0, 0x71), 0, 65535),
    ((0x156, 0x105), 0, 65535),
)
FIRST_NEW_INDEX = 577


def add_play_icons(e7, e8):
    assert struct.unpack_from("<I", e7, 24)[0] == FIRST_NEW_INDEX
    assert len(store.names(e7)) == FIRST_NEW_INDEX
    _, table = store.font(e7, b"hx28_boldFont")
    items = []
    records = []
    preview = Image.new("RGB", (242, 70 * len(ICON_STYLES)))

    for style, (pair, background, ink) in enumerate(ICON_STYLES):
        images = [store.image_at(e7, e8, index) for index in pair]
        first, second = images
        assert (first.width, first.height, first.bpp) == (second.width, second.height, 16)
        pixels = [
            np.frombuffer(e8[icon.offset:icon.offset + icon.length], dtype="<u2").reshape(icon.width, icon.height).T[::-1]
            for icon in images
        ]
        rows, columns = np.where(pixels[0] != pixels[1])
        top, bottom = rows.min(), rows.max() + 1
        left, right = columns.min(), columns.max() + 1
        assert (bottom - top, right - left) == (21, 13)
        assert set(np.unique(pixels[0][top:bottom, left:right])) == {background, ink}

        for position, digit in enumerate("56"):
            height, width, item = store.glyph(e7, table, ord(digit))
            start, length = store.item(e8, item)
            glyph = np.frombuffer(e8[start:start+length], dtype="<u2").reshape(width, height).T[::-1]
            ys, xs = np.where(glyph != 0)
            mask = glyph[ys.min():ys.max()+1, xs.min():xs.max()+1] != 0
            assert mask.shape[0] <= 21 and mask.shape[1] <= 15
            icon = pixels[0].copy()
            icon[top:bottom, left:right] = background
            y = top + (bottom - top - mask.shape[0]) // 2
            x = left + (right - left - mask.shape[1]) // 2
            area = icon[y:y+mask.shape[0], x:x+mask.shape[1]]
            assert np.all(area == background)
            area[mask] = ink

            record_offset = store.record_at(e7, pair[0])
            record = bytearray(e7[record_offset:record_offset + store.RECORD])
            item = struct.unpack_from("<I", e8, 8)[0] + len(items)
            for word in (2, 3, 9):
                struct.pack_into("<I", record, word * 4, item)
            records.append(bytes(record))
            items.append(icon[::-1].T.astype("<u2").tobytes())
            rgb = np.stack(((icon & 31) * 255 // 31, ((icon >> 5) & 63) * 255 // 63, (icon >> 11) * 255 // 31), axis=2)
            preview.paste(Image.fromarray(rgb.astype("uint8")), (121 * position, 70 * style))

    out = io.BytesIO()
    preview.save(out, format="PNG")
    return store.append_records(e7, records), store.append_items(e8, items), out.getvalue()
