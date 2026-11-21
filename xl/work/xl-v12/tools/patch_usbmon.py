#!/usr/bin/env python3
"""patch_usbmon.py - Path A Out's output modes in the DSP (issues #81 and #93): the mode word and the USB Only mode.

usage: patch_usbmon.py <in .hxf | L6IA> <out .hxf | L6IA> [--donor stock.hxf]

The M4 (tools/features/usb_monitor.py) sends the mode inside USB Input Trim, the app parameter usbInGain0_1, after each send of
path A's destination: trim + 1000 * (mode + 1). The app's parameter map hands that float unchanged to its members [99] and [105]
(blob 0's root members 98 and 104), Level gains 0x80, as pid 1. Blob 1 cannot change at all: any edit hangs the unit at boot
(docs/research/sharc/usb-routing.md).
  Entry 2: src/sharc/usb_monitor.asm in Block 3 where tools/block3.py places it; 0x80's control function keeps the mode in USB_MODE
           and hands the trim on, and the Send jacks' writer 0x2aaa writes silence while it is USB Only; src/sharc/main_send.asm
           after it: while it is Main+Snd the Main jacks' writer 0x2aa8 keeps its samples and the phones' writer 0x2aab, which
           runs after the Send writer, adds them into the Send jacks; USB out's writer 0x2aac adds them into USB 3/4.
"""
import os

import nam_multi
import patch_amp as pa

SHARC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'sharc')
ASM, MAIN_ASM = (os.path.join(SHARC, f) for f in ('usb_monitor.asm', 'main_send.asm'))
FLAG = 'HX_USB_MONITOR'
MODE_MAX = 3                            # 0 Main L/R, 1 Send/USB, 2 USB Only, 3 Main+Snd (DECISIONS.md)
SEND, SEND_PROC = 0x2aaa, 0x8ce36       # the Send jacks' writer and its stock process code
MAIN, MAIN_PROC = 0x2aa8, 0x8ce33       # the Main jacks' writer and its stock process code
PHONES, PHONES_PROC = 0x2aab, 0x8ce30   # the phones' writer and its stock process code
USB_OUT, USB_OUT_PROC = 0x2aac, 0x8ce11 # USB out's writer and its stock process code
GAIN, GAIN_PROC, GAIN_CTRL = 0x80, 0x8d7f5, 0x60f3e2   # the Level gain: process code (unchanged) and control function


def dsp_asm(dm, pm):
    """usb_monitor.asm with its data at dm and its code at pm, main_send.asm's right after each (USB_MODE stays the first word)."""
    um = open(ASM).read().replace('UM_DM_BASE', f'{dm:#x}').replace('UM_PM_BASE', f'{pm:#x}')
    secs, _ = pa.sasm.assemble(um, 'usb_monitor.asm')
    n_dm, n_pm = (sum(len(s.words) for s in secs if s.kind == k) for k in ('dm', 'pm'))
    main_pm = pm + n_pm + (n_pm & 1)    # from an even instruction, as each Block 3 feature starts
    return um + '\n' + open(MAIN_ASM).read().replace('SM_DM_BASE', f'{dm + n_dm:#x}').replace('SM_PM_BASE', f'{main_pm:#x}')


def dsp_size():
    """(data words, instructions) of usb_monitor.asm and main_send.asm, the instruction between them that evens main_send's start
    counted."""
    secs, _ = pa.sasm.assemble(dsp_asm(nam_multi.B3, nam_multi.NW3), 'usb_monitor.asm')
    pm = [s for s in secs if s.kind == 'pm']
    return sum(len(s.words) for s in secs if s.kind == 'dm'), max(s.addr + len(s.words) for s in pm) - min(s.addr for s in pm)


def patch_dsp(l6ia_bytes, placement, log=print):
    """Entry 2: the DSP code at dsp_place(); the Send, Main, phones and USB out writers' process functions and the gain's control
    function entering it."""
    dm, pm = placement
    secs, syms = pa.sasm.assemble(dsp_asm(dm, pm), 'usb_monitor.asm')
    entries = pa.l6ia.parse(l6ia_bytes)
    e2 = l6ia_bytes[entries[2]['payload_off']: entries[2]['payload_off'] + entries[2]['payload_len']]
    ldr = []
    for sec in secs:
        ldr += (pa.pack_init_l48 if sec.kind == 'pm' else pa.pack_init_l32)(sec.addr, sec.words)
        log(f"[+] Entry 2: USB monitor {len(sec.words)} {'instructions' if sec.kind == 'pm' else 'words'} @ {sec.kind.upper()} {sec.addr:#x}")
    ldr += pa.wrap_primitive(e2, f'{SEND:#x}:{SEND_PROC:#x}', syms['ENTRY_2AAA'])
    ldr += pa.wrap_primitive(e2, f'{MAIN:#x}:{MAIN_PROC:#x}', syms['ENTRY_2AA8'])
    ldr += pa.wrap_primitive(e2, f'{PHONES:#x}:{PHONES_PROC:#x}', syms['ENTRY_2AAB'])
    ldr += pa.wrap_primitive(e2, f'{USB_OUT:#x}:{USB_OUT_PROC:#x}', syms['ENTRY_2AAC'])
    ldr += pa.wrap_primitive(e2, f'{GAIN:#x}:{GAIN_PROC:#x}', GAIN_PROC, (GAIN_CTRL, syms['CTRL_80']))
    log(f"[+] Entry 2: the mode word is DM {syms['USB_MODE']:#x}")
    new, _, _ = pa.l6ia.rebuild_archive(l6ia_bytes, {2: pa.l6ia.swap32(pa.inject_sharc_ldr_blocks(e2, ldr))})
    return new
