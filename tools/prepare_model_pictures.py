#!/usr/bin/env python3
"""Prepare a local Model Pictures input from pinned Line 6 photos (requires Pillow)."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import struct
from urllib.request import Request, urlopen

import image_store
import patch_amp as pa
from features import model_pictures as feature

CATALOG = Path(__file__).with_name('model_pictures_art.json')
MAX_DOWNLOAD = 4 * 1024 * 1024
ALIASES = {
    "1x15 Tuck n' Go": '1x15 Ampeg B-15',
    '2x12 Mandarin': '2x12 Mandarin 30',
    '2x15 US Dripman': '2x15 Dripman',
    '4x12 1960A T75': '4x12 1960 T75',
    '4x12 Blckbck H30': '4x12 Blackback 30',
    '4x12 Mandarin': '4x12 Mandarin EM',
    '8x10 SV Beast': '8x10 Ampeg SVT E',
    'Alpaca Rouge': 'Alpaca Rogue',
    'GrammaticoLG Jmp': 'GrammaticoLG Jump',
    'HX Room': 'Room',
    'Infinite Sustain': 'Poly Sustain',
    'Line 6 Bigger': 'Line 6 Badonk',
    'Low Res': 'Lo Res',
    'Mandarin Bass 200': 'Mandarin 200',
    'Pillars': 'Pillars OD',
    'ShuflMon': 'Glitch Delay',
    'Tremolo': 'Tremolo/Autopan',
    'US Dripman Norm': 'US Dripman Nrm',
    'US Super Norm': 'US Super Nrm',
    'Wringer': 'Wringer Fuzz',
}


def normalized(name):
    return re.sub(r'[^a-z0-9]', '', name.casefold())



def fetch_artwork(record, cache):
    """Use a verified cache file or fetch the fixed URL and check its SHA-256."""
    path = cache / record['source_file']
    expected = record['sha256']
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
        return path
    request = Request(record['source_url'], headers={'User-Agent': 'HXtra Model Pictures'})
    with urlopen(request, timeout=30) as stream:
        data = stream.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f'Artwork size or SHA-256 changed: {record["source_url"]}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def catalog_matches(models, catalog):
    """Match stock display names against the pinned catalog, keyed by internal name."""
    by_name = {}
    for row in catalog:
        by_name.setdefault(normalized(row['name']), []).append(row)
    for model in models:
        name, display = model['name'], model['displayName']
        if not display or name.startswith(('HD2_AppDSPFlow', 'HelixStomp_AppDSPFlow')):
            continue
        if name.startswith('HD2_Looper'):
            display = '1 Switch Looper' if 'OneSwitch' in name else '6 Switch Looper'
        rows = by_name.get(normalized(ALIASES.get(display, display)), [])
        if name.startswith('HD2_Cab'):
            rows = [r for r in rows if r['category'] == 'CAB MODELS']
        elif name.startswith(('HD2_Amp', 'HD2_Preamp')):
            rows = [r for r in rows if r['category'] == 'AMP MODELS']
        else:
            rows = [r for r in rows if r['category'] not in ('AMP MODELS', 'CAB MODELS')]
        if rows:
            # The Line 6 table lists the current effects before their Legacy variants.
            legacy = name.startswith(('HD2_DL4', 'HD2_Cab')) and not name.startswith('HD2_CabMicIr')
            yield name, rows[-1 if legacy else 0]


def tile(image, height):
    """A centred, bottom-first RGB565 tile. Zero is transparent."""
    from PIL import Image

    width = feature.WIDTH
    image = image.copy()
    image.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (width, height))
    canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
    return b''.join(struct.pack('<H', image_store.pixel(r*a//255, g*a//255, b*a//255))
                    for x in range(width) for y in range(height - 1, -1, -1)
                    for r, g, b, a in (canvas.getpixel((x, y)),)).hex()


def unmatted(image):
    """Clear the nearly white background connected to the outside of a catalog photo."""
    from collections import deque

    image = image.convert('RGBA')
    if image.getchannel('A').getextrema() != (255, 255):
        return image.crop(image.getbbox()) if image.getbbox() else image
    w, h = image.size
    pixels = image.load()
    edge = deque([(x, y) for x in range(w) for y in (0, h - 1)] +
                 [(x, y) for x in (0, w - 1) for y in range(h)])
    while edge:
        x, y = edge.popleft()
        r, g, b, a = pixels[x, y]
        if not a or min(r, g, b) < 232 or max(r, g, b) - min(r, g, b) > 15:
            continue
        pixels[x, y] = (0, 0, 0, 0)
        edge.extend((nx, ny) for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)) if 0 <= nx < w and 0 <= ny < h)
    box = image.getbbox()
    return image.crop(box) if box else image


def prepare(stock, output, cache):
    from PIL import Image

    data, _ = pa.load_l6ia_from_any(str(stock))
    models = pa.parse_entry3_full(pa.get_entry_swapped(data, 3))['models']
    catalog = json.loads(CATALOG.read_bytes())['models']
    groups = {}
    for name, record in catalog_matches(models, catalog):
        _, names = groups.setdefault(record['sha256'], (record, []))
        names.append(name)
    pictures = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        paths = pool.map(lambda entry: fetch_artwork(entry[0], cache), groups.values())
        for (_, names), path in zip(groups.values(), paths):
            with Image.open(path) as source:
                image = unmatted(source)
            pictures.append({'models': sorted(set(names)), 'edit': tile(image, feature.EDIT_HEIGHT),
                             'browser': tile(image, feature.BROWSER_HEIGHT)})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'version': 1, 'pictures': pictures}, separators=(',', ':')) + '\n')
    print(f'Prepared {len(pictures)} pictures in {output}')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stock', type=Path, help='stock HX Stomp 3.80.0 HXF')
    ap.add_argument('-o', '--output', type=Path, default=Path('build') / feature.ARTWORK_FILE)
    ap.add_argument('--cache', type=Path, default=Path('build/model-pictures-art'))
    args = ap.parse_args()
    prepare(args.stock, args.output, args.cache)


if __name__ == '__main__':
    main()
