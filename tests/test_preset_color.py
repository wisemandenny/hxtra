"""tools/features/preset_color.py and src/m4/preset_color.s: the handlers in unicorn against a fake preset store (each preset's ring
and switch icon, lit for the current preset and dimmed for a coloured other one, the colour read from the end of another preset's
file, the key a save writes and a load finds, the Home paint's recolouring after a change), the stock sites they take, and the
firmware it builds (Displays' second page, the virtual settings, the hooks)."""
import struct

import pytest

import features
import image_store
import patch_menu as pm
import setting_ids
from features import more_snapshots as ms, preset_color as pc, tap_color as tc
from firmware import assert_virtual, branch_target, built, built_e0, reader, stock_e0, stock_entry

MODS = features.load()
IDS = setting_ids.by_name()
SETTING, THIS = pc.SETTINGS
COLOR_ID, THIS_ID = IDS['preset_color.color'], IDS['preset_color.this']
MOD = 0x28e60000
GET_VALUE, VIRT_SET = 0x28e1f844, 0x28700400
HOME = 0x2812a0c8
FS_FUNCTIONS, LED_MODES, FS_STATE_OBJ = 0x28128a74, 0x281f35f8, 0x28128a70
FS_STATE, FS_PRESET, CUR_REF, DIR = 0x28d9607c, 0x28dd5454, 0x28df024c, 0x28df0634
H_INIT, H_OPEN, H_CLOSE, FS_SEEK, FS_READ, FS_SIZE = 0x28def7b4, 0x28df006c, 0x28defde0, 0x28daa2d8, 0x28daa268, 0x28daa3ec
H_FILE = 0x18
STREAM, WRITE_FN, SINK = 0x28700000, 0x28700200, 0x28700300
TRAMPOLINE = 0x28700500
PRESET, STOMP, SNAPSHOT = 13, 2, 14
RED_ICON, DARK_ICON = 0x78, 0x112
START = 0xffffffff
COLOURS = ('Red', 'DarkOrange', 'LightOrange', 'Yellow', 'Green', 'Turquoise', 'Blue', 'Violet', 'Pink', 'White')
LEDS = (0x0300ff, 0x002dff, 0x00afd0, 0x00ff84, 0x00ff06, 0x80ff00, 0xff3200, 0xff0032, 0x2800ff, 0xceff6b)
DIMS = (0x02000c, 0x000410, 0x000608, 0x000c08, 0x000901, 0x060d00, 0x0d0400, 0x0b0003, 0x07000b, 0x0c1007)
ICONS = (0x78, 0x1ca, 0x90, 0x83, 0x1b6, 0x21e, 0x234, 0x110, 0x127, 0x115)
DIM_ICONS = (0x9c, 0x1e0, 0x214, 0xb7, 0x1fb, 0x8, 0x184, 0xc0, 0x117, 0x76)
NAMES = b'\x0c\x92\xa3abc\xc0'           # a stock file's section 10 ends with key 12's names
_code = {}


def key(colour):
    """The bytes a save appends for This Preset = colour (1 Red .. 10 White)."""
    return bytes([0x65, 0xc4, 5]) + b'HXPC' + bytes([colour])


class Preset:
    """preset_color.s in tests/m4emu.py's M4. self.values answers GET_VALUE by ID (missing: unset) and the engine's store sets
    them; self.files is the preset store, by slot (missing: a file that does not open), the current preset at self.current, its
    bank's footswitches at self.footswitch (None: no preset). The LED, image and store calls are logged."""

    def __init__(self, m4emu):
        if 'preset' not in _code:
            _code['preset'] = m4emu.assemble(pc.MODULE, MODS, IDS, virt_set=VIRT_SET)
        code, self.sym = _code['preset']
        self.m = m4emu.M4(code, MOD)
        self.values, self.files, self.current, self.footswitch = {}, {}, 4, [3, 4, 5]
        self.pos, self.opened, self.written = 0, None, []
        self.m.stub(GET_VALUE, self._get)
        self.m.stub(VIRT_SET, lambda m: (self.values.__setitem__(m.reg('r0'), m.reg('r1')), m.reg('r0', 0)))
        for fn in (pc.LED_COLOUR, pc.SET_IMAGE, pc.LED_MODE):
            self.m.stub(fn)
        self.m.stub(FS_STATE, lambda m: m.reg('r0', FS_STATE_OBJ))
        self.m.stub(FS_PRESET, self._fs_preset)
        self.m.stub(CUR_REF, lambda m: m.write(m.reg('r0'), struct.pack('<II', 0, self.current)))
        self.m.stub(DIR, lambda m: m.write(m.reg('r1'), struct.pack('<I', 0x100 + m.u32(m.reg('r0') + 4)) + b'name'.ljust(32, b'\0')))
        self.m.stub(H_INIT, lambda m: m.u32(m.reg('r2'), m.reg('r0')))
        self.m.stub(H_OPEN, self._open)
        self.m.stub(H_CLOSE, lambda m: setattr(self, 'opened', None))
        self.m.stub(FS_SEEK, self._seek)
        self.m.stub(FS_READ, self._read)
        self.m.stub(FS_SIZE, self._size)
        self.m.stub(WRITE_FN, lambda m: self.written.append(m.read(m.reg('r1'), m.reg('r2'))))
        self.m.u32(STREAM, SINK)
        self.m.u32(STREAM + 4, WRITE_FN | 1)
        self.mode((PRESET,) * 3, (0, 0, 0))

    def _get(self, m):
        pid = m.reg('r0')
        assert pid in (COLOR_ID, THIS_ID)
        if pid in self.values:
            m.write(m.reg('r1'), struct.pack('<II', 0, self.values[pid]))
            m.reg('r0', 0)
        else:
            m.reg('r0', -1)

    def _fs_preset(self, m):
        assert m.reg('r0') == FS_STATE_OBJ
        slot = self.footswitch[m.reg('r1')]
        if slot is None:
            m.reg('r0', -1)
        else:
            m.u8(m.reg('r2'), slot)
            m.reg('r0', 0)

    def _open(self, m):
        handle = m.reg('r0')
        slot = m.u32(handle) - 0x100
        if slot not in self.files:
            m.reg('r0', -5)
            return
        self.opened, self.handle = slot, handle
        m.u32(handle + 0xb4, 0x2a2)             # another section's start, which the probe first took for the end
        m.reg('r0', slot)

    def _size(self, m):
        assert m.reg('r0') == self.handle + H_FILE, "the open handle's store file"
        m.reg('r0', len(self.files[self.opened]))

    def _seek(self, m):
        assert m.reg('r2') == 0 and m.reg('r0') == self.handle + H_FILE, "from the start, the open handle's store file"
        self.pos = m.reg('r1')
        m.reg('r0', 1)

    def _read(self, m):
        data = self.files[self.opened][self.pos:self.pos + m.reg('r2')]
        m.write(m.reg('r1'), data)
        m.reg('r0', len(data))

    def mode(self, fns, rings):
        for k, f in enumerate(fns + (2, 2)):
            self.m.write(FS_FUNCTIONS + 2 * k, bytes([f, 0]))
        self.m.write(LED_MODES, bytes(rings))

    def call(self, sym, *args, r4=None):
        """The handler sym(args); r4: what r4 holds at the call, as the Home builder's preset there, through a trampoline
        (push {r4, lr}; mov r4, r2; bl sym; pop {r4, pc}) taking it in r2."""
        self.m.log.clear()
        fn = MOD + self.sym[sym]
        if r4 is not None:
            self.m.load(TRAMPOLINE, bytes.fromhex('10b5 1446') + pm.bl(TRAMPOLINE + 4, fn) + bytes.fromhex('10bd'))
            fn, args = TRAMPOLINE, (*args, r4)
        self.m.call(fn, *args)
        return [(f, tuple(regs[:2])) for f, regs in self.m.log if f in (pc.LED_COLOUR, pc.SET_IMAGE, pc.LED_MODE)]


@pytest.fixture
def preset(m4emu):
    return Preset(m4emu)


def test_feature_settings():
    assert pc.FLAG == 'HX_PRESET_COLOR' and pc.MENU == 'Displays'
    assert SETTING.label == b'LED\nPreset' and SETTING.default == 0
    assert SETTING.values == (b'Red', b'DkOrange', b'LtOrange', b'Yellow', b'Green', b'Teal', b'Blue', b'Violet', b'Pink', b'White')
    assert THIS.label == b'Preset\nThis' and THIS.default == 0 and THIS.values == (b'None',) + SETTING.values
    assert pc.LEDS == tc.LEDS == LEDS and (pc.ICONS, pc.DIMS, pc.DIM_ICONS) == (ICONS, DIMS, DIM_ICONS), "Tap LED Color's palette"
    assert pc.PRESET_KEY == 0x65 and ms.FILE_KEY < pc.PRESET_KEY


def test_its_key_is_the_last_a_save_writes():
    """Another preset's colour is read from the last 8 bytes of its file, so preset_color writes after every other feature's key."""
    keyed = [m for m in MODS if m.__name__.endswith(('more_snapshots', 'preset_color'))]
    assert [features.name(m) for m in keyed] == ['more_snapshots', 'preset_color'], 'features.load() is in ORDER'


@pytest.mark.parametrize('value', range(10))
def test_without_this_preset_the_global_colour_lights_the_ring_and_the_icon(preset, value):
    preset.values[COLOR_ID] = value
    assert preset.call('preset_led', 1, 0x0300ff) == [(pc.LED_COLOUR, (1, LEDS[value]))]
    assert preset.call('preset_icon', 0x2812a4bc, RED_ICON) == [(pc.SET_IMAGE, (0x2812a4bc, ICONS[value]))]


@pytest.mark.parametrize('this', range(1, 11))
def test_this_preset_lights_the_current_ring_and_icon_over_the_global_colour(preset, this):
    preset.values.update({COLOR_ID: 6, THIS_ID: this})
    assert preset.call('preset_led', 1, 0x0300ff) == [(pc.LED_COLOUR, (1, LEDS[this - 1]))]
    assert preset.call('preset_icon', 0x2812a4bc, RED_ICON) == [(pc.SET_IMAGE, (0x2812a4bc, ICONS[this - 1]))]


@pytest.mark.parametrize('values', [{}, {COLOR_ID: 10}, {COLOR_ID: 15, THIS_ID: 11}])
def test_unset_or_out_of_range_is_stock_red(preset, values):
    preset.values.update(values)
    assert preset.call('preset_led', 0, 0) == [(pc.LED_COLOUR, (0, LEDS[0]))]
    assert preset.call('preset_icon', 1, RED_ICON) == [(pc.SET_IMAGE, (1, RED_ICON))]


@pytest.mark.parametrize('colour', range(1, 11))
def test_another_coloured_preset_dims_its_ring_and_icon(preset, colour):
    preset.files[3] = NAMES + key(colour)
    assert preset.call('preset_off', 0, 0) == [(pc.LED_MODE, (0, 1)), (pc.LED_COLOUR, (0, DIMS[colour - 1]))]
    assert preset.call('preset_icon', 0x2812a4bc, DARK_ICON, r4=3) == [(pc.SET_IMAGE, (0x2812a4bc, DIM_ICONS[colour - 1]))]


@pytest.mark.parametrize('file', [None, NAMES, b'', key(3)[:7], NAMES + key(11), NAMES + key(0), NAMES + key(3)[:-1] + b'',
                                  NAMES + bytes([0x65, 0xc4, 5]) + b'HXPD' + b'\x03', NAMES + bytes([0x64, 0xc4, 5]) + b'HXPC\x03'])
def test_a_preset_without_a_whole_colour_key_stays_off_and_dark(preset, file):
    if file is not None:
        preset.files[3] = file
    assert preset.call('preset_off', 0, 0) == [(pc.LED_MODE, (0, 0))]
    assert preset.call('preset_icon', 0x2812a4bc, DARK_ICON, r4=3) == [(pc.SET_IMAGE, (0x2812a4bc, DARK_ICON))]
    assert preset.opened is None, 'closed again'


def test_the_tail_is_read_from_the_end_the_handle_gives(preset):
    preset.files[3] = NAMES + key(2) + NAMES + key(7)      # an earlier key in the file does not count, only the last
    assert preset.call('preset_off', 0, 0)[-1] == (pc.LED_COLOUR, (0, DIMS[6]))


@pytest.mark.parametrize('fn', [STOMP, SNAPSHOT, 1, 12])
def test_other_footswitch_functions_turn_off_as_stock_without_a_read(preset, fn):
    preset.mode((fn,) * 3, (0, 0, 0))
    preset.files[3] = NAMES + key(5)
    preset.m.log.clear()
    assert preset.call('preset_off', 0, 0) == [(pc.LED_MODE, (0, 0))]
    assert not preset.m.calls(H_OPEN) and not preset.m.calls(FS_PRESET)


def test_a_footswitch_without_a_preset_turns_off(preset):
    preset.footswitch = [None, 4, 5]
    preset.files[3] = NAMES + key(5)
    assert preset.call('preset_off', 0, 0) == [(pc.LED_MODE, (0, 0))]


def test_each_footswitch_reads_its_own_presets_file(preset):
    preset.files.update({3: NAMES + key(2), 5: NAMES + key(9)})
    assert preset.call('preset_off', 0, 0)[-1] == (pc.LED_COLOUR, (0, DIMS[1]))
    assert preset.call('preset_off', 2, 0)[-1] == (pc.LED_COLOUR, (2, DIMS[8]))
    assert [regs[0] - 0x100 for regs in preset.m.calls(H_INIT)] == [5]


@pytest.mark.parametrize('this', range(11))
def test_a_save_appends_this_presets_key_or_nothing_for_none(preset, this):
    preset.values[THIS_ID] = this
    preset.m.log.clear()
    assert preset.m.call(MOD + preset.sym['preset_key_write'], STREAM) == (1 if this else 0), 'the keys written'
    assert preset.written == ([key(this)] if this else [])


@pytest.mark.parametrize('this', range(1, 11))
def test_a_load_takes_this_preset_from_its_key_and_the_read_of_another_matches(preset, this):
    data = key(this)
    preset.values[THIS_ID] = 0
    preset.m.write(0x28710000, data)
    preset.m.call(MOD + preset.sym['preset_key_found'], data[0], 0x28710003, 5)
    assert preset.values[THIS_ID] == this
    preset.files[3] = NAMES + data
    assert preset.call('preset_off', 0, 0)[-1] == (pc.LED_COLOUR, (0, DIMS[this - 1])), 'what a save writes, another read finds'


def test_a_load_starts_this_preset_at_none_and_ignores_other_keys(preset):
    preset.values[THIS_ID] = 7
    found = lambda k, data: (preset.m.write(0x28710000, data), preset.m.call(MOD + preset.sym['preset_key_found'], k, 0x28710000, len(data)))
    found(START, b'')
    assert preset.values[THIS_ID] == 0, 'START: a preset without the key has none'
    preset.values[THIS_ID] = 7
    for k, data in ((0x64, b'HXPC\x03'), (0x65, b'HXPC\x03\x00'), (0x65, b'HXPD\x03'), (0x65, b'HXPC\x0b')):
        found(k, data)
    assert preset.values[THIS_ID] == 7


def lit(k, colour):
    return [(pc.LED_COLOUR, (k, LEDS[colour])), (pc.SET_IMAGE, (HOME + 0x3f4 + 0x24 * k, ICONS[colour]))]


def test_home_paint_recolours_the_current_presets_ring_once_per_change(preset):
    preset.mode((PRESET,) * 3, (1, 1, 0))       # FS1 a coloured other preset, dimmed; FS2 the current one
    preset.values[COLOR_ID] = 4
    assert preset.call('preset_paint', 0x28d1ce98, HOME) == lit(1, 4)
    assert preset.call('preset_paint', 0x28d1ce98, HOME) == [], 'the same settings: nothing to do'
    preset.values[COLOR_ID] = 7
    assert preset.call('preset_paint', 0x28d1ce98, HOME) == lit(1, 7)
    preset.values[THIS_ID] = 2
    assert preset.call('preset_paint', 0x28d1ce98, HOME) == lit(1, 1), 'This Preset Red over the global colour'


@pytest.mark.parametrize('fns, rings', [
    ((PRESET,) * 3, (0, 0, 0)),                 # a bank opened that holds no current preset: every ring off
    ((STOMP,) * 3, (1, 1, 0)),                  # Stomp mode: block colours, not ours
    ((SNAPSHOT,) * 3, (1, 0, 0)),               # Snapshot mode
    ((PRESET,) * 3, (2, 2, 2)),                 # blinking
    ((PRESET,) * 3, (1, 0, 1)),                 # only other presets' rings lit, dimmed
])
def test_home_paint_leaves_rings_that_are_not_the_current_presets(preset, fns, rings):
    preset.mode(fns, rings)
    preset.values[COLOR_ID] = 5
    assert preset.call('preset_paint', 0, HOME) == []


def test_module_tables_are_the_palette(preset):
    words = lambda name: struct.unpack('<10I', preset.m.read(MOD + preset.sym[name], 40))
    assert [words(n) for n in ('preset_leds', 'preset_dims', 'preset_icons', 'preset_dim_icons')] == [LEDS, DIMS, ICONS, DIM_ICONS]


def stock_code(m4emu, start, end):
    return m4emu.M4(reader(stock_e0())(start, end - start), start)


@pytest.mark.firmware
def test_dims_are_the_stock_dim_palette(m4emu):
    m = stock_code(m4emu, 0x28dd8030, 0x28dd8110)
    assert tuple(m.call(0x28dd8030, 0, i, 0) & 0xffffff for i in (2, 3, 4, 5, 6, 7, 8, 9, 10, 1)) == DIMS


@pytest.mark.firmware
def test_the_preset_case_lights_the_stock_red_from_one_literal():
    read = reader(stock_e0())
    assert struct.unpack('<I', read(pc.PRESET_RED_LIT, 4))[0] == pc.PRESET_RED
    assert struct.unpack('<I', read(pc.PRESET_RED, 4))[0] == LEDS[0], 'the Preset ring is the palette red'
    assert read(0x28dd0b52, 4) == bytes.fromhex('dff8eca3'), 'ldr.w r10, [pc, #0x3ec]: the literal at 0x28dd0f40'
    assert read(pc.LED_LOAD[0], 4) == pc.LED_LOAD[1] and read(pc.LED_CALL, 4) == pm.bl(pc.LED_CALL, pc.LED_COLOUR)
    assert stock_e0().count(struct.pack('<I', pc.PRESET_RED)) == 1, 'no other code loads the red word'
    assert read(pc.OFF_ZERO[0], 2) == pc.OFF_ZERO[1] and read(pc.OFF_CALL, 4) == pm.bl(pc.OFF_CALL, pc.LED_MODE)
    assert read(0x28dd0c36, 2) == bytes.fromhex('ad d1'), 'bne 0x28dd0b94: another preset than the current one goes off there'


@pytest.mark.firmware
def test_the_preset_icons_are_red_and_dark_and_each_colour_has_both(m4emu):
    read = reader(stock_e0())
    assert read(pc.ICON_PICK[0], 4) == pc.ICON_PICK[1]
    assert read(pc.ICON_PICK[0] + 8, 4) == bytes([0x08, 0xbf, RED_ICON, 0x21]), 'it eq; moveq r1, #0x78'
    assert read(pc.ICON_CALL, 4) == pm.bl(pc.ICON_CALL, pc.SET_IMAGE)
    assert read(0x28dc718e, 4) == bytes.fromhex('039b 9c42'), 'ldr r3, [sp, #0xc]; cmp r4, r3: r4 the preset at the call'
    names = image_store.names(stock_entry(7))
    assert (names[RED_ICON], names[DARK_ICON]) == (b'Icon_SwitchRed', b'Icon_SwitchDark')
    assert [names[i] for i in ICONS] == [f'Icon_Switch{c}'.encode() for c in COLOURS]
    assert [names[i] for i in DIM_ICONS] == [f'Icon_Switch{c}Off'.encode() for c in COLOURS]


@pytest.mark.firmware
def test_build_sends_the_preset_calls_the_home_paint_and_the_key_to_the_module(m4emu, monkeypatch):
    virt, real = {}, pm.Patch.module

    def module(self, path, inc=None):          # the virtual settings engine's store, which This Preset is set through
        virt[path] = getattr(self, 'virt_set', None)
        return real(self, path, inc)

    monkeypatch.setattr(pm.Patch, 'module', module)
    read, on = built({'HX_PRESET_COLOR': '1'})
    code, sym = m4emu.assemble(pc.MODULE, MODS, IDS, virt_set=virt[pc.MODULE])
    assert 'preset_color' in on
    module = branch_target(pc.LED_CALL, read(pc.LED_CALL, 4)) - sym['preset_led']
    assert read(module, len(code)) == code
    assert branch_target(pc.OFF_CALL, read(pc.OFF_CALL, 4)) == module + sym['preset_off']
    assert branch_target(pc.ICON_CALL, read(pc.ICON_CALL, 4)) == module + sym['preset_icon']
    stub = struct.unpack('<I', read(pc.HOME_PAINT_LIT, 4))[0] & ~1
    assert branch_target(stub + 6, read(stub + 6, 4)) == module + sym['preset_paint'], 'push, ldm, then the before handler'
    _, esym = m4emu.assemble('src/m4/preset_keys.s', MODS, IDS, inc={'preset_keys.inc': pm.preset_keys_inc({0x65: ('', 0, 0)})})
    site = pm.PRESET_FILE_CALLS[0][0]
    engine = branch_target(site, read(site, 4)) - esym['pk_serialize']
    tables = struct.unpack('<2I', read(engine + esym['pk_writers'], 8))
    assert tables == ((module + sym['preset_key_write']) | 1, (module + sym['preset_key_found']) | 1), 'key 0x65 on the engine'


@pytest.mark.firmware
def test_build_puts_both_settings_on_the_displays_page():
    new = built_e0({'HX_PRESET_COLOR': '1'})
    assert reader(new)(0x28e3b540, 6) == reader(stock_e0())(0x28e3b540, 6), 'the stock table stays'
    assert_virtual(new, pc, SETTING)
    assert_virtual(new, pc, THIS)


@pytest.mark.firmware
def test_without_the_flag_the_sites_stay_stock():
    read, on = built({})
    assert 'preset_color' not in on
    assert read(pc.LED_CALL, 4) == pm.bl(pc.LED_CALL, pc.LED_COLOUR)
    assert read(pc.OFF_CALL, 4) == pm.bl(pc.OFF_CALL, pc.LED_MODE)
    assert read(pc.ICON_CALL, 4) == pm.bl(pc.ICON_CALL, pc.SET_IMAGE)


@pytest.mark.firmware
def test_builds_alongside_every_other_feature():
    env = {f: '1' for m in MODS if not getattr(m, 'CONFLICTS', ()) for f in features.flags(m)}   # but a feature that conflicts
    _, on = built(env)
    assert {'tap_color', 'preset_color', 'bpm', 'breathing_line', 'more_snapshots'} <= set(on)
