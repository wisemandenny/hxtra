"""fx_block.py - a new mono effect block whose kernel is our own, for tools/patch_midi.py and tools/patch_phones.py: a copy of a
stock mono modulation's Entry 0 and 3 records on the mono effect host (Entry 4), with a primitive of kit_patch_amp's
UNUSED_SHARC_PRIMS that no other step took, and its kernel in Block 3 where tools/block3.py places it."""
import struct

import kit_patch_amp as kit
import l6ia
import patch_comp as pc

CLONE = 'HD2_Tremolo60sBiasTremMono'    # a stock mono modulation: no trails, as delays have
SRC_CATEGORY = 5                        # Modulation, the source's, so the block stays a plain effect
HOST = 'HD2_VolPanVolMono'
INSTANCE = {'dm_words': 0x91, 'pm_words': 0x0d, 'sdram_words': 0}
TAKEN = (0x9c75, 0x0128)                # NAM A2 Lite's and the Metronome's (tools/patch_click.py PRIM)


def f32(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def param(slot, name, pid, ty, mn, mx, dflt, meta=()):
    """A knob: slot (display order), name (what the knob shows), pid (DM(pid, I0) in the kernel), type (3 float, 2 int), min, max,
    default, and Entry 3 meta [(key, value)]. Its key in Entry 3 and in presets is name without spaces, which the knob shows as
    stock knobs show theirs; a name with a space goes in displayNameShort, as 60s Bias Trem's Intensity has 'Intnsty'. No
    displayName: the Edit view draws a parameter's displayName on a line under the bars, which stock knobs leave empty
    (stock displayNames are for the synced pairs' second knob) [seen on unit: HD2_EQ and stray letters there]."""
    w = f32 if ty == 3 else (lambda v: v & 0xffffffff)
    raw = [0, 0, 0, ty, slot, w(mn), w(mx), w(dflt)]
    key = name.replace(' ', '')
    meta = ([('displayNameShort', 7, name)] if key != name else []) + [(k, 7, v) for k, v in meta]
    return {'slot': slot, 'pid': pid, 'name': key, 'type': ty, 'op': kit.NAM_INPUT_OP[ty], 'raw': raw, 'meta': meta,
            'state': key + 'State', 'default_word': raw[7]}


def free_prim(l6ia_bytes):
    """A primitive of UNUSED_SHARC_PRIMS that no stock model uses and no earlier step hooked."""
    entries = l6ia.parse(l6ia_bytes)
    e2 = l6ia_bytes[entries[2]['payload_off']: entries[2]['payload_off'] + entries[2]['payload_len']]
    in_use, hooked = kit.stock_prims_in_use(l6ia_bytes), kit._scan_e2_injected(e2)[1]
    for prim in kit.UNUSED_SHARC_PRIMS:
        if prim[0] not in TAKEN and prim[0] not in in_use and prim[1] not in hooked:
            return prim
    raise SystemExit('no free SHARC primitive is left for the block')


def add_block(l6ia_bytes, name, display, folder, preset_id, cost, params, asm, asm_name, pm_base, log=print):
    """The model (Entries 0, 3, 4) and its kernel asm (its PM at pm_base). folder: (browser category, folder name), a folder of its
    own. Returns (new l6ia bytes, info)."""
    e0 = kit.get_entry_swapped(l6ia_bytes, 0)
    e3 = kit.get_entry_swapped(l6ia_bytes, 3)
    e4 = kit.get_entry_swapped(l6ia_bytes, 4)
    info = kit.parse_entry3_full(e3)
    if any(m['name'] == name for m in info['models']):
        raise SystemExit(f'{name} is already in this image')
    prim = free_prim(l6ia_bytes)
    src, hm = kit.find_model(info, CLONE), kit.find_model(info, HOST)
    kit.fx_source_check(e0, src, SRC_CATEGORY, 1)
    new_e4, blob, comp = kit.add_model_entry4(e4, hm['blob_index'], params, prim[0], INSTANCE, fx=True)
    log(f"[+] Entry 4: {display} blob {blob} on composite {comp:#x} (primitive {prim[0]:#06x})")
    new_e3, model_id, _ = kit.add_model_entry3(e3, src, name, display, blob, params, drop_meta=kit.FX_MODEL_META_DROP)
    # add-model copied the string section and the model table to the tail: back home, as patch_gate.py and patch_comp.py do, so a
    # later add-model or knob step doesn't copy them again
    tail_size, tail_view = len(new_e3), pc.models_view(kit.parse_entry3_full(new_e3))
    new_e3 = pc.e3_add_strings(new_e3, (), home=True)[0]
    assert pc.models_view(kit.parse_entry3_full(new_e3)) == tail_view, 'the move home changed a model'
    log(f"[+] Entry 3: {tail_size:#x} -> {len(new_e3):#x} bytes, the strings and model table back home")
    m = kit.parse_entry3_full(new_e3)['models'][model_id]
    assert [(p['name'], p['slot'], p['type']) for p in m['params']] == [(p['name'], p['slot'], p['type']) for p in params]
    assert not kit.pmap_slots_without_param(new_e4, blob, m['params'])
    log(f"[+] Entry 3: {name} ({display}) = model {model_id}, blob {blob}")
    new_e0, pid, dsp_cost, _ = kit.add_model_entry0(e0, src['words'][2], m['words'][2], display, preset_id=preset_id,
                                                    dsp_cost=cost, n_params=len(params), folder=folder, fx=True,
                                                    src_category=SRC_CATEGORY)
    assert pid == preset_id, (pid, preset_id)
    log(f"[+] Entry 0: preset_id {pid}, dsp_cost {dsp_cost}, browser {folder}")
    entries = l6ia.parse(l6ia_bytes)
    e2_raw = l6ia_bytes[entries[2]['payload_off']: entries[2]['payload_off'] + entries[2]['payload_len']]
    e2_raw, _ = kit.expand_sharc_blob0_buffer(e2_raw)
    out, _, _ = l6ia.rebuild_archive(l6ia_bytes, {0: bytes(new_e0), 2: l6ia.swap32(e2_raw), 3: new_e3, 4: new_e4})
    out, kinfo = kit.patch_kernel(out, asm, asm_name, prim=prim, pm_base=pm_base, relocate=False, log=log)
    return out, {'model_id': model_id, 'blob': blob, 'preset_id': pid, 'prim': prim, 'pm_base': pm_base, 'entry': kinfo['entry']}


def pm_words(asm, name):
    """The instructions of a kernel."""
    secs, _ = kit.sasm.assemble(asm, name)
    return sum(len(s.words) for s in secs if s.kind == 'pm')
