"""Assemble the XL snapshot prototype into a local, unpacked NAM test archive."""
from pathlib import Path
import argparse
import hashlib
import struct
import sys

WORK = Path(__file__).resolve().parent
ROOT = WORK.parent
sys.path.insert(0, str(WORK / "hxtra" / "tools"))
import hxf_ram
import image_store
import l6ia
import m4asm
import patch_amp
import patch_menu
import xl_play_icons
import xl_virtual_settings
import xl_settings_menu
import xl_tap_ring
import xl_tuner
import xl_bpm
import xl_breathing
import xl_dsp_meter
import xl_hold_tuner
from features import real_names
from PIL import Image, ImageOps
import numpy as np

options = argparse.ArgumentParser(description=__doc__)
options.add_argument("--real-names", action="store_true")
options.add_argument("--application-splash", type=Path)
options.add_argument("--settings-engine", action="store_true")
options.add_argument("--settings-menu", action="store_true")
options.add_argument("--tap-ring", action="store_true")
options.add_argument("--tuner", action="store_true")
options.add_argument("--bpm", action="store_true")
options.add_argument("--breathing-line", action="store_true")
options.add_argument("--dsp-meter", action="store_true")
options.add_argument("--nam-slots", type=int, choices=(2, 3), default=3)
options.add_argument("--hold-tuner", action="store_true")
options.add_argument("--metronome", action="store_true")
options.add_argument("--gr-dsp", action="store_true", help="offline gain-reduction DSP and model test")
options.add_argument("--gr-trace", action="store_true", help="temporary gain reduction diagnostics on Play")
options.add_argument("--gr-play", action="store_true", help="receive and display gain reduction in Play")
options.add_argument("--fx-gate", action="store_true")
options.add_argument("--input-sidechain", action="store_true")
options.add_argument("--usb-routing-dsp", action="store_true", help="offline USB and Send DSP test")
options.add_argument("--usb-routing", action="store_true")
options.add_argument("--preset-color", action="store_true")
options.add_argument("--tap-command", action="store_true")
options.add_argument("--label-color", action="store_true")
options.add_argument("--usb-input", action="store_true")
options.add_argument("--screen-mirror", action="store_true")
options.add_argument("--nam-baseline", type=Path, help="use an explicitly rebuilt NAM intermediate")
options.add_argument("--output", type=Path, help="write to a new archive path")
args = options.parse_args()
if args.preset_color and not args.settings_menu:
    options.error("--preset-color requires --settings-menu")
if args.usb_routing:
    if not args.settings_menu:
        options.error("--usb-routing requires --settings-menu")
    args.usb_routing_dsp = True
if args.gr_trace and not args.gr_play:
    options.error("--gr-trace requires --gr-play")
if args.gr_play:
    args.gr_dsp = True
if args.hold_tuner and not args.settings_menu:
    options.error("--hold-tuner requires --settings-menu")
if args.tap_ring and not args.settings_menu:
    options.error("--tap-ring requires --settings-menu")
if args.tuner and not (args.settings_menu or args.settings_engine):
    options.error("--tuner requires --settings-engine or --settings-menu")
if args.bpm and not args.settings_menu:
    options.error("--bpm requires --settings-menu")
if args.breathing_line and not args.settings_menu:
    options.error("--breathing-line requires --settings-menu")

HOOKS = (
    (0x28df157c, "04f030fa", "xl_hook_read_section_10", "bl"),
    (0x28df183e, "bde8f081", "xl_hook_finish_preset_load", "b"),
    (0x28df1880, "bde8f081", "xl_hook_finish_preset_load", "b"),
    (0x28d9e390, "032940f2a880", "xl_hook_cc69", "b"),
    (0x28df82f4, "f8f706fb", "xl_hook_save_compact", "bl"),
    (0x28df820a, "f8f793fd", "xl_hook_save_alternate", "bl"),
    (0x28df830c, "f8f786fc", "xl_hook_device_save_toc", "bl"),
    (0x28df8222, "f8f7fbfc", "xl_hook_device_save_toc", "bl"),
    (0x28df8160, "fff7aaff", "xl_hook_usb_import", "bl"),
    (0x28e22a02, "cef797f9", "xl_hook_usb_export", "bl"),
    (0x28e22a24, "cef7faf8", "xl_hook_usb_export_toc", "bl"),
    (0x28dd975a, "0ff017ff", "xl_hook_footswitch_previous", "b"),
    (0x28dd992a, "0ff02ffe", "xl_hook_footswitch_next", "b"),
    (0x28e2243a, "c6f7c7fc", "xl_hook_native_snapshot", "bl"),
    (0x28dd5940, "13f044fa", "xl_hook_native_snapshot", "bl"),
    # 0x28e22556 reapplies the active physical slot after an editor update.
    (0x28dc43be, "24f005fd", "xl_hook_native_snapshot", "bl"),
    (0x28dd2008, "16f0e0fe", "xl_hook_native_snapshot", "bl"),
    (0x28deb86c, "fdf7aeba", "xl_hook_native_snapshot", "b"),
    (0x28deb890, "fdf79cba", "xl_hook_native_snapshot", "b"),
    (0x28dd987c, "0ff0a6fa", "xl_hook_snapshot_button", "bl"),
    (0x28dca844, "60f0ccfa", "xl_hook_play_snapshot_set", "bl"),
    (0x28dcbae8, "53f82610", "xl_hook_play_snapshot_lookup", "bl"),
    (0x28dd5532, "55f055fc", "xl_hook_play_snapshot_set", "bl"),
    (0x28dca94c, "60f048fa", "xl_hook_play_snapshot_set", "bl"),
    (0x28dca95e, "60f03ffa", "xl_hook_play_snapshot_set", "bl"),
    (0x28dca96c, "60f038fa", "xl_hook_play_snapshot_set", "bl"),
    (0x28dca97a, "60f031fa", "xl_hook_play_snapshot_set", "bl"),
    (0x28dcf404, "5bf0ecfc", "xl_hook_play_snapshot_set", "bl"),
    (0x28dcf416, "5bf0e3fc", "xl_hook_play_snapshot_set", "bl"),
    (0x28dcf424, "5bf0dcfc", "xl_hook_play_snapshot_set", "bl"),
    (0x28dcf432, "5bf0d5fc", "xl_hook_play_snapshot_set", "bl"),
)

baseline_name = "nam-xl-two-slot.l6ia" if args.nam_slots == 2 else "nam-xl-baseline.l6ia"
baseline = (args.nam_baseline or WORK / baseline_name).read_bytes()
baseline_hashes = {
    2: "ebf672a660be7a5195199cb19e6667213780acc8ce72768c70eec01f711c2503",
    3: "bec3d8f5f2645ecc327d002f856b3231380129686653f67a073bc7e37657ed08",
}
if hashlib.sha256(baseline).hexdigest() != baseline_hashes[args.nam_slots]:
    raise SystemExit(f"{baseline_name}: unexpected NAM baseline SHA-256")
if args.label_color:
    import xl_label_color

    previous_counts = xl_label_color.model_counts(baseline)
if args.metronome or args.gr_dsp or args.fx_gate or args.input_sidechain or args.usb_routing_dsp:
    import patch_click

    layout = patch_click.nam_multi.layout(["--mid-sweep", "--slots", str(args.nam_slots)])
    expected_limit = {2: 0xe743e, 3: 0xe7c1e}
    assert (layout.b3_to, layout.cold_nw) == (expected_limit[args.nam_slots], 0xe7e1e)
    room_tail = layout.cold_nw
if args.metronome:
    baseline, click_info = patch_click.add_click(baseline, layout=layout)
    assert click_info["preset_id"] == 181
    room_tail = patch_click.nam_multi.NW3 + (click_info["pm_base"] - patch_click.nam_multi.NW3) * 3 // 2
if args.fx_gate or args.input_sidechain or args.usb_routing_dsp:
    sys.path.insert(0, str(WORK / "xl-v12" / "tools"))
    if args.fx_gate:
        import patch_gate
    if args.input_sidechain:
        import patch_sidechain
    if args.usb_routing_dsp:
        import patch_usbmon

    for enabled, module, apply_models in (
        (args.fx_gate, "patch_gate", "patch_gate"),
        (args.input_sidechain, "patch_sidechain", "patch_sidechain"),
        (args.usb_routing_dsp, "patch_usbmon", None),
    ):
        if not enabled:
            continue
        patch = sys.modules[module]
        data_words, instructions = patch.dsp_size()
        nw3 = patch_click.nam_multi.NW3
        pm = nw3 + (room_tail - nw3) * 2 // 3
        pm = (pm & ~1) - ((instructions + 1) & ~1)
        room_tail = nw3 + (pm - nw3) * 3 // 2 - data_words
        assert room_tail >= layout.b3_to, f"{module} does not fit beside this NAM kernel"
        baseline = patch.patch_dsp(baseline, (room_tail, pm))
        if apply_models:
            baseline = getattr(patch, apply_models)(baseline)
if args.gr_dsp:
    import patch_comp

    source = (WORK / "xl_gr_frame.asm").read_text(encoding="ascii")
    if args.fx_gate or args.input_sidechain or args.usb_routing_dsp:
        gr_dm, gr_pm = patch_comp.dsp_place(layout, source)
        sections, _ = patch_comp.pa.sasm.assemble(patch_comp.dsp_asm(gr_dm, gr_pm, source), "frame_probe.asm")
        gr_end = max(patch_comp.nw(section.addr + ((len(section.words) + 1) & ~1))
                     for section in sections if section.kind == "pm")
        assert gr_end <= room_tail, "Gain reduction overlaps an upper DSP allocation"
    baseline = patch_comp.patch_dsp(baseline, layout=layout, source=source)
    baseline = patch_comp.patch_comp(baseline)
entry = bytearray(patch_amp.get_entry_swapped(baseline, 0))
segments = patch_amp._parse_e0_segments(entry)
header, payload, size, base, old_end = segments[-1]
assert base == 0x28d92230 and 0 <= len(entry) - old_end <= 3 and not any(entry[old_end:])
assert (base + size) % 4 == 0
code, symbols = m4asm.assemble_module(str(ROOT / "outputs" / "xl-snapshot-persistence.s"))
code_addr = base + size
occupied = set()
written = []
for site, original, symbol, kind in HOOKS:
    expected = bytes.fromhex(original)
    offset = patch_amp._e0_vaddr_to_foff(segments, site, len(expected))
    assert entry[offset:offset + len(expected)] == expected, hex(site)
    region = set(range(offset, offset + len(expected)))
    assert not occupied.intersection(region)
    occupied.update(region)
    written.append((site, site + len(expected), "XL snapshots", symbol))
    target = code_addr + symbols[symbol]
    assert code_addr <= target < code_addr + len(code) and not target & 1
    encode = patch_amp._thumb_bl if kind == "bl" else patch_amp.thumb_bw
    replacement = encode(site, target) + b"\x00\xbf" * ((len(expected) - 4) // 2)
    entry[offset:offset + len(replacement)] = replacement

if args.real_names:
    class ModelNamesPatch(patch_menu.Patch):
        """Model tables support XL; do not enable the Stomp-only menu engine."""

        def __init__(self):
            self.e0 = entry
            self.segs = segments
            self.load = lambda index: patch_amp.get_entry_swapped(baseline, index)
            self.owner = "real names"
            self.written = written

    names_patch = ModelNamesPatch()
    renames = real_names.renames(names_patch)
    assert len(renames) > 200
    real_names.apply(names_patch)
    for row, name in renames.values():
        assert names_patch.read(row + 4, real_names.SHORT).split(b"\0")[0] == name.encode("ascii")
    model_data = real_names.strings(patch_amp.get_entry_swapped(baseline, 3))
    assert all(model_data[i] != "HD2_DistNAMLite" for i in renames)
    print(f"Verified {len(renames)} optional HXtra model-title replacements on the XL.")

tap_targets = (0, 0)
if args.settings_engine or args.settings_menu:
    assert len(code) % 4 == 0
    settings_addr = code_addr + len(code)
    settings_code, settings_symbols, settings = xl_virtual_settings.compile_settings(
        entry, settings_addr, hold_tuner=args.hold_tuner, usb_routing=args.usb_routing,
        active_preset_color=code_addr + symbols["xl_active_preset_color"] if args.preset_color else 0,
        dsp_options=args.dsp_meter
    )
    for name, (site, expected) in xl_virtual_settings.SITES.items():
        offset = patch_amp._e0_vaddr_to_foff(segments, site, 4)
        region = set(range(offset, offset + 4))
        assert not occupied.intersection(region)
        assert entry[offset:offset + 4] == bytes.fromhex(expected)
        occupied.update(region)
        entry[offset:offset + 4] = patch_amp.thumb_bw(site, settings_addr + settings_symbols["virt_" + name])
    code += settings_code
    print(f"Verified 4 additional settings hooks and {len(settings)} setting definitions at {settings_addr:#x}.")
    if args.settings_menu:
        cave = patch_menu.Cave(code_addr + len(code))
        targets = {name: settings_addr + settings_symbols["virt_" + name] for name in ("turn", "click")}
        pages, _ = xl_settings_menu.apply_menu(
            entry, segments, cave, targets, occupied, hold_tuner=args.hold_tuner, usb_routing=args.usb_routing,
            preset_color_enabled=args.preset_color, dsp_options=args.dsp_meter
        )
        code += bytes(cave.buf)
        print(f"XL menu page counts: Footswitches {pages[2]}, Displays {pages[5]}.")
    tap_now = 0
    if args.tap_ring:
        code += b"\0" * (-len(code) % 4)
        tap_base = code_addr + len(code)
        tap_code, tap_symbols = xl_tap_ring.apply_tap_ring(entry, segments, tap_base, occupied)
        code += tap_code
        tap_now = tap_base + tap_symbols["tap_now"]
        tap_targets = tuple((tap_base + tap_symbols[name]) | 1 for name in ("tap_led", "tap_led_again"))
        print(f"Verified XL Tap LED ring branch sites at module address {tap_base:#x}.")
    if args.tuner:
        code += b"\0" * (-(code_addr + len(code)) % 16)
        tuner_base = code_addr + len(code)
        code += xl_tuner.apply_tuner(
            entry, segments, tuner_base, settings_addr + settings_symbols["virt_set"], occupied,
            teal_labels=args.label_color
        )
        print(f"Verified XL tuner controls and page branch sites at module address {tuner_base:#x}.")
    prior_tick = xl_breathing.TICK_STOCK
    if args.bpm:
        code += b"\0" * (-(code_addr + len(code)) % 4)
        bpm_base = code_addr + len(code)
        bpm_code, bpm_symbols = xl_bpm.apply_bpm(entry, segments, bpm_base, tap_now, occupied)
        code += bpm_code
        prior_tick = bpm_base + bpm_symbols["xl_bpm_tick"]
        print(f"Verified XL Play BPM hooks at module address {bpm_base:#x}.")
    if args.breathing_line:
        code += b"\0" * (-(code_addr + len(code)) % 4)
        line_base = code_addr + len(code)
        line_code, line_symbols = xl_breathing.apply_line(entry, segments, line_base, prior_tick, occupied)
        code += line_code
        print(f"Verified XL Edit breathing-line hooks at module address {line_base:#x}.")

prior_edit_paint = xl_breathing.EDIT_PAINT
if args.breathing_line:
    prior_edit_paint = (line_base + line_symbols["xl_line_edit_paint"]) | 1
if args.dsp_meter:
    code += b"\0" * (-(code_addr + len(code)) % 4)
    dsp_base = code_addr + len(code)
    dsp_code, dsp_symbols = xl_dsp_meter.apply_meter(entry, segments, dsp_base, prior_edit_paint, occupied)
    code += dsp_code
    prior_edit_paint = (dsp_base + dsp_symbols["xl_dsp_edit_paint"]) | 1
    print(f"Verified XL DSP meter hooks and cost guards at module address {dsp_base:#x}.")

gr_data = 0
if args.gr_play:
    import xl_gr_play

    prior_play = (bpm_base + bpm_symbols["xl_bpm_paint"]) | 1 if args.bpm else xl_bpm.PLAY_PAINT
    code += b"\0" * (-(code_addr + len(code)) % 4)
    gr_code, gr_data = xl_gr_play.install(
        entry, segments, code_addr + len(code), occupied, prior_play, prior_edit_paint,
        xl_gr_play.compressor_indices(baseline),
        line_base + line_symbols["xl_line_meter_middle"] if args.breathing_line else 0,
        diagnostic=args.gr_trace,
    )
    code += gr_code

if args.hold_tuner:
    code += b"\0" * (-(code_addr + len(code)) % 4)
    hold_base = code_addr + len(code)
    code += xl_hold_tuner.apply_hold(
        entry, segments, hold_base, occupied, code_addr + symbols["xl_step_logical_snapshot"]
    )
    print(f"Verified XL footswitch listener and Hold to Tuner hook at module address {hold_base:#x}.")

if args.usb_routing:
    import xl_usb_routing

    code += b"\0" * (-(code_addr + len(code)) % 4)
    code += xl_usb_routing.install(entry, segments, code_addr + len(code), occupied)

if args.label_color:
    code += b"\0" * (-(code_addr + len(code)) % 4)
    code += xl_label_color.install(entry, segments, code_addr + len(code), occupied, baseline, previous_counts)

if args.tap_command:
    import xl_tap_command

    code += b"\0" * (-(code_addr + len(code)) % 4)
    code += xl_tap_command.install(entry, segments, code_addr + len(code), occupied, tap_targets)

images = [patch_amp.get_entry_swapped(baseline, idx) for idx in (7, 8)]
index, pixels, preview = xl_play_icons.add_play_icons(*images)
if args.preset_color:
    import xl_preset_color

    code += b"\0" * (-(code_addr + len(code)) % 4)
    preset_color_code, index, pixels = xl_preset_color.install(
        entry, segments, code_addr + len(code), occupied, index, pixels,
        code_addr + symbols["xl_active_preset_color"]
    )
    code += preset_color_code
if args.metronome:
    import xl_metronome

    code += b"\0" * (-(code_addr + len(code)) % 4)
    metronome_code, index, pixels = xl_metronome.install(
        entry, segments, code_addr + len(code), occupied, index, pixels
    )
    code += metronome_code

if args.usb_input or args.screen_mirror:
    import xl_usb_dev

    code += b"\0" * (-(code_addr + len(code)) % 4)
    code += xl_usb_dev.install(entry, segments, code_addr + len(code), occupied,
                               usb_input=args.usb_input, mirror=args.screen_mirror,
                               gr_data=gr_data if args.gr_trace else 0)

del entry[old_end:]
entry.extend(code)
code_end = len(entry)
entry.extend(b"\0" * (-len(entry) % 4))
struct.pack_into("<I", entry, 4, len(entry))
struct.pack_into("<III", entry, header, code_end - payload, base, code_end)
entry = l6ia.fix_internal_crcs(entry)
hxf_ram.app_segments(entry)
if args.application_splash:
    from patch_splash import encode

    splash = image_store.image(index, pixels, b"HXStompXL_Splash")
    assert (splash.width, splash.height, splash.bpp) == (320, 181, 16)
    original = pixels[splash.offset:splash.offset + splash.length]
    assert hashlib.md5(original).hexdigest() == "e957b7911c4a01d666a4a8f41ea43dd8"
    with Image.open(args.application_splash) as source:
        oriented = ImageOps.exif_transpose(source).convert("RGBA")
        composite = Image.new("RGBA", oriented.size, "black")
        composite.alpha_composite(oriented)
        picture = ImageOps.fit(composite.convert("RGB"), (320, 181), Image.Resampling.LANCZOS)
    rows = np.asarray(picture).tolist()
    replacement = encode(rows)
    assert len(replacement) == splash.length and replacement != original
    end = splash.offset + splash.length
    pixels = pixels[:splash.offset] + replacement + pixels[end:]
    assert pixels[splash.offset:end] == replacement
    print("Verified optional XL application splash replacement (320 x 181).")
combined, _, _ = l6ia.rebuild_archive(baseline, {0: entry, 7: index, 8: pixels})
for item in l6ia.parse(baseline):
    index = item["index"]
    if index not in (0, 7, 8):
        assert patch_amp.get_entry_swapped(combined, index) == patch_amp.get_entry_swapped(baseline, index)
target_name = "xl-snapshots-nam-two-slot-offline.l6ia" if args.nam_slots == 2 else "xl-snapshots-nam-offline.l6ia"
if args.hold_tuner:
    target_name = target_name.replace("-offline", "-hold-tuner-offline")
if args.metronome:
    target_name = target_name.replace("-offline", "-metronome-offline")
if args.gr_dsp:
    target_name = target_name.replace("-offline", "-gr-play-offline" if args.gr_play else "-gr-dsp-offline")
if args.fx_gate:
    target_name = target_name.replace("-offline", "-fx-gate-offline")
if args.input_sidechain:
    target_name = target_name.replace("-offline", "-input-sidechain-offline")
if args.usb_input:
    target_name = target_name.replace("-offline", "-usb-input-offline")
if args.screen_mirror:
    target_name = target_name.replace("-offline", "-screen-mirror-offline")
if args.label_color:
    target_name = target_name.replace("-offline", "-label-color-offline")
if args.tap_command:
    target_name = target_name.replace("-offline", "-tap-command-offline")
if args.preset_color:
    target_name = target_name.replace("-offline", "-preset-color-offline")
if args.usb_routing_dsp:
    target_name = target_name.replace("-offline", "-usb-routing-offline" if args.usb_routing else "-usb-routing-dsp-offline")
target = args.output or WORK / target_name
with target.open("xb" if args.output else "wb") as archive:
    archive.write(combined)
(WORK / "xl-play-icons-preview.png").write_bytes(preview)
print(f"Verified {len(HOOKS)} non-overlapping hook ranges and appended {len(code)} bytes at {code_addr:#x}.")
print(f"Only Entry 0 and the image stores changed. The {args.nam_slots}-slot NAM DSP code is byte-identical to baseline.")
