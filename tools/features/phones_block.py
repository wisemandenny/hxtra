"""Phones Block: a block that sends its input to the headphones only, and Global Settings > Ins/Outs > Phones Monitor's third value,
HP Block, with which the phones play the Phones blocks and nothing else (tools/patch_phones.py adds the model Send/Return > Phones >
Phones and its DSP code). The block's knobs: Level, what it sends to the phones, and Dry Thru, what goes on down the chain (at
-60 dB each is off: Dry Thru off makes the block a dead end, as a Send block). Main L/R, Send and USB stay as they are; the phones'
Volume knob still sets their level. With Main L/R or Send the phones play as stock and the Phones blocks send nowhere.

Phones Monitor here is a virtual setting in the stock one's slot (REPLACES its ID), with the stock's Main L/R and Send and a third,
HP Block; src/m4/phones_block.s keeps the stock setting in step (HP Block sets it to Main L/R) and sends the mode to the DSP inside
USB Input Trim, as USB Monitor sends its own: so the two conflict. Built with HX_PHONES_BLOCK=1 python3 build.py; its DSP code takes Block 3 room (tools/block3.py FEATURES). Not on the setup page yet (WEB False): its model
adds Entry 3 strings, and beside NAM A2 Lite's Entry 3 has room for the MIDI and Phones blocks together but neither beside the
Metronome (build.py E3_MAX; tools/fx_block.py stops such a build), which the page and tools/m4cache.py's combinations don't yet know
about, nor about CONFLICTS."""
from features import Setting

FLAG = 'HX_PHONES_BLOCK'
WEB = False                         # build.py only, for now: see the module's docstring
CONFLICTS = ('usb_monitor',)        # both carry a mode in USB Input Trim and wrap the Level gain's control function
MENU = 'Ins/Outs'
REPLACES = 0x9e                     # Phones Monitor (phonesSelect): HP Block is Main L/R there
SETTINGS = (
    Setting('monitor', b'Monitor\nPhones', (b'Main L/R', b'Send', b'HP Block')),
)

DEST_SEND = 0x28df5760              # (ctx, app, path, value): a path's destination to the DSP
DEST_SEND_STOCK = bytes.fromhex('f0b5 85b0')        # push {r4-r7, lr}; sub sp, #0x14
CHANGED = 0x28dceb30                # (view, ID): the Global Settings slot repaint after a change, stock or virtual
CHANGED_STOCK = bytes.fromhex('70b5 1029')          # push {r4-r6, lr}; cmp r1, #0x10
PAGE = 0x28dce854                   # (view): the Global Settings page repaint, as after a click's reset
PAGE_STOCK = bytes.fromhex('2de9 f047')             # push.w {r4-r10, lr}


def apply(p):
    m = p.module('src/m4/phones_block.s')
    p.chain_entry(DEST_SEND, DEST_SEND_STOCK, before=m['phones_block_dest_before'], after=m['phones_block_dest_after'])
    p.chain_entry(CHANGED, CHANGED_STOCK, after=m['phones_block_changed'])
    p.chain_entry(PAGE, PAGE_STOCK, after=m['phones_block_page'])
