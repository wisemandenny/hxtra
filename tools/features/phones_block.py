"""Phones Block: a block that sends its input to the headphones only, and Global Settings > Ins/Outs > Phones Monitor's third value,
HP Block, with which the phones play the Phones blocks and nothing else (tools/patch_phones.py adds the model Send/Return > Phones >
Phones and its DSP code). The block's knobs: Level, what it sends to the phones, and Dry Thru, what goes on down the chain (at
-60 dB each is off: Dry Thru off makes the block a dead end, as a Send block). Main L/R, Send and USB stay as they are; the phones'
Volume knob still sets their level. With Main L/R or Send the phones play as stock and the Phones blocks send nowhere.

Phones Monitor here is a virtual setting in the stock one's slot (REPLACES its ID), with the stock's Main L/R and Send and a third,
HP Block; src/m4/phones_block.s keeps the stock setting in step (HP Block sets it to Main L/R) and sends the mode to the DSP inside
USB Input Trim (USB In 1/2 Trim, I/O setting 0x99), in the code word USB monitoring's mode rides in too: K = U + 5 * H. In a build
with USB monitoring (ORDER after it), src/m4/usb_monitor.s sends the whole word after each send of path A's destination, which it
owns, and this module asks it to send again at a turn (its um_resend); alone, this module chains that send and sends K = 5 * H.
A checkbox in the web page's DSP features (WEB 'dsp': its DSP code takes Block 3 room, tools/block3.py) and HX_PHONES_BLOCK for
build.py."""
from features import Setting

FLAG = 'HX_PHONES_BLOCK'
WEB = 'dsp'
ORDER = 110                         # after usb_monitor, whose um_resend it calls
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
USB_MONITOR = 'src/m4/usb_monitor.s'


def apply(p):
    usb = p.modules.get(USB_MONITOR)
    inc = {'phones_block.inc': f'.equ UM_RESEND, {usb["um_resend"] | 1:#x}\n' if usb else '@ no USB monitoring\n'}
    m = p.module('src/m4/phones_block.s', inc)
    if not usb:
        p.chain_entry(DEST_SEND, DEST_SEND_STOCK, before=m['phones_block_dest_before'], after=m['phones_block_dest_after'])
    p.chain_entry(CHANGED, CHANGED_STOCK, after=m['phones_block_changed'])
    p.chain_entry(PAGE, PAGE_STOCK, after=m['phones_block_page'])
