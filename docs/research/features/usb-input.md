# USB input (`HX_USB_INPUT=1`, `tools/features/usb_input.py`, `src/m4/usb_input.s`, `tools/hx_input.py`)

The HX Stomp's footswitches, knobs and buttons pressed and turned from a computer, for the on-device tests and for demos. Status tags as in [conventions.md](../conventions.md).

## How it works

- **The command** [verified offline, m4emu]: the build chains `ui_register` after the boot's call of the editor's command registrations (`0x28d96adc`, shared with the [screen mirror](screen-mirror.md)), and it registers command `0x51` (its line in `tools/usb_commands.py`) as `{ui_cmd, 0x28e19205, 0}`: `ui_cmd` does the work and replies, the second call returns 0. How the dispatcher calls the two: [m4/usb-editor.md](../m4/usb-editor.md).
- **The parameter** is a MessagePack string (fixstr or str16, as hx_ctl packs bytes; str8 and bin8 are taken too) of 1..16 UI events, 8 bytes each: `{class, code, 0, 0, u32 value}`, the layout `0x28db90ec` builds (bytes 2 and 3 are never read). `ui_cmd` copies each to the stack and puts it on the key queue with `0x28db88fc`, the put every control of the unit uses ([m4/footswitches.md](../m4/footswitches.md)), so the UI task posts it in turn through `0x28db8830` like a real press. The reply is `{0x66: seq, 0x67: 0, 0x68: nil}` through the stock sender `0x28e15b30`.
- **Refusals**: a parameter that is not 1..16 whole events, or runs past the request, returns -3 and the dispatcher sends its error reply (`hx_ctl` raises `HxError`), with nothing queued. The put stops the unit (`bkpt`) when the queue has fewer than 8 free bytes, so `ui_cmd` puts an event only with 64 free (other controls put theirs meanwhile), sleeping 1 ms between looks; after 200 it returns -16, the events before it queued.
- **Events** (`hx_mirror.STOMP`, learned on the unit): class 1 keys, types 1 press, 2 release, 3 release before a hold (right after the 2), 5 hold; FS1..FS5 codes 12..16, FS1..FS3's touch sensors 9..11, knob presses 0..4, VIEW, ACTION, PAGE◀, PAGE▶ 5..8. Class 2: knob 1..5 turns, codes 0..4, value the clicks (+ clockwise).
- **What the host must do** [verified offline]: the queue drops a class-1 event equal to one still in it, and adds a knob turn to one of the same knob still in it, so `tools/hx_input.py` sends the same press twice with a gap (`GAP_S`). The firmware makes a hold from its own timer of a key held down (`0x281f5d98` bits), which an injected press does not set, so `Input.hold` sends the type 5 itself after 1 s, then the release without a type 3.
- **Tests** (`tests/test_usb_input.py`): the registration, the parameter forms and refusals, the waits for room and the give-up, in `tests/m4emu.py`; the host's events for each control; the build, alone and beside the screen mirror. `tools/hx_devtest.py` (its logic in `tests/test_devtest.py`) uses it to test every feature on the unit.

## Using it

- Build with `HX_USB_INPUT=1` (with `HX_SCREEN_MIRROR=1` to see what it does) and run it from RAM. Close HX Edit: it uses the editor stream.
- `python3 tools/hx_input.py press fs2`, `hold fs1 --seconds 1.5`, `turn knob3 -4`, `touch fs1`, `press view` (also `action`, `page_left`, `page_right`, `knob1`..`knob5`). Not the volume knob: it sets only the headphone level, with its own physical marker.
- From a script: `hx_input.Input(ctl)` with an `hx_ctl.HxCtl`, or `Input(s.ctl)` inside an `hx_mirror.Session`, whose ctl calls take turns with the frames.

- A script that prints while an `hx_mirror.Session` runs loses lines: hx_ctl's quiet mode swaps `sys.stdout` around every frame's request. Write with `os.write(1, ...)` or to a file.
- `hx_mirror`'s event log keeps the last 64 events a frame, and the 100 Hz tick is one of them, so a check of the events needs frames at least every 0.6 s: a `Session` (15 a second), not single `Mirror.frame()` calls with gaps.

## The UI as the tests drive it [verified on unit 2026-11-13, usb-button-inputs-2]

- **Menu**: PAGE◀ and PAGE▶ pressed together; its page 2 has Global EQ and Global Settings, opened by the knob below the tile (knob 2). On the Home screen alone, PAGE◀ and PAGE▶ step the footswitch mode.
- **Knob code 3** (`knob4`) steps Global Settings' sections, and the Edit view's selected block. **Knob code 4** (`knob5`): its press opens the model browser on the selected block, and its turn moves the browser's cursor, which on a model list **changes the block at once** (a turn on an EQ block's list made it Parametric). The cursor is drawn bold, with ▶ on a category.
- **Knob counts are finer than a value**: the USB In 1/2 trim moved about 0.067 dB a count (shown to 0.1), and a two-value list needed several counts. So a test turns a count at a time and reads the value back.
- **Taps**: four TAP presses 0.5 s apart read 120 only when no frame is fetched between them (`hx_devtest.taps` holds the session's lock); with frames between, each request waits for one, and the taps read 97.
- **Vision** reads the screen's fonts at confidence 1.0, but not a lone character (the NAM Model's "1", the snapshot number in the camera icon), it reads some capitals as Cyrillic and the edited marker as # or ®, and the browser's DSP share as a prefix ("00: Metronome").
- **Tempo** on this unit is global: loading the preset again kept the tapped tempo.

## On the unit [verified on unit 2026-11-13, usb-button-inputs-1, MD5 e3bf2692…]

- VIEW opens the Edit view and closes it; FS1 turns its block off and on again (twice in a row: the gap keeps the second press); PAGE▶ and PAGE◀ step the page and back; FS2 toggles its stomp. The mirror's event log shows each injected event as sent, in order: presses `1, 2, 3`, the hold `1, 5, 2`, knob turns +3 and −2, FS3's touch (81 frames alongside, none dropped).
- A parameter of 3 bytes gets `status 255, error -3` and the unit carries on.
- `tools/hx_devtest.py`, every case on usb-button-inputs-2 (MD5 `1e131cb6…`, every release feature, real names, the mirror and USB input): 12 of 12 pass in about 2 minutes, the preset left as saved.
