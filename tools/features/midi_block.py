"""MIDI Block: Modulation > MIDI > MIDI, a block that sends a MIDI message (tools/patch_midi.py adds the model and its pass-through
kernel; this is the M4 side, src/m4/midi_block.s). Its knobs: Chan (All or 1..16), Type (CC or PC), Num (the CC or the
program number), On and Off (a CC's value as the block turns on and off). When the block turns on or off (a footswitch, Bypass
Assign, a snapshot), and when a preset loads with it, it sends a CC of Num with On or Off, or a PC of Num when it turns on;
All sends it on all 16 channels. The messages go out of MIDI Out and USB, as the stock's own MIDI does. Several MIDI blocks in a
preset each send their own.

Twenty times a second, from the UI task's 100 Hz tick (class-3 events, seen before the key events' post), the module looks at the
current preset's blocks; the sound passes the block unchanged. A checkbox in the web page's DSP features (WEB 'dsp': its kernel
takes Block 3 room, tools/block3.py), ticked by default as the others are, and HX_MIDI_BLOCK for build.py."""
FLAG = 'HX_MIDI_BLOCK'
WEB = 'dsp'

POST, POST_STOCK = 0x28db8830, bytes.fromhex('f8b5 0446')   # (event): every UI event to its listeners; push {r3-r7,lr}; mov r4,r0
MIDI_PID = 380                      # tools/patch_midi.py PRESET_ID


def apply(p):
    m = p.module('src/m4/midi_block.s', {'midi_block.inc': f'.equ MIDI_PID, {MIDI_PID}\n'})
    p.chain_entry(POST, POST_STOCK, before=m['midi_block_post'])
