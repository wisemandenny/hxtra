# Testing a build on the unit

These tools test a build on a real HX Stomp over USB, with nothing installed. Each run starts the image from RAM (see [RAM_RUN.md](RAM_RUN.md)). The tools then drive the Stomp the way HX Edit does: they put blocks into the edit buffer, change knobs and presets, record the Stomp's USB audio and check it. They never save a preset, and the eMMC isn't touched. Turn the Stomp off and on and it starts whatever is installed, as before.

**Status:** on 2026-11-05 the smoke suite from this repository ran on an HX Stomp against the Stomp build (MD5 e6431a5f) from RAM: 48 pass, 0 fail, 1 skip (the soak, which runs only with `--soak`). All of this was written for and run on an HX Stomp. The XL should behave the same but has not been tested with these tools, and the HX Effects can't run builds from RAM.

## What you need

- A Mac. The USB control and the RAM run work anywhere pyusb does, but recording and playing audio use two small macOS programs.
- Python 3.10 or newer: `pip install msgpack pyusb` (and libusb), plus `dfu-util`.
- Your stock `HX_Stomp_v3.80.0_0x103966115.hxf`, either in the repository root or named by `HX_STOMP_HXF`. The tools read each stock model's block kind and default knobs from its factory presets.
- Stock 3.80.0 (or this build) installed on the Stomp.
- HX Edit and Line 6 Updater closed, because they hold the USB connection.
- Captures in User IR slots 4 and 5, and slot 6 empty. Import them with the installed firmware first: what you import during a RAM run is gone at power-off.
- The recorder and the player, built once:

```sh
mkdir -p build
swiftc -O tools/mac/record_mac.swift -o build/record_mac   # the terminal needs microphone access once
swiftc -O tools/mac/play_mac.swift -o build/play_mac
```

Keep the Mac's screen unlocked during a run. macOS delivers no audio frames while the screen is locked, and the audio cases then fail.

## The smoke suite

```sh
python3 build.py HX_Stomp_v3.80.0_0x103966115.hxf
python3 tools/hx_smoke.py build/HX_Stomp_v3.80.0_HXtra.hxf --json smoke.json
```

`tools/hx_smoke.py` runs the image from RAM (`tools/hx_ramrun.sh`: it asks the running Stomp to restart in update mode, sends the loader, then the image) and runs these cases. `--list` prints them, and `--only` and `--skip` take names or tags.

- **control:** the unit answers, the setlist reads, the edit buffer round-trips byte for byte, and presets switch.
- **nam:** one, two and three NAM blocks load and play with no repeated block, dropout or click. Also a block on path B, bypass, the knobs' value types, Model at its edges (0, an empty slot, 128), and Model changed under full load.
- **limits:** NAM blocks plus a stock block that fits the DSP budget load; one that doesn't fit is refused and the unit stays up. Same with the dearest delay that fits and the cheapest that doesn't, and a third amp is refused.
- **stock:** the cheapest stock block of each browser category, alone and beside NAM.
- **stress:** Model and preset changes in a row, and `--soak S` seconds with three blocks.
- **Opt-in:** `--only sweep` places every stock block once (about 12 minutes). `--only rewrites` rewrites the edit buffer 40 times to find where the unit stops answering.

The budget cases read each block's DSP cost from the image itself, so they still hold when a build changes it. The audio cases use whatever reaches the input: a guitar with its volume at 0 is close enough to silence. Cases that need audio report SKIP without `build/record_mac`. Exit status 0 means nothing failed.

For a fixed signal instead, `tools/hx_reamp.py` sets the input block to USB 5/6, plays a pluck there with `build/play_mac` and measures the output:

```sh
python3 tools/hx_reamp.py build/HX_Stomp_v3.80.0_HXtra.hxf dry 555:4 555:4,555:5
```

Each case is a list of `preset_id:model` blocks on path A, or `dry` for a volume block alone. In this build, NAM is preset ID 555.

## The feature tests

`tools/hx_devtest.py` tests each HXtra feature on the unit the way you would: it presses the footswitches, knobs and buttons over USB and reads the screen. It tests the build that is already running and never starts, flashes or restarts the unit, so start it yourself first:

```sh
HX_TUNER=1 HX_TAP_COLOR=1 HX_BPM=1 HX_GR=1 HX_BREATHING_LINE=1 HX_DSP_METER=1 HX_LONG_PRESS=1 HX_CLICK=1 \
HX_MORE_SNAPSHOTS=1 HX_REAL_NAMES=1 HX_SCREEN_MIRROR=1 HX_USB_INPUT=1 python3 build.py HX_Stomp_v3.80.0_0x103966115.hxf
tools/hx_ramrun.sh build/HX_Stomp_v3.80.0_HXtra.hxf
python3 tools/hx_devtest.py                      # every case, about 2 minutes
python3 tools/hx_devtest.py --only bpm,tuner     # some; --list names them all
python3 tools/hx_devtest.py --record devtest     # and a recording of the run, as hx_mirror.py view --record
```

- **What it needs:** a build with `HX_SCREEN_MIRROR=1` (the screen, over USB) and `HX_USB_INPUT=1` (the controls, over USB), on a Mac (it reads the screen's text with macOS's Vision). Close HX Edit. Leave the unit on its Home screen in Stomp footswitch mode, on a preset with a TAP/TUNER footswitch, an empty block and no unsaved changes.
- **What it checks:** BPM Display (taps move the tempo, Font Size Off hides it), Tap LED Color (the TAP ring turns green), Breathing Line (the divider moves, Type Off stills it), the DSP usage display (the Edit view's total out of 75), Real block names (no stock title the feature renames), the tuner's settings page, Long press's settings, More snapshots (the lit footswitch flips to 4..6 and back), and the Metronome, NAM and GR meter blocks, added from the model browser with their knobs read.
- **What it leaves:** each case puts back every setting it changes, and the run loads the preset again at the end, as it was saved, so its edits are gone. A preset with unsaved changes of yours is not loaded again: the cases that add blocks skip instead. Nothing is saved.
- **Results:** `PASS`, `FAIL` or `SKIP` a case, `build/devtest/report.json`, and the screen of each failure as `build/devtest/<case>.png`. Exit status 0 when nothing failed.
- **Not covered:** the GR meter's lights (they need sound through the compressor) and the boot screen (seen only at power-on).

## The factory-preset sweep (Test A)

Does any stock preset leave something running that writes into NAM's memory? `tools/qa/preset_sweep.py` selects each of the unit's 126 presets in turn, then loads NAM alone with the input on USB 5/6 and nothing playing. With no input, NAM outputs a constant (its bias), and any corruption would move or disturb it. `preset_sweep2.py` does the same with three NAMs and a stock EQ, at default knobs and with the tone knobs moved.

```sh
python3 tools/qa/preset_sweep.py  build/HX_Stomp_v3.80.0_HXtra.hxf fwd.jsonl fwd
python3 tools/qa/preset_sweep.py  build/HX_Stomp_v3.80.0_HXtra.hxf rev.jsonl rev
python3 tools/qa/sweep_analyze.py fwd.jsonl rev.jsonl
python3 tools/qa/preset_sweep2.py build/HX_Stomp_v3.80.0_HXtra.hxf p2_fwd.jsonl fwd
python3 tools/qa/sweep_analyze2.py p2_fwd.jsonl
```

Each pass restarts the image from RAM every few presets. Our results are in [docs/research/STOMP_TEST_A_PRESET_SWEEP.md](docs/research/STOMP_TEST_A_PRESET_SWEEP.md), with the raw rows in `docs/research/stomp_test_a/`.

## Driving the unit yourself

`tools/hx_ctl.py` is the USB control the tests use, as a command:

```sh
python3 tools/hx_ctl.py status
python3 tools/hx_ctl.py presets
python3 tools/hx_ctl.py select 3
python3 tools/hx_ctl.py get-preset -o cur.json
python3 tools/hx_ctl.py set-model --slot 0 --model-id 555 --clear-after --clear-path-b
python3 tools/hx_ctl.py load-preset cur.json
python3 tools/hx_ctl.py --dry-run set-model --slot 0 --model-id 182    # prints, sends nothing
```

`tools/hx_input.py` presses the unit's controls on a build with `HX_USB_INPUT=1`: `press fs2`, `hold fs1`, `turn knob3 -4`, `touch fs1`, `press view` (also `action`, `page_left`, `page_right`, `knob1`..`knob5`).

`tools/hx_dfu_reboot.py` restarts the running Stomp in update mode, as Line 6 Updater does (`--dry-run` prints the exchange). `tools/hx_ramrun.sh IMAGE` does the whole RAM run in one step.

## When something goes wrong

- **The unit stops answering or the screen freezes:** turn it off and on. The installed firmware comes back.
- **No audio frames:** after many RAM runs macOS can lose the Stomp's USB audio. Re-plug it or power-cycle it.
- **A cab write is dropped after another dropped preset:** start again from a fresh boot.
- **A report:** please include the `--json` output, the image's MD5 and what the Stomp's screen showed.
