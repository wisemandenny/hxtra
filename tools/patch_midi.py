#!/usr/bin/env python3
"""patch_midi.py - the MIDI block: a block that sends a MIDI message when it turns on or off, and when a preset loads with it.

usage: patch_midi.py <in .hxf | L6IA> <out .hxf | L6IA> [--donor stock.hxf]

Run after tools/patch_amp.py patch and tools/patch_click.py, before tools/patch_gate.py (build.py does it for HX_MIDI_BLOCK=1
builds). It adds the model Modulation > MIDI > MIDI
(Entries 0, 3, 4; preset ID PRESET_ID) on the mono effect host, with the knobs Chan (All, 1..16), Type (CC, PC), Num, On and
Off, and its kernel src/sharc/midi_thru.asm (Entry 2), which passes the sound through unchanged, in Block 3
where tools/block3.py places it. The M4 side, which reads the knobs and sends the message, is tools/features/midi_block.py.
"""
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sharc'))

import block3
import fx_block
import kit_patch_amp as kit

FLAG = 'HX_MIDI_BLOCK'
ASM = os.path.join(SCRIPT_DIR, '..', 'src', 'sharc', 'midi_thru.asm')
NAME, DISPLAY = 'HD2_Midi', 'MIDI'      # short: Entry 3's strings (fx_block.param)
FOLDER = (5, 'MIDI')                # Modulation > MIDI
PRESET_ID = 380                     # fixed for ever: presets store it (tools/features/midi_block.py looks for it)
DSP_COST = 10
P = fx_block.param
# Chan (All, 1..16), Type (CC, PC), Num (the CC or program number), On and Off (the CC's value as the block turns on and off)
PARAMS = [P(1, 'Chan', 5, 2, 0, 16, 1, [('displayType', 'list'), ('0', 'All')] + [(str(c), str(c)) for c in range(1, 17)]),
          P(2, 'Type', 6, 2, 0, 1, 0, [('displayType', 'list'), ('0', 'CC'), ('1', 'PC')]),
          P(3, 'Num', 7, 2, 0, 127, 0),
          P(4, 'On', 8, 2, 0, 127, 127),
          P(5, 'Off', 9, 2, 0, 127, 0)]


def asm(pm):
    return open(ASM).read().replace('KIT_PM_BASE', f'{pm:#x}')


def dsp_size():
    """(data words, instructions): the kernel keeps nothing outside the block's own DM."""
    return 0, fx_block.pm_words(asm(0xe0000), 'midi_thru.asm')


def add_midi(l6ia_bytes, log=print):
    pm = block3.place(FLAG)[1]
    return fx_block.add_block(l6ia_bytes, NAME, DISPLAY, FOLDER, PRESET_ID, DSP_COST, PARAMS, asm(pm), 'midi_thru.asm', pm, log)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input')
    ap.add_argument('output')
    ap.add_argument('--donor', help='Stock .hxf of the unit, when input is a raw L6IA and output a .hxf')
    args = ap.parse_args()
    data, is_hxf = kit.load_l6ia_from_any(args.input)
    out, _ = add_midi(data)
    kit.save_l6ia_to_any(out, args.output, donor_hxf=args.input if is_hxf else args.donor)
    print(f"[+] Wrote {args.output}")


if __name__ == '__main__':
    main()
