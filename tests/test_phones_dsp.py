"""The Phones block's DSP side (src/sharc/phones.asm, phones_send.asm) in ssim: the phones' gains get the Phones bus while the
mode is on, the writer learns its gain and clears the bus, the code word both the Phones block and USB monitoring ride in USB
Input Trim (K = U + 5 * H) split by the Level gain's control wrapper, and the Phones kernel sends at Level and passes at Dry Thru."""
import random

import pytest

import patch_phones as pp
import patch_amp as pa
import ssim

G132, G133, GPATH = 0xb1000, 0xb1100, 0xb1200     # the phones' two gains' instances, and a block's in the path
W134, W135, KI = 0xb2000, 0xb2100, 0xb3000         # the phones' writers' instances (channel 0, 1), the kernel's
B3, B4, IO, T = 0xb8000, 0xb8100, 0xb9000, 0xb4000
DM, PM = 0xe7a00, 0xe5000
USB_ENV = {'HX_PHONES_BLOCK': '1', 'HX_USB_MONITOR': '1'}


class Dsp:
    def __init__(self, env=None):
        env = {} if env is None else env
        secs, self.S, kpm, kernel = pp.layout(DM, PM, env)
        ksecs, self.K = pa.sasm.assemble(kernel, 'phones_send.asm')
        self.log, self.rnd = [], random.Random(7)
        usb = pp.usb_monitoring(env)
        nxt = usb[1] if usb else pp.PHONES_W_PROC
        self.usb_mode = usb[0] if usb else self.S['C_SINK']
        self.sim = ssim.Sim(hle={self.S['ORIG_80']: self.stub('gain'), nxt: self.stub('writer'),
                                 self.S['ORIG_CTRL_80']: self.stub('ctrl')})
        self.sim.load(secs)
        self.sim.load(ksecs)
        self.sim.wr(W134, 0)
        self.sim.wr(W135, 1)

    def stub(self, tag):
        def f(sim):
            self.log.append((tag, [ssim.b2f(sim.rd(sim.get(0x11) + k)) for k in range(16)] if tag != 'ctrl'
                             else ssim.b2f(sim.rd(sim.R(8)))))
            if sim.pcstk:
                sim.pc = sim.pcstk.pop()
                return True
            return False
        return f

    def regs(self):
        return [self.sim.R(r) for r in range(16)], [self.sim.get(c) for c in range(0x13, 0x30)]

    def call(self, entry, R=None, **kw):
        sim = self.sim
        for c, v in kw.items():
            sim.set({'I0': 0x10, 'I1': 0x11, 'I2': 0x12}[c], v)
        for r in range(16):
            sim.setR(r, self.rnd.getrandbits(32))
        for r, v in (R or {}).items():
            sim.setR(r, v)
        sim.u[ssim.U_MODE1] |= 0x1000000
        before = self.regs()
        sim.call(entry, limit=100000)
        assert not sim.loops and not sim.pcstk
        if entry != self.S['CTRL_80']:
            assert self.regs() == before, 'a process wrapper keeps every register'

    def fill(self, buf, v):
        for k in range(16):
            self.sim.wr(buf + k, ssim.f2b(v + k / 100))

    def block(self, path_gain=False):
        """One block of the root graph as the unit runs it: (a path gain,) the phones' gains 132/133, then the writers 134/135."""
        self.log.clear()
        if path_gain:
            self.fill(B3, 0.75)
            self.call(self.S['ENTRY_80'], I0=GPATH, I1=B3, I2=B3)
        self.fill(B4, 0.5)
        self.call(self.S['ENTRY_80'], I0=G132, I1=B4, I2=B4)
        self.fill(B3, 0.25)
        self.call(self.S['ENTRY_80'], I0=G133, I1=B3, I2=B3)
        self.call(self.S['ENTRY_2AAB'], I0=W134, I1=B3)
        self.call(self.S['ENTRY_2AAB'], I0=W135, I1=B4)
        return [v for t, v in self.log if t == 'gain']

    def ctrl(self, value, pid=1):
        """The control function on value -> (the value the stock function got, PH_MODE, USB monitoring's mode word)."""
        self.sim.wr(T, ssim.f2b(value))
        self.call(self.S['CTRL_80'], R={4: pid, 8: T})
        return ssim.b2f(self.sim.rd(T)), self.sim.rd(self.S['PH_MODE']), self.sim.rd(self.usb_mode)

    def send(self, x, level, dry):
        self.sim.wr(KI + 5, ssim.f2b(level))
        self.sim.wr(KI + 6, ssim.f2b(dry))
        for k in range(16):
            self.sim.wr(IO + k, ssim.f2b(x[k]))
        self.call(self.K['CUSTOM_AMP_ENTRY'], I0=KI, I1=IO, I2=IO)
        return [ssim.b2f(self.sim.rd(IO + k)) for k in range(16)]


def close(a, b, tol=2e-4):
    return all(abs(p - q) < tol for p, q in zip(a, b))


def test_mode_off_the_gains_see_their_own_buffers_and_the_writer_learns_them():
    d = Dsp()
    assert [round(g[0], 4) for g in d.block()] == [0.5, 0.25]
    assert (d.sim.rd(d.S['PH_GAIN']), d.sim.rd(d.S['PH_GAIN'] + 1)) == (G133, G132)


@pytest.mark.parametrize('k, hp', ((5, 0), (10, 1)))
def test_the_phones_blocks_code_alone(k, hp):
    d = Dsp()
    assert d.ctrl(-3.0 + 1000 * k) == (pytest.approx(-3.0, abs=0.01), hp, 0)
    assert d.ctrl(-3.0)[:2] == (-3.0, hp), 'a plain trim keeps the mode'
    assert d.ctrl(2.5, pid=2)[0] == 2.5, 'another pid as it came'


@pytest.mark.parametrize('usb', range(4))
@pytest.mark.parametrize('hp', (0, 1))
def test_with_usb_monitoring_one_word_carries_both(usb, hp):
    d = Dsp(USB_ENV)
    trim, ph, um = d.ctrl(-12.5 + 1000 * (usb + 1 + 5 * (hp + 1)))
    assert (trim, ph, um) == (pytest.approx(-12.5, abs=0.01), hp, usb)


@pytest.mark.parametrize('usb', range(4))
def test_usb_monitorings_word_alone_leaves_the_phones_mode(usb):
    """A build with both before the Phones block's setting is read: K = U only sets USB monitoring's mode."""
    d = Dsp(USB_ENV)
    d.sim.wr(d.S['PH_MODE'], 1)
    assert d.ctrl(4.0 + 1000 * (usb + 1)) == (pytest.approx(4.0, abs=0.01), 1, usb)


def test_beyond_the_codes_goes_as_it_came():
    d = Dsp(USB_ENV)
    assert d.ctrl(15000.0) == (15000.0, 0, 0) and d.ctrl(400.0) == (400.0, 0, 0)


@pytest.mark.parametrize('level, dry', ((-6.0, 0.0), (0.0, -60.0)))
def test_the_kernel_sends_at_level_and_the_phones_gains_take_it(level, dry):
    d = Dsp()
    d.block()                       # the writers learn the phones' gains
    d.ctrl(1000 * 10)
    x = [d.rnd.uniform(-1, 1) for _ in range(16)]
    y = d.send(x, level, dry)
    g, dr = 10 ** (level / 20), (10 ** (dry / 20) if dry > -59.9 else 0)
    assert close(y, [dr * v for v in x])
    bus = [ssim.b2f(d.sim.rd(d.S['PH_BUS'] + k)) for k in range(32)]
    assert close(bus[:16], [g * v for v in x]) and close(bus[16:], [g * v for v in x])
    gains = d.block(path_gain=True)
    assert round(gains[0][0], 4) == 0.75, 'a path gain on the same buffer keeps its own audio'
    assert close(gains[1], [g * v for v in x]) and close(gains[2], [g * v for v in x])
    assert all(d.sim.rd(d.S['PH_BUS'] + k) == 0 for k in range(32)), 'the bus taken, and emptied'


def test_the_units_order_the_blocks_run_after_the_writers():
    """[verified on unit, test14/15]: the blocks run after the writers, so the next block's phones gains get what they sent, once."""
    d = Dsp()
    d.ctrl(1000 * 10)
    d.block()
    x = [d.rnd.uniform(-1, 1) for _ in range(16)]
    d.send(x, 0.0, 0.0)
    gains = d.block()
    assert close(gains[0], x) and close(gains[1], x)
    assert all(abs(a) < 2e-4 for a in d.block()[0]), 'taken once'


def test_mode_off_again_the_phones_get_their_stock_input():
    d = Dsp()
    d.ctrl(1000 * 10)
    d.ctrl(1.0 + 1000 * 5)
    assert d.sim.rd(d.S['PH_MODE']) == 0
    assert [round(g[0], 4) for g in d.block()] == [0.5, 0.25]


def test_with_usb_monitoring_the_writer_calls_its_wrapper():
    usb = pp.usb_monitoring(USB_ENV)
    _, S, _, _ = pp.layout(DM, PM, USB_ENV)
    assert S['NEXT_2AAB'] == usb[1] and pp.layout(DM, PM, {})[1]['NEXT_2AAB'] == pp.PHONES_W_PROC
