# Northern Audio GR display (review prototype)

This is a contribution for discussion with the HXtra maintainers, not an enabled feature. It extracts the Edit-view renderer from Northern Audio Live 1.0, a custom firmware experiment built on HXtra and hx-stomp-nam-lite. Credit to Denny Wiseman, Derek Bui and the upstream contributors. The extracted code is offered under GPL-3.0-or-later. It includes no Line 6 firmware, binaries or copied stock instructions.

- **[verified on unit]** The original Northern Audio renderer displayed 24 one-dB segments and a numeric dB value on the HX Stomp's Edit screen, responding to bass playing and compressor controls. The combined Northern Audio Live 1.0 build was played through with both custom effects and survived preset storage and power cycling. This is a report from its hardware tester, not verification of the extracted renderer or its integration with HXtra.
- **[verified offline]** The extracted renderer assembles; its palette, glyph table, 99 non-overlapping rectangles and saved-pixel storage pass a geometry/table test. The emulator tests for painting, erasing and stock repaint preservation are provided but were not run in the preparation environment (Unicorn was unavailable).
- **[hypothesis]** The renderer can be integrated as an optional alternative Edit-view layout for HXtra's existing GR meter without changing its Home widgets or DSP probe. The existing 10-light non-linear layout should remain the default unless the maintainers decide otherwise.

## Interface

`src/m4/northern_gr_display.s`: `northern_gr_paint(fb, db, show)` accepts an unsigned whole-dB reduction magnitude (0..24, saturated above 24; `0xffffffff` for unavailable data). `show=0` restores the pixels it owns. `northern_gr_forget()` resets saved-pixel ownership when the framebuffer or view has been replaced. The caller must serialize calls, gate the active view and perform any required locking. No hardware hooks are installed by this module. The bitmap is 320 x 240, bottom-up and column-major, BGR565. The display uses 24 8x8 bar slots and a five-character 3x5 font, enlarged 2x. At zero, the numeric readout is `00dB`; unavailable telemetry displays `--dB`. The extracted renderer retains the saved-pixel scheme of the existing HXtra Edit-view meter, adapted for the smaller rectangles.

## Integration questions

- Use the existing upstream GR telemetry contract rather than Northern Audio's incompatible direct-dB packet interpretation. Convert the upstream fixed-point log ratio to whole dB before calling the renderer. Keep existing Home layout and all position/direction/size choices intact.
- Decide whether a fixed top-edge overlay is suitable: on the tested Northern Audio unit it sat close to the preset title. Confirm display geometry and behavior on every supported view, including other effects and the model browser.
- Run the M4 emulator tests and upstream regression/firmware tests. Check module allocation, timing and pixel ownership during repaints. Test the integrated build from RAM before merging. Do not treat the Northern Audio hardware test as evidence for the extracted module on the upstream build.
- This first contribution deliberately excludes the custom compressor and saturation algorithms; their registry allocation and telemetry integration require separate review.

See [the existing GR meter note](gr-meter.md) and [GR meter standards](../../gr-meter-standards.md).
