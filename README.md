<div align="center">

<a href="https://wisemandenny.github.io/hxtra/web/"><img src="docs/assets/banner.svg" alt="HXtra: custom firmware for the Line 6 HX Stomp" width="100%"></a>

[![Release](https://img.shields.io/github/v/release/wisemandenny/hxtra?style=flat-square&color=ff2e93&label=release)](https://github.com/wisemandenny/hxtra/releases/latest)
[![License: GPL-3.0](https://img.shields.io/github/license/wisemandenny/hxtra?style=flat-square&color=blue)](LICENSE)
[![Stars](https://img.shields.io/github/stars/wisemandenny/hxtra?style=flat-square&color=yellow)](https://github.com/wisemandenny/hxtra/stargazers)
[![Last commit](https://img.shields.io/github/last-commit/wisemandenny/hxtra?style=flat-square)](https://github.com/wisemandenny/hxtra/commits/main)

<!-- demo: tour, a short loop of the virtual HX Stomp from tools/hx_mirror.py -->
<p><img src="https://github.com/user-attachments/assets/99592c3e-ca54-4d37-9175-e349437fe3bb" width="480" alt="A tour of HXtra on the HX Stomp: the BPM display, the Breathing Line, DSP usage in the Edit view, six snapshots and the Rainbow TAP LED"></p>

</div>

<a href="https://wisemandenny.github.io/hxtra/web/#recovery"><img src="docs/assets/safe.svg" alt="100% safe for your HX Stomp: HXtra never touches the bootloader, so the stock firmware can always go back on." width="100%"></a>

<table>
<tr>
<td width="33%" valign="top">

&nbsp;

<img src="docs/assets/icons/try.svg" width="40" height="40" align="absmiddle" alt=""> **[Try before you install](https://wisemandenny.github.io/hxtra/web/#try-without-installing)**

Run HXtra from the HX Stomp's memory for one session. Nothing is written to the unit, and a power-cycle brings back what you had.

&nbsp;

</td>
<td width="33%" valign="top">

&nbsp;

<img src="docs/assets/icons/recover.svg" width="40" height="40" align="absmiddle" alt=""> **[Always recoverable](https://wisemandenny.github.io/hxtra/web/#recovery)**

If an install ever stops at the splash screen, hold Page Right while powering on and reinstall stock with Line 6 Updater. Every feature ran on a real HX Stomp before release.

&nbsp;

</td>
<td width="33%" valign="top">

&nbsp;

<img src="docs/assets/icons/install.svg" width="40" height="40" align="absmiddle" alt=""> **[Install from your browser](https://wisemandenny.github.io/hxtra/web/)**

The setup page builds HXtra locally from your own firmware file, right in your browser. Your firmware file never leaves your computer, and there's no software to set up.

&nbsp;

</td>
</tr>
</table>

## Installation

<p align="center"><a href="https://wisemandenny.github.io/hxtra/web/"><img src="docs/assets/install-hxtra.svg" alt="Install HXtra" width="60%"></a></p>

## Features

HXtra's settings and block knobs have teal labels, so you can tell them from the stock ones at a glance.

<sub>*Demos were recorded from a real HX Stomp's screen, along with its audio and button presses, then overlaid on a simulated HX Stomp.*</sub>

### <img src="docs/assets/icons/tuner.svg" width="28" height="28" align="top" alt=""> Extra tuner settings

*On the tuner's own third page*

- **Tuner button** (Hold, Press): "Hold" opens the tuner when you hold TAP (stock behavior); "Press" opens it with a press, and TAP no longer taps the tempo.
- **Tuner lock** (Off, On): On locks the tuner's other settings (Output, Reference, Type, Trails, Offsets).

<a href="https://wisemandenny.github.io/hxtra/web/features.html#tuner-settings"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/bpm.svg" width="40" height="28" align="top" alt=""> BPM Display

*Global Settings › BPM Display*

- **Font size** (XL, L, M, S, Off): the size of the tempo text at the top left of the Home screen. Off hides it.
- **Color** (White, Gray, Red, Orange, Yellow, Green, Cyan, Blue, Purple, Tempo): the tempo text's and the beat dot's colour. Tempo follows the TAP footswitch's colour (Tap LED Color).
- **Dot position** (Left, Right, Both, Off): where the beat dot blinks with TAP, beside the preset number. Off hides it; with both Off the BPM display is off.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#bpm"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/breathing-line.svg" width="28" height="28" align="top" alt=""> Breathing Line

*Global Settings › Breathing Line*

- **Color** (White, Red, Green, Blue, Fire, Ice, Sunset, Ocean, Aurora, Neon, Rainbow): the colour or gradient of the line across the middle of the Home screen.
- **Type** (Off, Steady, Breathe, Cylon, Comet, Heart, Sparkle): how it moves; Off gives back the stock line.
- **Speed** (1–10, Tempo): the speed of the animation. 1 = 8s/cycle, 10 = 0.8s/cycle; Tempo follows the tempo.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#breathing-line"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/dsp-usage.svg" width="32" height="32" align="top" alt=""> DSP Usage Display

*Global Settings › DSP Usage Display*

- Each block shows its share of the DSP, in the Edit view and in the model browser, and the top right corner the total.
- **Model Browser** (On, Off): the shares in the model browser.
- **Edit Blocks** (On, Off): the shares on the Edit view's blocks.
- **Total** (Small, Large, Off): the total in the top right corner. Small, the default, draws it in the meter's small digits; Large in the title's font; Off leaves the corner to the title, so a long preset name isn't covered.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#dsp-usage-display"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/gr-meter.svg" width="28" height="28" align="top" alt=""> Compressor Gain Reduction Meter

*New settings on the Deluxe, LA Studio, Kinky, Ampeg Opto, Rochester and Red Squeeze compressors*

- **Mtr Size** (Off, S, M, L, XL): the meter's thickness. Each size is an additional 5px; off disables the meter.
- **Mtr Pos** (Middle, Top, Left, Bottom, Right): Location of the meter on the Home screen and on the compressor's edit screen. Middle takes the place of the line across the middle, and disables breathing line.
- **Mtr Dir** (Normal, Reverse): Normal fills left to right or top to bottom; Reverse the other way. Useful for Left/Right position settings.

The meter also shows while you edit the compressor, so you can dial in Threshold, Ratio, Attack and Release while you play.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#gr-meter"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/long-press.svg" width="28" height="28" align="top" alt=""> Virtual Footswitches (FS6-10)

*Global Settings › Footswitches*

- **Assign a block**: in the block's Bypass Assign, press Page › once to see MIDI In, then turn MIDI In up from Off: FS6 is one click up, FS10 five
- **Parameters**: assign one to the same FS in Controller Assign, and it follows the footswitch too.
- **MIDI**: **underneath, FS6 … FS10 are MIDI CC 20 … 24.** HX Edit shows them that way, and a MIDI controller sending those CCs switches them as well.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#virtual-footswitches"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/long-press.svg" width="28" height="28" align="top" alt=""> Foot Switch Long Press

*Global Settings › Footswitches*

- **FS1 … FS5 Hold** (Off, Tuner, FS4, FS5, FS6 … FS10): what holding that footswitch for a second does in Stomp mode. FS6 … FS10 are virtual footswitches: assign blocks to them in Bypass Assign.
- **FS6 … FS10 Function** (Tuner, Stomp, Bank Up, Bank Dn, PresetUp, PresetDn, SnpshtUp, SnpshtDn, FS Mode&gt;, &lt;FS Mode, AllBypas, TogglEXP, GlobalEQ): what that virtual footswitch does, as FS3 … FS5 Function do for the real ones. Stomp, the default, toggles its blocks; GlobalEQ opens Global EQ, and any footswitch press goes back to Home.
- **Switch a virtual footswitch**: hold the footswitch whose Hold is set to that FS. By default, holding FS1 switches FS6, and so on up to FS5 and FS10.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#long-press"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/snapshots.svg" width="104" height="32" align="top" alt=""> More Snapshots (4-6)

*Global Settings › Footswitches*

- Six snapshots per preset: hold FS1 or FS2 for 1 s and the snapshot footswitches select snapshots 1–3 or 4–6, then tap one to select it. A hold changes no sound.
- **Snapshot BankSel** (Hold, Tap): Hold, the default, works as above. With Tap, press the lit snapshot footswitch again to flip between 1–3 and 4–6.
- Once a preset has snapshots 4–6, next and previous snapshot (SnpshtUp, SnpshtDn, MIDI CC 69) step through all six: next on 3 goes to 4, and next on 6 back to 1.
- MIDI CC 69 selects any of the six directly: values 0–2 for snapshots 1–3, 3–5 for 4–6.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#more-snapshots"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/tap-command.svg" width="28" height="28" align="top" alt=""> Tap Command

*Menu › Command Center, on FS1 … FS5*

- **Tap** (a Command for an FS slot, after Hotkey): the footswitch taps the tempo as TAP does, only in the presets where you put it, and its ring blinks the tempo. The footswitch must be a Stomp switch (Global Settings › Footswitches for FS3 … FS5). On stock firmware the footswitch doesn't tap.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#tap-command"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/tap-color.svg" width="28" height="28" align="top" alt=""> TAP LED Color

*Global Settings › Displays*

- **Tap LED Color** (Red, DkOrange, LtOrange, Yellow, Green, Teal, Blue, Violet, Pink, White, Rainbow, Random, Off): the colour of the TAP footswitch's blinking LED ring, and the icon and label of TAP/TUNER on the Home screen. Rainbow fades the ring a small step through the rainbow on each beat; Random picks a new colour at each beat. Both keep the label white. Off stops the blink: it takes the place of the stock Tap Tempo LED setting.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#tap-led-color"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/preset-color.svg" width="28" height="28" align="top" alt=""> Preset Mode LED Color

*Global Settings › Displays, page 2*

- **This Preset** (None, Red, DkOrange, LtOrange, Yellow, Green, Teal, Blue, Violet, Pink, White): the current preset's own colour, kept when you save the preset. In Preset footswitch mode its ring and its switch icon on the Home screen are lit in that colour while it is selected, and dimmed while it is not.
- **Preset LED Color** (Red, DkOrange, LtOrange, Yellow, Green, Teal, Blue, Violet, Pink, White): the colour of a preset without its own while it is selected. Such a preset's ring stays off while it is not, as stock.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#preset-led-color"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/metronome.svg" width="35" height="28" align="top" alt=""> Metronome

*New block: Volume/Pan › Metronome*

- **Time** (a note value, synced to the tempo): the beat, as a delay's Time.
- **Level** (−60 … +6 dB): the click's volume.
- **Accent** (Off, 2 … 12): every nth beat is a downbeat, a higher click.
- **Thru** (Off, On): On plays your signal with the click under it; Off plays the click alone.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#metronome"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/usb-monitor.svg" width="28" height="28" align="top" alt=""> USB & Send Routing

*Global Settings › Ins/Outs, page 3*

- **Path A Out**: where path A's output goes, in every preset.
  - **Main L/R**: as stock.
  - **Send/USB**: to your computer on USB 3/4, so you monitor through your DAW. Main and the phones play what the computer sends back. The Send jacks get it too.
  - **USB Only**: to your computer only; the Send jacks stay silent.
  - **Main+Snd**: Main L/R as usual, plus a copy to the Send jacks and USB 3/4.
- Don't use Send/USB or Main+Snd in a preset with an FX Loop block: it feeds back.

### <img src="docs/assets/icons/real-names.svg" width="28" height="28" align="top" alt=""> Real Block Names

*No settings*

- Renames blocks to the gear they were based on: e.g. Deez One Mod becomes Boss DS-1 Mod.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#real-block-names"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/fx-gate.svg" width="28" height="28" align="top" alt=""> FX Loop Noise Gate

*Gate, Threshold and Decay knobs on the FX Loop and Return blocks*

- A noise gate on what comes back from the loop, like the Input block's, so a noisy pedal in the loop no longer takes a Noise Gate block.
- Each FX Loop and Return block then counts 0.2% (mono) or 0.4% (stereo) more toward the DSP limit.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#fx-loop-gate"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/gate-sidechain.svg" width="28" height="28" align="top" alt=""> Noise Gate Input Sidechain

*Input Sidechain knob on the Noise Gate block*

- On, the Noise Gate opens and closes on your guitar as it comes in, so a gate after a high-gain drive follows the clean guitar.
- Each Noise Gate block then counts 0.1% (mono) or 0.2% (stereo) more toward the DSP limit.
- *Experimental:* tested with recorded signals, not yet with a played instrument, so it may need tuning. It works only with a cable in the HX Stomp's guitar input.

<a href="https://wisemandenny.github.io/hxtra/web/features.html#gate-sidechain"><img src="docs/assets/icons/watch-demo.svg" width="124" height="28" alt="Watch demo"></a>

### <img src="docs/assets/icons/nam.svg" width="28" height="28" align="top" alt=""> NAM A2 Lite

- [Neural Amp Modeler](https://www.neuralampmodeler.com) captures on the HX Stomp's own DSP, from [hx-stomp-nam-lite](https://github.com/nocaseguy/hx-stomp-nam-lite). The setup page converts your `.nam` files.

<div align="center">

<a href="https://wisemandenny.github.io/hxtra/web/features.html"><img src="docs/assets/feature-guide.svg" alt="Read the feature guide" width="45%"></a>

</div>

## Engineering

<table>
<tr>
<td width="50%" valign="top">

### <img src="docs/assets/icons/dev-module.svg" width="28" height="28" align="top" alt=""> Feature modules
Each feature is one Python module in `tools/features/` with its Cortex-M4 code in `src/m4/`, and the build automatically finds it.

&nbsp;

</td>
<td width="50%" valign="top">

### <img src="docs/assets/icons/dev-hooks.svg" width="28" height="28" align="top" alt=""> Hook layer
Features reach the firmware only through hooks that the patcher, `tools/patch_menu.py`, lets them share, and every write checks the stock bytes first, so a clash fails the build, not the unit.

&nbsp;

</td>
</tr>
<tr>
<td valign="top">

### <img src="docs/assets/icons/dev-settings.svg" width="28" height="28" align="top" alt=""> Virtual global settings
The patcher makes up its own setting IDs and packs their values into unused records the HX Stomp already saves, increasing the capacity from 10 settings to 46.

&nbsp;

</td>
<td valign="top">

### <img src="docs/assets/icons/dev-pipeline.svg" width="28" height="28" align="top" alt=""> From Python to HX Stomp
`tools/m4asm.py` assembles each feature's code with `clang`, the patcher places it in free space in the firmware and points the hooked stock calls at it, and `tools/hxf.py` packs the result into a new `.hxf`.

&nbsp;

</td>
</tr>
<tr>
<td valign="top">

### <img src="docs/assets/icons/dev-tested.svg" width="28" height="28" align="top" alt=""> Emulated first
Every feature's M4 code runs on an emulated Cortex-M4 ([unicorn](https://www.unicorn-engine.org), `tests/m4emu.py`) before it runs on a unit, and a pinned MD5 of the whole build catches any byte that changes by accident.

&nbsp;

</td>
<td valign="top">

### <img src="docs/assets/icons/dev-mirror.svg" width="28" height="28" align="top" alt=""> Screen mirror and demo videos
A developer build streams the HX Stomp's screen over USB, and `tools/hx_mirror.py` records it with every control event and renders the demo videos on the [feature tour](https://wisemandenny.github.io/hxtra/web/features.html).

&nbsp;

</td>
</tr>
</table>

<div align="center">

<a href="docs/architecture.md"><img src="docs/assets/engineering-guide.svg" alt="Read the engineering guide" width="51%"></a>

</div>

## Why use AI?

<table>
<tr>
<td width="50%" valign="top">

### 100% reverse engineered
The HX Stomp has no SDK, no documentation, no source code and no debug symbols. Everything HXtra changes had to be found first by reading raw disassembly of a stripped binary that runs on two processors: the Cortex-M4 that runs the screen and footswitches, and the SHARC DSP that processes the audio.

&nbsp;

</td>
<td valign="top">

### AI only writes code
One person chose every feature and decided how each should look, feel and behave, and shelved ideas that were unsafe or not worth the risk. I loaded every test build onto my own HX Stomp, played through it and watched the screen, which is where most bugs were caught, and tuned animation speeds, colours and the click's volume by eye and ear. All AI did is write the code.

&nbsp;

</td>
</tr>
</table>

## FAQ

<table>
<tr>
<td width="50%" valign="top">

### <img src="docs/assets/icons/faq-stock.svg" width="28" height="28" align="top" alt=""> How do I go back to stock firmware?
[See the recovery guide on the setup page](https://wisemandenny.github.io/hxtra/web/#recovery)

&nbsp;

</td>
<td width="50%" valign="top">

### <img src="docs/assets/icons/faq-presets.svg" width="28" height="28" align="top" alt=""> Will this break my presets?
- **No.** Presets made on stock firmware open in HXtra.
- A preset saved with snapshots 4–6 still loads on stock firmware, as snapshots 1–3.
- HX Edit opens, exports and imports HXtra presets, but its exports (`.hlx`) and backups (`.hxb`) hold snapshots 1–3 only.
- Presets made with an older release of [hx-stomp-nam-lite](https://github.com/nocaseguy/hx-stomp-nam-lite) won't load their NAM blocks in HXtra, so add NAM to those presets again. Presets from its current release open as they are.

&nbsp;

</td>
</tr>
<tr>
<td valign="top">

### <img src="docs/assets/icons/faq-dsp.svg" width="28" height="28" align="top" alt=""> Does HXtra use up extra DSP?
HXtra itself doesn't: it runs on the processor that drives the screen and footswitches. A few features put code on the DSP and use a little:

- **Compressor Gain Reduction Meter**, on the compressors that have it
- **Metronome**, while the block is in a preset
- **FX Loop Noise Gate**, on each FX Loop and Return block
- **Noise Gate Input Sidechain**, on each Noise Gate block
- **USB & Send Routing**, to move path A's output
- **NAM A2 Lite** blocks, like any amp block

If you hear crackling, leave those out on the setup page.

&nbsp;

</td>
<td valign="top">

### <img src="docs/assets/icons/faq-choose.svg" width="28" height="28" align="top" alt=""> Can I choose which features I get?
Partly. On the setup page you pick the **DSP features**: how many NAM A2 Lite blocks (3, 2, 1 or none), the gain reduction meter, the Metronome, the FX Loop gate, USB & Send Routing and Input Sidechain. They share the HX Stomp's spare DSP memory, so the page shows what's left as you tick, and fewer NAM blocks leave room for more of the others. Real block names is a box too. Every other feature is always in; to leave one of those out, [build it yourself](docs/building.md).

&nbsp;

</td>
</tr>
<tr>
<td valign="top">

### <img src="docs/assets/icons/faq-platforms.svg" width="28" height="28" align="top" alt=""> Which operating systems are supported?
*Only macOS and Windows are fully supported.*

- The setup page builds HXtra on Windows, macOS and Linux, in any modern browser.
- Its Run from RAM step needs Chrome or Edge.
- Installing uses Line 6 Updater, which runs on Windows and macOS.
- Building from the command line needs clang to assemble the features' code: Apple's Command Line Tools on a Mac, or clang on Linux and WSL (`apt install clang`). Both give the same build, MD5 included.

&nbsp;

</td>
<td valign="top">

### <img src="docs/assets/icons/faq-legal.svg" width="28" height="28" align="top" alt=""> Is this legal?
*This isn't legal advice, and where you live matters.*

- **No locks are broken.** The firmware isn't encrypted or signed, so HXtra doesn't violate copy protection. That is what anti-circumvention laws such as the US DMCA (§1201) forbid.
- **Reverse engineering for compatible software is protected** in the US (*Sega v. Accolade*), the EU (Software Directive, Articles 5(3) and 6), the UK (CDPA ss. 50B and 50BA) and Canada (Copyright Act s. 30.61).
- **This repo does not contain Line 6 IP** The patcher holds only addresses, table layouts and a few short runs of stock bytes it checks before writing. You bring your own copy of the official firmware, and the build changes it on your computer.
- **Changing the firmware on your own unit** is private use. US law lets the owner of a program's copy adapt it to run it on their machine (17 U.S.C. §117), other countries are less clear, and Line 6's license terms may forbid it: that is a contract matter between you and Line 6.
- **Don't share the built `.hxf`.** It is Line 6's firmware with changes, and passing it on would infringe their copyright.
- No NAM captures are included either; you bring your own.

&nbsp;

</td>
</tr>
</table>

## Known issues

- With the breathing line on, the BPM beat dot sometimes draws half lit.
- Tapping the tempo doesn't yet move the Metronome's beat onto your taps.
- A preset made before 1.2 (on stock firmware or an earlier HXtra) that is close to the DSP limit may open empty. With FX Loop Noise Gate in your build, each FX Loop and Return block counts 0.2% more (0.4% stereo); with Input Sidechain, each Noise Gate block counts 0.1% more (0.2% stereo). To fix it, remove a block from the preset on stock firmware, or untick those features on the setup page.

Found something else? [Open an issue](https://github.com/wisemandenny/hxtra/issues/new/choose).

## Acknowledgements

- **[Derek Bui (nocaseguy)](https://github.com/nocaseguy)**, for [hx-stomp-nam-lite](https://github.com/nocaseguy/hx-stomp-nam-lite), the foundation HXtra is forked from. It brought the SHARC assembler and simulator, the NAM A2 Lite kernel, the firmware container tools, the RAM loader and the setup page, and it showed that the HX Stomp's firmware can be changed safely.
- **[ghidra-sharc](https://github.com/roblg/ghidra-sharc)**, whose SHARC opcode tables the assembler adapts.
- **[Neural Amp Modeler](https://github.com/sdatkinson/neural-amp-modeler)**, by Steven Atkinson.
- **[Jason Shimmy](https://jasonshimmy.com/)**, for [HelixHelp](https://helixhelp.com/), whose model list gives Real block names the gear each model is based on.

## License

HXtra is [GPL-3.0-or-later](LICENSE). Third-party notices are in [NOTICE](NOTICE). Line 6, Helix, HX Stomp, HX Effects and HX Edit are trademarks of Yamaha Guitar Group, Inc. HXtra is not affiliated with, endorsed by or supported by Line 6 or Yamaha Guitar Group.
