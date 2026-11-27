"""USB Monitor: Global Settings > Ins/Outs > Path A Out picks where path A's Output block goes: Main L/R (stock), Send/USB (the
Send bus: the Send jacks and USB 3/4 to the computer), USB Only (USB 3/4 alone, the Send jacks silent) or Main+Snd (Main L/R, and
the Send bus too, on top of what goes there already: issue #93). With Send/USB or USB Only a DAW records and monitors the processed
sound while Main and the phones play only what it sends back on USB 1/2: software monitoring (issue #81). The stock firmware lets only path B reach the Send bus, and only by moving its merge to the end.

src/m4/usb_monitor.s owns the function that sends a path's destination to the DSP: it sends Send for path A's Main, and after it
the setting inside USB Input Trim (trim + 1000 * (mode + 1)), which src/sharc/usb_monitor.asm takes back out into its mode word
(tools/patch_usbmon.py; USB Only silences the Send jacks' writer, Main+Snd adds Main into the Send jacks' words). With the Phones
block (tools/features/phones_block.py) the word carries its Phones Monitor too: trim + 1000 * (mode + 1 + 5 * (HP Block + 1)), and
um_resend sends it again when Phones Monitor turns. A preset saved meanwhile holds Send for path A, which a stock unit refuses on load, leaving path
A on Main. A turn or a reset of the setting sends path A's destination again at once. A checkbox in the web page's DSP features
(WEB 'dsp': its DSP code takes Block 3 room, tools/block3.py) and HX_USB_MONITOR for build.py."""
import features
from features import Setting
import patch_menu as pm

FLAG = 'HX_USB_MONITOR'
WEB = 'dsp'
MENU = 'Ins/Outs'
SETTINGS = (     # Ins/Outs' last empty slot; a label's last line shows on top
    Setting('path_a', b'Out\nPath A', (b'Main L/R', b'Send/USB', b'USB Only', b'Main+Snd')),
)

SEND_FN = 0x28df5760                # (ctx, app, path, value): a path's destination to the DSP, after 0x28e002a8's range check
SEND_FN_STOCK = bytes.fromhex('f0b5 85b0')          # push {r4-r7, lr}; sub sp, #0x14
CHANGED = 0x28dceb30                # (view, ID): the Global Settings slot repaint after a change, stock or virtual
CHANGED_STOCK = bytes.fromhex('70b5 1029')          # push {r4-r6, lr}; cmp r1, #0x10
PAGE = 0x28dce854                   # (view): the Global Settings page repaint, as after a click's reset
PAGE_STOCK = bytes.fromhex('2de9 f047')             # push.w {r4-r10, lr}


def apply(p):
    hook = p.own_entry(SEND_FN, SEND_FN_STOCK, 'the send of a path\'s destination to the DSP')
    phones = any(features.name(f) == 'phones_block' for f in p.mods)     # its mode rides in the same code word (src/sharc/phones.asm)
    m = p.module('src/m4/usb_monitor.s', {'usb_monitor.inc': '.equ UM_PHONES, 1\n' if phones else '@ no Phones block\n'})
    p.chain_entry(CHANGED, CHANGED_STOCK, after=m['um_changed'])
    p.chain_entry(PAGE, PAGE_STOCK, after=m['um_page'])
    a = pm.Asm(p.next())
    a.movw_movt(12, hook.stock | 1)
    a.bw(m['um_send'])
    hook.to(p.add(a.bytes()))
