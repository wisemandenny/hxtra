#!/usr/bin/env python3
"""hx_input.py - the HX Stomp's footswitches, knobs and buttons from this computer, on a build with HX_USB_INPUT=1
(tools/features/usb_input.py).

Each call is one request on HX Edit's editor service (command 0x51), so HX Edit must be closed. The unit queues the events as its
own controls queue theirs (src/m4/usb_input.s), so its UI cannot tell them apart.

  hx_input.py press fs2                 # a click: pressed, then released (fs1..fs5, knob1..knob5, view, action, page_left,
                                        # page_right)
  hx_input.py hold fs1 [--seconds 1.5]  # held: the hold comes after 1 s, as the unit's own
  hx_input.py turn knob3 -4             # four clicks anticlockwise
  hx_input.py touch fs1 [--seconds 1]   # FS1..FS3's touch sensors

A script uses Input(ctl): with an hx_mirror.Session, Input(s.ctl) presses while the mirror records, its calls taking turns with
the frames.
"""
import argparse
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hx_ctl  # noqa: E402
from hx_mirror import STOMP  # noqa: E402

PRESS, RELEASE, RELEASED, HOLD = 1, 2, 3, 5     # key events' types; RELEASED follows a release that came before the hold
HOLD_S = 1.0                                    # every key's hold, docs/research/m4/footswitches.md
CLICK_S = 0.08
GAP_S = 0.05        # between clicks: the queue drops a key event equal to one still in it, so the same press twice needs a gap
MAX = 16            # events a request (src/m4/usb_input.s)


def event(cls, code, value=0):
    """An 8-byte UI event {class, code, 0, 0, value}: a key's type or a knob's clicks."""
    return bytes([cls, code, 0, 0]) + struct.pack('<i', value)


def key(name, typ, part='press'):
    """The key event of control name's press (or its touch) of type typ."""
    try:
        cls, code = STOMP[name][part]
    except KeyError:
        raise ValueError(f'{name} has no {part}: one of ' +
                         ', '.join(n for n in STOMP if part in STOMP[n] and STOMP[n][part][0] == 1)) from None
    if cls != 1:
        raise ValueError(f'{name} is not a key')
    return event(cls, code, typ)


class Input:
    """The controls of the unit an hx_ctl session (or an hx_mirror.Session's s.ctl) talks to."""

    def __init__(self, ctl, sleep=time.sleep):
        self.ctl, self.sleep = ctl, sleep

    def send(self, *events):
        for i in range(0, len(events), MAX):
            self.ctl.send_events(b''.join(events[i:i + MAX]))

    def press(self, name, seconds=CLICK_S):
        """A click of a footswitch, a knob or a button, released before its hold."""
        if seconds >= HOLD_S:
            return self.hold(name, seconds)
        self.send(key(name, PRESS))
        self.sleep(seconds)
        self.send(key(name, RELEASE), key(name, RELEASED))
        self.sleep(GAP_S)

    def hold(self, name, seconds=1.5):
        """Held for seconds (at least HOLD_S): pressed, its hold after HOLD_S, released."""
        self.send(key(name, PRESS))
        self.sleep(HOLD_S)
        self.send(key(name, HOLD))
        self.sleep(max(0.0, seconds - HOLD_S))
        self.send(key(name, RELEASE))
        self.sleep(GAP_S)

    def turn(self, name, clicks):
        """clicks of a knob, clockwise when positive."""
        if not clicks:
            return
        cls, code, sign = STOMP[name]['turn']
        self.send(event(cls, code, clicks * sign))
        self.sleep(GAP_S)

    def touch(self, name, seconds=CLICK_S):
        """A foot on FS1..FS3's touch sensor for seconds."""
        self.send(key(name, PRESS, 'touch'))
        self.sleep(seconds)
        self.send(key(name, RELEASE, 'touch'))
        self.sleep(GAP_S)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Press, hold and turn the HX Stomp\'s controls over USB (a build with HX_USB_INPUT=1).')
    sub = ap.add_subparsers(dest='what', required=True)
    for what in ('press', 'hold', 'touch'):
        a = sub.add_parser(what)
        a.add_argument('control')
        a.add_argument('--seconds', type=float, default=1.5 if what == 'hold' else CLICK_S)
    a = sub.add_parser('turn')
    a.add_argument('control')
    a.add_argument('clicks', type=int)
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args(argv)
    with hx_ctl.HxCtl(verbose=args.verbose) as ctl:
        i = Input(ctl)
        if args.what == 'turn':
            i.turn(args.control, args.clicks)
        else:
            getattr(i, args.what)(args.control, args.seconds)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, hx_ctl.HxError) as e:
        sys.exit(f'hx_input: {e}')
