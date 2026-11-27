"""Footswitch View: a Footswitches screen, as the HX Stomp XL shows its switches. VIEW cycles Play -> Edit -> Footswitches -> Play.
The screen shows the preset's number and name, then two rows of three tiles: FS6 FS7 FS8 above FS1 FS2 FS3. Each tile is lit in its
block's category colour, dimmed while the block is off, with the block's name. FS1..FS3 show what the Play view's own footswitch
labels say. FS6..FS8 are virtual: the blocks whose bypass is assigned to incoming MIDI CC 20, 21 and 22 (Bypass Assign > MIDI In),
for a MIDI foot controller's switches.

The screen is drawn over the Play view (src/m4/footswitch_view.s, after the Play view's two paints), which stays the active view under
it, so the footswitches and knobs work as they do in Play. Leaving it reactivates the Play view (a handler before the view controller),
which redraws it whole. VIEW is read before the key events' post: a press the screen takes is turned into a key no listener knows.
Leaving Play any other way (the tuner, the Menu) turns the screen off: any event while another screen is up clears it.

The tiles' names and categories come from the firmware's own model tables as they are at run time (Table 1: name index -> preset
model ID, Table 2: name and category; their pointer literals and the movw instructions holding their counts, which every add-model
step keeps up to date), so a block added by a later build step (the Metronome, the MIDI and Phones blocks) has its tile too."""
import patch_amp as pa

FLAG = 'HX_FOOTSWITCH_VIEW'
ORDER = 200                         # after every other Play-view painter (more_snapshots' bank numbers)

POST, POST_STOCK = 0x28db8830, bytes.fromhex('f8b5 0446')           # (event): every UI event to its listeners; push {r3-r7,lr}; mov r4,r0
CONTROLLER, CONTROLLER_STOCK = 0x28d93db4, bytes.fromhex('2de9 f04f')   # the view controller: push.w {r4-r11, lr}
TOP_PAINT_LIT, TOP_PAINT = 0x28d96d90, 0x28dca359                    # the Play view's top half's paint, as registered
HOME_PAINT_LIT, HOME_PAINT = 0x28d96e28, 0x28dc8d39                  # its bottom half's (the footswitch labels)
TAB1_BASE_PTR, TAB1_CNT_INSN = 0x28e01c08, 0x28e01c74   # Static Model Table: 12-byte rows {name index, preset ID, 0, cost}
TAB2_BASE_PTR, TAB2_CNT_INSN = 0x28de8fd4, 0x28de8f30   # UI Model Info: 44-byte rows {name index, name +4, ..., category +0x15}
INC = (f'.equ TAB1_BASE_PTR, {TAB1_BASE_PTR:#x}\n.equ TAB1_CNT_INSN, {TAB1_CNT_INSN:#x}\n'
       f'.equ TAB2_BASE_PTR, {TAB2_BASE_PTR:#x}\n.equ TAB2_CNT_INSN, {TAB2_CNT_INSN:#x}\n')


def apply(p):
    for insn in (TAB1_CNT_INSN, TAB2_CNT_INSN):
        pa._decode_thumb_movw(p.read(insn, 4))     # a movw, as model_row reads it at run time
    m = p.module('src/m4/footswitch_view.s', {'footswitch_view.inc': INC})
    p.chain_entry(POST, POST_STOCK, before=m['footswitch_view_post'])
    p.chain_entry(CONTROLLER, CONTROLLER_STOCK, before=m['footswitch_view_controller'])
    p.chain_ptr(TOP_PAINT_LIT, TOP_PAINT, after=m['footswitch_view_paint'])
    p.chain_ptr(HOME_PAINT_LIT, HOME_PAINT, after=m['footswitch_view_paint'])
