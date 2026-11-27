"""patch_amp.py model-int: NAM's Model knob (a float shown as a dynamicList) reads as a whole number on the HX Stomp.

The firmware tests run the parameter value formatter of the stock and of the patched Entry 0 in unicorn, with only its metadata
lookup stubbed, and read the text it prints."""
import struct

import pytest

import patch_amp as pa
from firmware import stock, stock_e0

X = pa.MODEL_INT[0x28d8fa80]
LOOKUP = 0x28df35b8                 # (_, store, key, &out): 1 and out[1] = the value's string index when the key is there
DISPLAY_TYPE_KEY = 0xe              # "displayType", the string index the formatter looks up
CTX, PARAM, VALUE, BUF = 0x28700000, 0x28700100, 0x28700200, 0x28700300
BUF_LEN = 16


def test_cave_loads_as_the_stock_and_truncates_only_a_dynamic_list():
    cave = pa.model_int_cave()
    assert len(cave) % 4 == 0 and cave[:4] == bytes.fromhex(X.STOCK[X.LOAD]), 'the stock load first'
    assert bytes.fromhex('bcf10c0f') in cave, 'cmp.w ip, #12: dynamicList'
    assert cave.endswith(bytes.fromhex('7047'))


def test_the_dynamic_list_entry_is_the_float_switchs_twelfth():
    assert X.TBH + 2 * (pa.DISPLAY_DYNAMIC_LIST - 1) in X.STOCK
    assert (X.NO_DECIMALS - X.TBH) % 2 == 0 and 0 < (X.NO_DECIMALS - X.TBH) // 2 < 0x10000, 'a forward TBH offset'


def display_types():
    """{displayType string: its Entry 3 string index} for every displayType a stock parameter has."""
    info = pa.parse_entry3_full(pa.get_entry_swapped(stock(), 3))
    names = {p['meta']['displayType'] for m in info['models'] for p in m['params'] if 'displayType' in p['meta']}
    return {n: info['strings'].index(n) for n in names}


def formatter(m4emu, e0):
    """fmt(display type string index or None, value, lo, hi) -> the text the Entry 0 e0's formatter prints for a float parameter."""
    segs = pa._parse_e0_segments(e0)
    m = m4emu.M4(b'', 0x28000000)
    for _, poff, slen, dst, _ in segs[:2] + segs[4:]:
        (m.write if segs[4][3] <= dst < segs[6][3] else m.load)(dst, e0[poff:poff + slen])
    shown = {}

    def lookup(m):
        found = m.reg('r2') == DISPLAY_TYPE_KEY and shown['type'] is not None
        if found:
            m.u32(m.reg('r3') + 4, shown['type'])
        m.reg('r0', int(found))
    m.stub(LOOKUP, lookup)
    m.u32(CTX + 0xc, CTX + 0x80)

    def fmt(display_type, value, lo=0.0, hi=1000.0):
        shown['type'] = display_type
        m.u8(PARAM + 0xc, 3)
        m.write(PARAM + 0x14, struct.pack('<2f', lo, hi))
        m.write(VALUE + 4, struct.pack('<f', value))
        m.write(BUF, bytes(BUF_LEN))
        m.u32(m4emu.STACK_TOP, BUF_LEN)
        m.u32(m4emu.STACK_TOP + 4, 1)
        assert m.call(X.FORMAT, CTX, PARAM, VALUE, BUF) == 0
        return m.read(BUF, BUF_LEN).split(b'\0')[0].decode()
    return fmt


@pytest.mark.firmware
def test_stock_shows_model_with_a_decimal(m4emu):
    fmt = formatter(m4emu, stock_e0())
    assert fmt(display_types()['dynamicList'], 4.0) == '4.0', 'the issue: Model 4 reads 4.0'


@pytest.mark.firmware
@pytest.mark.parametrize('value, text', [(1.0, '1'), (4.0, '4'), (49.0, '49'), (128.0, '128'), (0.0, '0'), (999.0, '999'),
                                         (7.874, '7'), (0.6, '0')])
def test_model_shows_the_slot_the_kernel_plays(m4emu, value, text):
    fmt = formatter(m4emu, pa.model_int_entry0(stock_e0())[0])
    assert fmt(display_types()['dynamicList'], value) == text


@pytest.mark.firmware
def test_other_float_knobs_print_as_stock(m4emu):
    stock_fmt, fmt = formatter(m4emu, stock_e0()), formatter(m4emu, pa.model_int_entry0(stock_e0())[0])
    # micPosition also looks up positionCapEdge, which the stub never finds, and then loops
    cases = [(t, v, lo, hi) for t in [None, *(i for n, i in display_types().items() if n not in ('dynamicList', 'micPosition'))]
             for v, lo, hi in ((0.5, 0.0, 1.0), (4.0, 0.0, 1000.0), (7.874, 0.0, 1000.0), (650.0, 150.0, 3000.0), (-6.5, -60.0, 6.0))]
    assert [fmt(*c) for c in cases] == [stock_fmt(*c) for c in cases]


@pytest.mark.firmware
def test_model_int_runs_once_and_only_where_it_knows_the_addresses():
    e0, info = pa.model_int_entry0(stock_e0())
    assert info['cave'] == pa._parse_e0_segments(stock_e0())[6][3] + pa._parse_e0_segments(stock_e0())[6][2]
    with pytest.raises(SystemExit, match='not the stock'):
        pa.model_int_entry0(e0)
    xl = bytearray(stock_e0())
    struct.pack_into('<I', xl, pa._parse_e0_segments(xl)[6][0] + 4, 0x28d92230)
    with pytest.raises(SystemExit, match='not the stock'):
        pa.model_int_entry0(bytes(xl))
