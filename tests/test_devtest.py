"""tools/hx_devtest.py: reading the screen's text as Vision gives it, where the UI is, dialling a setting, taps on the clock, and a
run's results and clean-up, against a fake mirror session and a fake OCR."""
import json
import threading
import time

import numpy as np
import pytest

import hx_devtest as dt
import hx_mirror as hm

# What Vision read on the unit (2026-11-13), as (text, x, y, w, h) in screen pixels
HOME = [('97', 0, 3, 20, 14), ('007', 114, 3, 90, 34), ('BAS:Studio Jazz®', 17, 43, 270, 30), ('TUBEDI SMILEY EQ', 15, 143, 190, 18),
        ('TАP/', 240, 131, 50, 18), ('TUNER', 234, 154, 60, 18)]
EDIT = [('007 BAS:Studio Jaz31/75', 6, 6, 300, 16), ('MXR 10-Band EQ', 42, 127, 200, 20), ('0.0dB', 24, 160, 50, 16),
        ('+0.1dB', 233, 160, 60, 16), ('31.25Hz', 8, 205, 70, 16)]
MENU = [('007', 114, 3, 90, 34), ('BAS:Studio Jazz®', 17, 43, 270, 30), ('Menu', 40, 130, 70, 22), ('Global', 22, 190, 60, 18),
        ('Settings', 118, 215, 80, 18)]


def ocr_reply(lines):
    return json.dumps({'lines': [{'text': t, 'conf': 1, 'box': [x / hm.W, y / hm.H, w / hm.W, h / hm.H]} for t, x, y, w, h in lines]})


class FakeOcr:
    """ocr_mac: answers each picture with the next screen's lines (the last one again and again)."""

    def __init__(self, *screens):
        self.screens, self.asked = list(screens), []
        self.stdin, self.stdout = self, self

    def write(self, path):
        self.asked.append(path.strip())

    def flush(self):
        pass

    def readline(self):
        return ocr_reply(self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]) + '\n'

    def close(self):
        pass


class FakeSession:
    """An hx_mirror.Session: a frame each wait, the controls' requests logged with their times."""

    def __init__(self, img=None, modified=(False,)):
        self.frames, self.last, self.events, self.leds = 0, img if img is not None else np.zeros((hm.H, hm.W, 3), np.uint8), [], []
        self.lock = threading.RLock()
        self.sent, self.selected, self.modified = [], [], list(modified)
        self.ctl = self

    def wait(self, seconds):
        self.frames += 1

    def send_events(self, blob):
        self.sent.append((time.monotonic(), self.lock._is_owned(), bytes(blob)))

    def current(self):
        m = self.modified.pop(0) if len(self.modified) > 1 else self.modified[0]
        return {'setlist': 0, 'preset': 7, 'raw': {'117': m}}

    def select(self, preset, setlist):
        self.selected.append((setlist, preset))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def unit(*screens, **kw):
    return dt.Unit(FakeSession(**kw), FakeOcr(*screens))


def test_text_is_compared_as_vision_reads_it():
    assert dt.norm('TАP/') == 'tap/', 'a Cyrillic A'
    assert dt.norm('BAS:Studio Jazz®') == dt.norm('BAS:Studio Jazz#') == 'bas:studiojazz', 'the edited marker'
    assert dt.named('00: Metronome', 'Metronome') and dt.named('≥ Deluxe Comp', 'Deluxe Comp')
    assert not dt.named('Amp+Cab', 'Amp') and not dt.named('1x12 Mesa', 'Mesa')


def test_lines_are_in_screen_pixels_and_found_by_text_pattern_and_region():
    u = unit(EDIT)
    ln = u.find('mxr 10-band')
    assert ln.text == 'MXR 10-Band EQ' and ln.box == pytest.approx((42, 127, 200, 20))
    assert u.find(dt.re.compile(r'\d+/75')).x == pytest.approx(6), 'n/75 merged into the title line'
    assert u.find('+0.1dB', (0, 150, 107, 36)) is None and u.find('+0.1dB', (214, 150, 106, 36))


def test_home_is_the_large_preset_number_without_the_menu():
    assert unit(HOME).at_home()
    assert not unit(EDIT).at_home() and not unit(MENU).at_home()


def test_see_waits_and_fails_with_what_was_on_the_screen():
    u = unit(EDIT, EDIT, HOME)
    assert u.see('tuner').text == 'TUNER'
    with pytest.raises(dt.Fail, match='MXR 10-Band EQ'):
        unit(EDIT).see('tuner', timeout=0)


def test_a_value_is_the_line_above_its_knob_or_read_enlarged():
    u = unit(EDIT)
    assert u.value(1) == '0.0dB' and u.value(3) == '+0.1dB'
    u = unit(EDIT, [('1', 10, 20, 8, 30)])
    assert u.value(2) == '1', 'a lone character: read again enlarged'
    assert u.ocr.asked[-1].endswith('zoom.png')


class Dial(dt.Unit):
    """A setting of values whose knob steps a value a click."""

    def __init__(self, values, at):
        super().__init__(FakeSession(), FakeOcr(HOME))
        self.values, self.at, self.turns = values, at, []

    def value(self, knob):
        return self.values[self.at]

    def turn(self, name, clicks, settle=0):
        self.turns.append(clicks)
        self.at = max(0, min(len(self.values) - 1, self.at + clicks))


def test_dial_turns_toward_the_value_and_returns_the_one_before():
    d = Dial(('Off', 'Steady', 'Breathe', 'Cylon'), 3)
    assert d.dial(2, 'Steady', d.values) == 'Cylon' and d.turns == [-1, -1]
    assert d.dial(2, 'Cylon', d.values) == 'Steady' and d.turns[2:] == [1, 1]
    with pytest.raises(dt.Fail, match='not one of'):
        d.dial(2, 'Off', ('Red', 'Green'))


def test_taps_go_on_the_clock_with_no_frame_between():
    u = unit(HOME)
    dt.taps(u, 'fs3', 600)
    presses = [(t, owned) for t, owned, blob in u.s.sent if blob[4] == 1]
    assert len(presses) == 4 and all(owned for _, owned in presses), 'the session lock held: no frame fetched'
    gaps = np.diff([t for t, _ in presses])
    assert gaps == pytest.approx([0.1] * 3, abs=0.02)
    assert u.s.sent[1][2] == bytes([1, 14, 0, 0, 2, 0, 0, 0, 1, 14, 0, 0, 3, 0, 0, 0])


def test_the_knob_below_a_point_on_the_screen():
    assert [dt.knob_under(x) for x in (0, 106, 107, 213, 214, 319)] == ['knob1', 'knob1', 'knob2', 'knob2', 'knob3', 'knob3']


def test_every_case_has_a_name_and_a_description():
    names = [n for n, _, _ in dt.CASES]
    assert len(names) == len(set(names)) and all(what for _, what, _ in dt.CASES)
    assert {'harness', 'bpm', 'tap_color', 'breathing_line', 'dsp_meter', 'real_names', 'tuner', 'long_press', 'more_snapshots',
            'more_snapshots_tap', 'metronome', 'metronome_bypass', 'nam', 'gr', 'global_eq', 'preset_color'} <= set(names)


def test_teal_is_the_volume_blocks_ring_lit_or_dim_and_not_white_or_grey():
    assert dt.teal(0xb5ce3c) and dt.teal(0x5d6621), 'the Metronome colours as 0xBBGGRR, lit and dim'
    assert not dt.teal(0xffffff) and not dt.teal(0x808080) and not dt.teal(0x0300ff) and not dt.teal(0)


def test_a_ring_is_waited_for_until_it_is_wanted():
    u = unit(HOME)
    seen = iter([[(0xffffff, 1)] * 3, [(0xffffff, 1)] * 3, [(0xb5ce3c, 1)] * 3])
    u.leds = lambda: next(seen)
    assert dt.ring(u, 1, want=lambda c, mode: dt.teal(c)) == (0xb5ce3c, 1)
    u.leds = lambda: [(0xffffff, 1)] * 3
    assert dt.ring(u, 0, timeout=0, want=lambda c, mode: dt.teal(c)) == (0xffffff, 1), 'the last one when time is up'


# Global Settings > Footswitches: FS1..FS3 Hold on one page (FS1 Hold's value reads FS6), FS6..FS8 Function on a later one
HOLD_PAGE = [('Footswitches', 100, 120, 120, 20), ('FS6', 30, 160, 40, 16), ('FS7', 136, 160, 40, 16), ('FS8', 242, 160, 40, 16),
             ('Function', 15, 200, 80, 16), ('FS1 Hold', 15, 218, 80, 16), ('FS2 Hold', 121, 218, 80, 16)]
FUNCTION_PAGE = [('Footswitches', 100, 120, 120, 20), ('Stomp 6', 20, 160, 70, 16), ('Function', 121, 200, 80, 16),
                 ('FS6', 30, 218, 40, 16), ('FS7', 136, 218, 40, 16), ('FS8', 242, 218, 40, 16)]


def test_a_knob_is_found_by_its_label_not_by_a_value_that_reads_the_same():
    u = unit(HOLD_PAGE, HOLD_PAGE, FUNCTION_PAGE)
    assert dt.label_knob(u, 'FS2 Hold') == 2
    assert dt.label_knob(u, 'FS6') == 1, 'FS1 Hold\'s value FS6 is not the label'
    page_right = hm.STOMP['page_right']['press'][1]
    assert [blob[1] for _, _, blob in u.s.sent] == [page_right, page_right], 'one page right: PAGE▶ pressed, then released'
    with pytest.raises(dt.Fail, match='no knob labelled'):
        dt.label_knob(unit(HOLD_PAGE), 'FS9')


def test_a_foot_hold_touches_with_the_press_and_holds_both():
    u = unit(HOME)
    looked = []
    dt.foot_hold(u, 'fs1', look=lambda: looked.append(len(u.s.sent)))
    events = [[(b[i], b[i + 1], b[i + 4]) for i in range(0, len(b), 8)] for _, _, b in u.s.sent]
    assert events == [[(1, 9, 1), (1, 12, 1)], [(1, 9, 5), (1, 12, 5)], [(1, 12, 2), (1, 9, 2)]], 'touch code 9, press code 12'
    assert looked == [2], 'looked at the screen right after the holds'


def test_a_foot_tap_touches_with_the_press_and_lets_go_with_the_release():
    u = unit(HOME)
    dt.foot_tap(u, 'fs2')
    events = [[(b[i], b[i + 1], b[i + 4]) for i in range(0, len(b), 8)] for _, _, b in u.s.sent]
    assert events == [[(1, 10, 1), (1, 13, 1)], [(1, 13, 2), (1, 13, 3), (1, 10, 2)]], 'touch code 10, press code 13'


def test_a_run_reports_each_case_saves_a_failures_screen_and_reloads_the_preset_it_found(tmp_path, monkeypatch):
    s = FakeSession(modified=(False, True))
    monkeypatch.setattr(dt, 'OUT', str(tmp_path))
    monkeypatch.setattr(hm, 'Session', lambda **kw: s)

    real = dt.Unit
    monkeypatch.setattr(dt, 'Unit', lambda session: real(session, FakeOcr(HOME)))

    def bad(u):
        raise dt.Fail('the dot is missing')

    def skip(u):
        raise dt.Skip('no TAP')
    monkeypatch.setattr(dt, 'CASES', [('good', '', lambda u: None), ('bad', '', bad), ('skip', '', skip)])
    results = dt.run()
    assert [(r['case'], r['status'], r['why']) for r in results] == [('good', 'PASS', ''), ('bad', 'FAIL', 'the dot is missing'),
                                                                     ('skip', 'SKIP', 'no TAP')]
    assert (tmp_path / 'bad.png').exists() and not (tmp_path / 'good.png').exists()
    assert json.load(open(tmp_path / 'report.json')) == results
    assert s.selected == [(0, 7)], 'the preset was saved when the run began and edited by its end: loaded again'


def test_cases_that_add_blocks_skip_on_a_preset_with_unsaved_changes():
    u = unit(HOME, modified=(True,))
    u.start = u.saved()
    with pytest.raises(dt.Skip, match='unsaved changes'):
        u.preset()
    u = unit(HOME)
    u.start = u.saved()
    assert u.preset() == (0, 7)


def test_list_and_unknown_cases(capsys):
    assert dt.main(['--list']) == 0
    assert 'more_snapshots' in capsys.readouterr().out
    with pytest.raises(SystemExit, match='no case nope'):
        dt.main(['--only', 'nope'])
