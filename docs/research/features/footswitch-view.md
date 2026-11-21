# Footswitch View

VIEW's third screen, after Play and Edit, which shows the footswitches as the HX Stomp XL shows its own (`HX_FOOTSWITCH_VIEW`, `tools/features/footswitch_view.py`, `src/m4/footswitch_view.s`). Status tags as in [conventions.md](../conventions.md).

## How it works [verified offline, unicorn: tests/test_footswitch_view.py]

- **VIEW**: a handler before the key events' post `0x28db8830(event)` (event: class byte, key code, type at +4). In Edit (`0x28128260` = 1) a VIEW press arms the screen and goes on, so the stock shows Play and the screen paints over it. On the screen, the VIEW press, its holds and its release become key `0xff`, which no listener knows; the press asks for view 0 (`0x28d96320`).
- **The paint**: after the Play view's two paints (literals `0x28d96d90` → `0x28dca359`, top; `0x28d96e28` → `0x28dc8d39`, the footswitch labels). The Play view stays the active view underneath, so footswitches and knobs work as in Play.
- **Leaving**: a handler before the view controller `0x28d93db4` deactivates and activates the Play view's two handlers (`0x28dca554`, `0x28dc9128`) once, which redraws it whole.
- **FS1..FS3** copy what the Play view's own footswitch labels hold. **FS6..FS8** look up the blocks whose Bypass Assign MIDI In is CC 20, 21 or 22 (the [virtual footswitches](long-press.md)). Names and categories come from Table 1 (`0x28e01c08`/`0x28e01c74`) and Table 2 (`0x28de8fd4`/`0x28de8f30`) at build time, into PID_INFO: 20 bytes a preset model ID. A model added by a later build step (the Metronome, the MIDI and Phones blocks) isn't in those tables then, so its tile has no name.

## On the unit [verified on unit, 2026-11]

Built on top of HXtra v1.2.1 (with the MIDI and Phones blocks): VIEW cycles Play → Edit → Footswitches → Play, the tiles light and dim with their blocks, and FS6–FS8 show the blocks assigned to MIDI In CC 20–22. The ported feature in this tree was built and checked offline. It is the same code with the MIDI tick and the debug lines taken out.
