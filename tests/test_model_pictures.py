"""Model selection, shared paints and picture input for the Model Pictures feature."""
import struct

import pytest

import features
import patch_menu as pm
import setting_ids
from features import dsp_meter, gr, model_pictures as mp

EDIT, PARAMS, BROWSER = 0x281282f8, 0x28128270, 0x281299d0
SCREEN, PANEL = 0x28128260, 0x28128258
FB, CODE, GR, DSP_METER, CHAIN = 0x28a00000, 0x28e40000, 0x28e60000, 0x28e70000, 0x28e80000
DSP, NODES, BLOCK, ITEM = 0x28b10000, 0x28b20000, 0x28b30000, 0x28b40000
MODEL, PRESET, ART_EDIT, ART_BROWSER = 671, 204, 701, 702
SELECTED, COUNT, GET_ITEM, GET_COST = 0x28df0280, 0x28e0edcc, 0x28e01204, 0x28e01d50
LOCK, UNLOCK, FILL = 0x28e24970, 0x28e24ae8, 0x100017e8
IDS = setting_ids.by_name()
MODS = features.load()


def test_mapping_uses_internal_models_and_shares_resources(model_pictures_art):
    pictures = mp.artwork(model_pictures_art)
    (name, pair), = pictures.items()
    pictures['Stereo'] = pair
    allocated = []

    def add(template, width, height, data):
        allocated.append((template, width, height, data))
        return 700 + len(allocated)

    models = [('Unmatched', 7, 8), ('Stereo', 800, 211), (name, MODEL, PRESET)]
    assert mp.picture_rows(models, pictures, add) == [(MODEL, PRESET, ART_EDIT, ART_BROWSER),
                                                      (800, 211, ART_EDIT, ART_BROWSER)]
    assert allocated == [(mp.IMAGE_TEMPLATE, mp.WIDTH, mp.EDIT_HEIGHT, pair[0]),
                         (mp.IMAGE_TEMPLATE, mp.WIDTH, mp.BROWSER_HEIGHT, pair[1])]


def test_bad_artwork_fails_before_the_build(model_pictures_art):
    model_pictures_art.write_text('{"version":1,"pictures":[{"models":["SomeModel"],"edit":"aa","browser":"bb"}]}')
    with pytest.raises(SystemExit, match='wrong picture dimensions'):
        mp.artwork(model_pictures_art)


class Paint:
    def __init__(self, m4emu, meters=False):
        code, sym = m4emu.assemble(mp.MODULE, MODS, IDS, inc=mp.inc([(MODEL, PRESET, ART_EDIT, ART_BROWSER)]))
        m = self.m = m4emu.M4(code, CODE)
        self.settings = {IDS['model_pictures.enabled']: 0}
        self.model, self.preset, self.path = MODEL, PRESET, 0
        self.drawn, self.widget = [], {}

        def setting(m):
            value = self.settings.get(m.reg('r0'))
            m.u32(m.reg('r1') + 4, value or 0)
            m.reg('r0', -3 if value is None else 0)

        def selected(m):
            m.u8(m.reg('r0'), self.path)
            m.reg('r0', 1)

        def block_info(m):
            m.write(m.reg('r2') + 1, struct.pack('<H', self.preset))
            m.reg('r0', 0)

        def item(m):
            m.u32(ITEM + 4, self.model)
            m.u32(m.reg('r3'), ITEM)
            m.reg('r0', 0)

        def cost(m):
            m.u32(m.reg('r1'), 2100)
            m.reg('r0', 0)

        m.stub(pm.GET_VALUE, setting)
        m.stub(SELECTED, selected)
        m.stub(0x28d92a98, lambda m: m.reg('r0', DSP))
        m.stub(0x28e0fe94, block_info)
        m.stub(COUNT, lambda m: m.reg('r0', 5))
        m.stub(GET_ITEM, item)
        m.stub(GET_COST, cost)
        m.stub(FILL, self.fill)
        for fn in (0x28e249d0, 0x28e24a68, 0x28e24ac8, 0x28e249e8, 0x28e24a28):
            m.stub(fn)
        for fn in (LOCK, UNLOCK, 0x28e07844, 0x28e0785c, 0x28e24ab0, 0x28e24aa8, 0x28e24a98):
            m.stub(fn)
        m.stub(0x28e24c18, lambda m: self.widget.update(image=m.reg('r1')))
        m.stub(0x28e24c68, lambda m: self.widget.update(x=m.reg('r1'), y=m.reg('r2')))
        m.stub(0x28e24a00, self.draw)

        after = {EDIT: [], PARAMS: [], BROWSER: []}
        if meters:
            gr_code, gr_sym = m4emu.assemble(gr.MODULE, MODS, IDS, inc=gr.inc((MODEL,)))
            dsp_code, dsp_sym = m4emu.assemble('src/m4/dsp_meter.s', MODS, IDS)
            m.load(GR, gr_code)
            m.load(DSP_METER, dsp_code)
            after[EDIT] = [GR + gr_sym['edit_top'], DSP_METER + dsp_sym['dsp_paint']]
            after[PARAMS] = [GR + gr_sym['edit_params']]
            after[BROWSER] = [DSP_METER + dsp_sym['dsp_browser']]
            m.u32(GR + gr_sym['data'] + 40, 20 << 24 | 7)
            m.u32(0x28449e78, DSP)
            m.u32(DSP + 0x4400, NODES)
            m.u32(DSP + 0x14, 0)
            for i in range(1, 16):
                m.u32(DSP + 0x14 + 0x54 * i, 0xffffffff)
            m.u32(NODES + 0x24, BLOCK)
            m.u8(BLOCK + 5, 1)
            m.u32(BLOCK + 0x44, 2100)
            m.u32(BLOCK + 0x54, MODEL)
            self.widget_at(EDIT + 0x4a4, 41, 165, 4)
            self.settings[IDS['dsp_meter.total']] = 0

        self.chains = {}
        for i, (view, stock, handler) in enumerate((
                (EDIT, mp.EDIT_PAINT, 'edit'), (PARAMS, mp.PARAM_PAINT, 'params'),
                (BROWSER, mp.BROWSER_PAINT, 'browser'))):
            address = CHAIN + 0x100 * i
            m.stub(stock, self.stock)
            m.load(address, pm.chain_cave(address, stock & ~1, [CODE + sym['model_pictures_erase']],
                                          after[view] + [CODE + sym[f'model_pictures_{handler}']]))
            self.chains[view] = address
        self.views(1)

    def widget_at(self, va, x, y, anchor):
        self.m.write(va, struct.pack('<7I2B', 3, 0, 0, x, y, 24, 24, anchor, 1))

    def views(self, screen):
        m = self.m
        m.u8(SCREEN, screen)
        m.u8(PANEL, 2)
        for i, (head, view) in enumerate(((0x281f35b8, PARAMS), (0x281f3d2c, EDIT if screen == 1 else BROWSER))):
            node = NODES + 0x100 + 0x20 * i
            m.u32(head, node)
            m.write(node, struct.pack('<6I', 1, 1, 0, view, 0, 0))
        m.u8(BROWSER + 0x40, 2)
        m.u8(BROWSER + 0x56e, 11)
        m.u32(BROWSER + 0x574, 0)
        for i in range(5):
            self.widget_at(BROWSER + 0x22c + 0x24 * i, 21, 194 - 40 * i, 7)

    def px(self, x, y):
        return struct.unpack('<H', self.m.read(FB + 2 * (240 * x + y), 2))[0]

    def rectangle(self, x, y, w, h, colour):
        column = struct.pack('<H', colour) * h
        for col in range(x, x + w):
            self.m.write(FB + 2 * (240 * col + y), column)

    def stock(self, m):
        view = m.reg('r1')
        if view == PARAMS:
            self.rectangle(20, 25, 20, 12, 0xf7e0)         # Teal parameter label
        elif view == EDIT:
            self.rectangle(29, 153, 24, 24, 0x001f)       # signal-flow block with room for DSP digits
        elif view == BROWSER:
            self.rectangle(60, 170, 95, 22, 0xffff)       # stock name
            self.rectangle(310, 100, 5, 12, 0xffff)       # scrollbar

    def fill(self, m):
        x, y, w = (m.reg(r) for r in ('r1', 'r2', 'r3'))
        h, colour, anchor = m.stack_args(3)
        assert anchor == 0
        self.rectangle(x, y, w, h, 0xffff if colour else 0)

    def draw(self, m):
        image, x, y = (self.widget[name] for name in ('image', 'x', 'y'))
        assert m.reg('r0') == m.reg('r1') == FB
        self.drawn.append((image, x, y))
        self.rectangle(x + 10, y + 2, 8, 10, 0x07e0)

    def paint(self, view):
        self.m.call(self.chains[view], FB, view, 0, 0)

    def snapshot(self):
        return self.m.read(FB, 320 * 480)


def test_both_edit_paints_and_unmapped_selection(m4emu):
    paint = Paint(m4emu)
    for view in (EDIT, PARAMS):
        paint.paint(view)
        assert paint.drawn[-1] == (ART_EDIT, 123, 129)
    assert len(paint.drawn) == 2 and paint.px(133, 131) == 0x07e0
    paint.preset = 65535
    paint.paint(EDIT)
    assert len(paint.drawn) == 2 and paint.px(133, 131) == 0
    assert paint.px(31, 26) == 0xf7e0


@pytest.mark.parametrize('setting', [None, 1, 3])
def test_edit_off_unset_and_out_of_range(m4emu, setting):
    paint = Paint(m4emu)
    paint.settings[IDS['model_pictures.enabled']] = setting
    paint.paint(EDIT)
    assert paint.drawn == [] and not paint.m.calls(SELECTED)


def test_browser_tracks_highlight_and_keeps_labels(m4emu):
    paint = Paint(m4emu)
    paint.views(2)
    paint.rectangle(249, 181, 20, 1, 0xffff)               # long name in the first row
    paint.paint(BROWSER)
    assert paint.drawn == [(ART_BROWSER, 234, 121)]
    assert paint.px(250, 181) == 0xffff
    assert paint.px(310, 100) == 0xffff
    paint.paint(PARAMS)
    assert paint.drawn[-1] == (ART_BROWSER, 234, 121)     # list A alone preserves the preview
    paint.m.u32(BROWSER + 0x574, 2)
    paint.rectangle(244, 123, 1, 1, 0x001f)               # another painter replaced one of our old pixels
    paint.paint(BROWSER)
    assert paint.drawn[-1] == (ART_BROWSER, 234, 81)
    assert paint.px(244, 123) == 0x001f and paint.px(245, 123) == 0
    paint.m.u8(BROWSER + 0x40, 1)
    paint.paint(BROWSER)
    assert len(paint.drawn) == 3 and paint.px(244, 83) == 0


def test_edit_and_browser_keep_the_real_gr_and_dsp_outputs(m4emu):
    for screen, views, pixel in ((1, (EDIT, PARAMS), (133, 131)), (2, (BROWSER,), (244, 163))):
        paint = Paint(m4emu, meters=True)
        paint.views(screen)
        paint.settings[IDS['model_pictures.enabled']] = 1
        for view in views:
            paint.paint(view)
        without_picture = paint.snapshot()
        if screen == 1:
            assert paint.px(0, 118) != 0                  # GR's middle lights
            assert any(paint.px(x, y) == 0 for x in range(33, 50) for y in range(159, 171))
            assert paint.px(31, 26) == 0xf7e0
        else:
            assert any(paint.px(x, 185) == 0xffff for x in range(34, 60))
        assert any(paint.px(x, y) == 0xffff for x in range(270, 316) for y in range(222, 232))
        paint.settings[IDS['model_pictures.enabled']] = 0
        for view in views:
            paint.paint(view)
        x0, y0 = pixel
        assert paint.px(x0, y0) == 0x07e0
        paint.rectangle(x0, y0, 8, 10, 0)
        assert paint.snapshot() == without_picture


def test_downloader_checks_cached_and_fetched_hashes(tmp_path, monkeypatch):
    import hashlib
    import io

    import prepare_model_pictures as prepare

    record = {'source_file': 'example.jpg', 'source_url': 'https://line6.com/example.jpg',
              'sha256': hashlib.sha256(b'verified photo').hexdigest()}
    cache = tmp_path / record['source_file']
    cache.write_bytes(b'corrupt cache')
    monkeypatch.setattr(prepare, 'urlopen', lambda *args, **kwargs: io.BytesIO(b'changed website'))
    with pytest.raises(ValueError, match='SHA-256 changed'):
        prepare.fetch_artwork(record, tmp_path)
    assert cache.read_bytes() == b'corrupt cache'
    monkeypatch.setattr(prepare, 'urlopen', lambda *args, **kwargs: io.BytesIO(b'verified photo'))
    assert prepare.fetch_artwork(record, tmp_path).read_bytes() == b'verified photo'
    monkeypatch.setattr(prepare, 'urlopen', lambda *args, **kwargs: pytest.fail('verified file should be reused'))
    assert prepare.fetch_artwork(record, tmp_path) == cache
