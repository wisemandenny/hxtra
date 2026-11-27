"""Optional illustrations for Edit and the model browser (src/m4/model_pictures.s)."""
import json
from pathlib import Path
import struct

from features import Input, Setting

FLAG = 'HX_MODEL_PICTURES'
ARTWORK = 'HX_MODEL_PICTURES_ART'
ARTWORK_FILE = 'model-pictures.json'
INPUTS = (Input(ARTWORK, path=True),)
MENU = 'Displays'
ORDER = 120                         # paint after GR and DSP, so occupied pixels are visible
SETTINGS = (Setting('enabled', b'Pictures\nModel', (b'On', b'Off'), default=1),)
MODULE = 'src/m4/model_pictures.s'

EDIT_PAINT_LIT, EDIT_PAINT = 0x28d96da0, 0x28dc27f9
PARAM_PAINT_LIT, PARAM_PAINT = 0x28d96e38, 0x28d947c9
BROWSER_PAINT_LIT, BROWSER_PAINT = 0x28d96df0, 0x28dc4dd1

WIDTH, EDIT_HEIGHT, BROWSER_HEIGHT = 74, 23, 32
IMAGE_TEMPLATE = 0x43              # a stock 16-bit image record
ENTRY8_LIMIT = 8 * 1024 * 1024


def artwork(path):
    """Read prepared RGB565 images. Each pair may serve several internal model names."""
    if path is None:
        return {}
    try:
        data = json.loads(Path(path).read_bytes())
        if data['version'] != 1 or not isinstance(data['pictures'], list):
            raise ValueError('expected a version 1 bundle')
        pictures = {}
        for record in data['pictures']:
            edit, browser = (bytes.fromhex(record[key]) for key in ('edit', 'browser'))
            if len(edit) != 2 * WIDTH * EDIT_HEIGHT or len(browser) != 2 * WIDTH * BROWSER_HEIGHT:
                raise ValueError('wrong picture dimensions')
            names = record['models']
            if not isinstance(names, list) or not names or any(not isinstance(n, str) or not n for n in names):
                raise ValueError('expected a list of internal model names')
            for name in names:
                if name in pictures:
                    raise ValueError(f'duplicate model {name}')
                pictures[name] = edit, browser
        return pictures
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise SystemExit(f'model_pictures: {path}: {exc}') from exc


def model_rows(p):
    """(internal name, model index, preset ID) from Entries 3 and 0, including NAM if built."""
    import patch_amp as pa

    device = pa.e0_device(p.segs)
    table = p.u32(device.TAB1_BASE_PTRS[0])
    _, count = pa._decode_thumb_movw(p.read(device.TAB1_CNT_INSN, 4))
    pids = dict(struct.unpack_from('<IH', p.read(table + 12 * i, 6)) for i in range(count))
    return [(m['name'], index, pids[index]) for m in pa.parse_entry3_full(p.load(3))['models']
            if (index := m['words'][2]) in pids]


def picture_rows(models, pictures, add_image):
    """(model index, preset ID, Edit image, browser image), sharing identical image pairs."""
    resources, rows, seen_indices, seen_pids = {}, [], set(), set()
    for name, index, pid in sorted(models, key=lambda row: row[1:]):
        if name not in pictures:
            continue
        if index in seen_indices or pid in seen_pids or not (0 <= index < 0xffff and 0 <= pid < 0xffff):
            raise SystemExit(f'model_pictures: invalid or duplicate ID for {name}')
        seen_indices.add(index)
        seen_pids.add(pid)
        pair = pictures[name]
        if pair not in resources:
            resources[pair] = tuple(add_image(IMAGE_TEMPLATE, WIDTH, h, pixels)
                                    for h, pixels in zip((EDIT_HEIGHT, BROWSER_HEIGHT), pair))
        rows.append((index, pid, *resources[pair]))
    return rows


def inc(rows):
    table = ''.join(f'    .hword {index}, {pid}, {edit}, {browser}\n' for index, pid, edit, browser in rows)
    return {'model_pictures.inc':
            f'.equ PICTURE_COUNT, {len(rows)}\n.equ PICTURE_WIDTH, {WIDTH}\n'
            f'.equ EDIT_HEIGHT, {EDIT_HEIGHT}\n.equ BROWSER_HEIGHT, {BROWSER_HEIGHT}\n'
            f'.macro PICTURE_TABLE\n{table}.endm\n'}


def apply(p):
    pictures = artwork(p.input(ARTWORK))
    if not pictures:
        raise SystemExit(f'model_pictures: set {ARTWORK} to a prepared picture bundle')
    rows = picture_rows(model_rows(p), pictures, p.add_image)
    if not rows:
        raise SystemExit('model_pictures: the input has no pictures for this firmware')
    # The engine appends aligned items and a replacement item table to Entry 8.
    entry = p.entry(8)
    original_items = struct.unpack_from('<I', entry.data, 8)[0]
    size = ((len(entry.data) + 3) & ~3) + sum((len(item) + 3) & ~3 for item in entry.items)
    size += 8 * (original_items + len(entry.items))
    if size > ENTRY8_LIMIT:
        raise SystemExit('model_pictures: the image store exceeds its 8 MiB boot read window')
    m = p.module(MODULE, inc=inc(rows))
    p.chain_ptr(EDIT_PAINT_LIT, EDIT_PAINT, before=m['model_pictures_erase'], after=m['model_pictures_edit'])
    p.chain_ptr(PARAM_PAINT_LIT, PARAM_PAINT, before=m['model_pictures_erase'], after=m['model_pictures_params'])
    p.chain_ptr(BROWSER_PAINT_LIT, BROWSER_PAINT, before=m['model_pictures_erase'], after=m['model_pictures_browser'])
