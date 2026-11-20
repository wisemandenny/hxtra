# Building HXtra

Most people never need this page: the [setup page](https://wisemandenny.github.io/hxtra/web/) does the whole build in your browser. Build from the command line to pick features one by one, to use your own boot picture, or to work on HXtra.

## Requirements

- An **HX Stomp**: HXtra is for the HX Stomp only, and `build.py` refuses any other firmware file.
- Line 6's firmware 3.80.0 for the HX Stomp. The build checks the MD5 and refuses any other file:
  - `HX_Stomp_v3.80.0_0x103966115.hxf`, MD5 `a2cd8f4ae56f49415380270ebc484bf1`. Download it from [line6.com](https://line6.com/software/readeula.html?rid=12906); you need to sign in with a free Line 6 (Helix) account to get the download.
- Python 3.10 or newer with `numpy`: `pip install numpy`. To run a build from RAM from the command line, also `pyusb` and `dfu-util`.
- For every feature but the boot screen and real block names, clang: their M4 code is assembled with it at build time. On a Mac, Apple's Command Line Tools (`xcode-select --install`); on Linux or WSL, `apt install clang` (clang 18 gives the same bytes as Apple's). `tools/m4asm.py` takes `HX_CLANG` (a path, or a name on `PATH`) first, then the Command Line Tools' clang, then `clang` on `PATH`. For the boot screen, macOS converts pictures (`sips`) and renders emoji (`swift`); elsewhere give a 320x240 PNG and `--splash-glyph` pictures.
- **Line 6 Updater** to install, and **HX Edit** to import captures.

## Build

```sh
git clone https://github.com/wisemandenny/hxtra.git
cd hxtra
python3 build.py path/to/HX_Stomp_v3.80.0_0x103966115.hxf
```

This writes `build/HX_Stomp_v3.80.0_HXtra.hxf`. It takes about 2 minutes, most of it the kernel check of step 1. The build:

1. Assembles the NAM kernel for the NAM slot count and runs it in the SHARC simulator, checking every block's output bit for bit against a reference NAM A2 implementation (`src/sharc/nam_a2.asm`). Add `--no-check` to skip this step.
2. Adds NAM A2 Lite in place of Xenomorph Fuzz Mono (preset ID 555): `tools/patch_amp.py remove-model`, `add-fx-model --knobs eq`, `move-folder` (into Amp > NAM) and `ir-title --knob 6` (the IR name in the block title, from the Model knob). These are `build.py`'s `STEPS`.
3. On the HX Stomp, adds the HXtra features that are turned on to the main application (`tools/patch_menu.py`, from `tools/features/`).
4. Adds the kernel to the DSP's boot code (`patch_amp.py patch`).
5. Recomputes and verifies every checksum: the container MD5, the archive Fletcher-32 and CRC-32, and the image CRCs.

The build is deterministic. The default HX Stomp build (no switches) has MD5 `9d804d5e99f19b0223f2f3d866e60807`, pinned in `tests/test_firmware.py`.

A default build changes only 5 of the 15 parts of the firmware: the main application, the DSP program, the model list, the DSP graph library and the image store (the boot picture; emoji in the boot text also change the font table). **The bootloader is never touched**, which is what keeps [recovery](https://wisemandenny.github.io/hxtra/web/#recovery) possible.

To add features, set their switches (the [features page](https://wisemandenny.github.io/hxtra/web/features.html) describes each feature):

| Feature | Switch |
|---|---|
| [Extra tuner settings](https://wisemandenny.github.io/hxtra/web/features.html#tuner-settings) | `HX_TUNER=1` |
| [BPM Display](https://wisemandenny.github.io/hxtra/web/features.html#bpm) | `HX_BPM=1` |
| [DSP Usage Display](https://wisemandenny.github.io/hxtra/web/features.html#dsp-usage-display) | `HX_DSP_METER=1` |
| [Breathing Line](https://wisemandenny.github.io/hxtra/web/features.html#breathing-line) | `HX_BREATHING_LINE=1` |
| [More Snapshots (4-6)](https://wisemandenny.github.io/hxtra/web/features.html#more-snapshots) | `HX_MORE_SNAPSHOTS=1` |
| [TAP LED Color](https://wisemandenny.github.io/hxtra/web/features.html#tap-led-color) | `HX_TAP_COLOR=1` |
| [Preset Mode LED Color](https://wisemandenny.github.io/hxtra/web/features.html#preset-led-color) | `HX_PRESET_COLOR=1` |
| [Tap Command](https://wisemandenny.github.io/hxtra/web/features.html#tap-command) | `HX_CC_TAP=1` |
| [Real Block Names](https://wisemandenny.github.io/hxtra/web/features.html#real-block-names) | `HX_REAL_NAMES=1` |
| [EXP Display](https://wisemandenny.github.io/hxtra/web/features.html#exp-display) | `HX_EXP_DISPLAY=1` |
| [FX Loop Noise Gate](https://wisemandenny.github.io/hxtra/web/features.html#fx-loop-gate) | `HX_FX_GATE=1` |
| [Noise Gate Input Sidechain](https://wisemandenny.github.io/hxtra/web/features.html#gate-sidechain) | `HX_GATE_SC=1` |
| [Foot Switch Long Press](https://wisemandenny.github.io/hxtra/web/features.html#long-press) | `HX_LONG_PRESS=1` |
| [Virtual Footswitches (FS6-10)](https://wisemandenny.github.io/hxtra/web/features.html#virtual-footswitches) | `HX_LONG_PRESS=1`, with Foot Switch Long Press |
| [Metronome](https://wisemandenny.github.io/hxtra/web/features.html#metronome) | `HX_CLICK=1` |
| [USB & Send Routing](https://wisemandenny.github.io/hxtra/web/features.html#usb-monitoring) | `HX_USB_MONITOR=1` |
| [Compressor Gain Reduction Meter](https://wisemandenny.github.io/hxtra/web/features.html#gr-meter) | `HX_GR=1` |
| [NAM A2 Lite](https://wisemandenny.github.io/hxtra/web/features.html#nam-a2-lite) | `HX_NAM_SLOTS=3`, `2`, `1`, `0` (off); unset, the most that fit |
| [Boot screen](#boot-screen) | `--splash`, `--splash-text` |

Switches combine. The Metronome, the FX Loop gate, the GR meter, USB & Send Routing and Input Sidechain put code on the DSP, in the room NAM A2 Lite's blocks leave (`python3 tools/block3.py` prints it): `HX_NAM_SLOTS=3`, `2`, `1` or `0` sets how many NAM blocks can play at once (`0`: no NAM A2 Lite, which skips steps 1, 2 and 4), and unset, `build.py` takes the most that leave room for the features you turned on. A build whose DSP features don't fit beside `HX_NAM_SLOTS` stops with what they take and what is left. For example, every feature but the boot picture:

```sh
HX_TUNER=1 HX_BPM=1 HX_DSP_METER=1 HX_BREATHING_LINE=1 HX_LONG_PRESS=1 HX_MORE_SNAPSHOTS=1 HX_CLICK=1 HX_GR=1 HX_TAP_COLOR=1 HX_PRESET_COLOR=1 HX_CC_TAP=1 HX_REAL_NAMES=1 HX_EXP_DISPLAY=1 \
  python3 build.py path/to/HX_Stomp_v3.80.0_0x103966115.hxf
```

## Boot screen

HX Stomp only.

```sh
python3 build.py path/to/HX_Stomp_v3.80.0_0x103966115.hxf --splash my_picture.jpg --splash-text "HXS OS v0.1"
```

- Without `--splash`, the boot picture is the stock one with "HX STOMP" relabelled "HXtra STOMP" (`tools/splash_hxtra.py`). It's made from the firmware's own pixels at build time, so the repo holds no Line 6 artwork.
- `--splash` takes any picture macOS can open (PNG, JPEG, HEIC, ...) at any size. The screen is **320x240**; a 320x240 PNG is used exactly as it is, and anything else is converted to it with macOS's `sips`: scaled to cover the screen and cropped at the centre, or with `--splash-fit fit`, scaled to fit inside it on black. Off macOS, give a 320x240 PNG.
- The loading bar crosses the picture about halfway down, and the text sits on it in the bottom 40 rows, in grey (`0xb1b1b1`), so keep the bottom darkish.
- The boot text reads "v1.2.1", the HXtra version, in place of "Firmware 3.80.0". `--splash-text` replaces it with up to 23 characters: ASCII, and emoji, each of which counts as one, e.g. `--splash-text "HXS OS v0.1 🎸"`.
- Each emoji becomes a colour glyph of the line's font, 18 px tall, level with the capitals. On macOS it's rendered from Apple Color Emoji; `--splash-glyph 🎸=guitar.png` (repeatable) gives your own picture instead, and off macOS it's required. A line with emoji is drawn white, not grey, as the firmware shows a glyph's own colours only on a white line.
- The boot screen is an HXtra feature (`tools/features/splash.py`). The flags set its inputs `HX_SPLASH`, `HX_SPLASH_FIT`, `HX_SPLASH_TEXT` and `HX_SPLASH_GLYPHS`, which work as environment variables too, as the other features' flags do.
- `python3 tools/splash_topo.py out.png [--seed N]` draws a neon contour-map picture to start from; `python3 tools/patch_splash.py export firmware.hxf out.png` saves the picture an image has now.
- The bootloader shows its own copy of the stock picture for a moment at power-on, before the firmware starts; that copy is not changed.

This also changes the image store (part 8 of the 15), and with emoji, the font table (part 7).

## Build in the browser

The setup page, **[wisemandenny.github.io/hxtra](https://wisemandenny.github.io/hxtra/web/)**, does the same build in the browser, and your file never leaves your computer: you drop your stock `.hxf` and download `HXtra_v<version>.hxf` (e.g. `HXtra_v1.2.0.hxf`), with every feature on and the ones you tick: the DSP features (how many NAM A2 Lite blocks, the GR meter, the Metronome block, the FX Loop gate, USB & Send Routing, Input Sidechain), which share the DSP memory and show what is left as you tick, and the others (Real block names, EXP Display). It also runs the build from RAM and converts `.nam` captures, and it reads in 10 languages. It runs `build.py`'s own commands in [Pyodide](https://pyodide.org) (`web/firmware-worker.js`); its builds have the same MD5s as `build.py`'s.

The browser has no clang to assemble the features' M4 code, so each release brings that code made in advance: `tools/m4cache.py` runs the page's features on the stock file and keeps what each module assembled to, in `m4cache.json`, with the MD5 of the build, and `tools/m4asm.py` reads it when `HX_M4_CACHE` names it. The page compares its build with that MD5 and says **Verified**. The page runs `build.py`'s other steps for them too: the Metronome block (`tools/patch_click.py`), the FX Loop gate (`tools/patch_gate.py`), and the GR meter's knobs and DSP code (`tools/patch_comp.py`). `m4cache.json` also holds the DSP memory each NAM slot count leaves and each DSP feature's cost (`"dsp"`), and the MD5 of every combination that fits. A copy of the page served from a checkout (`python3 -m http.server`, then `/web/`) has no `m4cache.json` and builds without features, unless you make one: `python3 tools/m4cache.py path/to/HX_Stomp_v3.80.0_0x103966115.hxf -o m4cache.json`.

The page is published only for a release, never from `main`, so it always matches one; see [Releases](../CONTRIBUTING.md#releases).

## Try it first, from RAM

You can run the built firmware from the HX Stomp's memory for one session before you install it. Nothing is written to the HX Stomp, and turning it off and on brings back what is installed. The HX Stomp must have stock 3.80.0 installed. This is how every HXtra change is tested.

Close HX Edit, then:

```sh
python3 tools/hxf_ram.py dfu    # or hold Page Right while you power on
dfu-util -d 1fc9:000c -a 0 -D tools/ramboot/firmware-ramboot.dfu
python3 tools/hxf_ram.py run build/HX_Stomp_v3.80.0_HXtra.hxf --stock HX_Stomp_v3.80.0_0x103966115.hxf
```

The setup page's **Run from RAM** step does the same in Chrome or Edge. Presets and IRs you change during the run are lost at power-off. [RAM_RUN.md](../RAM_RUN.md) explains how it works and its limits.

Then install it with Line 6 Updater, as the [setup page](https://wisemandenny.github.io/hxtra/web/)'s install step says.
