"""Reference renderer: no firmware image or hardware required."""
import struct
from pathlib import Path
import pytest
import m4asm

ROOT = Path(__file__).resolve().parent.parent
MODULE = 0x28a80000
FB = 0x28a00000
PATTERN = struct.pack('<H', 0x1234) * (320 * 240)

@pytest.fixture
def assembled():
    if not Path(m4asm.CLANG).exists():
        pytest.skip('no clang')
    return m4asm.assemble_module(str(ROOT / 'src/m4/northern_gr_display.s'))


def test_tables_and_geometry(assembled):
    code, sym = assembled
    colours = struct.unpack_from('<24H', code, sym['colours'])
    glyphs = struct.unpack_from('<14H', code, sym['glyphs'])
    assert len(set(colours)) == 24 and all(colours)
    assert len(set(glyphs[:10])) == 10 and glyphs[11] == 0
    rects = [(8 + 10*j + 2*sum(j >= i for i in (3, 6, 12, 18)), 232, 8, 8) for j in range(24)]
    rects += [(264 + 8*c + 2*(p % 3), 238 - 2*(p // 3), 2, 2) for c in range(5) for p in range(15)]
    seen = set()
    for x, y, w, h in rects:
        assert 0 <= x < x+w <= 320 and 0 <= y < y+h <= 240
        pixels = {(xx, yy) for xx in range(x, x+w) for yy in range(y, y+h)}
        assert seen.isdisjoint(pixels)
        seen.update(pixels)
    assert sym['esave'] - sym['eprev'] >= 99*2
    assert len(code) - sym['esave'] >= 2*len(seen)


@pytest.mark.parametrize('db', [0, 1, 8, 24, 60, 0xffffffff])
def test_paint_and_erase(m4emu, assembled, db):
    code, sym = assembled
    m = m4emu.M4(code, MODULE)
    m.write(FB, PATTERN)
    paint = MODULE + sym['northern_gr_paint']
    m.call(paint, FB, db, 1)
    n = 0 if db == 0xffffffff else min(db, 24)
    colours = struct.unpack_from('<24H', code, sym['colours'])
    for j in range(24):
        x = 8 + 10*j + 2*sum(j >= i for i in (3, 6, 12, 18))
        want = colours[j] if j < n else 0x2945
        assert struct.unpack('<H', m.read(FB + 2*(240*x+232), 2))[0] == want
    m.call(paint, FB, db, 0)
    assert m.read(FB, len(PATTERN)) == PATTERN


def test_preserves_stock_repaint(m4emu, assembled):
    code, sym = assembled
    m = m4emu.M4(code, MODULE)
    m.write(FB, PATTERN)
    paint = MODULE + sym['northern_gr_paint']
    m.call(paint, FB, 8, 1)
    pixel = FB + 2*(240*8+232)
    m.write(pixel, b'\x78\x56')
    m.call(paint, FB, 8, 1)
    m.call(paint, FB, 8, 0)
    assert m.read(pixel, 2) == b'\x78\x56'
