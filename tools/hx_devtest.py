#!/usr/bin/env python3
"""hx_devtest.py - an automated test of each HXtra feature on the HX Stomp, pressing its controls over USB and reading its screen.

It tests the build already running on the unit and never boots, flashes or restarts it. Boot a build with the features to test and
HX_SCREEN_MIRROR=1 HX_USB_INPUT=1 (hxboot), close HX Edit, put the unit on its Home screen in Stomp footswitch mode, then:

  hx_devtest.py                     # every case
  hx_devtest.py --only bpm,tuner    # by case name
  hx_devtest.py --list
  hx_devtest.py --record devtest    # also records the run (build/recordings/devtest.mov, as hx_mirror.py view --record)

Each case starts and ends on the Home screen and puts back every setting it changes; nothing is saved to the unit. A failed case
saves the screen as build/devtest/<case>.png, and the run its results as build/devtest/report.json. Exit status 0 when nothing
failed. macOS only: the screen is read with Vision (tools/mac/ocr_mac.swift, built into build/ocr_mac on first use).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hx_input  # noqa: E402
import hx_mirror as hm  # noqa: E402

ROOT = hm.ROOT
OCR_SRC = os.path.join(ROOT, 'tools', 'mac', 'ocr_mac.swift')
OCR = os.path.join(ROOT, 'build', 'ocr_mac')
OUT = os.path.join(ROOT, 'build', 'devtest')
SCALE = 2                           # Vision reads the screen's small fonts better at twice its size
SETTLE = 0.4                        # after a control, for the UI to redraw
LOOKALIKE = str.maketrans('АВСЕНКМОРТХаеорсху®#', 'ABCEHKMOPTXaeopcxy  ')   # Vision's Cyrillic reads of Latin capitals


class Fail(AssertionError):
    pass


class Skip(Exception):
    pass


def norm(text):
    """text as compared: Vision's lookalikes in Latin, case and spacing ignored."""
    return re.sub(r'\s+', '', text.translate(LOOKALIKE)).lower()


class Line:
    """A line of text on the screen: its box in screen pixels (x, y, w, h) from the top left."""

    def __init__(self, text, box):
        self.text, self.box = text, box
        self.x, self.y, self.w, self.h = box

    @property
    def cx(self):
        return self.x + self.w / 2

    def __repr__(self):
        return f'{self.text!r}@({self.x:.0f},{self.y:.0f})'


def lines_of(found):
    """Lines from ocr_mac's reply, in screen pixels."""
    return [Line(x['text'], (x['box'][0] * hm.W, x['box'][1] * hm.H, x['box'][2] * hm.W, x['box'][3] * hm.H))
            for x in found['lines']]


class Unit:
    """The running HX Stomp: its screen (frames and text), its controls and the way round its menus."""

    def __init__(self, session, ocr=None):
        self.s = session
        self.input = hx_input.Input(session.ctl)
        self.ocr = ocr or subprocess.Popen([hm.build_tool(OCR_SRC, OCR)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        os.makedirs(OUT, exist_ok=True)
        self.shot = os.path.join(OUT, 'screen.png')
        self.start = None

    # -- the screen

    def frame(self):
        """A frame taken after this call: the screen as RGB rows."""
        n = self.s.frames
        end = time.monotonic() + 3
        while self.s.frames <= n + 1:
            if time.monotonic() > end:
                raise Fail('no frame from the unit for 3 s')
            self.s.wait(0.02)
        return self.s.last

    def read(self, img=None):
        """The text on the screen, as Lines."""
        img = self.frame() if img is None else img
        with open(self.shot, 'wb') as f:
            f.write(hm.png(img, SCALE))
        self.ocr.stdin.write(self.shot + '\n')
        self.ocr.stdin.flush()
        return lines_of(json.loads(self.ocr.stdout.readline()))

    def zoom(self, region, scale=6, pad=12):
        """The text in region (x, y, w, h), read enlarged on a black margin: Vision misses a lone character at the screen's size."""
        x, y, w, h = region
        img = np.zeros((h + 2 * pad, w + 2 * pad, 3), np.uint8)
        img[pad:pad + h, pad:pad + w] = self.frame()[y:y + h, x:x + w]
        path = os.path.join(OUT, 'zoom.png')
        with open(path, 'wb') as f:
            f.write(hm.png(img, scale))
        self.ocr.stdin.write(path + '\n')
        self.ocr.stdin.flush()
        return ' '.join(x['text'] for x in json.loads(self.ocr.stdout.readline())['lines'])

    def find(self, text, region=None, lines=None):
        """The first line holding text (a string, or a compiled pattern matched on the normalised line) within region (x, y, w, h)."""
        for ln in lines if lines is not None else self.read():
            if region and not (region[0] <= ln.cx <= region[0] + region[2] and region[1] <= ln.y + ln.h / 2 <= region[1] + region[3]):
                continue
            if (text.search(norm(ln.text)) if isinstance(text, re.Pattern) else norm(text) in norm(ln.text)):
                return ln
        return None

    def see(self, text, region=None, timeout=3.0, what=None):
        """Waits for text on the screen; returns its Line."""
        end = time.monotonic() + timeout
        while True:
            lines = self.read()
            ln = self.find(text, region, lines)
            if ln:
                return ln
            if time.monotonic() > end:
                raise Fail(f'{what or text!r} not on the screen; it shows {lines}')

    def gone(self, text, region=None, timeout=3.0):
        end = time.monotonic() + timeout
        while self.find(text, region):
            if time.monotonic() > end:
                raise Fail(f'{text!r} still on the screen')

    def pixels(self, region, img=None):
        """The RGB pixels of region (x, y, w, h) of a frame."""
        x, y, w, h = region
        return (self.frame() if img is None else img)[y:y + h, x:x + w].astype(int)

    def leds(self):
        """The footswitch rings now: [(0xBBGGRR, mode)] for FS1..FS3."""
        self.frame()
        return self.s.leds[-1][1] if self.s.leds else None

    # -- the controls

    def press(self, name, settle=SETTLE):
        self.input.press(name)
        self.s.wait(settle)

    def hold(self, name, seconds=1.5, settle=SETTLE):
        self.input.hold(name, seconds)
        self.s.wait(settle)

    def turn(self, name, clicks, settle=SETTLE):
        self.input.turn(name, clicks)
        self.s.wait(settle)

    def both_pages(self, settle=SETTLE):
        """PAGE◀ and PAGE▶ at once: the Menu."""
        i = self.input
        i.send(hx_input.key('page_left', hx_input.PRESS), hx_input.key('page_right', hx_input.PRESS))
        self.s.wait(hx_input.CLICK_S)
        i.send(*[hx_input.key(b, t) for t in (hx_input.RELEASE, hx_input.RELEASED) for b in ('page_left', 'page_right')])
        self.s.wait(settle)

    # -- where the UI is

    def at_home(self, lines=None):
        """The Home screen: the preset number large at the top, the Menu's panel not over the bottom half."""
        lines = self.read() if lines is None else lines
        big = any(re.fullmatch(r'\d{3}', norm(ln.text)) and ln.h > 24 and ln.y < 40 for ln in lines)
        return big and not self.find('menu', (0, 120, 160, 30), lines)

    def home(self):
        """Back to the Home screen from the Edit view, the Menu, Global Settings or the tuner."""
        for _ in range(4):
            if self.at_home():
                return
            self.press('view', settle=0.6)
        raise Fail('could not get back to the Home screen')

    def global_settings(self, section):
        """Opens Global Settings at section (its title as the screen shows it)."""
        self.home()
        self.both_pages()
        self.see('menu', (0, 120, 160, 30), what='the Menu')
        tiles = (0, 150, 320, 90)                   # Vision reads a tile's two lines apart: "Global", "Settings"
        for _ in range(3):
            if self.find('settings', tiles):
                break
            self.press('page_right')
        else:
            raise Fail('no Global Settings in the Menu')
        ln = self.see('settings', tiles)
        self.press(knob_under(ln.cx), settle=0.6)
        self.see('global settings', (0, 0, 320, 40))
        self.section(section)

    def section(self, title, steps=16):
        """Steps Global Settings' sections (knob code 3) to title, rightward, wrapping."""
        for _ in range(steps):
            if self.find(title, (0, 115, 320, 35)):
                return
            self.turn('knob4', 1)
        raise Fail(f'no Global Settings section {title!r}')

    def page_to(self, label, steps=6):
        """Pages within a section to the page that has label."""
        for direction in ('page_right', 'page_left'):
            for _ in range(steps):
                if self.find(label, (0, 150, 320, 90)):
                    return
                self.press(direction)
        raise Fail(f'no page with {label!r}')

    def value(self, knob):
        """The value shown above knob 1..3's label, as text."""
        x0 = (knob - 1) * hm.W // 3
        lines = self.read()
        vals = [ln for ln in lines if x0 <= ln.cx < x0 + hm.W / 3 and 150 <= ln.y + ln.h / 2 <= 185]
        text = vals[0].text if vals else self.zoom((x0, 150, hm.W // 3, 36))
        if not text:
            raise Fail(f'no value above knob {knob}; the screen shows {lines}')
        return text

    def dial(self, knob, want, values, steps=40):
        """Turns knob 1..3 a click at a time until its value reads want, values being the setting's values in order; returns the
        value it had."""
        before = self.value(knob)
        for _ in range(steps):
            now = self.value(knob)
            if norm(now) == norm(want):
                return before
            try:
                way = 1 if [norm(v) for v in values].index(norm(want)) > [norm(v) for v in values].index(norm(now)) else -1
            except ValueError:
                raise Fail(f'knob {knob} reads {now!r}, not one of {values}') from None
            self.turn(f'knob{knob}', way, settle=0.25)
        raise Fail(f'knob {knob} did not reach {want!r}')

    # -- blocks and the model browser (knob code 4: its press opens the browser; a turn there changes the block at once)

    def cursor(self):
        """The model browser's selected line: it is drawn bold, so its box has the most lit pixels."""
        img = self.frame()
        rows = [ln for ln in self.read(img) if 40 <= ln.y <= 230 and ln.w > 10]

        def ink(ln):
            x, y, w, h = (max(0, int(v)) for v in ln.box)
            px = img[y:y + h, x:x + w]
            return (px.max(axis=2) > 100).mean() if px.size else 0
        if not rows:
            raise Fail('no list on the screen')
        return max(rows, key=ink)

    def browse(self, *path):
        """In the model browser, down to each name in path in turn and into it; the last one is the model, chosen."""
        for name in path:
            for _ in range(40):
                if named(self.cursor().text, name):
                    break
                self.turn('knob5', 1, settle=0.3)
            else:
                raise Fail(f'no {name!r} in the model browser')
            self.press('knob5', settle=0.8)

    def empty_slot(self):
        """The Edit view, on an empty block."""
        self.home()
        self.press('view', settle=0.6)
        for _ in range(12):
            if self.find('none', (0, 115, 320, 30)):
                return
            self.turn('knob4', 1, settle=0.4)
        raise Fail('no empty block in this preset')

    def saved(self):
        """(setlist, preset) of the preset loaded if it has no unsaved changes, else None."""
        cur = self.s.ctl.current()
        return None if cur['raw'].get('117') else (cur['setlist'], cur['preset'])

    def preset(self):
        """(setlist, preset) of the preset the run began on, which had no unsaved changes: a case that adds blocks loads it again
        after, which also undoes what the cases before it left in the edit buffer (snapshots 4..6, a snapshot's tempo)."""
        if self.start is None:
            raise Skip('the preset had unsaved changes when the run began, which loading it again would lose')
        return self.start

    def reload(self, at):
        """Loads preset at again, as saved: every change since is gone."""
        self.s.ctl.select(at[1], at[0])
        self.s.wait(0.5)
        self.home()


def named(text, name):
    """A browser line is name: whole, so Amp is not Amp+Cab, after the icon's bullet and the model's DSP share as Vision reads
    them ('• ', '00: ')."""
    t, n = norm(text), norm(name)
    return t.endswith(n) and len(t) - len(n) <= 4 and not any(c.isalpha() for c in t[:len(t) - len(n)])


def knob_under(x):
    """The knob below the screen at x."""
    return f'knob{min(3, int(x // (hm.W / 3)) + 1)}'


# -- the cases: each takes a Unit, starts and ends on the Home screen, and raises Fail or Skip

CASES = []


def case(name, what):
    def add(fn):
        CASES.append((name, what, fn))
        return fn
    return add


def tap_footswitch(u):
    """The footswitch whose Home label is TAP/TUNER."""
    ln = u.see('tap', (0, 130, 320, 60), what='a TAP/TUNER footswitch label (Stomp footswitch mode)')
    return f'fs{int(ln.cx // (hm.W / 3)) + 1}'


@case('harness', 'frames come, and an injected VIEW press reaches the UI and its event log')
def t_harness(u):
    u.home()
    seen = len(u.s.events)
    u.press('view', settle=0.6)
    got = [e for _, e in u.s.events[seen:] if e[0] == 1 and e[1] == 5]
    if [e[4] for e in got] != [1, 2, 3]:
        raise Fail(f'VIEW gave events {got}')
    if u.at_home():
        raise Fail('VIEW did not leave the Home screen')
    u.home()


def taps(u, fs, bpm, n=4):
    """n taps of fs at bpm, each press sent on the clock, with no frame fetched meanwhile: a frame holds a request up ~70 ms."""
    with u.s.lock:
        t0 = time.monotonic() + 0.1
        for k in range(n):
            time.sleep(max(0.0, t0 + k * 60 / bpm - time.monotonic()))
            u.input.send(hx_input.key(fs, hx_input.PRESS))
            time.sleep(0.03)
            u.input.send(hx_input.key(fs, hx_input.RELEASE), hx_input.key(fs, hx_input.RELEASED))
    u.s.wait(0.6)


def tempo(u, region):
    """The tempo the Home screen shows at the top left, or 0."""
    ln = u.find(re.compile(r'^\d{2,3}'), region)
    return int(re.match(r'\d+', norm(ln.text)).group()) if ln else 0


@case('bpm', 'BPM Display: the tempo at the top left of Home follows taps; Font Size Off hides it')
def t_bpm(u):
    u.home()
    region = (0, 0, 70, 30)
    ln = u.see(re.compile(r'^(\d{2,3}|--)'), region, what='the tempo at the top left')
    tap = tap_footswitch(u)
    old = int(re.match(r'\d+', ln.text).group()) if re.match(r'\d+', ln.text) else None
    taps(u, tap, 120)
    end = time.monotonic() + 3
    while not 115 <= tempo(u, region) <= 125:
        if time.monotonic() > end:
            raise Fail(f'the tempo reads {tempo(u, region)} after taps 0.5 s apart, not about 120')
    if old:
        taps(u, tap, old)
    font = ('XL', 'L', 'M', 'S', 'Off')
    u.global_settings('BPM Display')
    was = u.dial(1, 'Off', font)
    u.home()
    try:
        u.gone(re.compile(r'^\d{2,3}'), region)
    finally:
        u.global_settings('BPM Display')
        u.dial(1, was, font)
        u.home()


@case('tap_color', 'Tap LED Color: the TAP ring takes the colour picked in Global Settings > Displays')
def t_tap_color(u):
    u.home()
    k = int(tap_footswitch(u)[2]) - 1
    if k > 2:
        raise Skip('TAP is on FS4/FS5, which have no ring')
    colours = ('Red', 'DkOrange', 'LtOrange', 'Yellow', 'Green', 'Teal', 'Blue', 'Violet', 'Pink', 'White', 'Rainbow', 'Random')
    u.global_settings('Displays')
    u.page_to('Tap LED')
    was = u.dial(3, 'Green', colours)
    try:
        u.home()
        end = time.monotonic() + 3
        while True:
            c, _ = u.leds()[k]
            r, g, b = c & 0xff, c >> 8 & 0xff, c >> 16
            if g > 2 * max(r, b):
                break
            if time.monotonic() > end:
                raise Fail(f'the TAP ring is {c:06x} (0xBBGGRR), not green')
            u.s.wait(0.1)
    finally:
        u.global_settings('Displays')
        u.page_to('Tap LED')
        u.dial(3, was, colours)
        u.home()


@case('breathing_line', 'Breathing Line: the Home divider moves; Type Off stills it')
def t_breathing_line(u):
    u.home()
    row = (0, 118, 320, 6)

    def moving():
        a = u.pixels(row)
        u.s.wait(0.5)
        return np.abs(u.pixels(row) - a).sum() > 0
    if not moving():
        raise Fail('the divider does not change in 0.5 s')
    types = ('Off', 'Steady', 'Breathe', 'Cylon', 'Comet', 'Heart', 'Sparkle')
    u.global_settings('Breathing Line')
    was = u.dial(2, 'Off', types)
    try:
        u.home()
        u.s.wait(0.5)
        if moving():
            raise Fail('the divider still moves with Type Off')
    finally:
        u.global_settings('Breathing Line')
        u.dial(2, was, types)
        u.home()


@case('dsp_meter', 'DSP usage display: the Edit view shows the blocks\' total out of 75 at the top right')
def t_dsp_meter(u):
    u.home()
    u.press('view', settle=0.6)
    try:
        u.see(re.compile(r'\d+/75'), what='n/75 in the Edit view')     # Vision reads it on the title's line
    finally:
        u.home()


@case('real_names', 'Real block names: no block in the preset shows a stock title that real names replaces')
def t_real_names(u):
    from features import real_names

    def known(title, among):                # Vision reads the block's icon as a first letter and may cut the title's end
        t = norm(re.sub(r'^\W*\w?\W+(?=\w{3})', '', title)) if re.match(r'^\W*\w?\s', title) else norm(title)
        return len(t) >= 6 and any(a.startswith(t) or t.startswith(a) for a in among)
    stock = [norm(t) for t, r in real_names.BY_TITLE.items() if norm(t) != norm(r)]
    real = [norm(t) for t in real_names.BY_TITLE.values()]
    u.home()
    u.press('view', settle=0.6)
    titles = []
    try:
        for _ in range(8):
            lines = [ln for ln in u.read() if 115 <= ln.y <= 140 and ln.h > 14]     # the title, below the blocks' DSP shares
            titles += [ln.text for ln in lines[:1]]
            u.turn('knob4', 1)
    finally:
        u.home()
    bad = [t for t in titles if known(t, stock) and not known(t, real)]
    if bad:
        raise Fail(f'stock titles shown: {bad}')
    if not any(known(t, real) for t in titles):
        raise Skip(f'no renamed model in this preset (titles {sorted(set(titles))})')


@case('tuner', 'Tuner settings: the tuner\'s third page has Activate and Lock')
def t_tuner(u):
    u.home()
    u.hold(tap_footswitch(u), 1.3, settle=0.8)
    try:
        for _ in range(4):
            if u.find('activate'):
                break
            u.press('page_right')
        u.see('activate', what='the tuner page with Activate')
        u.see('lock')
    finally:
        u.home()


@case('long_press', 'Long press: Footswitches has FS1..FS5 Hold Function and FS6..FS10 Function')
def t_long_press(u):
    u.global_settings('Footswitches')
    try:
        u.page_to('FS1 Hold')
        u.page_to('FS6')
    finally:
        u.home()


@case('more_snapshots', 'More snapshots: in Snapshot mode the lit footswitch again flips to snapshots 4..6 and back')
def t_more_snapshots(u):
    u.home()
    u.press('page_left', settle=0.6)            # the footswitch mode, from Stomp to Snapshot
    try:
        lit = [k for k, (c, mode) in enumerate(u.leds()) if mode and c]
        if not lit:
            raise Fail(f'no lit snapshot footswitch: {u.leds()}')
        fs = f'fs{lit[0] + 1}'
        camera = (262, 0, 58, 40)               # the snapshot's number in the camera icon, which Vision does not read
        a = u.pixels(camera)
        u.press(fs, settle=0.6)
        if np.array_equal(u.pixels(camera), a):
            raise Fail(f'the camera icon did not change when the lit {fs} was pressed again')
        u.press(fs, settle=0.6)
        if not np.array_equal(u.pixels(camera), a):
            raise Fail(f'pressing {fs} once more did not bring snapshots 1..3 back')
    finally:
        u.press('page_right', settle=0.6)
        u.home()


@case('metronome', 'Metronome: Looper > Metronome > Metronome adds the block, Time 1/4, Level -14.0 dB, Accent Off')
def t_metronome(u):
    at = u.preset()
    try:
        u.empty_slot()
        u.press('knob5', settle=0.8)
        u.browse('Looper', 'Metronome', 'Metronome')
        u.see('metronome', (0, 115, 320, 30), what='the Metronome block in the Edit view')
        for knob, want in ((1, '1/4'), (2, '-14.0dB'), (3, 'Off')):
            if norm(u.value(knob)) != norm(want):
                raise Fail(f'knob {knob} reads {u.value(knob)!r}, not {want!r}')
    finally:
        u.reload(at)


@case('nam', 'NAM A2 Lite: Amp > NAM > NAM A2 Lite adds the block; its Model knob reads a whole number')
def t_nam(u):
    at = u.preset()
    try:
        u.empty_slot()
        u.press('knob5', settle=0.8)
        u.browse('Amp', 'NAM', 'NAM A2 Lite')
        u.page_to('Model')
        model = ''
        for _ in range(40):                     # to two digits: Vision does not read a lone one
            model = u.zoom((0, 150, hm.W // 3, 36))
            if len(norm(model)) >= 2:
                break
            u.turn('knob1', 1, settle=0.3)
        if not re.fullmatch(r'\d{2,3}', norm(model)):
            raise Fail(f'Model reads {model!r}, not a whole number')
    finally:
        u.reload(at)


@case('gr', 'GR meter: Dynamics > Mono > Deluxe Comp has Mtr Pos (Middle), Mtr Dir (Normal) and the meter\'s size knob')
def t_gr(u):
    at = u.preset()
    try:
        u.empty_slot()
        u.press('knob5', settle=0.8)
        u.browse('Dynamics', 'Mono', 'Deluxe Comp')
        u.page_to('Mtr Pos')
        for knob, want in ((2, 'Middle'), (3, 'Normal')):
            if norm(u.value(knob)) != norm(want):
                raise Fail(f'knob {knob} reads {u.value(knob)!r}, not {want!r}')
        u.page_to(re.compile(r'mtr(thk|size)'))
    finally:
        u.reload(at)


def run(names=None, record=None, stop=False):
    results = []
    with hm.Session(window=False, record=record, render=False) as s:
        u = Unit(s)
        s.wait(0.5)
        u.start = u.saved()
        for name, what, fn in CASES:
            if names and name not in names:
                continue
            t0 = time.monotonic()
            try:
                fn(u)
                status, why = 'PASS', ''
            except Skip as e:
                status, why = 'SKIP', str(e)
            except Exception as e:  # noqa: BLE001 (every failure is reported, the run goes on)
                status, why = 'FAIL', str(e) if isinstance(e, Fail) else traceback.format_exc(limit=3)
                with open(os.path.join(OUT, f'{name}.png'), 'wb') as f:
                    f.write(hm.png(s.last, SCALE))
                try:
                    u.home()
                except Fail:
                    pass
            results.append({'case': name, 'status': status, 'why': why, 'seconds': round(time.monotonic() - t0, 1)})
            os.write(1, f'{status}  {name:16s} {why}\n'.encode())
            if stop and status == 'FAIL':
                break
        if u.start and not u.saved():
            u.reload(u.start)                   # the preset as saved, as the run found it
        u.ocr.stdin.close()
    with open(os.path.join(OUT, 'report.json'), 'w') as f:
        json.dump(results, f, indent=1)
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description='Test each HXtra feature on the running HX Stomp (HX_SCREEN_MIRROR=1 HX_USB_INPUT=1).')
    ap.add_argument('--only', help='cases, comma-separated')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--record', help='record the run as build/recordings/<name>.mov')
    ap.add_argument('-x', '--stop', action='store_true', help='stop at the first failure')
    args = ap.parse_args(argv)
    if args.list:
        for name, what, _ in CASES:
            print(f'{name:16s} {what}')
        return 0
    names = set(args.only.split(',')) if args.only else None
    unknown = (names or set()) - {n for n, _, _ in CASES}
    if unknown:
        sys.exit(f'hx_devtest: no case {", ".join(sorted(unknown))}')
    record = os.path.join(hm.RECORDINGS, args.record + '.mov') if args.record and os.sep not in args.record else args.record
    results = run(names, record, args.stop)
    failed = [r['case'] for r in results if r['status'] == 'FAIL']
    print(f'{len(results) - len(failed)} of {len(results)} passed or skipped' + (f'; failed: {", ".join(failed)}' if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
