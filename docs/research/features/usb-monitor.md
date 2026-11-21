# USB monitoring

Global Settings > Ins/Outs > Path A Out (`HX_USB_MONITOR`, `tools/features/usb_monitor.py`, `src/m4/usb_monitor.s`, `tools/patch_usbmon.py`, `src/sharc/usb_monitor.asm`, `src/sharc/main_send.asm`): Send/USB sends path A to the Send bus, which is USB 3/4 to the computer and the Send jacks, instead of Main L/R, and USB Only also silences the Send jacks. A DAW can then monitor the processed sound (issue #81). Main+Snd (3) keeps path A on Main and adds Main into the Send bus too (#93). How the routing works: [sharc/usb-routing.md](../sharc/usb-routing.md). Status tags as in [conventions.md](../conventions.md).

## How it works [verified offline, unicorn: tests/test_usb_monitor.py]

- **The setting**: virtual ID `0xe0`, container 112 bits 0..1, in Ins/Outs' last empty slot (page 3, slot 3). Ins/Outs is stock category 0, with page table `0x28e3b55c` and 3 pages (`patch_menu.STOCK_CATEGORIES`).
- **The swap**: the feature owns `0x28df5760(ctx, app, path, value)`, which sends a path's destination to the DSP. For path 0 with value 1 (Main) it reads the setting and sends 6 (Send) instead when the setting is Send/USB. Every other path and value goes through unchanged. It notes the value it sent for path A in `um_sent`.
- **A change takes effect at once**:
  - After CHANGED `0x28dceb30(view, ID)` with ID `0xe0` (a turn), and after the page repaint `0x28dce854(view)` (a click's reset), `um_apply` compares the setting with `um_sent`.
  - When they differ and path A is on Main or Send, it calls the stock output API `0x28e03c68(engine, 9, 1)`. The engine comes from `0x28d92a98()`, and 9 is path A's Output block's grid position. That call ends in the owned send, which applies the setting.
  - Nothing is sent while path A's Output is off (0) or before the first send.
- **The mode word** [verified on unit, usb-monitor-8; offline: ssim, tests/test_usbmon.py]: the mode rides inside USB Input Trim, because the app (blob 1) cannot take a parameter of our own (see [sharc/usb-routing.md](../sharc/usb-routing.md), "Blob 1 cannot change").
  - After each send of path A's destination that succeeded, `um_send` looks up the app parameter `usbInGain0_1` (string 4209; `0x28df35a0`, each time: a rebuilt app gets new handles), reads the trim (USB In 1/2 Trim, I/O setting `0x99`, with `0x28e1f844`; 0 dB when that read fails) and sends trim + 1000 × (mode + 1) as a float with the trim's own type (`0x28df35e8`).
  - **The trim is I/O setting `0x99`** [verified offline: disassembly, and the stock code in unicorn, tests/test_usb_monitor.py; on unit with the fix, 2026-11-20, below]: `0x28e1f844` reads IDs `0x96..0xa4` from the I/O store (`0x2845e98c`, 0x2c-byte records: the type byte at +4, the value at +8, the app parameter's handle at +0x1c). For `0x99` the key table `0x28e3ec68` (index ID − 0x96) gives 4209, `usbInGain0_1`, and the long-label function `0x28d97634` takes the label from `0x28e252f4 + 27 × (ID − 0x96)`: "Trim\nUSB In 1/2" (shown as USB In 1/2 Trim). A knob turn goes through the step `0x28e20158` to the setter `0x28e1f458`, a click to the reset `0x28e1fb7c`, which takes the record's default (type +0x18, value +0x28); `0x28e1f8f4` is the setter other code calls. Each sends the {type, value} with `0x28df35e8` under the record's handle, then stores that type and value, so `um_send` reads the number the stock last sent and the DSP gets it back unchanged. No conversion is needed: `usbInGain0_1` is a float in dB ([sharc/usb-routing.md](../sharc/usb-routing.md)).
  - **Before the fix it read ID 3** [verified offline: `um_send`'s code; on unit, 2026-11-20, below]: the main store's Send/Return R (label `0x28e25624 + 27 × 3`). Every send of path A's destination (a preset load, a Path A Out change), in every mode, gave the DSP that setting's int (0 or 1) as a float: about 0 dB, whatever USB In 1/2 Trim said.
  - The app hands that float as it comes to its members [99] and [105], two Level gains `0x80`, as pid 1. The wrapped control function of `0x80` (registry row `0x200298`, stock `0x60f3e2`) takes a pid 1 value above 500 apart: the mode into `USB_MODE`, the trim on to the stock function. Any other pid or value goes on unchanged, and a code past mode 3 too. `0x80` is in many blocks; no Level comes near 500.
  - `USB_MODE` is the first data word of `usb_monitor.asm`, placed by `tools/block3.py`. The stock trim sends between ours pass through plain, so it keeps the last mode.
  - The Send jacks' writer `0x2aaa` is wrapped and gets a silent input (16 zero words) while the mode is 2. It runs before the Main writer in each block, so mode 3's add lands in the same block.
  - Main+Snd [verified offline: ssim, tests/test_main_send.py]: `main_send.asm` follows `usb_monitor.asm` in one placement. While the mode is 3, its wrapper of the Main writer `0x2aa8` (runs first in a block) keeps Main's 16 samples a channel, and its wrapper of the phones' writer `0x2aab` (runs last) adds them into the Send words `0x2aaa` left this block (the buffer pointer in DM `0xc5b50`, stride 2, FIX by 31), clipped at `0x3f7ffffe` as the writers do: Send ch s takes Main ch s XOR 1. Taking Main from its own writer keeps the Volume knob out of it while the knob controls the phones only. post-send-7, which took the phones' input by mistake, put it on the Send jacks (USB 7/8 by the Return) but following the knob: -24.1 at its top, silent at its bottom. USB 3/4 is fed by its own writer, USB out `0x2aac` (ch 2 = USB 3, ch 3 = USB 4), which runs before Main's writer in a block [verified on unit, post-send-8: taking Main's copy there, USB 3 trailed USB 1 by 16 samples]. So a third wrapper keeps USB out's own USB 1/2 input (Main, as the computer gets it) and adds it to USB 3/4 in the same block while the mode is 3: USB 3/4 carries what the Send jacks do, as stock, in step with USB 1/2. Global EQ reaches the Send copy as it reaches Main, and not USB 3/4 [verified on unit, post-send-9 below].
- **Setting changes** also re-send path A when only the mode changes (Send/USB ↔ USB Only: the same destination). `um_sent` keeps the last destination in byte 0 and the mode in byte 1.
- **Presets**: the edit buffer reads back the value sent, so a preset saved with Send/USB on holds 6 for path A. A stock unit's setter refuses 6 on path A and keeps Main.

## On the unit [verified on unit, 2026-11-16]

All on RAM runs from `next`. The Volt 4 had the phones on input 1 and Main on input 2 (they were taken the other way round at the time; 2026-11-16, see [sharc/usb-routing.md](../sharc/usb-routing.md), "Which writer is which"). The levels below are labelled as corrected. Plucks played on USB 5/6 with input A on USB 5/6, or on USB 1/2 for "DAW".

- **usb-monitor-4** (own section, image `877cd8b0…`):
  - Main L/R: the guitar is on USB 1/2, Main at -1.9 dBFS and the phones at -15.6.
  - Send/USB: the guitar is on USB 3/4 at -21.3, and the phones and Main sit at their floors (-63.8 and -66.6 against -60 and -64 with nothing playing). The DAW on USB 1/2 reaches the phones (-33.6) and Main (-12.1).
  - A knob turn to Send/USB moved the sound to USB 3/4 with no preset reload, and a knob-press reset brought it back to Main.
  - The section's title, label and value read right.
- **usb-monitor-5** (in Ins/Outs, image `997d079e…`): Send/USB gave the same results (USB 3/4 at -21.3, Main and phones at their floors, the DAW on both).
- With a Send or FX Loop block in path A, their send adds into USB 3/4. See [sharc/usb-routing.md](../sharc/usb-routing.md), "Send and FX Loop blocks share the Send bus".
- **usb-monitor-8** (USB Only, image `3e5fcfbd…`; the phones on Volt input 1, Main on 2, Send into Return L so the Send jacks come back on USB 7/8):
  - USB Only: the guitar is on USB 3/4 at -21.3, USB 7/8 (the Send jacks) at -101.3, the floor, and Main and the phones carry only noise.
  - Send/USB: USB 3/4 at -21.3 and USB 7/8 at -21.8. Main L/R: USB 1/2 at -21.3, the phones at -16.3.
  - Turns Send/USB → USB Only → Main L/R took effect with no preset reload.
  - The DAW on USB 1/2 reaches the phones (-16.2) and Main (-8.2) the same in every mode. That does not show the trim arriving: with ID 3 read as the trim, every mode sent about 0 dB (see the trim on 2026-11-20 below).
- **post-send-9** (Main+Snd against Global EQ, payload MD5 `8dbbcd28…`, RAM run, 2026-11-17 09:25; Volt input 2 = Main L, Send L into Return L = USB 7): Global EQ's High Cut at 1 kHz, on against off, band by band.
  - Main L: -4.0 at 400 Hz–1 kHz, -16.8 at 1–2.5 kHz, -37.0 at 2.5–6 kHz, -50.3 at 6–16 kHz.
  - Send L: -4.0, -16.6, -36.7, -49.0. The copy is taken after Global EQ, so a Main+Snd front-of-house feed gets it.
  - USB 1/2 and USB 3/4: 0.0 in every band. USB out is fed before Global EQ.
- **USB In 1/2 Trim and USB monitoring** [verified on unit, 2026-11-20, two sessions; RAM runs driven from the Mac with the screen mirror and USB input]: a cable from Main L to Return L, Return Type on Return, a 110 Hz pluck at peak 0.3 played on USB 1/2 for 2 s, the Return recorded on USB 7 and its RMS over 0.8..2.6 s compared. The reload is preset 21, then 20 again.
  - First session. `next` 4d8e360 with the v1.1.0 feature set, HX_USB_MONITOR, HX_SCREEN_MIRROR and HX_USB_INPUT (MD5 `fd9ec272…`): -54.7 dBFS with the trim at 0 dB, -74.2 at -19.4 dB. After the reload: -54.7, while the menu still read -19.4 dB.
  - The same build without HX_USB_MONITOR (MD5 `34016dc9…`): -54.8 at 0 dB, -73.5 at -18.8 dB, and still -73.5 after the reload.
  - Second session, three runs in a row under the same conditions, the trim set with the knob; with the trim at 0 dB, at -18.8 dB, and after the reload:
    - the USB monitoring build above: -73.8, -92.1, -73.9, the menu still at -18.8 dB;
    - the build without HX_USB_MONITOR above: -73.9, -92.1, -92.1;
    - the fix (`0x99`, the USB monitoring build's flags, MD5 `e4c8bbc9…`): -73.9, -92.1, -92.1, the menu at -18.8 dB.
  - Every level in the second session is about 19 dB below the first's (-73.8 against -54.7 and -73.9 against -54.8 at 0 dB), alike for both builds measured in both; the cause was not identified.
  - So USB monitoring dropped the trim on every preset load, as reading ID 3 explains. The fix keeps the trim through a preset load, as the build without USB monitoring does.
