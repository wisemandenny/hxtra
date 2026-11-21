"""Looper: the 1 Switch Looper's footswitch (src/m4/looper.s), two settings in Global Settings > Footswitches.

Looper Stop>Ply (Press, Release) says when a press on a stopped loop starts it. Press is stock: it plays at once, so a hold to clear
the loop plays it for a second first. Release, the default, holds the play back to the release: a tap plays the loop as the
footswitch comes up, later than stock by the length of the press, a 1 s hold clears it without playing it, and a quick second press
stops as stock.

Looper DblPress (Release, Stock) says when the double-press window closes. Stock closes it 20 ticks after the first press while the
overdub a press on a playing loop arms starts 21 ticks after its release, so a second press in between neither stops nor comes after
the overdub, and its release arms the overdub again. Release, the default, keeps the window open after a first press's release that
finds the loop playing until that overdub starts (or would), so every second press before it stops; after any other release (of the
press that started recording, or in play once) the window is stock. Every other press, release and hold stays stock, as do the
Shuffling Looper, MIDI CC 60..66 and the Command Center's Looper commands. The looper's code: docs/research/features/looper.md."""
from features import Setting
import patch_menu as pm

FLAG = 'HX_LOOPER'
MENU = 'Footswitches'
SETTINGS = (Setting('stop_play', b'Stop>Ply\nLooper', (b'Press', b'Release'), default=1),  # 0 is the stock behaviour
            Setting('dbl_press', b'DblPress\nLooper', (b'Release', b'Stock')))      # Release first: the fix is on by default

# The 1 Switch Looper's footswitch state machine (switch, event): owned, as a held-back play runs it with another event. The
# footswitch handler's press (0x28dd1444), hold (0x28dd1c6c) and release (0x28dd1d28) are its only calls.
STATE_MACHINE, STATE_MACHINE_STOCK = 0x28d92490, bytes.fromhex('38b5 0d46')     # push {r3-r5,lr}; mov r5,r1


def apply(p):
    hook = p.own_entry(STATE_MACHINE, STATE_MACHINE_STOCK, "the 1 Switch Looper's footswitch state machine")
    m = p.module('src/m4/looper.s')
    a = pm.Asm(p.next())
    a.movw_movt(2, hook.stock | 1)
    a.bw(m['looper_event'])
    hook.to(p.add(a.bytes()))
