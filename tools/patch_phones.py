#!/usr/bin/env python3
"""patch_phones.py - the Phones block and HP Block: a block that sends its input to the headphones only.

usage: patch_phones.py <in .hxf | L6IA> <out .hxf | L6IA> [--donor stock.hxf]

Run after tools/patch_amp.py patch, tools/patch_click.py and tools/patch_midi.py, before tools/patch_gate.py and
tools/patch_usbmon.py (build.py does it for HX_PHONES_BLOCK=1 builds). It adds:
  - the model Send/Return > Phones > Phones (Entries 0, 3, 4; preset ID PRESET_ID) on the mono effect host, with the knobs Level
    (what it sends to the phones) and Dry Thru (what goes on down the chain; at -60 dB each is off), and its kernel
    src/sharc/phones_send.asm, which adds its input at Level into the Phones bus;
  - src/sharc/phones.asm: the Level gain 0x80 (process and control functions) and the phones' writer 0x2aab wrapped, so that
    while Global Settings > Ins/Outs > Phones Monitor is HP Block the phones carry the Phones bus, through the Volume knob, and
    nothing else. The mode rides in USB Input Trim (tools/features/phones_block.py, src/m4/phones_block.s), beside USB
    monitoring's in the same code word: in a build with both, this control wrapper takes both modes and the writer wrapper calls
    USB monitoring's (main_send.asm's ENTRY_2AAB), and tools/patch_usbmon.py wraps neither.
Both go in Block 3 where tools/block3.py places them: phones.asm's data, then its code, then the kernel's.
"""
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sharc'))

import block3
import fx_block
import kit_patch_amp as kit
import l6ia
import patch_amp as pa
import patch_usbmon

FLAG = 'HX_PHONES_BLOCK'
SHARC = os.path.join(SCRIPT_DIR, '..', 'src', 'sharc')
WRAP_ASM, KERNEL_ASM = os.path.join(SHARC, 'phones.asm'), os.path.join(SHARC, 'phones_send.asm')
NAME, DISPLAY = 'HD2_Phone', 'Phones'
FOLDER = (17, 'Phones')             # Send/Return > Phones
PRESET_ID = 381                     # fixed for ever: presets store it
DSP_COST = 10
P = fx_block.param
PARAMS = [P(1, 'Level', 5, 3, -60.0, 6.0, 0.0, [('displayType', 'db')]),
          P(2, 'Dry Thru', 6, 3, -60.0, 6.0, 0.0, [('displayType', 'db')])]
GAIN, GAIN_PROC, GAIN_CTRL = 0x80, 0x8d7f5, 0x60f3e2        # the Level gain: process code, control function
PHONES_W, PHONES_W_PROC = 0x2aab, 0x8ce30                   # the phones' writer and its stock process code


def usb_monitoring(env=os.environ):
    """(USB monitoring's mode word, its phones writer wrapper ENTRY_2AAB) in a build with it (tools/patch_usbmon.py), else None."""
    if not env.get(patch_usbmon.FLAG):
        return None
    dm, pm = block3.place(patch_usbmon.FLAG, env)
    _, syms = pa.sasm.assemble(patch_usbmon.dsp_asm(dm, pm), 'usb_monitor.asm')
    return syms['USB_MODE'], syms['ENTRY_2AAB']


def wrap_asm(dm, pm, env=os.environ):
    usb = usb_monitoring(env)
    mode, nxt = (f'{usb[0]:#x}', f'{usb[1]:#x}') if usb else ('C_SINK', f'{PHONES_W_PROC:#x}')
    return (open(WRAP_ASM).read().replace('PH_DM_BASE', f'{dm:#x}').replace('PH_PM_BASE', f'{pm:#x}')
            .replace('@USB_MODE@', mode).replace('@NEXT_2AAB@', nxt))


def layout(dm, pm, env=os.environ):
    """(phones.asm's sections, its symbols, the kernel's PM base, the kernel's text) with phones.asm at dm and pm."""
    secs, syms = pa.sasm.assemble(wrap_asm(dm, pm, env), 'phones.asm')
    n = sum(len(s.words) for s in secs if s.kind == 'pm')
    kpm = pm + n + (n & 1)              # from an even instruction
    kernel = open(KERNEL_ASM).read().replace('@PH_BUS@', f"{syms['PH_BUS']:#x}").replace('KIT_PM_BASE', f'{kpm:#x}')
    return secs, syms, kpm, kernel


def dsp_size():
    """(data words, instructions) of phones.asm and the kernel, the instruction between them that evens the kernel's start counted."""
    secs, _, kpm, kernel = layout(0xe7000, 0xe0000, {})
    return sum(len(s.words) for s in secs if s.kind == 'dm'), kpm - 0xe0000 + fx_block.pm_words(kernel, 'phones_send.asm')


def add_phones(l6ia_bytes, log=print):
    dm, pm = block3.place(FLAG)
    secs, syms, kpm, kernel = layout(dm, pm)
    out, info = fx_block.add_block(l6ia_bytes, NAME, DISPLAY, FOLDER, PRESET_ID, DSP_COST, PARAMS, kernel, 'phones_send.asm',
                                   kpm, log)
    en = l6ia.parse(out)
    e2 = out[en[2]['payload_off']: en[2]['payload_off'] + en[2]['payload_len']]
    ldr = []
    for s in secs:
        ldr += (pa.pack_init_l48 if s.kind == 'pm' else pa.pack_init_l32)(s.addr, s.words)
        log(f"[+] Entry 2: phones.asm {len(s.words)} {'instructions' if s.kind == 'pm' else 'words'} @ {s.kind.upper()} {s.addr:#x}")
    ldr += pa.wrap_primitive(e2, f'{GAIN:#x}:{GAIN_PROC:#x}', syms['ENTRY_80'], (GAIN_CTRL, syms['CTRL_80']))
    ldr += pa.wrap_primitive(e2, f'{PHONES_W:#x}:{PHONES_W_PROC:#x}', syms['ENTRY_2AAB'])
    if usb_monitoring():
        log('[+] Entry 2: with USB monitoring: 0x80\'s control takes its mode too, and the phones writer calls its wrapper')
    out, _, _ = l6ia.rebuild_archive(out, {2: l6ia.swap32(kit.inject_sharc_ldr_blocks(e2, ldr))})
    return out, dict(info, syms=syms)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input')
    ap.add_argument('output')
    ap.add_argument('--donor', help='Stock .hxf of the unit, when input is a raw L6IA and output a .hxf')
    args = ap.parse_args()
    data, is_hxf = kit.load_l6ia_from_any(args.input)
    out, _ = add_phones(data)
    kit.save_l6ia_to_any(out, args.output, donor_hxf=args.input if is_hxf else args.donor)
    print(f"[+] Wrote {args.output}")


if __name__ == '__main__':
    main()
