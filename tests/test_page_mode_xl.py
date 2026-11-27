import os
import struct

import pytest

import features
import patch_amp as pa
import patch_menu as pm
import setting_ids
from firmware import branch_target, menu_entry0, reader, stock_e0

CODE = 0x28e60000
EVENT = 0x28e50000
MODE = 0x2812c000
CONTEXT = 0x28470000


@pytest.fixture
def page_mode(m4emu):
    code, symbols = m4emu.assemble('src/m4/page_mode_xl.s', features.load(), setting_ids.by_name(), layout=pm.XL_MENU)
    machine = m4emu.M4(code, CODE)
    state = {'play': True, 'mode': 0, 'changes': [], 'writes': []}

    def view_is(m):
        assert m.reg('sp') % 8 == 0
        assert m.reg('r0') == 8
        m.reg('r0', int(state['play']))

    def mode_getter(m):
        assert m.reg('sp') % 8 == 0
        m.u8(MODE + 0x4d, state['mode'])
        m.reg('r0', MODE)

    def set_mode(m):
        assert m.reg('sp') % 8 == 0
        assert m.reg('r0') == MODE
        state['mode'] = m.reg('r1')
        state['changes'].append(state['mode'])

    def get_context(m):
        assert m.reg('sp') % 8 == 0
        m.reg('r0', CONTEXT)

    def write_setting(m):
        assert m.reg('sp') % 8 == 0
        state['writes'].append((m.reg('r0'), m.reg('r1'), m.u32(m.reg('r2') + 4), m.reg('r3')))

    machine.stub(0x28d98ce4, view_is)
    machine.stub(0x28d98cb4, mode_getter)
    machine.stub(0x28dd9300, set_mode)
    machine.stub(0x28e0690c, get_context)
    machine.stub(0x28e25d20, write_setting)

    def event(key, kind, event_class=1):
        data = bytes([event_class, key, 0, 0]) + struct.pack('<I', kind)
        machine.write(EVENT, data)
        machine.call(CODE + symbols['xl_page_event'], EVENT)
        assert machine.read(EVENT, len(data)) == data

    return state, event


@pytest.mark.parametrize('key, expected', [(7, 3), (8, 1)])
def test_page_click_steps_and_wraps_the_play_mode(page_mode, key, expected):
    state, event = page_mode
    for kind in (1, 2, 3):
        event(key, kind)
    assert state['changes'] == [expected]
    assert state['writes'] == [(CONTEXT, 21, expected, 6)]


@pytest.mark.parametrize('first, second', [(7, 8), (8, 7)])
def test_menu_chord_never_changes_mode_and_next_click_works(page_mode, first, second):
    state, event = page_mode
    for key, kind in ((first, 1), (second, 1), (first, 2), (first, 3), (second, 2), (second, 3), (7, 1), (7, 2), (7, 3)):
        event(key, kind)
    assert state['changes'] == [3]


def test_page_does_not_change_mode_outside_play_or_after_a_hold(page_mode):
    state, event = page_mode
    state['play'] = False
    for kind in (1, 2, 3):
        event(8, kind)
    state['play'] = True
    for kind in (1, 5, 2, 3):
        event(8, kind)
    assert state['changes'] == []


def test_page_click_is_discarded_when_play_is_left_mid_press(page_mode):
    state, event = page_mode
    event(8, 1)
    state['play'] = False
    event(8, 2)
    event(8, 3)
    state['play'] = True
    event(8, 3)
    assert state['changes'] == []


def test_leaving_play_clears_an_interrupted_menu_chord(page_mode):
    state, event = page_mode
    event(7, 1)
    event(8, 1)
    event(5, 1)
    for kind in (1, 2, 3):
        event(7, kind)
    assert state['changes'] == [3]


def test_repeated_press_during_menu_chord_does_not_change_mode(page_mode):
    state, event = page_mode
    for key, kind in ((7, 1), (8, 1), (7, 1), (7, 2), (7, 3), (8, 2), (8, 3)):
        event(key, kind)
    assert state['changes'] == []


def test_non_page_keys_do_not_change_mode(page_mode):
    state, event = page_mode
    for key in (*range(7), *range(9, 27)):
        for kind in (1, 2, 3, 5):
            event(key, kind)
    assert state['changes'] == []
    assert state['writes'] == []


@pytest.mark.firmware
@pytest.mark.parametrize('mirror', [False])
def test_xl_build_always_chains_page_mode_with_other_event_handlers(monkeypatch, mirror):
    stock = os.environ.get('HX_STOMP_XL_HXF')
    if not stock:
        pytest.skip('HX_STOMP_XL_HXF is not set')
    archive = pa.load_l6ia_from_any(stock)[0]
    modules, original = {}, pm.Patch.module

    def capture(patch, path, inc=None):
        result = original(patch, path, inc)
        modules[path] = result
        return result

    monkeypatch.setattr(pm.Patch, 'module', capture)
    entries, _ = pm.menu_entries(lambda index: pa.get_entry_swapped(archive, index),
                                 env={'HX_SCREEN_MIRROR': '1', 'HX_LONG_PRESS': '1'} if mirror else {},
                                 layout=pm.XL_MENU)
    read = reader(entries[0])
    site = 0x28dbb958
    stub = branch_target(site, read(site, 4))
    handlers = ([modules['src/m4/screen_mirror.s']['sm_event']] if mirror else [])
    handlers.append(modules['src/m4/page_mode_xl.s']['xl_page_event'])
    expected = pm.chain_cave(stub, stub - 8, handlers, [])
    assert read(stub, len(expected)) == expected


@pytest.mark.firmware
@pytest.mark.parametrize('address', [0x28d98ce4, 0x28d98cb4, 0x28dd9300, 0x28e0690c, 0x28e25d20])
def test_xl_build_rejects_changed_page_mode_helpers(address):
    stock = os.environ.get('HX_STOMP_XL_HXF')
    if not stock:
        pytest.skip('HX_STOMP_XL_HXF is not set')
    archive = pa.load_l6ia_from_any(stock)[0]
    entry = bytearray(pa.get_entry_swapped(archive, 0))
    offset = pa._e0_vaddr_to_foff(pa._parse_e0_segments(entry), address, 2)
    entry[offset:offset + 2] = b'\xff\xff'
    with pytest.raises(SystemExit, match='XL PAGE mode helper'):
        pm.menu_entries(lambda index: bytes(entry) if index == 0 else pa.get_entry_swapped(archive, index),
                        env={}, layout=pm.XL_MENU)


@pytest.mark.firmware
def test_stomp_build_does_not_add_xl_page_handler(monkeypatch):
    modules, original = [], pm.Patch.module

    def capture(patch, path, inc=None):
        modules.append(path)
        return original(patch, path, inc)

    monkeypatch.setattr(pm.Patch, 'module', capture)
    menu_entry0(stock_e0(), env={})
    assert 'src/m4/page_mode_xl.s' not in modules
