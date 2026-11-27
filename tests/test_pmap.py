"""tools/sharc/pmap.py: the map ops it evaluates, and what it reads from the stock file (docs/research/sharc/model-blobs.md)."""
import functools
import os

import pytest

import pmap


def knob(slot):
    return {'knob': 1, 'slot': slot}


def node(op, ins, data=None, table=None):
    e = {'op': hex(op), 'ins': {str(k): v for k, v in ins.items()}}
    if data is not None:
        e['data'] = data
    if table is not None:
        e['table'] = table
    return e


def test_curve_is_linear_between_its_nine_points():
    e = node(0x3, {0: knob(1)}, table=[0, 1, 2, 3, 4, 5, 6, 7, 16])
    assert pmap.evaluate(e, {1: 0.0}) == 0
    assert pmap.evaluate(e, {1: 0.5}) == 4
    assert pmap.evaluate(e, {1: 15 / 16}) == pytest.approx(11.5)
    assert pmap.evaluate(e, {1: 2.0}) == 16          # clamped to 0..1


def test_arithmetic_hot_variant_keeps_port_1_in_its_one_data_word():
    assert pmap.evaluate(node(0x14, {0: knob(1)}, data=[0, -1.0]), {1: 3.0}) == 2.0    # a + b
    assert pmap.evaluate(node(0x1d, {0: knob(1)}, data=[2.0]), {1: 3.0}) == 6.0        # hot a * b


def test_selects_and_conversions():
    sel = node(0x36, {0: knob(1)}, data=[10, 20, 30, 40])
    assert [pmap.evaluate(sel, {1: v}) for v in (0, 1, 3, 9)] == [10, 20, 40, 40]
    assert pmap.evaluate(node(0x27, {0: knob(1)}), {1: -20.0}) == pytest.approx(0.1)
    assert pmap.evaluate(node(0x27, {0: knob(1)}), {1: -120.0}) == 0.0
    assert pmap.evaluate(node(0x28, {0: knob(1)}), {1: 0.0}) == -120.0
    assert [pmap.evaluate(node(0x4e, {0: knob(1)}), {1: v}) for v in (0, 1, 2)] == [1, 0, 0]   # NOT


def test_an_op_it_does_not_model_gives_none():
    assert pmap.evaluate(node(0x17, {0: knob(1)}), {1: 0.5}) is None


@functools.lru_cache(maxsize=None)
def firmware():
    path = os.environ.get('HX_STOMP_HXF')
    if not path:
        pytest.skip('HX_STOMP_HXF is not set')
    return pmap.Firmware(path)


def sweep_of(name):
    fw = firmware()
    r = pmap.model_report(fw, pmap.kp.find_model(fw.e3, name))
    return {(k['knob'], tuple(w['path']), w['pid']): w['values'] for k in pmap.sweep(r) for w in k['writes']}


@pytest.mark.firmware
def test_teemah_knobs_reach_their_members():
    # docs/research/sharc/cores/teemah.md, "Parameter map and blob init"
    s = sweep_of('Teemah')
    assert s[('Level', (6,), 1)] == [-60.0, -21.0, -6.0, 3.0, 9.0]
    assert s[('TrebleCut', (4,), 2)] == [10610.0, 4775.0, 1600.0, 671.0, 309.0]
    assert s[('Gain', (3, 6), 1)][0] == 0.0 and s[('Gain', (3, 6), 1)][-1] == 48.75   # through the drive's nested map
    assert s[('Clipping', (3, 7), 3)] == [-11.1, -11.1, -17.4]    # Clipping == 2 ? -17.4 : -11.1
    assert s[('Clipping', (3, 7), 5)] == [-17.4, -11.1, -17.4]    # NOT (Clipping == 1) ? -17.4 : -11.1


@pytest.mark.firmware
def test_every_mono_distortion_and_eq_resolves():
    # model_report asserts one nested map (non-zero table F row) per composite member with a node-tree entry
    fw = firmware()
    ms = [m for m in fw.e3['models'] if m['meta'].get('category') in ('distortion', 'eq')
          and m['meta'].get('subcategory') == 'mono']
    assert len(ms) == 69
    for m in ms:
        pmap.model_report(fw, m)


@pytest.mark.firmware
def test_every_effect_model_resolves_and_sweeps():
    # every category, not only the distortions and EQs the notes were written from
    fw = firmware()
    ms = [m for m in fw.e3['models'] if m['meta'].get('category')]
    assert len(ms) == 830
    for m in ms:
        pmap.sweep(pmap.model_report(fw, m))


@pytest.mark.firmware
def test_a_composite_member_with_no_node_tree_entry_has_no_nested_map():
    # Simple Delay's 0x6000d7 (member 8) is written by nothing and runs on its init values
    s = sweep_of('Simple Delay')
    assert s[('Feedback', (4,), 2)] == [-120.0, -18.0, -12.0, -6.0, 0.0]
    assert s[('Mix', (10,), 1)] == [0.0, 0.0, 0.0, -12.0, -120.0]
    assert s[('Mix', (10,), 2)] == [-120.0, -12.0, 0.0, 0.0, 0.0]
    assert not any(p[:1] == (8,) for _, p, _ in s)


@pytest.mark.firmware
def test_a_blob_that_is_not_a_model_blob_is_refused():
    fw = firmware()
    for name in ('HelixStomp_App', 'HD2_AppTuner'):
        m = next(m for m in fw.e3['models'] if m['name'] == name)
        with pytest.raises(ValueError, match='not a model blob'):
            pmap.model_report(fw, m)


@pytest.mark.firmware
def test_nested_maps_pair_with_table_f_rows_in_tree_order():
    # 1x12 Blue Bell: member 23 comes before member 20 in the node tree, so table F's first filled
    # row is 23's map. Distance (slot 1) writes [20] pid 1, Early Reflections (slot 4) [23] pid 1;
    # paired in member order instead, Early Reflections would drive the filters inside [20].
    fw = firmware()
    m = next(m for m in fw.e3['models'] if m['name'] == 'HD2_Cab1x12BlueBell')
    r = pmap.model_report(fw, m)
    inside_20 = {k['knob'] for k in pmap.sweep(r) for w in k['writes'] if w['path'][:1] == [20]}
    assert inside_20 == {'Distance'}


@pytest.mark.firmware
def test_a_small_float_data_word_is_read_as_a_float():
    # Volume Pedal: Position -> max(x, 1e-6) -> op 0x28 (linear -> dB) -> 0x80 gain. float32(1e-6) is
    # just under 1e-6; read as an integer it gave 179 dB at every position.
    s = sweep_of('Volume Pedal')
    assert s[('Position', (2,), 1)] == pytest.approx([-120.0, -12.0412, -6.0206, -2.4988, 0.0], abs=1e-3)
    # Industrial Fuzz: max(x, -1e-6) before a min(.., 0.251); read as an integer it gave -0.169 at Compress 0
    assert sweep_of('Industrial Fuzz')[('Compress', (21,), 2)][0] == pytest.approx(0.0422, abs=1e-4)
