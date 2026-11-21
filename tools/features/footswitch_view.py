"""Footswitch View: a Footswitches screen, as the HX Stomp XL shows its switches. VIEW cycles Play -> Edit -> Footswitches -> Play.
The screen shows the preset's number and name, then two rows of three tiles: FS6 FS7 FS8 above FS1 FS2 FS3. Each tile is lit in its
block's category colour, dimmed while the block is off, with the block's name. FS1..FS3 show what the Play view's own footswitch
labels say. FS6..FS8 are virtual: the blocks whose bypass is assigned to incoming MIDI CC 20, 21 and 22 (Bypass Assign > MIDI In),
for a MIDI foot controller's switches.

The screen is drawn over the Play view (src/m4/footswitch_view.s, after the Play view's two paints), which stays the active view under
it, so the footswitches and knobs work as they do in Play. Leaving it reactivates the Play view (a handler before the view controller),
which redraws it whole. VIEW is read before the key events' post: a press the screen takes is turned into a key no listener knows.

The tiles' names and categories come from the firmware's own model tables at build time (Table 1: name index -> preset model ID,
Table 2: name and category), into PID_INFO: a block added by a later build step (the Metronome, the MIDI and Phones blocks) has
no name there, and its FS6..FS8 tile stays blank."""
import struct

import patch_amp as pa

FLAG = 'HX_FOOTSWITCH_VIEW'
WEB = 'opt-in'

POST, POST_STOCK = 0x28db8830, bytes.fromhex('f8b5 0446')           # (event): every UI event to its listeners; push {r3-r7,lr}; mov r4,r0
CONTROLLER, CONTROLLER_STOCK = 0x28d93db4, bytes.fromhex('2de9 f04f')   # the view controller: push.w {r4-r11, lr}
TOP_PAINT_LIT, TOP_PAINT = 0x28d96d90, 0x28dca359                    # the Play view's top half's paint, as registered
HOME_PAINT_LIT, HOME_PAINT = 0x28d96e28, 0x28dc8d39                  # its bottom half's (the footswitch labels)
TAB1_BASE_PTR, TAB1_CNT_INSN = 0x28e01c08, 0x28e01c74   # Static Model Table: 12-byte rows {name index, preset ID, 0, cost}
TAB2_BASE_PTR, TAB2_CNT_INSN = 0x28de8fd4, 0x28de8f30   # UI Model Info: 44-byte rows {name index, name +4, ..., category +0x15}
PID_MAX = 832


def footswitch_view_info(p):
    """PID_INFO: 20 bytes a preset model ID 0..PID_MAX, its name (16 bytes, NUL-padded) and its block category."""
    tab1 = p.u32(TAB1_BASE_PTR)
    _, n1 = pa._decode_thumb_movw(p.read(TAB1_CNT_INSN, 4))
    pid_of = {}
    for i in range(n1):
        idx, pid, _, _ = struct.unpack('<IHHI', p.read(tab1 + 12 * i, 12))
        pid_of[idx] = pid
    tab2 = p.u32(TAB2_BASE_PTR)
    _, n2 = pa._decode_thumb_movw(p.read(TAB2_CNT_INSN, 4))
    row_of = {}
    for i in range(n2):
        r = p.read(tab2 + 44 * i, 44)
        row_of[struct.unpack_from('<I', r)[0]] = (r[4:20], r[0x15])
    info = bytearray(20 * (PID_MAX + 1))
    for idx, pid in pid_of.items():
        if pid <= PID_MAX and idx in row_of:
            name, cat = row_of[idx]
            info[20 * pid:20 * pid + 16] = name.split(b'\0')[0][:16].ljust(16, b'\0')
            info[20 * pid + 16] = cat
    return bytes(info)


def apply(p):
    info_at = p.add(footswitch_view_info(p))
    m = p.module('src/m4/footswitch_view.s',
                 {'footswitch_view.inc': f'.equ PID_INFO, {info_at:#x}\n.equ PID_MAX, {PID_MAX}\n'})
    p.chain_entry(POST, POST_STOCK, before=m['footswitch_view_post'])
    p.chain_entry(CONTROLLER, CONTROLLER_STOCK, before=m['footswitch_view_controller'])
    p.chain_ptr(TOP_PAINT_LIT, TOP_PAINT, after=m['footswitch_view_paint'])
    p.chain_ptr(HOME_PAINT_LIT, HOME_PAINT, after=m['footswitch_view_paint'])
