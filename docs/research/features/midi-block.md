# MIDI block

Modulation > MIDI > MIDI: a block that sends a MIDI CC or PC when it turns on or off and when a preset loads with it (`HX_MIDI_BLOCK`, `tools/patch_midi.py`, `tools/features/midi_block.py`, `src/m4/midi_block.s`, `src/sharc/midi_thru.asm`). Status tags as in [conventions.md](../conventions.md).

## The model [verified offline: build, tests/test_midi_block.py]

- Preset ID 380, a copy of the mono modulation `HD2_Tremolo60sBiasTremMono`'s Entry 0 and 3 records on the mono effect host, in its own browser folder (Modulation > MIDI), with a free primitive from `kit_patch_amp.UNUSED_SHARC_PRIMS` (`tools/fx_block.py`). Its kernel passes its input through (`midi_thru.asm`, 30 instructions in Block 3).
- Knobs, pids 5..9: Chan (0 All, 1..16), Type (0 CC, 1 PC), Num, On, Off. **Entry 3 room**: beside NAM A2 Lite, Entry 3 is `0xf0d00` of the `0xf10f0` an HX Stomp loads amps from (build.py `E3_MAX`). The kit's Entry 3 layout puts the model table at the next 512-byte boundary after the strings, which had `0x8b` bytes to spare. So new strings past that cost 512 bytes at once. The knob keys are stock strings with their `State` (Mode, Type, Amount, High, Low), and the names are short (Chan, Num, On, Off; `HD2_Midi`). With the Phones block, Entry 3 ends at `0xf1094`. The Metronome alone ends it at `0xf10e4`, so neither block fits beside it, and `tools/fx_block.py` stops such a build.

## The messages [verified on unit, 2026-11]

- **The look**: twenty times a second, from the UI task's tick, which runs at 100 Hz as class-3 events through the key events' post `0x28db8830` (a handler before it). It looks at grid positions 0..39 (path A's Output is 9): the block `0x28e0fe94(engine, position, info)` (preset ID at +1), the bypass `0x28e04514(engine, position, &byte)`, and the knobs `0x28e11338(engine, position, {-2, index}, out)` (value at out+1, an int or a float). The engine comes from `0x28d92a98()`.
- **Which preset**: from the Play view's preset number and name texts (`0x2812aae0` + `0x30` and + `0x8c`), read without a lock. Calling the current-preset function `0x28df024c` from this task froze the unit [verified on unit: test builds 1 and 3].
- **The send**: `0x28dacf6c(0x281252f0, msg)`, the Command Center's MIDI sender. msg is 16 bytes: kind at +0 (3 CC, 5 PC), channel − 1 at +8, data 1 at +9, data 2 at +10. All loops over channels 0..15.
- **On the unit**: on-screen counters in a debug build showed the look finding the block and the sends climbing with each turn [verified on unit]. The receiving pedal heard nothing, and neither did the stock Command Center's messages over the same cable, so that cable is the suspect. Reception is not yet confirmed on a second device.
