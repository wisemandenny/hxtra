"""tools/features/more_snapshots.py and src/m4/more_snapshots.s: the module run in unicorn against a fake snapshot manager and stock
select (a flip on the lit snapshot, next and previous across the banks, bank B's defaults and edits, preset load and save, the lock,
the previous snapshot across the banks), the Hold mode's footswitch events (presses held back, clicks, holds, the bank the
footswitches select in and what leaves it alone, the layout's reads and the tick), the number it draws over the snapshot icon in
bank B, and the firmware it builds, its footswitch handler and label layout run in unicorn."""
import os
import struct

import pytest

import features
import patch_amp as pa
import patch_menu as pm
import setting_ids
from features import Setting, long_press, more_snapshots as ms
from firmware import assert_virtual, branch_target, built, built_e0, reader, stock_e0

MODS = features.load()
IDS = setting_ids.by_name()

MGR, CODE, ENGINE = 0x2812c630, 0x28e60000, 0x28e70000
SELECT, RECORD_INIT = 0x28de2f90, 0x28de14b4
LOCK, UNLOCK, MEMCPY, MEMSET = 0x28e24c00, 0x28e24bb0, 0x28e24c78, 0x28e24b78
STREAM, HEADER = 0x28700000, 0x28700100     # a serializer's arguments: it finds the manager itself
WRITE_FN, SINK = 0x28700200, 0x28700300      # the stream's write(context, bytes, length) and its context
SERIALIZE, TOC_WRITE, SECTION_READ, PRESET, PRESET_FLAG = 0x28deacf4, 0x28deabdc, 0x28def9a8, 0x28d92a98, 0x28e026f0
SECTION = 0x2821fcc8                         # section 10's buffer
CONTROLLERS, SWITCHES = 0x741, 0x742
ICON, LABELS, NODE, FB = 0x2812ade8, 0x2812a4bc, 0x28600000, 0x28d1ce98
FS_FUNCTIONS = 0x28128a74                    # footswitch k's function at + 2k: 14 snapshot k (Snapshot mode), 2 stomp, 1 TAP
CAMERAS = {'white': (0x1a0, 0x71, 0x10f), 'red': (0x156, 0x105, 0x4f), 'lit': (0x13, 0x202, 0x12a)}   # Icon_Snapshot1..3, Red, Sel
LABEL_X, LABEL_Y = (53, 160, 267), 100
WIDGET_LOCK, WIDGET_UNLOCK, REDRAW, FILL, TEXT = 0x28e24970, 0x28e24ae8, 0x28db8508, 0x100017e8, 0x28db7aa4
REC, RECS, CUR, PREV, BUSY = 0x260, 0xc, 0x743, 0x744, 0x9a9
VALID, NAME = 0x24b, 0x255            # in a record: set once it holds a sound; its name, 11 bytes
COLOUR, RENAMED = 0x254, 0x24c        # its colour, 0 the default; set once it has a name of its own
STOCK_SELECT = 0x28780000             # stock select as the select hook's stub reaches it: a stand-in, past the hook
SAVE, WRITER = 0x28790000, 0x287a0000  # a preset serializer chained as the build chains both (the save's, HX Edit's), and its write
BANK_SWITCH, FS_MODE, RESELECT = IDS['more_snapshots.bank_switch'], 0x15, 103
HOLD_SEL, TAP_SEL, SNAPSHOT_MODE = 0, 1, 3
VIEW_IS, HOME_GET, LAYOUT, SELECTED_BLOCK = 0x28d96134, 0x28d960f4, 0x28dc87cc, 0x28df0280
HOME, HOME_VIEW, TUNER_VIEW, EDIT_VIEW = 0x2812a05c, 0, 5, 1
OBJ = 0x28730000                      # the handler's object, a stand-in for the unit's 0x28128a80
EVENT, OUT, KEPT = 0x28600400, 0x28600500, 0x28600600     # an event, the getter's out, r4 and r5 after
EVENT_TRAMPOLINE = 0x28750000
PRESS, RELEASE, CLICK, HOLD = 1, 2, 3, 5
PENDING, PENDING_FS, IMMEDIATE, PRESSED = 0x4f, 0x50, 0x6d, 0x78
LISTS_GET, CTRLS_GET, LISTS, CTRLS = 0x28d96084, 0x28d9608c, 0x28128b4c, 0x28125d30    # the footswitch lists, the controllers
FS_LEARNING, CC_LEARNING = 0x28dd87a0, 0x28dde9ec    # (lists), (controllers) -> set while a learn waits
SAVING, VIEW, WRAP, RELAYOUT, PREV6, NONE, STEP, DSP_HELD = 2, 4, 5, 7, 8, 0xff, 3, 9     # in snaps_data
DSP_LOCK, DSP_UNLOCK, DSP_MODEL = 0x28e07844, 0x28e0785c, 0x28449e78   # D, the DSP model's lock: (engine), at [DSP_MODEL] + 8
# What PRESET (0x28d92a98) returns here, the DSP index D's calls take: 0 on the unit, any other value here, so the D stubs can tell
# it came from that call (the ROM would lock address 8 with it); a DSP model, made
DSP_ENGINE, MODEL = 0x28710000, 0x28770000
GET_EDIT_BUFFER = 0x28760000                # HX Edit's Get edit buffer as 0x28e1c55c runs a serializer: D taken around it
LOAD = 0x287b0000                           # a preset load as 0x28df2038 or 0x28df22f8 runs the parser's chain: under D
MANAGERS = []                               # every Manager a test made, for the check that D is let go
STACKS = {'key': 0x8000, 'request': 0x10000, 'transport': 0x18000}     # each task's stack, below the one m4emu's call() takes
HELD, REPOST, LEDS = 10, 11, 12             # in snaps_data: the module's D depth, a held-back 0x2102, the rings to refresh
# Stock's count of held-back editor posts, its one more or one less (0x28d99728), and the post of event 0x2102 (0x28d99888), which
# select makes last, after it lets D go; both posts (and 0x28d99820's) do nothing while the count is above 0
COUNT, QUIET, SELECTED_POST = 0x281caa8c, 0x28d99728, 0x28d99888
SELECTED_EV, SWITCH_EV, BEGIN_EV, COPY_EV = 0x2102, 0x24112, 0x44113, 0x44115    # select's posts: end, footswitch entry, start, copy
LED_REFRESH = ms.LED_REFRESH


def record(i):
    return MGR + RECS + REC * i


def clobber(m, *more):
    """What a ROM call may leave in the caller-saved registers (r1-r3, r12, and the others named): the D stubs and the DSP
    index's getter write junk there, so a caller that needs them kept has to keep them."""
    for i, r in enumerate(('r1', 'r2', 'r3', 'r12', *more)):
        m.reg(r, 0xdead0001 + i)


def bank_a(i):
    """Snapshot i+1's record as a loaded preset has it: a pattern of its own and its name."""
    r = bytearray([0xa0 + i]) * REC
    r[VALID] = 1
    r[NAME:NAME + 11] = f'A{i + 1}'.encode().ljust(11, b'\0')
    return bytes(r)


class Manager:
    """The module in unicorn, with the manager's records, the lock, select doing what stock does to them behind the select hook
    (snaps_selecting, as the build chains it), a serializer behind snaps_saving and snaps_saved, the settings (Snapshot BankSel on
    Tap unless a test sets Hold; Reselect Snapshot unset, so it recalls), the current view, the Home layout, and the footswitch
    event handler's object and its call of snaps_event. D, the DSP model's lock, is the ROM's recursive mutex: an owner (the task
    a test says is running) and a depth; a task that would wait for it stops the emulation (start, resume), and stock select
    waits for it too, as it takes it first (0x28de2fd0). Select posts to the editor as stock does (_post), unless stock's count
    holds the posts back; a post with data takes a block of the event pool, which a test can run out (pool)."""

    def __init__(self, m4emu, at=CODE, bank_switch=TAP_SEL):
        code, self.sym = m4emu.assemble('src/m4/more_snapshots.s', MODS, IDS)
        self.at, self.emu, self.code_end = at, m4emu, at + len(code)
        self.m = m4emu.M4(code, at)
        MANAGERS.append(self)
        self.task, self.d_owner, self.d_depth, self.d_log, self.waiting, self.waits = 'key', None, 0, [], None, []
        self.module_d = 0                   # how many of D's locks are the module's
        self.boot_window = False
        self.posts, self.dropped, self.quiet_log, self.leds = [], [], [], []
        self.pool, self.pool_blocks, self.pool_waits, self.count_kept = None, False, [], 0
        self.select_fails = None            # select's error exits: 'count' through 0x28de326c (the count one less), 'plain' not
        self.m.stub(QUIET, self._quiet)
        self.m.stub(SELECTED_POST, lambda m: self._post(m, SELECTED_EV, True, 'module'))
        self.during_leds = None
        self.m.stub(LED_REFRESH, self._led_refresh)
        self.m.u32(DSP_MODEL, MODEL)
        self.m.stub(DSP_LOCK, self._dsp_lock)
        self.m.stub(DSP_UNLOCK, self._dsp_unlock)
        data = at + self.sym['snaps_data']
        click = (at + self.sym['snaps_click'], at + self.sym['snaps_back'])
        self.m.uc.hook_add(m4emu.unicorn.UC_HOOK_MEM_READ, lambda uc, kind, addr, size, value, _: (
            click[0] <= self.m.reg('pc') < click[1] and self.d_log.append(('click reads SAVING', self.task, self.d_depth))),
            begin=data + SAVING, end=data + SAVING)
        self.m.uc.hook_add(m4emu.unicorn.UC_HOOK_MEM_WRITE, lambda uc, kind, addr, size, value, _: (
            self.d_log.append(('byte 0', self.task, self.d_depth))), begin=data, end=data)
        self.settings = {FS_MODE: SNAPSHOT_MODE, BANK_SWITCH: bank_switch}
        self.view, self.layouts, self.during_layout = HOME_VIEW, [], None
        self.m.stub(pm.GET_VALUE, self._get_value)
        self.m.stub(VIEW_IS, lambda m: m.reg('r0', int(m.reg('r0') == self.view)))
        self.m.stub(HOME_GET, lambda m: m.reg('r0', HOME))
        self.m.stub(LAYOUT, self._layout)
        self.m.stub(SELECTED_BLOCK, lambda m: m.reg('r0', 0x5e1ec7ed ^ m.reg('r0')))
        self.learning = [0, 0]              # Bypass Assign's footswitch learn, and its or Controller Assign's CC learn
        self.m.stub(LISTS_GET, lambda m: m.reg('r0', LISTS))
        self.m.stub(CTRLS_GET, lambda m: m.reg('r0', CTRLS))
        self.m.stub(FS_LEARNING, lambda m: m.reg('r0', self.learning[0] if m.reg('r0') == LISTS else 0xbad))
        self.m.stub(CC_LEARNING, lambda m: m.reg('r0', self.learning[1] if m.reg('r0') == CTRLS else 0xbad))
        for fn, off in ((ms.CUR_GET, CUR), (ms.COLOUR_GET, RECS + COLOUR), (ms.RENAMED_GET, RECS + RENAMED)):
            self.m.stub(fn, lambda m, fn=fn, off=off: m.reg('r0', self._record_byte(m, fn, off)))
        self.m.stub(ms.NAME_GET, lambda m: m.reg('r0', m.reg('r0') + RECS + REC * m.reg('r1') + NAME))
        self.m.load(SELECT, pm.chain_cave(SELECT, STOCK_SELECT, [at + self.sym['snaps_selecting']], []))
        self.m.load(SAVE, pm.chain_cave(SAVE, WRITER, [at + self.sym['snaps_saving']], [at + self.sym['snaps_saved']]))
        self.saved = []                     # the bank live, the current snapshot and bank A's records, as each write saw them
        self.m.stub(WRITER, lambda m: (self.d_held('the write'), self.saved.append((self.bank_b_live(), self.cur(),
                                                                                     [self.rec(i) for i in range(3)])),
                                       m.reg('r0', 1)))
        a = pm.Asm(EVENT_TRAMPOLINE)        # r4 the event, r5 the object, r0 the getter's out, as the handler calls it; r4, r5 after
        a.h(0xb5f8, 0x4604, 0x460d, 0x4610, 0x461f)        # push {r3-r7,lr}; mov r4,r0; mov r5,r1; mov r0,r2; mov r7,r3
        a.bl(at + self.sym['snaps_event'])
        a.h(0x603c, 0x607d, 0xbdf8)                         # str r4,[r7]; str r5,[r7,#4]; pop {r3-r7,pc}
        self.m.load(EVENT_TRAMPOLINE, a.bytes())
        keys = {ms.FILE_KEY: ('more_snapshots', at + self.sym['snaps_key_write'], at + self.sym['snaps_key_found'])}
        engine, self.esym = m4emu.assemble('src/m4/preset_keys.s', MODS, IDS, inc={'preset_keys.inc': pm.preset_keys_inc(keys)})
        self.m.load(ENGINE, engine)
        self.stack_top = m4emu.STACK_TOP
        self.depth, self.selects, self.inits, self.held, self.during_select = 0, [], [], [], None
        self.m.stub(LOCK, self._lock)
        self.m.stub(UNLOCK, self._unlock)
        self.m.stub(MEMCPY, lambda m: m.write(m.reg('r0'), m.read(m.reg('r1'), m.reg('r2'))))
        self.m.stub(MEMSET, lambda m: m.write(m.reg('r0'), bytes([m.reg('r1') & 0xff]) * m.reg('r2')))
        self.m.stub(STOCK_SELECT, self._select)
        self.m.stub(RECORD_INIT, self._init)
        self.written, self.section, self.flag = [], b'', 0
        self.write_held = []                # per write: D held by the task running, once the DSP model is made
        self.m.stub(WRITE_FN, lambda m: (self.written.append(m.read(m.reg('r1'), m.reg('r2'))),
                                         self.write_held.append(self.d_owner == self.task and self.d_depth > 0)))
        self.m.u32(STREAM, SINK)
        self.m.u32(STREAM + 4, WRITE_FN | 1)
        self.m.stub(SERIALIZE, lambda m: m.reg('r0', 5))
        self.m.stub(TOC_WRITE, lambda m: m.reg('r0', 0))
        self.m.stub(PRESET, lambda m: (m.reg('r0', DSP_ENGINE), clobber(m)))
        a = pm.Asm(GET_EDIT_BUFFER)         # 0x28e1c55c: D (0x28e1c566, 0x28e1c56a), the serializer (0x28e1c5b2), D let go
        a.h(0xb510)                         # push {r4,lr}
        a.bl(PRESET)
        a.bl(DSP_LOCK)
        a.movw_movt(0, STREAM)
        a.movw_movt(1, HEADER)
        a.bl(SAVE)
        a.h(0x4604)                         # mov r4,r0
        a.bl(PRESET)
        a.bl(DSP_UNLOCK)
        a.h(0x4620, 0xbd10)                 # mov r0,r4; pop {r4,pc}
        self.m.load(GET_EDIT_BUFFER, a.bytes())
        self.m.stub(PRESET_FLAG, lambda m: m.reg('r0', self.flag))
        self.m.stub(SECTION_READ, self._section)
        self.events = []
        self.m.stub(WIDGET_LOCK, lambda m: self.events.append('widget lock'))
        self.m.stub(WIDGET_UNLOCK, lambda m: self.events.append('widget unlock'))
        self.m.stub(REDRAW, lambda m: self.events.append(('redraw', m.reg('r0'), m.reg('r1'))))
        self.m.stub(FILL, lambda m: self.events.append(('fill', m.reg('r0'), m.reg('r1'), m.reg('r2'), m.reg('r3'),
                                                        *m.stack_args(3))))
        self.m.stub(TEXT, lambda m: self.events.append(('text', m.reg('r0'), m.read(m.reg('r1'), 32).split(b'\0')[0], m.reg('r3'),
                                                        *m.stack_args(5))))     # the renderer draws to the NUL
        self.icon_style = 'white'
        self.camera(ICON, 262, 237, 6, NODE)                             # the top view's, at its stock place
        for i in range(3):
            self.camera(LABELS + 0x24 * i, LABEL_X[i], LABEL_Y, 7, NODE + 0x40 * (i + 1))
        for i in range(3):
            self.m.write(record(i), bank_a(i))
        self.m.u8(MGR + CUR, 0)
        self.m.u8(MGR + PREV, 0)
        self.m.u8(MGR + BUSY, 0)
        self.mode([14, 14, 14])

    def mode(self, functions):
        """The footswitches' functions, as Footswitch Mode sets them."""
        for i, f in enumerate(functions):
            self.m.u8(FS_FUNCTIONS + 2 * i, f)

    def _get_value(self, m):
        pid, out = m.reg('r0'), m.reg('r1')
        if pid in self.settings:
            m.u8(out, 2)
            m.u32(out + 4, self.settings[pid])
            m.reg('r0', 0)
        else:
            m.reg('r0', -1)

    def _record_byte(self, m, fn, off):
        """The stock getters: the current snapshot, or record k's colour, or 1 when it is renamed."""
        if fn == ms.CUR_GET:
            return m.read(m.reg('r0') + CUR, 1)[0]
        v = m.read(m.reg('r0') + REC * m.reg('r1') + off, 1)[0]
        return int(v != 0) if fn == ms.RENAMED_GET else v

    def _led_refresh(self, m):
        self.leds.append((m.reg('r0'), m.reg('r1')))
        if self.during_leds:
            self.during_leds()

    def _layout(self, m):
        assert (m.reg('r0'), m.reg('r1')) == (HOME, 0), 'the Home layout, as the stomp toggle calls it'
        self.layouts.append(self.data(VIEW))
        if self.during_layout:
            self.during_layout()

    def data(self, i, value=None):
        """snaps_data byte i, or set it."""
        at = self.at + self.sym['snaps_data'] + i
        if value is None:
            return self.m.read(at, 1)[0]
        self.m.u8(at, value)

    def armed(self):
        return list(self.m.read(self.at + self.sym['snaps_armed'], 3))

    def event(self, code, kind):
        """The footswitch event handler's call at 0x28dd1986 with event {1, code, -, -, kind}: snaps_event's result is the getter's."""
        self.m.write(EVENT, bytes([1, code, 0, 0]) + struct.pack('<I', kind))
        r0 = self.m.call(EVENT_TRAMPOLINE, EVENT, OBJ, OUT, KEPT)
        assert r0 == 0x5e1ec7ed ^ OUT, "the selected block's getter, with the handler's out, and its result"
        assert struct.unpack('<2I', self.m.read(KEPT, 8)) == (EVENT, OBJ), 'r4 and r5 kept'
        assert self.m.calls(SELECTED_BLOCK)[-1][0] == OUT

    def _section(self, m):
        assert (m.reg('r1'), m.reg('r3'), m.stack_args(1)[0]) == (10, SECTION, 0x5000), 'section 10, as the load reads it'
        m.write(SECTION, self.section)
        m.reg('r0', len(self.section) or -0x2a)

    def _lock(self, m):
        """The manager lock is the same recursive ROM mutex as D; the module never nests it: select takes it after D, so the
        module lets it go before select (which takes D again, nested, then this lock) and takes it only under D itself."""
        assert m.reg('r0') == MGR + 4 and self.depth == 0, 'the manager lock, once'
        self.d_held('the manager lock')
        self.depth += 1

    def _unlock(self, m):
        assert m.reg('r0') == MGR + 4 and self.depth == 1
        self.depth -= 1

    def model(self):
        return self.m.u32(DSP_MODEL)

    def d_held(self, what):
        """D is held by the task running, once the DSP model is made (unless a test makes it during a call: boot_window)."""
        if self.model() and not self.boot_window:
            assert self.d_owner == self.task and self.d_depth > 0, f'{what} under D, the DSP model lock'

    def _dsp_lock(self, m):
        """The ROM mutex (0x10000500): the owner again adds to its depth; another task waits, with no timeout."""
        assert m.reg('r0') == DSP_ENGINE, 'the DSP index, as stock select and Get edit buffer pass it'
        assert self.model(), 'D at the DSP model + 8: never taken before the boot makes the model'
        assert m.reg('sp') % 8 == 0, 'the stack 8-byte aligned at the call'
        if self.d_owner not in (None, self.task):
            self.waiting = self.task
            self.waits.append((self.task, 'D', m.reg('lr') & ~1))
            m.uc.emu_stop()
            return
        self.d_owner, self.d_depth = self.task, self.d_depth + 1
        self.module_d += self._from_module(m)
        self.d_log.append(('lock', self.task, self.d_depth))
        clobber(m, 'r0')

    def _dsp_unlock(self, m):
        assert m.reg('r0') == DSP_ENGINE and m.reg('sp') % 8 == 0
        assert self.d_owner == self.task and self.d_depth > 0, 'D let go by the task that holds it'
        self.d_depth -= 1
        self.module_d -= self._from_module(m)
        assert 0 <= self.module_d <= self.d_depth
        if not self.d_depth:
            self.d_owner = None
        self.d_log.append(('unlock', self.task, self.d_depth))
        clobber(m, 'r0')

    def _from_module(self, m):
        return self.at <= (m.reg('lr') & ~1) < self.code_end

    def module_holds_d(self):
        """The task running holds D through the module's own lock (not only Get edit buffer's or a load's)."""
        return self.d_owner == self.task and self.module_d > 0

    def count(self, value=None):
        """Stock's count of held-back editor posts at 0x281caa8c, or set it (and expect it back there after the test)."""
        if value is None:
            return self.m.u32(COUNT)
        self.m.u32(COUNT, value)
        self.count_kept = value

    def _count(self, on):
        n = self.m.u32(COUNT)
        self.m.u32(COUNT, n + 1 if on else max(n - 1, 0))

    def _quiet(self, m):
        """0x28d99728(on): the count one more, or one less unless it is 0 (a load, an add and a store, no lock): the module changes
        it only while it holds D, which select and the loads hold when they change it."""
        if not self.boot_window:
            assert self.module_holds_d(), "stock's count changed only under the module's D (none before the DSP model is made)"
        self.quiet_log.append((self.task, m.reg('r0')))
        self._count(m.reg('r0'))
        clobber(m, 'r0')

    def _post(self, m, event, data, origin='select'):
        """0x28d99820(event, data) or 0x28d99888 (event 0x2102, which has data): nothing while the count is above 0; else an event
        for the editor's notify listener, the only listener of these events, and with data a block of the pool at 0x28120060 first,
        which the poster waits for while every block is taken (0x28d93b14: no timeout). pool None: blocks enough; a number: the free
        blocks, a wait recorded (task, event, the module's D held) when there is none, and with pool_blocks the poster stops there
        (a wait under the module's D is the dev4 hang: whatever takes D then waits too)."""
        if self.m.u32(COUNT):
            self.dropped.append((event, origin))
            return
        held = self.module_holds_d()
        if data and self.pool is not None:
            if not self.pool:
                self.pool_waits.append((self.task, event, held))
                if self.pool_blocks:
                    self.waiting = self.task
                    self.waits.append((self.task, 'pool', event))
                    m.uc.emu_stop()
                    return
            else:
                self.pool -= 1
        self.posts.append((event, self.task, held, origin, data, self.d_owner == self.task and self.d_depth > 0))

    def _select(self, m):
        """Stock select (0x28de2f90). It takes D first and lets it go last, so it waits while another task holds D. An index above 2
        does nothing and returns -0x2e (0x28de36d0). The current index again recalls it, or with Reselect Snapshot set swaps the
        current and previous ones (0x28de341a..0x28de3426); a new index becomes the current one and the old one the previous one
        (0x28de2ff2, 0x28de2ff6). Both are written before its posts and its error exits. Then 0x44113 with no data (0x28de3006).
        A target never marked valid (+0x24b) is filled from the old record by 0x28de12d4(..., 0) with the count up (0x28de3294..
        0x28de32c4), which leaves it unmarked, so it is filled again next time; 0x44115 unless it is the old one (0x28de32bc);
        no error exit there, and the result is 0 (0x28de32c8). Only a marked target can fail (0x28de3268..0x28de3290: 0x44118 with
        no data, no 0x2102) or post 0x24112 for a footswitch entry that changes (0x28de678e, under its own D). Then, after it
        lets its D go, 0x2102 (0x28de32d8). Its result on a marked target is its last call's, 1 here so a test sees it come back.
        Not modelled: 0x24112 is per footswitch byte against the footswitch manager's live values, not per record; it reads BUSY
        and the old index before it takes D (0x28de2f98, 0x28de2fb4)."""
        mgr, new = m.reg('r0'), m.reg('r1')
        assert mgr == MGR and self.depth == 0, 'select takes the lock itself'
        if self.model() and self.d_owner not in (None, self.task):
            self.waiting = self.task
            self.waits.append((self.task, 'select', new))
            m.uc.emu_stop()
            return
        self.d_log.append(('select', self.task, self.d_depth))
        if self.during_select:
            self.during_select()
        if self.m.read(MGR + BUSY, 1)[0]:
            self.held.append(new)
            m.reg('r0', 0)
            return
        old = self.cur()
        if new > 2:
            self.selects.append((new, old, self.rec(old), self.rec(new)))
            m.reg('r0', -0x2e)
            return
        if new == old and self.settings.get(RESELECT):
            new = self.prev()
        self.selects.append((new, old, self.rec(old), self.rec(new)))
        if new != old:
            m.u8(MGR + PREV, old)
        m.u8(MGR + CUR, new)
        self._post(m, BEGIN_EV, False)
        if not self.rec(new)[VALID]:
            self._count(1)
            if old <= 2:
                self._fill(m, new, old)
            if new != old:
                self._post(m, COPY_EV, True)
            self._count(0)
            self._post(m, SELECTED_EV, True)
            m.reg('r0', 0)
            return
        if self.select_fails:               # 0x28de326c or 0x28de3272..0x28de3290: 0x44118 with no data, no 0x2102
            if self.select_fails == 'count':
                self._count(0)
            self._post(m, 0x44118, False)
            m.reg('r0', -4)
            return
        if self.rec(new)[0x1e8:0x1e8 + 9] != self.rec(old)[0x1e8:0x1e8 + 9]:
            self._post(m, SWITCH_EV, True)
        self._post(m, SELECTED_EV, True)
        m.reg('r0', 1)

    def _fill(self, m, to, frm):
        """0x28de12d4(manager, to, from, 0): the block states (+0x00..0x13), the controller entries (+0x741 of them, 7 bytes apart
        from +0x28, each with the 8 bytes after its key), the footswitch entries (+0x742, 9 bytes apart from +0x1e8) and the tempo
        (+0x250); not the valid byte, the name, the renamed byte or the colour."""
        src, dst = self.rec(frm), bytearray(self.rec(to))
        dst[0:0x14] = src[0:0x14]
        for i in range(self.m.read(MGR + CONTROLLERS, 1)[0]):
            at = 0x28 + 7 * i
            dst[at:at + 9] = src[at:at + 9]
        for i in range(self.m.read(MGR + SWITCHES, 1)[0]):
            at = 0x1e8 + 9 * i
            dst[at:at + 9] = src[at:at + 9]
        dst[0x250:0x254] = src[0x250:0x254]
        m.write(record(to), bytes(dst))

    def _init(self, m):
        """0x28de14b4(manager, record, name): not valid, not renamed, tempo 120, the default colour, the controller entries' keys
        0x40 and the footswitch entries' keys 0x0d (0x28de14c8..0x28de154c), and the name. The block states it clears are left
        alone here: the module zeroes the bank first."""
        assert m.reg('r0') == MGR and self.depth == 0, 'the record defaults take the lock themselves'
        self.d_held('the record defaults, which take the manager lock and then D (0x28de14c2, 0x28e04044),')
        rec, name = m.reg('r1'), m.read(m.reg('r2'), 11)
        self.inits.append(name.rstrip(b'\0'))
        m.write(rec + VALID, b'\0\0')
        m.write(rec + 0x250, struct.pack('<f', 120.0))
        m.write(rec + COLOUR, b'\0')
        for i in range(64):
            m.write(rec + 0x28 + 7 * i, b'\x40')
        for i in range(11):
            m.write(rec + 0x1e8 + 9 * i, b'\x0d')
        m.write(rec + NAME, name)

    def camera(self, w, x, y, anchor, node):
        """A visible 52x35 camera image widget."""
        for off, v in ((0xc, x), (0x10, y), (0x14, 52), (0x18, 35), (0x20, node)):
            self.m.u32(w + off, v)
        self.m.u8(w + 0x1c, anchor)
        self.m.u8(w + 0x1d, 1)

    def rec(self, i):
        return self.m.read(record(i), REC)

    def read_busy(self):
        return self.m.read(MGR + BUSY, 1)[0]

    def cur(self):
        return self.m.read(MGR + CUR, 1)[0]

    def prev(self):
        return self.m.read(MGR + PREV, 1)[0]

    def name(self, i):
        return self.rec(i)[NAME:NAME + 11].rstrip(b'\0')

    def press(self, i):
        """The footswitch for snapshot i+1 (i 0..2), as the snapshot action calls select."""
        return self.m.call(self.at + self.sym['snaps_select'], MGR, i)

    def call(self, sym, *args):
        return self.m.call(self.at + self.sym[sym], *args)

    def engine(self, sym, *args):
        """src/m4/preset_keys.s's handler sym, the preset file's write and read, with this module's key on it."""
        return self.m.call(ENGINE + self.esym[sym], *args)

    def step(self, way, source='fs'):
        """Next (+1) or previous (-1) as stock does it: the footswitch functions read the current snapshot, wrap it in 0..2 and call
        select; CC 69 reads it straight, and calls the manager getter only where it wraps."""
        if source == 'fs':
            cur = self.call('snaps_next_cur' if way > 0 else 'snaps_prev_cur', MGR)
            assert cur == self.cur(), 'the current snapshot, as the stock read returns it'
            return self.call('snaps_select', MGR, (cur + way) % 3)
        cur = self.cur()
        mgr = MGR
        if cur == (2 if way > 0 else 0):
            mgr = self.call('snaps_cc_wrap')
            assert mgr == MGR, 'the manager, as the stock getter returns it'
        return self.call('snaps_cc_select', mgr, (cur + way) % 3)

    def cc(self, value):
        """CC 69 with value 0..5: the manager getter, then select of the value."""
        assert self.call('snaps_cc_value') == MGR, 'the manager, as the stock getter returns it'
        return self.call('snaps_cc_select', MGR, value)

    def go(self, i):
        """Snapshot i in the live bank: select, unless it's lit."""
        if self.cur() != i:
            self.m.call(SELECT, MGR, i)
        self.selects.clear()

    def bank_b_live(self):
        return self.m.read(self.at + self.sym['snaps_data'], 1)[0] == 1

    def read_section(self):
        """The load's read of section 10: (file, 10, 0, buffer) and the buffer's size on the stack."""
        self.m.u32(self.stack_top, 0x5000)
        return self.engine('pk_section', 0x28720000, 10, 0, SECTION)

    def paint(self, view='top', lit=None):
        """The top view's (or Home view's) paint, then the module after it, with the cameras as stock sets them for the current
        snapshot (the labels for lit, 0xff none, if given); what the module did, and which camera nodes it marked to draw (0 the
        top icon, 1..3 the labels)."""
        cur = self.cur()
        lit = cur if lit is None else lit
        self.m.u32(ICON, CAMERAS[self.icon_style][cur])
        for i in range(3):
            self.m.u32(LABELS + 0x24 * i, CAMERAS['lit' if i == lit else 'white'][i])
        self.events.clear()
        for n in range(4):
            self.m.u8(NODE + 0x40 * n + 0x24, 0)
        self.m.write(self.stack_top - 0x400, b'\xaa' * 0x400)     # a stack that is not zeroed, as on the unit
        sym, view_at = ('snaps_paint', 0x2812aae0) if view == 'top' else ('snaps_home_paint', 0x2812a05c)
        self.m.call(self.at + self.sym[sym], FB, view_at)
        return self.events, [n for n in range(4) if self.m.read(NODE + 0x40 * n + 0x24, 1)[0]]

    def obj(self, off, value=None):
        """The handler's object's byte at off, or set it."""
        if value is None:
            return self.m.read(OBJ + off, 1)[0]
        self.m.u8(OBJ + off, value)

    def dispatch(self, k):
        """The function dispatch for footswitch k, as far as Snapshot mode goes: function 14 selects snapshot k while it is pressed."""
        if self.m.read(FS_FUNCTIONS + 2 * k, 1)[0] == 14 and self.obj(PRESSED + k):
            self.call('snaps_select', MGR, k)

    def fs_press(self, k):
        """A press of footswitch k: the hook, then what stock does with it (0x28dd19f8..0x28dd1a9c, 0x28dd1fd2, 0x28dd2040)."""
        self.event(12 + k, PRESS)
        if self.view == TUNER_VIEW:
            return
        self.obj(PRESSED + k, 1)
        if self.settings[FS_MODE] not in (2, 3) or self.obj(IMMEDIATE):
            return self.dispatch(k)
        if not self.obj(PENDING):
            self.obj(PENDING, 1)
            self.m.u32(OBJ + PENDING_FS, k)
            return
        if self.m.u32(OBJ + PENDING_FS) == k:
            return
        self.obj(PENDING, 0)
        pressed = [self.obj(PRESSED + i) for i in range(3)]
        if pressed[:2] == [1, 1] or pressed == [0, 1, 1]:
            self.settings[FS_MODE] = 2              # the combo: Preset mode, its bank view
            self.mode([5, 6, 3])

    def fs_fire(self):
        """The press's 30-tick timer, then its deferred dispatch (0x28dd048c, 0x28dd18b0)."""
        if self.obj(PENDING):
            self.obj(PENDING, 0)
            k = self.m.u32(OBJ + PENDING_FS)
            self.dispatch(k)
            self.obj(PRESSED + k, 0)

    def fs_release(self, k):
        self.event(12 + k, RELEASE)
        if self.obj(PRESSED + k):
            self.obj(PRESSED + k, 0)
            self.dispatch(k)

    def fs_click(self, k):
        self.event(12 + k, CLICK)

    def fs_hold(self, k):
        self.event(12 + k, HOLD)
        self.obj(PRESSED + k, 0)

    def tap(self, k):
        """Footswitch k tapped for longer than the 30-tick window: its press waits, is dispatched, then released."""
        self.fs_press(k)
        self.fs_fire()
        self.fs_release(k)
        self.fs_click(k)

    def hold_fs(self, k):
        """Footswitch k held for 1 s, then let go: no click after a hold."""
        self.fs_press(k)
        self.fs_fire()
        self.fs_hold(k)
        self.event(12 + k, RELEASE)

    def tick(self):
        self.call('snaps_tick', 0, OBJ)

    def save(self):
        """A preset serializer through its chain: a save on the unit, or HX Edit's Get edit buffer (command 0x16)."""
        assert self.m.call(SAVE, STREAM, HEADER) == 1, "the serializer's result"

    def start(self, task, fn, *args, top=None, until=None):
        """task runs fn(args) on its own stack (top) until it returns (-> None), waits for D, or reaches until (-> its state, for
        resume)."""
        for i, a in enumerate(args):
            self.m.reg(f'r{i}', a)
        top = top or self.stack_top - STACKS[task]
        self.m.reg('sp', top)
        self.m.reg('lr', self.emu.RETURN | 1)
        return self._run(task, fn, top, until)

    def resume(self, state, until=None):
        task, ctx, top = state
        self.m.uc.context_restore(ctx)
        return self._run(task, self.m.reg('pc'), top, until)

    def _run(self, task, at, top, until):
        uc, reached = self.m.uc, []
        self.task, self.waiting, self.m.stray = task, None, None

        def stop(uc, addr, size, data):
            if not reached:
                reached.append(addr)
                uc.emu_stop()
        hook = until and uc.hook_add(self.emu.unicorn.UC_HOOK_CODE, stop, begin=until, end=until)
        uc.emu_start(at | 1, self.emu.RETURN, count=self.emu.STEPS)
        if hook:
            uc.hook_del(hook)
        assert self.m.stray is None, f'ran {self.m.stray:#x}, outside the code and the stubs'
        if self.waiting or reached:
            return task, uc.context_save(), top
        assert self.m.reg('pc') == self.emu.RETURN and self.m.reg('sp') == top, f'{task} returned, its stack balanced'
        self.task = 'key'
        return None

    def at_snapshot(self):
        """1..6: the live one."""
        return self.cur() + 3 * self.bank_b_live() + 1


@pytest.fixture(autouse=True)
def d_let_go():
    """After every test, D is free again in every Manager it made: each lock had its unlock. No post with data (one that waits for
    a free block of the event pool) was made while the module held D, stock's count is back where the test left it, and no
    held-back post of 0x2102 is left over."""
    MANAGERS.clear()
    yield
    for m in MANAGERS:
        assert (m.d_owner, m.d_depth, m.module_d) == (None, 0, 0), f'D still held: {m.d_log[-6:]}'
        assert m.data(HELD) == 0 and m.data(REPOST) == 0
        assert not [p for p in m.posts if p[2] and p[4]], f'a post that waits for the pool under the module\'s D: {m.posts}'
        assert m.count() == m.count_kept, "stock's count of held-back posts back where it was"


@pytest.fixture
def mgr(m4emu):
    return Manager(m4emu)


@pytest.fixture
def hm(m4emu):
    """Snapshot BankSel on Hold, as a unit that never stored it reads."""
    m = Manager(m4emu, bank_switch=HOLD_SEL)
    del m.settings[BANK_SWITCH]
    return m


def test_a_snapshot_not_lit_goes_straight_to_select(mgr):
    assert mgr.press(1) == 1
    assert mgr.selects == [(1, 0, bank_a(0), bank_a(1))] and mgr.cur() == 1 and mgr.prev() == 0
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)] and mgr.inits == []


@pytest.mark.parametrize('lit', [0, 1, 2])
def test_the_lit_snapshot_again_flips_to_bank_b(mgr, lit):
    """Bank B's three records start as defaults named SNAPSHOT 4-6; select comes from the sound being left, so the new one takes it
    (its block states and tempo, unmarked: select's result for a fill is 0)."""
    mgr.m.u8(MGR + CUR, lit)
    mgr.m.u8(MGR + PREV, 2 - lit)
    assert mgr.press(lit) == 0
    assert mgr.inits == [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6']
    (new, old, old_rec, new_rec), = mgr.selects
    assert new == lit and old != lit, 'a select of another index, so it recalls rather than reselects'
    assert old_rec == bank_a(lit), 'the record select comes from is the sound being left'
    assert not new_rec[VALID] and new_rec[NAME:NAME + 10] == f'SNAPSHOT {lit + 4}'.encode()
    rec = mgr.rec(lit)
    assert rec[:0x14] == bank_a(lit)[:0x14] and rec[0x250:0x254] == bank_a(lit)[0x250:0x254] and not rec[VALID]
    assert mgr.name(lit) == f'SNAPSHOT {lit + 4}'.encode()
    assert [mgr.name(i) for i in range(3)] == [f'SNAPSHOT {i + 4}'.encode() for i in range(3)]
    assert mgr.cur() == lit and mgr.prev() == lit, 'the previous snapshot is the new one: the one before it is in bank A'
    assert mgr.depth == 0


def test_a_second_press_flips_back_with_both_banks_kept(mgr):
    mgr.press(0)
    edited = bytearray(mgr.rec(0))
    edited[5] = 0x55                                    # an edit on snapshot 4, which marks its record valid
    edited[VALID] = 1
    mgr.m.write(record(0), edited)
    mgr.selects.clear()
    mgr.press(0)
    (new, old, old_rec, new_rec), = mgr.selects
    assert (new, old_rec, new_rec) == (0, bytes(edited), bank_a(0)), 'snapshot 1 again, from snapshot 4 with its edit'
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)]
    mgr.press(0)
    assert mgr.rec(0) == bytes(edited), 'snapshot 4 keeps its edit'
    assert mgr.inits == [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6'], 'bank B is set up once a preset'


def test_a_bank_b_snapshot_never_edited_takes_the_sound_it_comes_from_each_time(mgr):
    """As stock's unused snapshots: select fills an unmarked record from the one it leaves and leaves it unmarked, so snapshot 4,
    made from 1 and not edited, comes from 6 (made from 3) as 3's sound. An edit marks it, and then it keeps its own."""
    mgr.press(0)                                        # 4, from 1
    mgr.press(0)                                        # back to 1
    mgr.go(2)
    mgr.press(2)                                        # 6, from 3
    mgr.press(0)                                        # 4 again, from 6
    assert mgr.rec(0)[:0x14] == bank_a(2)[:0x14] and not mgr.rec(0)[VALID]
    edited = bytearray(mgr.rec(0))
    edited[5], edited[VALID] = 0x55, 1                  # an edit on 4: the block handler marks it (0x28de2572)
    mgr.m.write(record(0), edited)
    mgr.press(0)                                        # back to 1
    mgr.press(0)                                        # 4 again
    assert mgr.rec(0) == bytes(edited)


def test_another_switch_in_bank_b_selects_within_it(mgr):
    mgr.press(0)
    mgr.selects.clear()
    mgr.press(2)
    (new, old, _, _), = mgr.selects
    assert (new, old) == (2, 0) and mgr.name(2) == b'SNAPSHOT 6'


@pytest.mark.parametrize('index', [3, 8, 0xff])
def test_an_index_above_2_goes_to_select(mgr, index):
    mgr.m.u8(MGR + CUR, index & 0xff)
    mgr.press(index)
    assert [s[0] for s in mgr.selects] == [index] and mgr.inits == []


def test_while_select_is_held_off_the_press_goes_to_select(mgr):
    mgr.m.u8(MGR + BUSY, 1)
    mgr.press(0)
    assert mgr.held == [0] and mgr.selects == [] and mgr.inits == []
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)]


def test_a_preset_load_starts_bank_a_and_a_new_bank_b(mgr):
    mgr.press(0)
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    for i in range(3):                                  # the parser fills the records with the new preset
        mgr.m.write(record(i), bank_a(i))
    mgr.inits.clear()
    mgr.press(0)
    assert mgr.inits == [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6']
    assert mgr.name(0) == b'SNAPSHOT 4'


@pytest.mark.parametrize('busy', [0, 1])
def test_a_save_in_bank_b_recalls_bank_a_for_the_write(mgr, busy):
    """A load takes the preset's live values for its current snapshot, so the write must run with bank A's sound live: select
    recalls snapshot 1 from snapshot 4's sound, the writer runs, then select recalls snapshot 4. Select is let run for these two,
    as the load path lets its own, and its hold is put back."""
    mgr.press(0)
    edited = bytearray(mgr.rec(0))
    edited[5] = 0x55
    edited[VALID] = 1
    mgr.m.write(record(0), edited)
    bank_b = [mgr.rec(i) for i in range(3)]
    mgr.m.u8(MGR + BUSY, busy)
    mgr.selects.clear()
    mgr.call('snaps_saving', STREAM, HEADER)
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)]
    assert [(new, old_rec, new_rec) for new, _, old_rec, new_rec in mgr.selects] == [(0, bytes(edited), bank_a(0))]
    assert mgr.read_busy() == busy and mgr.held == []
    mgr.selects.clear()
    mgr.call('snaps_saved', STREAM, HEADER)
    assert [mgr.rec(i) for i in range(3)] == bank_b
    assert [(new, old_rec, new_rec) for new, _, old_rec, new_rec in mgr.selects] == [(0, bank_a(0), bytes(edited))]
    assert mgr.read_busy() == busy and mgr.held == [] and mgr.cur() == 0
    mgr.m.u8(MGR + BUSY, 0)
    mgr.press(0)
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)], 'still flips back after a save'


def test_a_save_in_bank_a_changes_nothing(mgr):
    mgr.call('snaps_saving', STREAM, HEADER)
    mgr.call('snaps_saved', STREAM, HEADER)
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)] and mgr.inits == []


def test_a_preset_load_during_a_save_does_not_flip_after_it(mgr):
    mgr.press(0)
    mgr.call('snaps_saving', STREAM, HEADER)
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    mgr.call('snaps_saved', STREAM, HEADER)
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)]


def camera(left, bottom, digit, lit=False):
    """A camera's new number: a box over its digit (white on a lit camera's circle), then the digit in hx28_boldFont."""
    box, ink = (0xffffff, 0x101010) if lit else (0, 0xffffff)
    return [('fill', FB, left + 22, bottom + 6, 16, 22, box, 0), ('text', FB, digit.encode(), left + 29, bottom + 1, 2, ink, 1, 1)]


def top(digit):
    """What the top view's paint does in bank B: the icon's number, at its stock place (262, 237, anchor 6: top left)."""
    return ['widget lock', *camera(262, 202, digit), 'widget unlock']


def labels(lit):
    """What the Home view's paint does in bank B: 4, 5, 6 over the labels (anchor 7: x the centre, y the top), the lit one inverted."""
    out = ['widget lock']
    for i in range(3):
        out += camera(LABEL_X[i] - 26, LABEL_Y - 35, str(i + 4), i == lit)
    return out + ['widget unlock']


def test_bank_a_paints_nothing(mgr):
    assert mgr.paint() == ([], []) and mgr.paint('home') == ([], [])


@pytest.mark.parametrize('lit', [0, 1, 2])
def test_bank_b_draws_its_numbers_over_the_icon_and_the_labels(mgr, lit):
    mgr.m.u8(MGR + CUR, lit)
    mgr.events.clear()
    mgr.press(lit)
    assert mgr.events[-1] == ('redraw', 0, 1), 'the flip asks for a paint, which draws the numbers'
    assert mgr.paint() == (top(str(lit + 4)), [])
    assert mgr.paint('home') == (labels(lit), [])


def test_the_numbers_follow_the_snapshot_within_bank_b(mgr):
    mgr.press(0)
    mgr.press(2)
    assert mgr.paint() == (top('6'), [])
    assert mgr.paint('home') == (labels(2), [])


def test_an_edited_snapshots_red_icon_gets_a_white_number(mgr):
    mgr.press(0)
    mgr.icon_style = 'red'
    assert mgr.paint() == (top('4'), [])


def test_hidden_or_other_images_get_no_number(mgr):
    """A label shows text instead of a camera once its snapshot is renamed; only a visible stock camera gets a number."""
    mgr.press(0)
    mgr.m.u8(ICON + 0x1d, 0)
    assert mgr.paint() == (['widget lock', 'widget unlock'], [])
    mgr.m.u8(LABELS + 0x1d, 0)
    mgr.m.u8(LABELS + 0x24 + 0x1d, 0)
    assert mgr.paint('home') == (labels(0)[:1] + labels(0)[5:], [])


@pytest.mark.parametrize('functions', [[2, 2, 2], [2, 2, 1]], ids=['stomp', 'stomp with TAP'])
def test_bank_b_in_another_footswitch_mode_leaves_the_labels_alone(mgr, functions):
    """The labels keep their last cameras outside Snapshot mode; numbering them filled black boxes over the stomp or preset names."""
    mgr.press(0)
    mgr.mode(functions)
    assert mgr.paint('home') == ([], [])
    assert mgr.paint() == (top('4'), []), 'the top icon still shows the bank'
    mgr.mode([14, 14, 14])
    assert mgr.paint('home') == (labels(0), []), 'back in Snapshot mode'


def test_back_in_bank_a_the_cameras_are_drawn_again(mgr):
    mgr.press(0)
    mgr.press(0)
    assert mgr.paint() == (['widget lock', 'widget unlock', ('redraw', 0, 1)], [0]), 'its node marked, and a paint to draw it'
    assert mgr.paint() == ([], []), 'once'
    assert mgr.paint('home') == (['widget lock', 'widget unlock', ('redraw', 0, 1)], [1, 2, 3]), 'the labels, once each paint'
    assert mgr.paint('home') == ([], [])


def test_a_preset_load_in_bank_b_draws_the_cameras_again(mgr):
    mgr.press(0)
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    assert mgr.paint() == (['widget lock', 'widget unlock', ('redraw', 0, 1)], [0])
    assert mgr.paint('home') == (['widget lock', 'widget unlock', ('redraw', 0, 1)], [1, 2, 3])
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    assert mgr.paint() == ([], []) and mgr.paint('home') == ([], []), 'a load in bank A leaves them alone'


@pytest.mark.parametrize('leave', ['flip', 'load'])
def test_leaving_bank_b_leaves_a_renamed_snapshots_label_alone(mgr, leave):
    """Issue #125: a renamed snapshot's label is text over a hidden camera; marking that camera's node made the stock erase fill
    black across the name, which nothing then redrew."""
    mgr.press(0)
    if leave == 'flip':
        mgr.press(0)
    else:
        mgr.call('snaps_loaded', MGR, 0, 0, 0)
    mgr.m.u8(LABELS + 0x1d, 0)
    assert mgr.paint('home') == (['widget lock', 'widget unlock', ('redraw', 0, 1)], [2, 3])
    mgr.m.u8(ICON + 0x1d, 0)
    assert mgr.paint() == (['widget lock', 'widget unlock', ('redraw', 0, 1)], [])


def test_a_save_in_bank_b_keeps_the_numbers(mgr):
    """The save's flip to bank A marks the cameras for a redraw; the next paint draws bank B's numbers over them again."""
    mgr.press(0)
    mgr.call('snaps_saving', STREAM, HEADER)
    mgr.call('snaps_saved', STREAM, HEADER)
    assert mgr.paint() == (top('4') + [('redraw', 0, 1)], [0])
    assert mgr.paint() == (top('4'), [])


def entries(rec, at, size, keys):
    """A record with entries (key, then size - 1 bytes of value) at offset at."""
    rec = bytearray(rec)
    for i, (key, value) in enumerate(keys):
        rec[at + size * i:at + size * (i + 1)] = bytes([key]) + bytes([value]) * (size - 1)
    return bytes(rec)


def test_a_flip_matches_the_incoming_banks_entries_to_the_outgoing_ones(mgr):
    """A controller assigned while bank B waited is in bank A's records only: on the flip, bank B takes it with bank A's value,
    and keeps its own values for the controllers both have. Footswitch entries the same."""
    mgr.press(0)                                        # bank B, made from bank A
    mgr.press(0)                                        # back to A; B waits in the shadow
    b0 = mgr.rec(0)
    for i in range(3):
        rec = entries(mgr.rec(i), 0x28, 7, [(3, 0x30 + i), (5, 0x50 + i)])
        mgr.m.write(record(i), entries(rec, 0x1e8, 9, [(2, 0x20 + i)]))
    shadow = CODE + mgr.sym['snaps_shadow']
    for i in range(3):
        rec = bytearray(entries(mgr.m.read(shadow + REC * i, REC), 0x28, 7, [(3, 0x90 + i), (0x40, 0)]))
        rec[VALID] = 1                                  # bank B's own values: edits there, which mark it valid
        mgr.m.write(shadow + REC * i, entries(rec, 0x1e8, 9, [(2, 0xa0 + i)]))
    mgr.m.u8(MGR + CONTROLLERS, 2)
    mgr.m.u8(MGR + SWITCHES, 1)
    mgr.press(0)
    for i in range(3):
        rec = mgr.rec(i)
        assert rec[0x28:0x28 + 14] == bytes([3]) + bytes([0x90 + i]) * 6 + bytes([5]) + bytes([0x50 + i]) * 6
        assert rec[0x1e8:0x1e8 + 9] == bytes([2]) + bytes([0xa0 + i]) * 8, 'its own footswitch entry, the keys matching'


def appended(mgr):
    """What pk_serialize writes after the map (the serializer itself a stub here); key 0x64 is written under D once the DSP model
    is made, and with no D before."""
    mgr.written.clear()
    mgr.write_held.clear()
    assert mgr.engine('pk_serialize', STREAM, HEADER) == 5, "the serializer's result"
    assert all(mgr.write_held) if mgr.model() else not any(mgr.write_held), 'key 0x64 written under D'
    return b''.join(mgr.written)


def head():
    return bytes([0x64, 0xc5, 0x07, 0x28]) + b'HX6B' + bytes([1, 0, 0, 0])


def test_a_preset_file_without_bank_b_stays_stock(mgr):
    assert appended(mgr) == b''
    mgr.written.clear()
    mgr.engine('pk_toc', STREAM, HEADER)
    assert mgr.written == [], 'and its count is left alone'


def test_a_preset_file_saved_in_bank_b_gets_bank_b_after_its_map(mgr):
    mgr.press(0)
    assert appended(mgr) == head() + b''.join(mgr.rec(i) for i in range(3))


def test_a_preset_file_saved_in_bank_a_gets_the_waiting_bank_b(mgr):
    mgr.press(0)
    bank_b = b''.join(mgr.rec(i) for i in range(3))
    mgr.press(0)
    assert appended(mgr) == head() + bank_b


@pytest.mark.parametrize('flag, count', [(0, 0x8a), (1, 0x8b)])
def test_the_maps_count_counts_key_0x64(mgr, flag, count):
    """The serializer writes (flag + 9) | 0x80 up front, flag saying whether key 12 follows; after the TOC's rewrite the file is at
    that byte, which gets one more."""
    mgr.flag = flag
    mgr.press(0)
    appended(mgr)
    mgr.written.clear()
    mgr.engine('pk_toc', STREAM, HEADER)
    assert mgr.written == [bytes([count])]
    mgr.written.clear()
    mgr.engine('pk_toc', STREAM, HEADER)
    assert mgr.written == [], 'once a save'


def bank_b_file(records):
    return head() + records


@pytest.mark.parametrize('names', [b'', b'\x0c\x92\xa3abc\xc0', b'\x0c\xdc\x00\x02\xd9\x02hi\xa0'])
def test_a_load_takes_bank_b_from_the_file(mgr, names):
    """Section 10 holds key 12's names (if any), then key 0x64; bank B comes back with the preset's snapshots."""
    records = b''.join(bytes([0xb0 + i]) * REC for i in range(3))
    mgr.section = names + bank_b_file(records)
    assert mgr.read_section() == len(mgr.section), "the read's result"
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    assert mgr.m.read(CODE + mgr.sym['snaps_shadow'], 3 * REC) == records
    mgr.inits.clear()
    mgr.press(0)
    assert mgr.inits == [] and mgr.rec(0)[:VALID] == records[:VALID], "the file's snapshot 4, not a new one"


@pytest.mark.parametrize('section', [b'', b'\x0c\x90', b'\x0c\x90' + bank_b_file(b'\0' * 0x100),
                                     b'\x0c\x90' + head()[:4] + b'HX6C' + bytes(4 + 3 * REC)])
def test_a_load_without_a_whole_bank_b_starts_bank_b_anew(mgr, section):
    """No key 0x64, a short one, or another magic: bank B is made anew, as in a stock preset."""
    mgr.section = section
    mgr.read_section()
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    mgr.inits.clear()
    mgr.press(0)
    assert mgr.inits == [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6']


FIXTURE = os.path.join(os.path.dirname(__file__), 'data', 'more_snapshots_bank_b_v1.bin')
FIXTURE_NAMES = b'\x0c\x92\xa3abc\xc0'


def test_bank_b_files_are_the_bytes_before_the_preset_file_engine(mgr):
    """tests/data/more_snapshots_bank_b_v1.bin: the map's count byte, then section 10 (two names, key 0x64), as more_snapshots.s
    wrote them before src/m4/preset_keys.s took the file's sites (made from its source on next 7ac75f8, bank B in the shadow,
    key 12 present). Through the engine a save writes the same bytes, and a load of them stages the same bank B."""
    with open(FIXTURE, 'rb') as f:
        data = f.read()
    count, section = data[:1], data[1:]
    assert section.startswith(FIXTURE_NAMES)
    key = section[len(FIXTURE_NAMES):]
    records = key[12:]
    assert len(records) == 3 * REC
    data_at = CODE + mgr.sym['snaps_data']
    mgr.flag = 1
    mgr.m.write(CODE + mgr.sym['snaps_shadow'], records)
    mgr.m.u8(data_at + 1, 1)
    assert appended(mgr) == key
    mgr.written.clear()
    mgr.engine('pk_toc', STREAM, HEADER)
    assert mgr.written == [count]
    mgr.m.u8(data_at + 1, 0)
    mgr.m.write(CODE + mgr.sym['snaps_staged'], bytes(3 * REC))
    mgr.section = section
    assert mgr.read_section() == len(section)
    assert mgr.m.read(CODE + mgr.sym['snaps_staged'], 3 * REC) == records
    assert mgr.m.read(data_at + 6, 1) == b'\x01', 'bank B read from the file'


def with_bank_b(mgr):
    """A flip to bank B, each of 4..6 selected so each holds a sound, and back: this preset has a bank B, and bank A is live on
    snapshot 1. Bank B's records."""
    mgr.press(0)
    mgr.press(1)
    mgr.press(2)
    mgr.press(0)
    for i in range(3):
        r = bytearray(mgr.rec(i))
        r[5] = 0xb0 + i                                 # an edit on each of snapshots 4..6, which marks it valid
        r[VALID] = 1
        mgr.m.write(record(i), r)
    bank_b = [mgr.rec(i) for i in range(3)]
    mgr.press(0)
    mgr.selects.clear()
    mgr.inits.clear()
    return bank_b


@pytest.mark.parametrize('source', ['fs', 'cc'])
@pytest.mark.parametrize('way, start, end', [(1, 2, 0), (-1, 0, 2)])
def test_without_bank_b_next_and_previous_wrap_within_1_to_3(mgr, source, way, start, end):
    """A preset that never had a bank B stays stock: next on 3 goes to 1 and previous on 1 to 3, with no bank B made."""
    mgr.m.u8(MGR + CUR, start)
    assert mgr.step(way, source) == 1
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(end, start)] and mgr.inits == []
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)] and not mgr.bank_b_live()


@pytest.mark.parametrize('source', ['fs', 'cc'])
@pytest.mark.parametrize('way, start, end', [(1, 2, 0), (-1, 0, 2)])
def test_with_bank_b_next_and_previous_cross_into_it(mgr, source, way, start, end):
    """Next on 3 goes to 4, previous on 1 to 6: bank B is swapped in and select recalls its snapshot from the sound being left."""
    bank_b = with_bank_b(mgr)
    mgr.go(start)
    assert mgr.step(way, source) == 1
    (new, old, old_rec, new_rec), = mgr.selects
    assert new == end and old != end, 'a select of another index, so it recalls rather than reselects'
    assert (old_rec, new_rec) == (bank_a(start), bank_b[end]), 'from the snapshot being left to the other bank\'s'
    assert [mgr.rec(i) for i in range(3)] == bank_b and mgr.bank_b_live() and mgr.cur() == end
    assert mgr.inits == [] and mgr.depth == 0


@pytest.mark.parametrize('source', ['fs', 'cc'])
@pytest.mark.parametrize('way, start, end', [(1, 2, 0), (-1, 0, 2)])
def test_in_bank_b_next_and_previous_cross_back_to_bank_a(mgr, source, way, start, end):
    """Next on 6 goes to 1, previous on 4 to 3."""
    bank_b = with_bank_b(mgr)
    mgr.press(0)
    mgr.go(start)
    mgr.step(way, source)
    (new, _, old_rec, new_rec), = mgr.selects
    assert (new, old_rec, new_rec) == (end, bank_b[start], bank_a(end))
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)] and not mgr.bank_b_live() and mgr.cur() == end


@pytest.mark.parametrize('source', ['fs', 'cc'])
def test_next_runs_through_all_six_and_previous_back(mgr, source):
    with_bank_b(mgr)
    seen = []
    for way in [1] * 6 + [-1] * 6:
        mgr.step(way, source)
        seen.append(mgr.cur() + 3 * mgr.bank_b_live() + 1)
    assert seen == [2, 3, 4, 5, 6, 1, 6, 5, 4, 3, 2, 1]


@pytest.mark.parametrize('source', ['fs', 'cc'])
@pytest.mark.parametrize('way, start', [(1, 0), (1, 1), (-1, 1), (-1, 2)])
def test_next_and_previous_inside_a_bank_go_straight_to_select(mgr, source, way, start):
    with_bank_b(mgr)
    mgr.go(start)
    mgr.step(way, source)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(start + way, start)] and not mgr.bank_b_live()


def test_a_wrap_while_select_is_held_off_goes_to_select_and_is_forgotten(mgr):
    with_bank_b(mgr)
    mgr.go(2)
    mgr.m.u8(MGR + BUSY, 1)
    mgr.step(1)
    assert mgr.held == [0] and not mgr.bank_b_live()
    mgr.m.u8(MGR + BUSY, 0)
    mgr.selects.clear()
    mgr.cc(1)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(1, 2)] and not mgr.bank_b_live(), 'the next select is stock'


def test_a_wrap_without_bank_b_is_forgotten(mgr):
    mgr.m.u8(MGR + CUR, 2)
    mgr.step(1)
    mgr.selects.clear()
    mgr.press(0)
    assert mgr.inits == [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6'] and mgr.bank_b_live(), 'the lit one again still flips'


@pytest.mark.parametrize('lit', [0, 1, 2])
def test_cc_69_on_the_lit_snapshot_stays_stock(mgr, lit):
    """Only the footswitches flip on the lit snapshot: CC 69's 0..2 go to select, which Reselect Snapshot then handles."""
    with_bank_b(mgr)
    mgr.go(lit)
    mgr.cc(lit)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(lit, lit)] and not mgr.bank_b_live()


@pytest.mark.parametrize('i', [0, 1, 2])
def test_cc_69_3_to_5_without_bank_b_makes_it_as_a_flip_does(mgr, i):
    """Snapshot 4..6 from a preset with no bank B: its records start as defaults, and select fills the new one from the sound."""
    mgr.go(1)
    assert mgr.cc(3 + i) == 0, "a fill's result"
    assert mgr.inits == [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6']
    (new, old, old_rec, new_rec), = mgr.selects
    assert new == i and old != i and old_rec == bank_a(1) and not new_rec[VALID]
    assert mgr.bank_b_live() and mgr.cur() == i and mgr.depth == 0


@pytest.mark.parametrize('start', [0, 1, 2])
@pytest.mark.parametrize('i', [0, 1, 2])
def test_cc_69_3_to_5_from_bank_a_cross_into_bank_b(mgr, start, i):
    bank_b = with_bank_b(mgr)
    mgr.go(start)
    assert mgr.cc(3 + i) == 1
    (new, old, old_rec, new_rec), = mgr.selects
    assert new == i and old != i, 'a select of another index, so it recalls rather than reselects'
    assert (old_rec, new_rec) == (bank_a(start), bank_b[i])
    assert [mgr.rec(j) for j in range(3)] == bank_b and mgr.bank_b_live() and mgr.cur() == i and mgr.inits == []


@pytest.mark.parametrize('start', [0, 1, 2])
@pytest.mark.parametrize('i', [0, 1, 2])
def test_cc_69_0_to_2_from_bank_b_cross_back_to_bank_a(mgr, start, i):
    bank_b = with_bank_b(mgr)
    mgr.press(0)
    mgr.go(start)
    mgr.cc(i)
    (new, _, old_rec, new_rec), = mgr.selects
    assert (new, old_rec, new_rec) == (i, bank_b[start], bank_a(i))
    assert [mgr.rec(j) for j in range(3)] == [bank_a(j) for j in range(3)] and not mgr.bank_b_live() and mgr.cur() == i


@pytest.mark.parametrize('start, i', [(0, 1), (0, 2), (1, 0), (2, 1)])
def test_cc_69_3_to_5_in_bank_b_select_within_it(mgr, start, i):
    with_bank_b(mgr)
    mgr.press(0)
    mgr.go(start)
    mgr.cc(3 + i)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(i, start)] and mgr.bank_b_live()


@pytest.mark.parametrize('lit', [0, 1, 2])
def test_cc_69_3_to_5_on_the_lit_snapshot_in_bank_b_stays_stock(mgr, lit):
    """As 0..2 in bank A: select with the current index, which Reselect Snapshot handles, and no flip."""
    with_bank_b(mgr)
    mgr.press(0)
    mgr.go(lit)
    mgr.cc(3 + lit)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(lit, lit)] and mgr.bank_b_live()


def test_cc_69_3_to_5_while_select_is_held_off_goes_to_select(mgr):
    with_bank_b(mgr)
    mgr.m.u8(MGR + BUSY, 1)
    assert mgr.cc(4) == 0
    assert mgr.held == [1] and mgr.selects == [] and not mgr.bank_b_live()
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)]


def test_a_bank_b_from_the_file_is_crossed_into_without_a_flip(mgr):
    records = b''.join(bytes([0xb0 + i]) * REC for i in range(3))
    mgr.section = bank_b_file(records)
    mgr.read_section()
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    mgr.m.u8(MGR + CUR, 2)
    mgr.step(1)
    assert mgr.inits == [] and mgr.bank_b_live() and mgr.rec(0)[:VALID] == records[:VALID], "the file's snapshot 4"


def test_a_preset_load_forgets_the_last_presets_bank_b(mgr):
    with_bank_b(mgr)
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    mgr.m.u8(MGR + CUR, 2)
    mgr.step(1)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(0, 2)] and mgr.inits == [] and not mgr.bank_b_live()


def test_snapshot_bank_sel_is_a_footswitches_setting_on_a_virtual_id():
    """Hold (0) is the default, which a unit reads before the setting is ever stored; the HX Stomp shows 'Snapshot' over 'BankSel'."""
    assert ms.FLAG == 'HX_MORE_SNAPSHOTS' and ms.MENU == 'Footswitches'
    assert ms.SETTINGS == (Setting('bank_switch', b'BankSel\nSnapshot', (b'Hold', b'Tap'), 0),)
    assert IDS['more_snapshots.bank_switch'] == 0xe6 and setting_ids.packing()[0xe6] == (114, 0, 2)


def bank_b_ready(m):
    """A preset with a bank B (each of 4..6 holding a sound of its own), bank A live on snapshot 1, then Snapshot BankSel on Hold;
    bank B's records."""
    m.settings[BANK_SWITCH] = TAP_SEL
    bank_b = with_bank_b(m)
    m.settings[BANK_SWITCH] = HOLD_SEL
    return bank_b


def test_the_event_hook_returns_the_selected_block_and_keeps_registers(hm):
    """Every event the handler gets reaches the hook: the stock getter runs once with the handler's out argument and its result
    comes back, r4 and r5 unchanged."""
    events = [(c, t) for c in (9, 10, 11, 12, 13, 14, 15, 16, 8, 0x40) for t in (PRESS, RELEASE, CLICK, HOLD, 4)]
    for code, kind in events:
        hm.event(code, kind)
    assert len(hm.m.calls(SELECTED_BLOCK)) == len(events)


def test_touches_other_keys_and_releases_select_nothing(hm):
    for k in range(3):
        hm.obj(PRESSED + k, 1)
    for code, kind in [(c, t) for c in (9, 10, 11, 15, 16, 8, 0x40) for t in (PRESS, RELEASE, CLICK, HOLD)] + [(12, RELEASE)]:
        hm.event(code, kind)
    assert hm.selects == [] and hm.layouts == [] and hm.armed() == [0, 0, 0] and hm.data(VIEW) == 0


def test_an_unset_setting_holds_back_a_snapshot_press(hm):
    """snaps_select with no mark is footswitch k's press of snapshot k: in Hold mode it selects nothing, takes no lock, paints
    nothing; its click selects."""
    for k in range(3):
        assert hm.call('snaps_select', MGR, k) == 0
    assert hm.selects == [] and hm.inits == [] and hm.depth == 0 and hm.events == []
    hm.settings[BANK_SWITCH] = 7
    assert hm.call('snaps_select', MGR, 1) == 0 and hm.selects == [], 'a value above Tap reads Hold, the default'


@pytest.mark.parametrize('index', [3, 8, 0xff])
def test_in_hold_mode_an_index_above_2_goes_to_select(hm, index):
    hm.call('snaps_select', MGR, index)
    assert [s[0] for s in hm.selects] == [index]


@pytest.mark.parametrize('sel', [HOLD_SEL, TAP_SEL])
@pytest.mark.parametrize('way, start', [(1, 0), (1, 1), (-1, 1), (-1, 2)])
def test_footswitch_steps_within_a_bank_reach_stock_select_in_both_modes(mgr, sel, way, start):
    """SnpshtUp and SnpshtDn share the select call with snapshot k's press; their read of the current snapshot marks a step, which
    snaps_select clears and sends to select, so Hold does not hold them back."""
    with_bank_b(mgr)
    mgr.go(start)
    mgr.settings[BANK_SWITCH] = sel
    assert mgr.step(way) == 1
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(start + way, start)] and not mgr.bank_b_live()
    assert mgr.data(WRAP) == 0, 'the mark is cleared'


@pytest.mark.parametrize('sel', [HOLD_SEL, TAP_SEL])
def test_footswitch_wraps_still_cross_in_both_modes(mgr, sel):
    bank_b = with_bank_b(mgr)
    mgr.go(2)
    mgr.settings[BANK_SWITCH] = sel
    mgr.step(1)
    (new, _, old_rec, new_rec), = mgr.selects
    assert (new, old_rec, new_rec) == (0, bank_a(2), bank_b[0]) and mgr.bank_b_live()


def test_a_stray_step_mark_at_cc_69_is_stock(mgr):
    with_bank_b(mgr)
    mgr.go(1)
    mgr.data(WRAP, STEP)
    mgr.call('snaps_cc_select', MGR, 2)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(2, 1)] and not mgr.bank_b_live() and mgr.data(WRAP) == 0


def test_a_click_selects_in_the_live_bank_on_its_release(hm):
    hm.fs_press(1)
    hm.fs_fire()
    assert hm.selects == [], 'the dispatch 30 ticks on is held back'
    hm.fs_release(1)
    assert hm.selects == []
    hm.fs_click(1)
    assert [(new, old) for new, old, _, _ in hm.selects] == [(1, 0)] and hm.armed() == [0, 0, 0]
    assert hm.data(VIEW) == 0 and hm.data(RELAYOUT) == 0, 'stock lays the labels out after its select'


def test_a_short_tap_selects_once_on_its_click(hm):
    """Released inside the 30-tick window: stock would select nothing; the click selects, and the dispatch after finds it released."""
    hm.fs_press(2)
    hm.fs_release(2)
    hm.fs_click(2)
    hm.fs_fire()
    hm.fs_click(2)
    assert [(new, old) for new, old, _, _ in hm.selects] == [(2, 0)], 'once: the click consumed the press'


@pytest.mark.parametrize('k', [0, 1, 2])
def test_a_lit_click_is_stock_select_which_does_what_reselect_says(hm, k):
    hm.m.u8(MGR + CUR, k)
    hm.tap(k)
    assert [(new, old) for new, old, _, _ in hm.selects] == [(k, k)] and not hm.bank_b_live() and hm.inits == []


@pytest.mark.parametrize('start, fs, hold_fs, end', [(2, 2, 1, 6), (6, 0, 0, 1), (2, 1, 1, 5), (5, 1, 0, 2), (1, 0, 1, 4)])
def test_hold_then_click_moves_with_one_sound_change(hm, start, fs, hold_fs, end):
    """Holding FS1 points the footswitches at 1..3 and FS2 at 4..6, with no sound change; the click then crosses, one select from
    the record left to the other bank's, and the footswitches stay on the bank now live. Bank B made live by CC 69 left them on
    bank A, so a hold of FS1 there has nothing to change."""
    bank_b = bank_b_ready(hm)
    if start > 3:
        hm.cc(start - 1)
    hm.go((start - 1) % 3)
    assert hm.at_snapshot() == start and hm.data(VIEW) == 0
    left = hm.rec(hm.cur())
    hm.layouts.clear()
    hm.hold_fs(hold_fs)
    assert hm.selects == [] and hm.data(VIEW) == hold_fs
    assert hm.layouts == ([] if hold_fs == 0 else [1]), 'a layout of the bank held, at once, when it changes'
    hm.fs_press(fs)
    hm.fs_fire()
    hm.fs_release(fs)
    assert hm.selects == []
    hm.fs_click(fs)
    (new, old, old_rec, new_rec), = hm.selects
    target = bank_b[fs] if end > 3 else bank_a(fs)
    assert (new, old_rec, new_rec) == (fs, left, target) and old != fs, 'from the sound left, a select of another index'
    assert hm.at_snapshot() == end and hm.prev() == hm.cur() and hm.data(PREV6) == start - 1
    assert hm.data(VIEW) == hold_fs and hm.data(RELAYOUT) == 1, 'the cross asks for a layout'
    hm.tick()
    assert hm.layouts[-1] == hold_fs and hm.data(RELAYOUT) == 0, 'the tick lays the labels out again, once the cross is whole'


def test_in_bank_b_a_click_selects_within_it(hm):
    bank_b_ready(hm)
    hm.hold_fs(1)
    hm.tap(0)
    hm.selects.clear()
    hm.tap(1)
    assert [(new, old) for new, old, _, _ in hm.selects] == [(1, 0)] and hm.bank_b_live() and hm.at_snapshot() == 5


def test_holding_fs3_and_the_release_after_a_hold_do_nothing(hm):
    bank_b_ready(hm)
    hm.layouts.clear()
    hm.hold_fs(2)
    hm.fs_click(2)
    assert hm.selects == [] and hm.data(VIEW) == 0 and hm.layouts == [], 'FS3 has no bank yet'
    hm.hold_fs(1)
    hm.fs_click(1)
    assert hm.selects == [] and hm.data(VIEW) == 1 and len(hm.layouts) == 1, 'the click after a hold is stray: no select'


def test_holding_the_viewed_bank_again_or_the_live_one(hm):
    bank_b_ready(hm)
    hm.hold_fs(1)
    hm.layouts.clear()
    hm.hold_fs(1)
    assert hm.data(VIEW) == 1 and hm.layouts == [], 'already on bank B'
    hm.hold_fs(0)
    assert hm.data(VIEW) == 0 and hm.layouts == [0] and hm.selects == [], 'bank A is live: back to it, no sound change'
    hm.view = EDIT_VIEW
    hm.hold_fs(1)
    assert hm.data(VIEW) == 1 and hm.layouts == [0] and hm.data(RELAYOUT) == 1, 'away from Home: laid out on its return'
    hm.tick()
    assert hm.layouts == [0] and hm.data(RELAYOUT) == 1
    hm.view = HOME_VIEW
    hm.tick()
    assert hm.layouts == [0, 1] and hm.data(RELAYOUT) == 0
    hm.tick()
    assert hm.layouts == [0, 1], 'once'


def test_an_aborted_hold_is_a_click(hm):
    hm.fs_press(1)
    hm.fs_fire()
    hm.fs_release(1)
    hm.fs_click(1)
    assert [new for new, _, _, _ in hm.selects] == [1] and hm.data(VIEW) == 0


@pytest.mark.parametrize('first, second', [(0, 1), (1, 2), (0, 2), (1, 0), (2, 1), (2, 0)])
def test_a_second_switch_held_inside_the_window_disarms_both(hm, first, second):
    """FS1+FS2 and FS2+FS3 switch to Preset mode (its bank view) and FS1+FS3 is dropped, as stock: neither press selects."""
    bank_b_ready(hm)
    hm.fs_press(first)
    hm.fs_press(second)
    assert hm.armed() == [0, 0, 0]
    for k in (first, second):
        hm.fs_hold(k)
        hm.fs_click(k)
    assert hm.selects == [] and hm.data(VIEW) == 0


def test_a_switch_let_go_inside_the_window_leaves_the_next_one_armed(hm):
    """A quick tap then another switch inside its window: stock drops both; the first selected on its click, the second on its own."""
    hm.fs_press(0)
    hm.fs_release(0)
    hm.fs_click(0)
    hm.fs_press(2)
    hm.fs_release(2)
    hm.fs_click(2)
    assert [new for new, _, _, _ in hm.selects] == [0, 2]


def test_overlapping_presses_outside_the_window_select_in_release_order(hm):
    """FS1 pressed and held past its window, then FS3 pressed, let go, then FS1: each selects on its own click, so the last let go
    wins (stock would have selected in press order)."""
    hm.fs_press(0)
    hm.fs_fire()
    hm.fs_press(2)
    hm.fs_fire()
    hm.fs_release(2)
    hm.fs_click(2)
    hm.fs_release(0)
    hm.fs_click(0)
    assert [new for new, _, _, _ in hm.selects] == [2, 0] and hm.cur() == 0


def test_cc_49_to_51_select_on_their_press_in_the_bank_shown(hm):
    """MIDI CC 49..51 press a footswitch with [obj+0x6d] set: the press dispatches at once, held back, and the hook selects as a
    tap does, across the banks after a hold of FS2, and on the lit one as Reselect Snapshot says; the click after it selects
    nothing."""
    bank_b = bank_b_ready(hm)
    hm.obj(IMMEDIATE, 1)
    for k in (1, 1):
        hm.fs_press(k)
        hm.fs_release(k)
        hm.fs_click(k)
    assert [(new, old) for new, old, _, _ in hm.selects] == [(1, 0), (1, 1)] and not hm.bank_b_live()
    hm.obj(IMMEDIATE, 0)
    hm.hold_fs(1)
    hm.obj(IMMEDIATE, 1)
    hm.selects.clear()
    hm.fs_press(2)
    (new, _, _, new_rec), = hm.selects
    assert (new, new_rec) == (2, bank_b[2]) and hm.at_snapshot() == 6 and hm.data(VIEW) == 1
    hm.fs_release(2)
    hm.fs_click(2)
    assert len(hm.selects) == 1 and hm.armed() == [0, 0, 0]


def test_a_cc_press_held_on_holds_nothing(hm):
    """A preset that makes the footswitch momentary: CC 49..51's on-value posts the press alone, and on-values sent again count
    towards a hold. The press selected; the hold and the click with the off-value do nothing."""
    bank_b_ready(hm)
    hm.obj(IMMEDIATE, 1)
    hm.fs_press(1)
    hm.fs_hold(1)
    hm.fs_release(1)
    hm.fs_click(1)
    assert [(new, old) for new, old, _, _ in hm.selects] == [(1, 0)] and hm.data(VIEW) == 0 and hm.layouts == []


@pytest.mark.parametrize('learn', [0, 1], ids=['bypass assign', 'controller assign'])
def test_a_press_a_learn_takes_selects_nothing(hm, learn):
    """While Bypass Assign's or Controller Assign's learn waits, the dispatch gives the press to it: not armed, so neither its
    click nor its hold selects or changes the bank shown, after the learn is done."""
    bank_b_ready(hm)
    for cc in (0, 1):
        hm.obj(IMMEDIATE, cc)
        for k, end in ((1, CLICK), (1, HOLD), (0, CLICK)):
            hm.learning[learn] = 1
            hm.event(12 + k, PRESS)
            assert hm.armed() == [0, 0, 0]
            hm.learning[learn] = 0
            hm.event(12 + k, end)
    assert hm.selects == [] and hm.data(VIEW) == 0 and hm.layouts == []


@pytest.mark.parametrize('why', ['preset mode', 'not snapshot k', 'tap', 'tuner'])
def test_no_click_selects_outside_snapshot_mode_on_tap_or_in_the_tuner(hm, why):
    """Not armed by a press made there; and a press armed before it changed is consumed by its click or hold, selecting nothing."""
    def leave():
        if why == 'preset mode':
            hm.settings[FS_MODE] = 2
        elif why == 'not snapshot k':
            hm.mode([14, 13, 14])
        elif why == 'tap':
            hm.settings[BANK_SWITCH] = TAP_SEL
        else:
            hm.view = TUNER_VIEW

    leave()
    hm.event(13, PRESS)
    hm.event(13, CLICK)
    assert hm.selects == [] and hm.armed() == [0, 0, 0]
    hm.settings[FS_MODE], hm.settings[BANK_SWITCH], hm.view = SNAPSHOT_MODE, HOLD_SEL, HOME_VIEW
    hm.mode([14, 14, 14])
    hm.event(13, PRESS)
    assert hm.armed() == [0, 1, 0]
    leave()
    hm.event(13, CLICK)
    hm.event(13, HOLD)
    assert hm.selects == [] and hm.armed() == [0, 0, 0] and hm.data(VIEW) == 0


def viewing_b(m):
    """Bank A live on snapshot 1, the footswitches pointed at bank B by a hold of FS2; the layouts and selects cleared."""
    bank_b = bank_b_ready(m)
    m.hold_fs(1)
    assert m.data(VIEW) == 1
    m.layouts.clear()
    m.selects.clear()
    return bank_b


@pytest.mark.parametrize('how', ['select', 'cc 4', 'cc 1', 'cc lit', 'cc wrap', 'fs wrap', 'fs step', 'action', 'busy'])
def test_no_other_select_moves_the_footswitches(hm, how):
    """HX Edit's select (command 0x58), CC 69's values, its next past the bank's end, SnpshtUp's, the Command Center's, one select
    refuses: the footswitches stay on the bank held, whichever bank is live after it. A move between the banks asks for a layout
    once it is whole; within a bank stock lays the labels out itself."""
    viewing_b(hm)
    if how == 'select':
        hm.m.call(SELECT, MGR, 2)
    elif how in ('cc 4', 'cc 1', 'cc lit'):
        hm.cc({'cc 4': 4, 'cc 1': 1, 'cc lit': 0}[how])
    elif how in ('cc wrap', 'fs wrap'):
        hm.go(2)
        hm.step(1, how[:2])
    elif how == 'fs step':
        hm.step(1)
    elif how == 'action':
        hm.call('snaps_action_select', MGR, 2)
    else:
        prev6 = hm.data(PREV6)
        hm.m.u8(MGR + BUSY, 1)
        hm.m.call(SELECT, MGR, 2)
        assert hm.held == [2] and hm.data(PREV6) == prev6 == 3, 'refused by select, after its hook, which keeps PREV6'
    cross = how in ('cc 4', 'cc wrap', 'fs wrap')
    assert hm.data(VIEW) == 1 and hm.bank_b_live() == cross and hm.data(RELAYOUT) == int(cross)
    hm.tick()
    assert hm.layouts == ([1] if cross else []) and hm.data(RELAYOUT) == 0 and hm.data(VIEW) == 1


def test_a_select_with_the_live_bank_shown_lays_out_nothing(hm):
    hm.m.call(SELECT, MGR, 2)
    hm.tick()
    assert hm.data(RELAYOUT) == 0 and hm.layouts == []


def test_a_click_leaves_the_footswitches_on_the_bank_now_live(hm):
    """A click selects in the bank the footswitches are on, which is then live; one select refuses (+0x9a9) leaves the live bank
    as it was, and the footswitches go back to it, laid out by the tick."""
    viewing_b(hm)
    hm.m.u8(MGR + BUSY, 1)
    hm.tap(1)
    assert hm.held == [1] and hm.data(VIEW) == 0 and hm.data(RELAYOUT) == 1 and not hm.bank_b_live()
    hm.tick()
    assert hm.layouts == [0]
    hm.m.u8(MGR + BUSY, 0)
    hm.hold_fs(1)
    hm.tap(1)
    assert hm.at_snapshot() == 5 and hm.data(VIEW) == 1
    hm.tap(0)
    assert hm.at_snapshot() == 4 and hm.data(VIEW) == 1


def test_a_preset_load_points_the_footswitches_at_bank_a(hm):
    """The load's bank A, whichever bank the footswitches were on or was live; the press made before it selects nothing in the
    new preset, and its previous snapshot is no other bank's."""
    viewing_b(hm)
    hm.cc(4)
    hm.event(12, PRESS)
    assert hm.armed() == [1, 0, 0] and hm.bank_b_live() and hm.data(PREV6) == 0
    hm.selects.clear()
    hm.call('snaps_loaded', MGR, 0, 0, 0)
    assert hm.data(VIEW) == 0 and hm.data(RELAYOUT) == 1 and hm.armed() == [0, 0, 0] and hm.data(PREV6) == NONE
    hm.event(12, CLICK)
    assert hm.selects == [], 'the press made before the load selects nothing in the new preset'


@pytest.mark.parametrize('sel, view, relayout', [(HOLD_SEL, 1, 1), (HOLD_SEL, 0, 0), (TAP_SEL, 1, 0)])
def test_a_preset_load_asks_the_tick_for_a_layout_only_off_bank_b_on_hold(hm, sel, view, relayout):
    """Stock lays the labels out after a load; the tick lays them out too only when Hold had them on bank B, so a load on Tap, or
    with the labels on bank A already, adds no layout from the key task."""
    hm.settings[BANK_SWITCH] = sel
    hm.data(VIEW, view)
    hm.call('snaps_loaded', MGR, 0, 0, 0)
    assert hm.data(VIEW) == 0 and hm.data(RELAYOUT) == relayout


@pytest.mark.parametrize('bank', ['a', 'b'])
def test_a_save_leaves_the_footswitches_and_the_previous_snapshot_alone(hm, bank):
    """Through a serializer's chain, as a save or HX Edit's Get edit buffer runs it, three times: in bank B each write sees bank A
    live and the two flips come back, SAVING set through both. The bank the footswitches are on and the current and previous
    snapshots, in both forms, are as before; only the flips ask for a layout."""
    bank_b_ready(hm)
    hm.go(1)
    hm.go(2)
    if bank == 'b':
        hm.cc(4)
        hm.go(0)
        hm.go(1)
    hm.hold_fs(0 if bank == 'b' else 1)
    hm.selects.clear()
    hm.layouts.clear()
    before = hm.cur(), hm.prev(), hm.data(PREV6), hm.data(VIEW), hm.bank_b_live()
    assert before == ((1, 0, 3, 0, True) if bank == 'b' else (2, 1, 1, 1, False))
    saving = []
    hm.during_select = lambda: saving.append(hm.data(SAVING))
    for _ in range(3):
        hm.save()
    assert [(b, cur) for b, cur, _ in hm.saved] == [(False, before[0])] * 3
    assert saving == ([1] * 6 if bank == 'b' else []) and hm.data(SAVING) == 0
    assert (hm.cur(), hm.prev(), hm.data(PREV6), hm.data(VIEW), hm.bank_b_live()) == before
    hm.tick()
    assert hm.layouts == ([0] if bank == 'b' else [])


@pytest.mark.parametrize('held, cc', [(1, 0), (0, 0), (1, 1)], ids=['on bank b', 'on bank a', 'cc 51'])
def test_without_d_a_tap_during_a_serializers_flips_selects_nothing(hm, held, cc):
    """Before the boot makes the DSP model nothing takes D, so a tap can land between a serializer's flips on 5 (with D it waits
    for the flip back: test_a_cross_waits_for_the_serializer): FS3's, or MIDI CC 51's, selects nothing and leaves the footswitches
    where they were, as byte 0 is bank A's there and the records are the ones the serializer reads. After the flip back the same
    tap selects 6, or 3 with FS1 held."""
    hm.m.u32(DSP_MODEL, 0)
    bank_b_ready(hm)
    hm.hold_fs(1)
    hm.tap(1)
    hm.hold_fs(held)
    hm.call('snaps_saving', STREAM, HEADER)
    assert hm.data(SAVING) == 1 and not hm.bank_b_live()
    hm.selects.clear()
    hm.obj(IMMEDIATE, cc)
    hm.tap(2)
    hm.obj(IMMEDIATE, 0)
    assert hm.selects == [] and hm.armed() == [0, 0, 0] and hm.data(VIEW) == held
    hm.call('snaps_saved', STREAM, HEADER)
    assert hm.at_snapshot() == 5 and hm.data(VIEW) == held and hm.data(SAVING) == 0
    hm.tap(2)
    assert hm.at_snapshot() == (6 if held else 3) and hm.data(VIEW) == held
    assert hm.m.calls(DSP_LOCK) == hm.m.calls(DSP_UNLOCK) == [], 'no D before the DSP model is made'


@pytest.mark.parametrize('during', [True, False], ids=['between the flips', 'outside them'])
def test_a_select_during_a_serializers_flips_keeps_the_previous_snapshot_in_bank_b(hm, during):
    """Reselect Snapshot set to go back. On 5, a select that does not wait for D, from another task (stock select takes D only
    while two state bytes are 2, 0x28e023b2..0x28e023c4, and nothing takes it before the boot makes the model), selects snapshot 3
    between a serializer's flips: record 2 of bank A's, which the flip back makes 6. The snapshot it left is 5, in bank B, so the
    lit FS3 goes back to 5 within the bank, as the same select does outside the flips."""
    hm.m.u32(DSP_MODEL, 0)
    bank_b_ready(hm)
    hm.settings[RESELECT] = 1
    hm.hold_fs(1)
    hm.tap(1)
    if during:
        hm.call('snaps_saving', STREAM, HEADER)
    hm.m.call(SELECT, MGR, 2)
    if during:
        hm.call('snaps_saved', STREAM, HEADER)
    assert hm.at_snapshot() == 6 and hm.data(PREV6) == 4 and hm.prev() == 1
    hm.tap(2)
    assert hm.at_snapshot() == 5 and hm.bank_b_live() and hm.data(VIEW) == 1


def records(m):
    """(bank A's three records, bank B's three records), wherever each is."""
    shadow = m.at + m.sym['snaps_shadow']
    live = [m.rec(i) for i in range(3)]
    other = [m.m.read(shadow + REC * i, REC) for i in range(3)]
    return (other, live) if m.bank_b_live() else (live, other)


def held_from_check_to_flip(log, task):
    """The click's read of SAVING and the cross's write of byte 0, both by task under D, and D not let go in between."""
    kinds = [e[:2] for e in log]
    check = kinds.index(('click reads SAVING', task))
    flip = kinds.index(('byte 0', task), check)
    return all(e[1] == task and e[2] > 0 for e in log[check:flip + 1])


def test_a_click_holds_d_from_its_saving_check_through_byte_0s_flip(hm):
    """The click's cross, 2 to 6: D taken before the click reads SAVING, kept through select and the swaps (the manager lock is
    taken only under it) until byte 0 says bank B, and let go after; select runs nested in it, as stock select takes D again."""
    bank_b_ready(hm)
    hm.go(1)
    hm.hold_fs(1)
    hm.d_log.clear()
    hm.tap(2)
    assert hm.at_snapshot() == 6
    assert held_from_check_to_flip(hm.d_log, 'key')
    assert ('select', 'key', 2) in hm.d_log, "select inside the click's D and the cross's"
    assert hm.d_log[-1] == ('unlock', 'key', 0)


@pytest.mark.parametrize('how', ['save', 'get edit buffer'])
def test_a_serializer_in_bank_b_holds_d_through_both_flips(hm, how):
    """On 5 a serializer, a save or HX Edit's Get edit buffer (which holds D around it, so snaps_saving's is nested): D from
    before the flip to bank A until after the flip back, the write in between (the writer's stub checks it)."""
    bank_b_ready(hm)
    hm.hold_fs(1)
    hm.tap(1)
    hm.d_log.clear()
    if how == 'save':
        hm.save()
    else:
        assert hm.start('transport', GET_EDIT_BUFFER) is None
    flips = [e for e in hm.d_log if e[0] in ('byte 0', 'select')]
    assert len(flips) == 4 and all(task == ('key' if how == 'save' else 'transport') and depth > 0 for _, task, depth in flips)
    assert [e[2] for e in hm.d_log if e[0] == 'lock'] == ([1, 2, 2] if how == 'save' else [1, 2, 3, 3])
    assert hm.d_log[-1][0] == 'unlock' and hm.d_log[-1][2] == 0
    assert len(hm.saved) == 1 and hm.at_snapshot() == 5 and hm.data(DSP_HELD) == 0


def crosser(m, how):
    """A move between the banks set up as it would come, with the task that runs it, its entry and arguments, and where it lands:
    a click of FS1 from 5 (Hold, the footswitches on bank A) or of FS3 from 2 (on bank B); the lit FS2 pressed again on 5 on
    Tap; CC 69's value 1 from 5; MIDI CC 51 from 2 with the footswitches on bank B."""
    bank_b_ready(m)
    if how in ('click 5 to 1', 'tap 5 to 2', 'cc 69 5 to 2'):
        m.hold_fs(1)
        m.tap(1)
    if how == 'click 5 to 1':
        m.hold_fs(0)
        m.fs_press(0)
        m.fs_fire()
        m.fs_release(0)
        m.m.write(EVENT, bytes([1, 12, 0, 0]) + struct.pack('<I', CLICK))
        return 'key', (EVENT_TRAMPOLINE, EVENT, OBJ, OUT, KEPT), 1
    if how == 'tap 5 to 2':
        m.settings[BANK_SWITCH] = TAP_SEL
        return 'request', (m.at + m.sym['snaps_select'], MGR, 1), 2
    if how == 'cc 69 5 to 2':
        m.call('snaps_cc_value')
        return 'request', (m.at + m.sym['snaps_cc_select'], MGR, 1), 2
    m.go(1)
    m.hold_fs(1)
    if how == 'click 2 to 6':
        m.fs_press(2)
        m.fs_fire()
        m.fs_release(2)
        m.m.write(EVENT, bytes([1, 14, 0, 0]) + struct.pack('<I', CLICK))
        return 'key', (EVENT_TRAMPOLINE, EVENT, OBJ, OUT, KEPT), 6
    m.obj(IMMEDIATE, 1)
    m.m.write(EVENT, bytes([1, 14, 0, 0]) + struct.pack('<I', PRESS))
    return 'request', (EVENT_TRAMPOLINE, EVENT, OBJ, OUT, KEPT), 6


CROSSES = ['click 5 to 1', 'click 2 to 6', 'tap 5 to 2', 'cc 69 5 to 2', 'cc 51 2 to 6']


@pytest.mark.parametrize('how', ['save', 'get edit buffer'])
@pytest.mark.parametrize('cross', CROSSES)
def test_the_serializer_waits_for_a_cross(hm, cross, how):
    """The review's race: a serializer (transport task) starts while a cross is past its swap, at its call of select. Its first
    call is the D lock, which waits for the cross; let run after it, it writes bank A's records and leaves both banks as they
    were, the cross on its snapshot (without D, 5 to 1 left bank A as A1, A1, A3)."""
    task, (fn, *args), target = crosser(hm, cross)
    a0, b0 = records(hm)
    hm.saved.clear()
    cross_state = hm.start(task, fn, *args, until=SELECT)
    assert cross_state and hm.d_owner == task and hm.d_depth == 2, 'stopped at its select, under its D and the cross\'s'
    entry = (SAVE, STREAM, HEADER) if how == 'save' else (GET_EDIT_BUFFER,)
    save_state = hm.start('transport', *entry)
    assert save_state and hm.waits == [('transport', 'D', hm.waits[0][2])] and hm.saved == []
    assert hm.waits[0][2] in (range(hm.at, hm.at + 0x2000) if how == 'save' else range(GET_EDIT_BUFFER, GET_EDIT_BUFFER + 0x40)), \
        "its first D lock: snaps_saving's, or Get edit buffer's own"
    assert hm.resume(cross_state) is None and hm.d_owner is None
    assert hm.resume(save_state) is None
    assert records(hm) == (a0, b0), 'both banks as they were'
    assert hm.saved and all(not live and recs == a0 for live, _, recs in hm.saved), 'the write saw bank A live'
    assert hm.at_snapshot() == target and hm.data(SAVING) == 0


@pytest.mark.parametrize('how', ['save', 'get edit buffer'])
@pytest.mark.parametrize('cross, target', [('click', 6), ('click to bank a', 1), ('cc 69 5 to 6', 6), ('cc 69 5 to 1', 1),
                                           ('tap', 2), ('cc 51', 6)])
def test_a_cross_waits_for_the_serializer(hm, cross, target, how):
    """On 5 a serializer is between its flips (bank A live, byte 0 bank A's) when a move comes from another task: a click of FS3
    with the footswitches on bank B, or of FS1 on bank A; CC 69's value 5 or 0; the lit FS2 again on Tap; MIDI CC 51. Each waits
    for D before it reads anything, so it decides on the bank heard once the serializer has flipped back: CC 69's 5 stays in
    bank B, where its value read between the flips would have crossed to 3."""
    bank_b_ready(hm)
    hm.hold_fs(1)
    hm.tap(1)
    if cross == 'click to bank a':
        hm.hold_fs(0)
    elif cross == 'tap':
        hm.settings[BANK_SWITCH] = TAP_SEL
    a0, b0 = records(hm)
    hm.saved.clear()
    entry = (SAVE, STREAM, HEADER) if how == 'save' else (GET_EDIT_BUFFER,)
    save_state = hm.start('transport', *entry, until=hm.at + hm.sym['snaps_saved'])
    assert save_state and len(hm.saved) == 1 and not hm.bank_b_live() and hm.d_owner == 'transport'
    hm.selects.clear()
    if cross in ('click', 'click to bank a', 'cc 51'):
        k = 0 if cross == 'click to bank a' else 2
        hm.obj(IMMEDIATE, int(cross == 'cc 51'))
        if cross != 'cc 51':
            hm.fs_press(k)
            hm.fs_fire()
            hm.fs_release(k)
        hm.m.write(EVENT, bytes([1, 12 + k, 0, 0]) + struct.pack('<I', PRESS if cross == 'cc 51' else CLICK))
        entry = (EVENT_TRAMPOLINE, EVENT, OBJ, OUT, KEPT)
    elif cross == 'tap':
        entry = (hm.at + hm.sym['snaps_select'], MGR, 1)
    else:
        hm.call('snaps_cc_value')
        entry = (hm.at + hm.sym['snaps_cc_select'], MGR, 5 if target == 6 else 0)
    task = 'key' if cross.startswith('click') else 'request'
    cross_state = hm.start(task, *entry)
    assert cross_state and [w[:2] for w in hm.waits] == [(task, 'D')] and hm.selects == [], 'it waits before it reads'
    assert hm.resume(save_state) is None and hm.at_snapshot() == 5 and hm.d_owner is None
    assert hm.resume(cross_state) is None
    hm.obj(IMMEDIATE, 0)
    assert hm.at_snapshot() == target and records(hm) == (a0, b0)
    assert hm.saved and all(not live and recs == a0 for live, _, recs in hm.saved)


@pytest.mark.parametrize('source', ['fs', 'cc'])
def test_a_wrap_waits_for_the_serializers_flip(hm, source):
    """On 6 a serializer is inside its flip to bank A, at its select, where CUR is the stand-in index and BUSY is cleared, when
    next's wrap (marked before it started, as the footswitch's or CC 69's read of the current snapshot marks it) comes to select:
    it waits for D before it reads them, then crosses from 6 to 1, from 6's own record."""
    bank_b = bank_b_ready(hm)
    hm.cc(5)
    assert hm.at_snapshot() == 6
    a0, b0 = records(hm)
    if source == 'fs':
        assert hm.call('snaps_next_cur', MGR) == 2
        entry = hm.at + hm.sym['snaps_select']
    else:
        assert hm.call('snaps_cc_wrap') == MGR
        entry = hm.at + hm.sym['snaps_cc_select']
    save_state = hm.start('transport', SAVE, STREAM, HEADER, until=SELECT)
    assert save_state and hm.cur() != 2 and hm.d_owner == 'transport', "the flip's stand-in index, before its select"
    hm.selects.clear()
    cross_state = hm.start('request', entry, MGR, 0)
    assert cross_state and [w[:2] for w in hm.waits] == [('request', 'D')]
    assert hm.resume(save_state) is None and hm.at_snapshot() == 6
    hm.selects.clear()
    assert hm.resume(cross_state) is None
    (new, _, old_rec, new_rec), = hm.selects
    assert (new, old_rec, new_rec) == (0, bank_b[2], bank_a(0)) and hm.at_snapshot() == 1 and records(hm) == (a0, b0)


def writer_past_its_read(m, task):
    """pk_serialize (0x28df20f2 in 0x28df2060) in task: the serializer's call (a stub here, its chain let D go), then key 0x64's
    writer, stopped once it has read bytes 0 and 1 and chosen the records to copy."""
    m.written.clear()
    m.write_held.clear()
    return m.start(task, ENGINE + m.esym['pk_serialize'], STREAM, HEADER, until=m.at + m.sym['snaps_key_put'])


@pytest.mark.parametrize('cross', CROSSES)
def test_a_cross_waits_for_key_0x64s_writer(hm, cross):
    """A save (0x28df25a4: on the unit, HX Edit's save-to-slot, MIDI) holds no D around pk_serialize, which runs key 0x64's
    writer after the serializer has let D go. A cross from another task while the writer is past its read of byte 0 waits for
    D: the writer copies bank B, and the cross then lands (without D it ran through, and key 0x64 got bank A, as the map has)."""
    task, (fn, *args), target = crosser(hm, cross)
    a0, b0 = records(hm)
    writer = writer_past_its_read(hm, 'transport')
    assert writer and hm.d_owner == 'transport', 'the writer under D'
    cross_state = hm.start(task, fn, *args)
    assert cross_state and [w[:2] for w in hm.waits] == [(task, 'D')], 'the cross waits before it reads'
    assert hm.resume(writer) is None and hm.d_owner is None
    assert b''.join(hm.written) == head() + b''.join(b0) and all(hm.write_held)
    assert hm.resume(cross_state) is None
    assert hm.at_snapshot() == target and records(hm) == (a0, b0)


@pytest.mark.parametrize('cross', CROSSES)
def test_a_cross_between_the_serializer_and_key_0x64s_writer_keeps_both_banks_in_the_file(hm, cross):
    """Nothing holds D between the serializer and key 0x64's writer, so a cross can run there. The map already has bank A, as the
    serializer wrote it under D, and the writer reads under D where bank B is after the cross."""
    task, (fn, *args), target = crosser(hm, cross)
    a0, b0 = records(hm)
    hm.saved.clear()
    hm.save()
    assert [(live, recs) for live, _, recs in hm.saved] == [(False, a0)] and hm.d_owner is None, 'the map: bank A, bank A live'
    assert hm.start(task, fn, *args) is None and hm.at_snapshot() == target
    assert appended(hm) == head() + b''.join(b0)


def test_a_load_waits_for_key_0x64s_writer(hm):
    """HX Edit's 0x28e1c1c2 loads a preset through 0x28df2038, which parses under D without the save lock, so it can come during a
    save on the unit. One that comes while key 0x64's writer copies bank B waits for D: the file gets this preset's bank B, and
    the load then takes the next preset's (without D the writer copied the next preset's)."""
    bank_b_ready(hm)
    hm.cc(4)
    a0, b0 = records(hm)
    a = pm.Asm(LOAD)                        # D, the parser (its chain's snaps_loaded), D let go
    a.h(0xb510)                             # push {r4,lr}
    a.bl(PRESET)
    a.bl(DSP_LOCK)
    a.movw_movt(0, MGR)
    a.h(0x2100, 0x2200, 0x2300)             # movs r1,#0; movs r2,#0; movs r3,#0
    a.bl(hm.at + hm.sym['snaps_loaded'])
    a.bl(PRESET)
    a.bl(DSP_UNLOCK)
    a.h(0xbd10)                             # pop {r4,pc}
    hm.m.load(LOAD, a.bytes())
    writer = writer_past_its_read(hm, 'key')
    assert writer and hm.d_owner == 'key'
    new = b''.join(bytes([0xc0 + i]) * REC for i in range(3))
    hm.section = bank_b_file(new)
    hm.read_section()                       # the next preset's section 10, which only snaps_staged takes
    load = hm.start('transport', LOAD)
    assert load and [w[:2] for w in hm.waits] == [('transport', 'D')]
    assert hm.resume(writer) is None
    assert b''.join(hm.written) == head() + b''.join(b0) and all(hm.write_held)
    assert hm.resume(load) is None
    assert hm.m.read(hm.at + hm.sym['snaps_shadow'], 3 * REC) == new and not hm.bank_b_live()


@pytest.mark.parametrize('how', ['click', 'cc 69', 'tap', 'save', 'key 0x64'])
def test_before_the_dsp_model_is_made_nothing_takes_d(hm, how):
    """[0x28449e78] still 0, as early in the boot: D would be at address 8, so no cross, serializer or key 0x64 writer locks or
    unlocks it, and each does what it does with D."""
    hm.m.u32(DSP_MODEL, 0)
    bank_b_ready(hm)
    hm.saved.clear()
    if how == 'click':
        hm.hold_fs(1)
        hm.tap(2)
        assert hm.at_snapshot() == 6
    elif how == 'cc 69':
        hm.cc(4)
        assert hm.at_snapshot() == 5
    elif how == 'tap':
        hm.settings[BANK_SWITCH] = TAP_SEL
        hm.press(0)
        assert hm.at_snapshot() == 4
    elif how == 'save':
        hm.cc(4)
        hm.save()
        assert len(hm.saved) == 1 and hm.at_snapshot() == 5
    else:
        hm.cc(4)
        assert appended(hm) == head() + b''.join(hm.rec(i) for i in range(3))
    assert hm.m.calls(DSP_LOCK) == hm.m.calls(DSP_UNLOCK) == [] and hm.data(DSP_HELD) == 0


@pytest.mark.parametrize('made', [True, False], ids=['made during the call', 'gone during the call'])
@pytest.mark.parametrize('how', ['click', 'cc 69', 'save'])
def test_the_boot_check_is_made_once_a_call(hm, how, made):
    """Each lock and its unlock follow the one check of the DSP model at the lock: a model made while the call runs gets no
    unlock of a D never taken, and one taken is let go whatever the pointer says by then."""
    bank_b_ready(hm)
    hm.boot_window = True
    hm.m.u32(DSP_MODEL, 0 if made else MODEL)
    if how == 'save':
        hm.cc(4)
    hm.m.log.clear()
    hm.saved.clear()
    hm.during_select = lambda: hm.m.u32(DSP_MODEL, MODEL if made else 0)
    if how == 'click':
        hm.hold_fs(1)
        hm.tap(2)
        assert hm.at_snapshot() == 6
    elif how == 'cc 69':
        hm.cc(4)
        assert hm.at_snapshot() == 5
    else:
        hm.save()
        assert len(hm.saved) == 1 and hm.at_snapshot() == 5
    locks, unlocks = hm.m.calls(DSP_LOCK), hm.m.calls(DSP_UNLOCK)
    assert len(locks) == len(unlocks) == {'click': (0, 2), 'cc 69': (0, 2), 'save': (1, 2)}[how][not made]


def fresh(m, pool=None):
    """The posts, selects and stock count's changes so far forgotten; pool: the event pool's free blocks from here (None: enough)."""
    for log in (m.posts, m.dropped, m.pool_waits, m.selects, m.held, m.quiet_log, m.waits):
        log.clear()
    m.pool = pool


def told_once(m, task):
    """The editor heard of the select once: the module's post of 0x2102, with no D held by the task that made it; select's own
    posts were held back (and no post of select's reached the editor)."""
    assert [(e, t, held, origin, d) for e, t, held, origin, _, d in m.posts] == [(SELECTED_EV, task, False, 'module', False)]
    assert SELECTED_EV in [e for e, origin in m.dropped if origin == 'select']


def quiet_around_each_select(m, task):
    """Stock's count one up before each select under the module's D and one down after it, by the task holding D."""
    assert m.quiet_log == [(task, 1), (task, 0)] * len(m.selects + m.held)


@pytest.mark.parametrize('busy', [0, 1], ids=['', 'busy'])
@pytest.mark.parametrize('setup', ['no bank b', 'bank a live', 'bank b live'])
@pytest.mark.parametrize('value', range(6))
def test_cc_69_posts_nothing_under_d_and_tells_the_editor_once(hm, value, setup, busy):
    """The dev4 hang: CC 69's selects ran stock select under the module's D, and select's posts waited there for a free block of
    the event pool, which only HX Edit reading its notify frees. Now each value, without a bank B, from bank A or from bank B, with
    the pool full: nothing posted under the module's D, stock's count up around the select and back to 0, and the editor told
    once, after D (where stock select posts it too). Select held off: refused, nothing posted, nothing told."""
    if setup != 'no bank b':
        bank_b_ready(hm)
    if setup == 'bank b live':
        hm.cc(4)
    hm.m.u8(MGR + BUSY, busy)
    before = hm.at_snapshot()
    fresh(hm, pool=0)
    assert hm.call('snaps_cc_value') == MGR
    assert hm.start('request', hm.at + hm.sym['snaps_cc_select'], MGR, value) is None
    quiet_around_each_select(hm, 'request')
    assert len(hm.selects + hm.held) == 1
    if busy:
        assert hm.posts == [] and hm.pool_waits == [] and hm.at_snapshot() == before and hm.held
    else:
        told_once(hm, 'request')
        assert hm.at_snapshot() == value + 1
        assert hm.pool_waits == [('request', SELECTED_EV, False)], 'the one wait for a block: after D, as stock select waits'
    assert hm.count() == 0


@pytest.mark.parametrize('busy', [0, 1], ids=['', 'busy'])
@pytest.mark.parametrize('source', ['fs', 'cc'], ids=['click', 'cc 49..51'])
@pytest.mark.parametrize('how, k, target', [('same bank', 1, 2), ('cross', 2, 6), ('back', 2, 2), ('lit', 0, 1)])
def test_a_hold_click_posts_nothing_under_d_and_tells_the_editor_once(hm, how, k, target, source, busy):
    """A click in Hold, from the key task or MIDI CC 49..51's press from the request task, with the event pool full: within the
    live bank (2), across to the bank held (FS2 held, then FS3: 6), back across with Reselect Snapshot (on 6 from 2, the lit FS3
    again: 2), the lit one recalled (1). The editor told once, after D; select held off: nothing."""
    bank_b_ready(hm)
    if how == 'cross':
        hm.hold_fs(1)
    elif how == 'back':
        hm.settings[RESELECT] = 1
        hm.go(1)
        hm.hold_fs(1)
        hm.tap(2)
        assert hm.at_snapshot() == 6
    hm.m.u8(MGR + BUSY, busy)
    before = hm.at_snapshot()
    task = 'key' if source == 'fs' else 'request'
    if source == 'fs':
        hm.fs_press(k)
        hm.fs_fire()
        hm.fs_release(k)
    fresh(hm, pool=0)
    hm.obj(IMMEDIATE, int(source == 'cc'))
    hm.m.write(EVENT, bytes([1, 12 + k, 0, 0]) + struct.pack('<I', CLICK if source == 'fs' else PRESS))
    assert hm.start(task, EVENT_TRAMPOLINE, EVENT, OBJ, OUT, KEPT) is None
    hm.obj(IMMEDIATE, 0)
    quiet_around_each_select(hm, task)
    if busy:
        assert hm.posts == [] and hm.at_snapshot() == before and hm.held == [k]
    else:
        told_once(hm, task)
        assert hm.at_snapshot() == target and hm.pool_waits == [(task, SELECTED_EV, False)]


@pytest.mark.parametrize('how', ['flip', 'within', 'fs wrap', 'cc wrap', 'action flip', 'cc 8 within', 'flip held off',
                                 'stray wrap above 2'])
def test_tap_and_the_wraps_post_nothing_under_d_and_tell_the_editor_once(mgr, how):
    """Tap's press from the request task's deferred dispatch (the lit one flips, another selects within the bank), next past the
    bank's end from a footswitch or CC 69, the Command Center's lit snapshot on Tap, CC 69's next within the bank: the editor told
    once, after D. Every select under the module's D has the count up around it, also one select refuses (the lit one while a
    load holds select off) or one with an index above 2 (a wrap's mark left for a call with one), which tell the editor nothing."""
    with_bank_b(mgr)
    if 'wrap' in how and how != 'stray wrap above 2':
        mgr.go(2)
    if how == 'flip held off':
        mgr.m.u8(MGR + BUSY, 1)
    fresh(mgr, pool=0)
    task = 'key' if how == 'action flip' else 'request'
    if how in ('flip', 'within'):
        entry = (mgr.at + mgr.sym['snaps_select'], MGR, 0 if how == 'flip' else 1)
    elif how == 'fs wrap':
        assert mgr.call('snaps_next_cur', MGR) == 2
        entry = (mgr.at + mgr.sym['snaps_select'], MGR, 0)
    elif how == 'cc wrap':
        assert mgr.call('snaps_cc_wrap') == MGR
        entry = (mgr.at + mgr.sym['snaps_cc_select'], MGR, 0)
    elif how == 'action flip':
        entry = (mgr.at + mgr.sym['snaps_action_select'], MGR, 0)
    elif how == 'flip held off':
        entry = (mgr.at + mgr.sym['snaps_select'], MGR, 0)
    elif how == 'stray wrap above 2':
        mgr.data(WRAP, 1)
        entry = (mgr.at + mgr.sym['snaps_select'], MGR, 5)
    else:
        entry = (mgr.at + mgr.sym['snaps_cc_select'], MGR, 1)
    assert mgr.start(task, *entry) is None
    if how in ('flip held off', 'stray wrap above 2'):
        quiet_around_each_select(mgr, task)
        assert mgr.posts == [] and mgr.at_snapshot() == 1 and (mgr.held, [s[0] for s in mgr.selects]) == (
            ([0], []) if how == 'flip held off' else ([], [5]))
        return
    if how == 'cc 8 within':
        assert mgr.quiet_log == [] and [p[:4] for p in mgr.posts] == [(BEGIN_EV, task, False, 'select'),
                                                                      (SWITCH_EV, task, False, 'select'),
                                                                      (SELECTED_EV, task, False, 'select')], \
            'a step within the bank takes no D of the module: stock select, which posts as stock'
        assert mgr.at_snapshot() == 2
        return
    quiet_around_each_select(mgr, task)
    told_once(mgr, task)
    assert mgr.at_snapshot() == {'flip': 4, 'within': 2, 'fs wrap': 4, 'cc wrap': 4, 'action flip': 4}[how]


@pytest.mark.parametrize('how', ['save', 'get edit buffer'])
@pytest.mark.parametrize('bank', ['a', 'b'])
def test_a_serializer_posts_nothing_and_tells_the_editor_nothing(hm, how, bank):
    """A save (key task) or HX Edit's Get edit buffer (transport task), with the event pool full: in bank B both flips select under
    the module's D with stock's count up, so nothing reaches the editor and nothing waits for a block, and the module tells the
    editor nothing, as the snapshot heard is the same after; in bank A nothing is selected."""
    bank_b_ready(hm)
    if bank == 'b':
        hm.cc(4)
    fresh(hm, pool=0)
    task = 'key' if how == 'save' else 'transport'
    if how == 'save':
        hm.save()
    else:
        assert hm.start(task, GET_EDIT_BUFFER) is None
    assert hm.posts == [] and hm.pool_waits == [] and hm.data(REPOST) == 0
    assert len(hm.selects) == (2 if bank == 'b' else 0)
    quiet_around_each_select(hm, task)
    assert [e for e, _ in hm.dropped] == ([BEGIN_EV, SWITCH_EV, SELECTED_EV] * 2 if bank == 'b' else [])
    assert hm.at_snapshot() == (5 if bank == 'b' else 1) and hm.count() == 0


@pytest.mark.parametrize('how', ['click', 'cc 69', 'tap', 'cc 51', 'save', 'get edit buffer'])
def test_stocks_count_comes_back_to_where_it_was(hm, how):
    """Someone else has the count up (a load's 0x28de039c, the boot's 0x28d96a76): the module adds one and takes one off around
    each select under its D, so it comes back to 2, and while it is up the module's post of 0x2102 is dropped too, as select's
    own would be."""
    if how in ('save', 'get edit buffer'):
        bank_b_ready(hm)
        hm.cc(4)
        hm.count(2)
        fresh(hm)
        if how == 'save':
            hm.save()
        else:
            assert hm.start('transport', GET_EDIT_BUFFER) is None
        assert len(hm.selects) == 2
    else:
        task, (fn, *args), target = crosser(hm, {'click': 'click 2 to 6', 'cc 69': 'cc 69 5 to 2', 'tap': 'tap 5 to 2',
                                                  'cc 51': 'cc 51 2 to 6'}[how])
        hm.count(2)
        fresh(hm)
        assert hm.start(task, fn, *args) is None
        assert ('module' in [o for _, o in hm.dropped]) and hm.selects and hm.at_snapshot() == target
    assert hm.count() == 2 and hm.posts == [] and hm.quiet_log
    assert [on for _, on in hm.quiet_log] == [1, 0] * (len(hm.quiet_log) // 2)


@pytest.mark.parametrize('cross', CROSSES)
def test_a_full_pool_stops_no_task_inside_the_modules_d(hm, cross):
    """The dev4 hang, with the event pool full and HX Edit reading nothing back: a cross stops only at its post of 0x2102, after it
    has let D go, so HX Edit's Get edit buffer (transport task) runs to its end meanwhile, and the cross ends once a block is free.
    With select's posts under the module's D (c026be1), the cross stopped holding D and Get edit buffer waited for D, as did
    everything else that takes D on the unit."""
    task, (fn, *args), target = crosser(hm, cross)
    fresh(hm, pool=0)
    hm.pool_blocks = True
    state = hm.start(task, fn, *args)
    assert state and hm.waits == [(task, 'pool', SELECTED_EV)] and hm.d_owner is None, 'stopped at its post, D let go'
    assert hm.at_snapshot() == target
    hm.saved.clear()
    assert hm.start('transport', GET_EDIT_BUFFER) is None and len(hm.saved) == 1, 'Get edit buffer ran to its end meanwhile'
    hm.pool = 1
    assert hm.resume(state) is None and hm.waits == [(task, 'pool', SELECTED_EV)]
    told_once(hm, task)
    assert hm.at_snapshot() == target


@pytest.mark.parametrize('fails', ['count', 'plain'])
@pytest.mark.parametrize('how', ['flip', 'click', 'cc 69'])
def test_a_select_that_fails_under_d_tells_the_editor_nothing(hm, how, fails):
    """Select's error exits (a DSP or setting call failed) post 0x44118 and no 0x2102; those through 0x28de326c take one off the
    count first, the module's, so their 0x44118 goes out, with no data (no block to wait for), and the others' is dropped. The
    module tells the editor nothing, and the count is back at 0."""
    bank_b_ready(hm)
    fresh(hm, pool=0)
    hm.select_fails = fails
    if how == 'flip':
        hm.settings[BANK_SWITCH] = TAP_SEL
        hm.press(0)
    elif how == 'click':
        hm.tap(1)
    else:
        hm.cc(4)
    assert len(hm.selects) == 1 and hm.count() == 0 and hm.data(REPOST) == 0 and hm.pool_waits == []
    if fails == 'count':
        assert [e for e, _ in hm.dropped] == [BEGIN_EV] and [(e, data) for e, _, _, _, data, _ in hm.posts] == [(0x44118, False)]
    else:
        assert [e for e, _ in hm.dropped] == [BEGIN_EV, 0x44118] and hm.posts == []


def literal_users(code, sym, word):
    """The labels whose code loads word from a literal pool (ldr rN, =word), by the nearest label before each load."""
    labels = sorted((v, k) for k, v in sym.items())
    users = set()
    for i in range(0, len(code) - 3, 2):
        h1, h2 = struct.unpack_from('<2H', code, i)
        if (h1 & 0xf800) == 0x4800:
            t = ((i + 4) & ~3) + ((h1 & 0xff) << 2)
        elif (h1 & 0xff7f) == 0xf85f:
            t = ((i + 4) & ~3) + ((h2 & 0xfff) if h1 & 0x80 else -(h2 & 0xfff))
        else:
            continue
        if 0 <= t <= len(code) - 4 and struct.unpack_from('<I', code, t)[0] == word:
            users.add(max((v, k) for v, k in labels if v <= i)[1])
    return users


def test_the_module_selects_changes_the_count_and_posts_from_their_own_routines_only(m4emu):
    """The module's code itself: select is called only from snaps_stock (the selects that hold no D of the module) and
    snaps_quiet; stock's count only from snaps_quiet; the post of 0x2102 only from snaps_dsp_unlock_post. A new call of select
    under D would have to go through snaps_quiet to be quiet."""
    code, sym = m4emu.assemble('src/m4/more_snapshots.s', MODS, IDS)
    assert literal_users(code, sym, ms.SELECT | 1) == {'snaps_stock', 'snaps_quiet'}
    assert literal_users(code, sym, QUIET | 1) == {'snaps_quiet'}
    assert literal_users(code, sym, SELECTED_POST | 1) == {'snaps_dsp_unlock_post'}
    assert literal_users(code, sym, LED_REFRESH | 1) == {'snaps_tick'}


@pytest.mark.parametrize('how', ['hold away', 'hold back', 'cc 69 cross', 'click cross', 'refused click', 'load off bank b',
                                 'tap flip'])
def test_the_tick_refreshes_the_rings_once_the_footswitches_or_the_banks_move(hm, how):
    """The rings follow the bank the footswitches select in (the refresh's reads go to the layout's hooks): a hold, a cross from any
    task and a load that takes Hold's footswitches off bank B ask the next tick (key task) for one refresh of the rings, as the
    handler's events call it (the handler's object, 0); a second tick refreshes nothing more."""
    bank_b_ready(hm)
    hm.tick()
    if how == 'hold back':
        hm.hold_fs(1)
        hm.tick()
    hm.leds.clear()
    if how in ('hold away', 'hold back'):
        hm.hold_fs(0 if how == 'hold back' else 1)
    elif how == 'cc 69 cross':
        hm.cc(4)
    elif how in ('click cross', 'refused click'):
        hm.hold_fs(1)
        hm.tick()
        hm.leds.clear()
        hm.m.u8(MGR + BUSY, int(how == 'refused click'))
        hm.tap(2)
        assert hm.data(VIEW) == int(how == 'click cross') and hm.bank_b_live() == (how == 'click cross')
    elif how == 'load off bank b':
        hm.hold_fs(1)
        hm.tick()
        hm.leds.clear()
        hm.call('snaps_loaded', MGR, 0, 0, 0)
    else:
        hm.settings[BANK_SWITCH] = TAP_SEL
        hm.press(0)
    assert hm.data(LEDS) == 1 and hm.leds == [], 'asked for, not done: the rings are refreshed in the key task'
    hm.tick()
    assert hm.leds == [(OBJ, 0)] and hm.data(LEDS) == 0
    hm.tick()
    assert hm.leds == [(OBJ, 0)]


def test_the_rings_wait_while_the_tuner_is_open(hm):
    """Stock refreshes no ring while the tuner is open (0x28dd26be); the refresh a hold asked for waits for the tuner to close."""
    bank_b_ready(hm)
    hm.tick()
    hm.leds.clear()
    hm.hold_fs(1)
    hm.view = TUNER_VIEW
    hm.tick()
    assert hm.leds == [] and hm.data(LEDS) == 1
    hm.view = HOME_VIEW
    hm.tick()
    assert hm.leds == [(OBJ, 0)] and hm.data(LEDS) == 0


def test_the_rings_are_refreshed_on_any_view_but_the_tuner(hm):
    """The rings show on every view, so a hold away from Home (a hold is taken on any view but the tuner's) is refreshed by the
    next tick there; the labels wait for Home."""
    bank_b_ready(hm)
    hm.tick()
    hm.leds.clear()
    hm.layouts.clear()
    hm.view = EDIT_VIEW
    hm.hold_fs(1)
    hm.tick()
    assert hm.leds == [(OBJ, 0)] and hm.data(LEDS) == 0
    assert hm.layouts == [] and hm.data(RELAYOUT) == 1


def test_a_change_during_the_ring_refresh_refreshes_again(hm):
    """The tick clears LEDS before the refresh reads the banks: a cross in another task storing LEDS during it is refreshed by
    the next tick."""
    bank_b_ready(hm)
    hm.tick()
    hm.leds.clear()
    hm.hold_fs(1)
    hm.during_leds = lambda: hm.data(LEDS, 1)
    hm.tick()
    hm.during_leds = None
    assert hm.leds == [(OBJ, 0)] and hm.data(LEDS) == 1
    hm.tick()
    assert hm.leds == [(OBJ, 0)] * 2 and hm.data(LEDS) == 0


@pytest.mark.parametrize('sel', [HOLD_SEL, TAP_SEL], ids=['hold on bank b', 'tap'])
def test_the_tick_waits_between_a_serializers_flips(hm, sel):
    """With bank B heard, a serializer (a save, HX Edit's Get edit buffer) flips to bank A and back; each flip asks for the rings
    and the labels. Between the flips the hooks read bank A as live, so the tick refreshes and lays out nothing there; the flip
    back asks again and the next tick shows bank B."""
    bank_b_ready(hm)
    hm.cc(4)
    hm.hold_fs(1)
    hm.settings[BANK_SWITCH] = sel
    hm.tick()
    hm.leds.clear()
    hm.layouts.clear()
    assert hm.bank_b_live() and hm.data(VIEW) == 1
    hm.call('snaps_saving', STREAM, HEADER)
    assert hm.data(SAVING) == 1 and hm.data(LEDS) == 1 and hm.data(RELAYOUT) == 1
    hm.tick()
    assert hm.leds == [] and hm.layouts == [] and hm.data(LEDS) == 1 and hm.data(RELAYOUT) == 1
    hm.call('snaps_saved', STREAM, HEADER)
    assert hm.data(SAVING) == 0 and hm.bank_b_live()
    hm.tick()
    assert hm.leds == [(OBJ, 0)] and hm.layouts == [1] and hm.data(LEDS) == 0 and hm.data(RELAYOUT) == 0


def test_a_select_within_the_bank_and_a_hold_of_the_bank_shown_ask_for_no_ring_refresh(hm):
    """Within the live bank stock refreshes the rings itself after its select; holding the bank already shown moves nothing."""
    bank_b_ready(hm)
    hm.tick()
    hm.leds.clear()
    hm.tap(1)
    hm.hold_fs(0)
    hm.cc(2)
    assert hm.data(LEDS) == 0
    hm.tick()
    assert hm.leds == []


@pytest.mark.parametrize('why', ['stomp mode', 'tap', 'tuner'])
def test_leaving_snapshot_mode_hold_or_home_leaves_the_footswitches_alone(hm, why):
    """Back in Snapshot mode, on Hold or out of the tuner, the footswitches are still on the bank held: the tick only lays out."""
    viewing_b(hm)
    if why == 'stomp mode':
        hm.mode([2, 2, 2])
    elif why == 'tap':
        hm.settings[BANK_SWITCH] = TAP_SEL
    else:
        hm.view = TUNER_VIEW
    for _ in range(3):
        hm.tick()
    hm.mode([14, 14, 14])
    hm.settings[BANK_SWITCH], hm.view = HOLD_SEL, HOME_VIEW
    hm.tick()
    assert hm.data(VIEW) == 1 and hm.layouts == [] and hm.selects == []


def test_the_tick_leaves_a_hold_alone(hm):
    viewing_b(hm)
    for _ in range(3):
        hm.tick()
    assert hm.data(VIEW) == 1 and hm.layouts == []


def test_a_change_during_the_holds_layout_lays_out_again(hm):
    """A cross in another task, or a preset load, while the hold's layout runs: each stores RELAYOUT after what it changed, so the
    next tick lays out what they left."""
    bank_b_ready(hm)
    stores = [lambda: hm.data(RELAYOUT, 1), lambda: (hm.data(VIEW, 0), hm.data(RELAYOUT, 1))]
    for store, after in zip(stores, (1, 0)):
        hm.data(VIEW, 0)
        hm.layouts.clear()
        hm.during_layout = store
        hm.hold_fs(1)
        hm.during_layout = None
        assert hm.layouts == [1] and hm.data(RELAYOUT) == 1
        hm.tick()
        assert hm.layouts == [1, after] and hm.data(RELAYOUT) == 0


def test_a_change_during_the_ticks_layout_lays_out_again(hm):
    """A hold away from Home is laid out by the tick on Home's return; a load in another task during that layout sets RELAYOUT
    again, so the next tick lays out bank A."""
    bank_b_ready(hm)
    hm.view = EDIT_VIEW
    hm.hold_fs(1)
    hm.view = HOME_VIEW
    hm.layouts.clear()
    hm.during_layout = lambda: (hm.data(VIEW, 0), hm.data(RELAYOUT, 1))
    hm.tick()
    hm.during_layout = None
    assert hm.layouts == [1] and hm.data(RELAYOUT) == 1
    hm.tick()
    assert hm.layouts == [1, 0] and hm.data(RELAYOUT) == 0


@pytest.mark.parametrize('code', [9, 10, 11])
def test_touches_leave_the_footswitches_alone(hm, code):
    """A foot touches a cap with every press and hold: the hook ignores the caps' codes, so none of them moves the footswitches or
    lays the labels out (the built handler's copy or swap is test_the_built_handler_leaves_the_bank_held_for_a_copy_or_swap)."""
    viewing_b(hm)
    for kind in (PRESS, RELEASE, CLICK, HOLD):
        hm.event(code, kind)
    assert hm.data(VIEW) == 1 and hm.layouts == [] and hm.selects == []


def test_on_tap_the_hooks_follow_the_live_bank_and_keep_the_footswitches_on_it(hm):
    """Snapshot BankSel on Tap: the layout's reads and the labels' numbers are the live bank's, whatever bank a hold left the
    footswitches on. A snapshot footswitch press and every move between the banks put them on the live bank, where Hold finds
    them; with neither, the bank held stays held."""
    viewing_b(hm)
    hm.data(3, 0)
    hm.settings[BANK_SWITCH] = TAP_SEL
    assert [layout(hm, i)[::2] for i in range(3)] == [(0, b'A1'), (0, b'A2'), (0, b'A3')], 'the stock reads: bank A, 1 lit'
    assert hm.paint('home') == ([], [])
    hm.settings[BANK_SWITCH] = HOLD_SEL
    assert hm.data(VIEW) == 1, 'the bank held, with nothing between'
    hm.settings[BANK_SWITCH] = TAP_SEL
    hm.press(1)
    assert hm.data(VIEW) == 0 and hm.at_snapshot() == 2
    hm.cc(4)
    assert hm.data(VIEW) == 1 and hm.at_snapshot() == 5
    hm.data(VIEW, 0)
    hm.step(1)
    hm.step(1)
    assert hm.data(VIEW) == 0 and hm.at_snapshot() == 1, 'next on 6: back to bank A'
    hm.press(0)
    assert hm.data(VIEW) == 1 and hm.at_snapshot() == 4, 'the lit one: the flip'
    hm.settings[BANK_SWITCH] = HOLD_SEL
    assert layout(hm, 0)[0] == 0, 'on Hold the labels show the live bank, its snapshot lit'


def test_the_lit_click_goes_back_across_the_banks_with_reselect_snapshot(hm):
    """Reselect Snapshot set to go back: on 2, FS2 held and FS3 tapped is 6; FS3 again is 2, from the sound left, and FS2 again
    6. On 6, FS1 held and FS1 tapped is 1; FS1 again is 6. The footswitches follow each."""
    bank_b = bank_b_ready(hm)
    hm.settings[RESELECT] = 1
    hm.go(1)
    hm.hold_fs(1)
    hm.tap(2)
    assert hm.at_snapshot() == 6 and hm.data(PREV6) == 1 and hm.prev() == hm.cur()
    hm.selects.clear()
    hm.tap(2)
    (new, _, old_rec, new_rec), = hm.selects
    assert (new, old_rec, new_rec) == (1, bank_b[2], bank_a(1)) and hm.at_snapshot() == 2
    assert hm.data(VIEW) == 0 and hm.data(PREV6) == 5
    hm.tap(1)
    assert hm.at_snapshot() == 6 and hm.data(VIEW) == 1 and hm.data(PREV6) == 1
    hm.hold_fs(0)
    hm.tap(0)
    assert hm.at_snapshot() == 1 and hm.data(PREV6) == 5
    hm.tap(0)
    assert hm.at_snapshot() == 6 and hm.data(VIEW) == 1 and hm.data(PREV6) == 0


def test_the_lit_click_goes_back_within_the_bank_as_stock(hm):
    """The previous snapshot in the live bank: stock select, whose swap of the current and previous ones goes back."""
    bank_b_ready(hm)
    hm.settings[RESELECT] = 1
    hm.tap(1)
    assert hm.at_snapshot() == 2 and hm.data(PREV6) == 0
    hm.tap(1)
    assert hm.at_snapshot() == 1 and hm.prev() == 1 and hm.data(PREV6) == 1
    hm.tap(0)
    assert hm.at_snapshot() == 2 and hm.data(PREV6) == 0
    assert [(new, old) for new, old, _, _ in hm.selects] == [(1, 0), (0, 1), (1, 0)] and not hm.bank_b_live()


def test_an_outside_select_is_the_previous_snapshot_for_the_lit_click(hm):
    """On 2, FS2 held and FS3 tapped (6), then HX Edit selects 4: the lit FS1 goes back to 6, within bank B, as stock does."""
    bank_b_ready(hm)
    hm.settings[RESELECT] = 1
    hm.go(1)
    hm.hold_fs(1)
    hm.tap(2)
    hm.m.call(SELECT, MGR, 0)
    assert hm.at_snapshot() == 4 and hm.data(PREV6) == 5 and hm.prev() == 2
    hm.tap(0)
    assert hm.at_snapshot() == 6 and hm.data(PREV6) == 3


def test_an_aborted_hold_of_the_lit_switch_goes_back_with_reselect_snapshot(hm):
    bank_b_ready(hm)
    hm.settings[RESELECT] = 1
    hm.go(1)
    hm.hold_fs(1)
    hm.tap(2)
    hm.fs_press(2)
    hm.fs_fire()
    hm.fs_release(2)                        # before the hold: a click
    hm.fs_click(2)
    assert hm.at_snapshot() == 2 and hm.data(VIEW) == 0


def test_the_lit_click_recalls_with_reselect_snapshot_off(hm):
    bank_b_ready(hm)
    hm.go(1)
    hm.hold_fs(1)
    hm.tap(2)
    hm.selects.clear()
    hm.tap(2)
    assert [(new, old) for new, old, _, _ in hm.selects] == [(2, 2)] and hm.at_snapshot() == 6 and hm.data(PREV6) == 1


def test_cc_69s_lit_value_and_the_command_center_stay_within_the_bank(hm):
    """Right after a move between the banks the previous snapshot select keeps is the current one, so CC 69's lit value and the
    Command Center's lit snapshot stay put with Reselect Snapshot set to go back; the lit footswitch still goes back across."""
    bank_b_ready(hm)
    hm.settings[RESELECT] = 1
    hm.go(1)
    hm.hold_fs(1)
    hm.tap(2)
    hm.selects.clear()
    hm.cc(5)
    hm.call('snaps_action_select', MGR, 2)
    assert [(new, old) for new, old, _, _ in hm.selects] == [(2, 2), (2, 2)] and hm.at_snapshot() == 6 and hm.data(PREV6) == 1
    hm.tap(2)
    assert hm.at_snapshot() == 2


def layout(m, k):
    """The layout's reads of snapshot k through the module's hooks: (current, colour, name, renamed)."""
    return (m.call('snaps_layout_cur', MGR), m.call('snaps_layout_colour', MGR, k),
            m.m.read(m.call('snaps_layout_name', MGR, k), 11).split(b'\0')[0], m.call('snaps_layout_renamed', MGR, k))


def test_the_layout_reads_follow_the_bank_the_footswitches_select_in(hm):
    for i in range(3):                      # bank A: colours 3 + i, names A1..A3, A2 renamed
        r = bytearray(bank_a(i))
        r[COLOUR], r[RENAMED] = 3 + i, int(i == 1)
        hm.m.write(record(i), r)
    hm.m.u8(MGR + CUR, 1)
    stock = [(1, 3 + i, f'A{i + 1}'.encode(), int(i == 1)) for i in range(3)]
    assert [layout(hm, i) for i in range(3)] == stock, 'the live bank: the stock reads'
    shadow = CODE + hm.sym['snaps_shadow']
    for i in range(3):
        r = bytearray(REC)
        r[COLOUR], r[RENAMED] = 9, 1
        r[NAME:NAME + 3] = b'OLD'
        hm.m.write(shadow + REC * i, r)
    hm.data(VIEW, 1)
    assert [layout(hm, i) for i in range(3)] == [(NONE, 0, f'SNAPSHOT {i + 4}'.encode(), 0) for i in range(3)], \
        'bank B not made yet: its defaults, none lit, whatever the last preset left in the shadow'
    for i in range(3):
        r = bytearray(REC)
        r[COLOUR], r[RENAMED] = 7 + i, int(i == 2)
        r[NAME:NAME + 3] = f'B{i + 4}'.encode()
        hm.m.write(shadow + REC * i, r)
    hm.data(1, 1)
    assert [layout(hm, i) for i in range(3)] == [(NONE, 7 + i, f'B{i + 4}'.encode(), int(i == 2)) for i in range(3)]
    hm.data(0, 1)
    hm.data(VIEW, 0)
    assert [layout(hm, i) for i in range(3)] == [(NONE, 7 + i, f'B{i + 4}'.encode(), int(i == 2)) for i in range(3)], \
        'bank B live: bank A waits in the shadow'
    hm.data(VIEW, 1)
    assert [layout(hm, i) for i in range(3)] == stock, 'VIEW on the live bank: the stock reads'
    hm.data(VIEW, 0)
    hm.settings[BANK_SWITCH] = TAP_SEL
    assert [layout(hm, i) for i in range(3)] == stock, 'Tap: the stock reads, whatever VIEW says'


def test_the_labels_show_the_bank_the_footswitches_select_in(hm):
    """Pointed at bank B with bank A live: 4..6 over the labels, none lit, and the top icon stays on the live snapshot; pointed at
    bank A with bank B live (CC 69 made it live, which leaves them there): no numbers over the labels, the top icon still 4..6."""
    viewing_b(hm)
    hm.data(3, 0)
    assert hm.paint('home', lit=NONE) == (labels(None), [])
    assert hm.paint() == ([], []), 'the top icon: bank A is live'
    hm.hold_fs(0)
    hm.go(1)
    hm.cc(4)
    assert hm.data(VIEW) == 0 and hm.at_snapshot() == 5
    assert hm.paint('home', lit=NONE) == ([], [])
    assert hm.paint() == (top('5'), [])
    hm.hold_fs(1)
    assert hm.paint('home') == (labels(1), []), 'back on the live bank B'


@pytest.mark.parametrize('how', ['flip', 'cc', 'wrap', 'click'])
def test_a_cross_leaves_the_previous_snapshot_on_the_new_one(mgr, how):
    """The previous snapshot after a cross is the new one, so Reselect Snapshot's previous recalls it rather than jump to an index
    of the other bank."""
    with_bank_b(mgr)
    mgr.go(1)
    mgr.go(2)
    if how == 'flip':
        mgr.press(2)
    elif how == 'cc':
        mgr.cc(4)
    elif how == 'wrap':
        mgr.step(1)
    else:
        mgr.settings[BANK_SWITCH] = HOLD_SEL
        mgr.hold_fs(1)
        mgr.tap(0)
    assert mgr.bank_b_live() and mgr.prev() == mgr.cur() and mgr.data(PREV6) == 2, 'snapshot 3, in PREV6'


@pytest.mark.parametrize('k', [0, 1, 2])
def test_the_snapshot_action_is_stock_on_hold_and_flips_on_tap(mgr, k):
    """The Command Center's snapshot k: on Hold stock select in the live bank, the lit one too, leaving the footswitches on the
    bank held; on Tap the flip, which puts them on the live bank."""
    with_bank_b(mgr)
    mgr.go(k)
    mgr.settings[BANK_SWITCH] = HOLD_SEL
    mgr.hold_fs(1)
    mgr.call('snaps_action_select', MGR, k)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(k, k)] and not mgr.bank_b_live() and mgr.data(VIEW) == 1
    mgr.selects.clear()
    mgr.settings[BANK_SWITCH] = TAP_SEL
    mgr.call('snaps_action_select', MGR, k)
    assert mgr.bank_b_live() and mgr.cur() == k and mgr.data(VIEW) == 1, 'Tap: the flip'


def module_of(read, sym):
    """Where the build put the module: from its footswitch select hook."""
    return branch_target(ms.FS_SELECT_CALL, read(ms.FS_SELECT_CALL, 4)) - sym['snaps_select']


def chain_handlers(read, stub, before, after):
    """The handlers a chain stub (tools/patch_menu.py chain_cave) calls before and after the original."""
    at = stub + 2
    befores = []
    for _ in range(before):
        befores.append(branch_target(at + 4, read(at + 4, 4)))
        at += 8
    at += 4 + 8 + 6
    afters = []
    for _ in range(after):
        afters.append(branch_target(at + 4, read(at + 4, 4)))
        at += 8
    return befores, afters


@pytest.mark.firmware
def test_build_sends_the_snapshot_footswitch_to_the_module_and_wraps_load_and_save(m4emu):
    code, sym = m4emu.assemble('src/m4/more_snapshots.s', MODS, IDS)
    _, esym = m4emu.assemble('src/m4/preset_keys.s', MODS, IDS, inc={'preset_keys.inc': pm.preset_keys_inc({ms.FILE_KEY: ('', 0, 0)})})
    read, on = built({'HX_MORE_SNAPSHOTS': '1'})
    assert 'more_snapshots' in on
    module = module_of(read, sym)
    assert read(module, len(code)) == code
    engine = branch_target(pm.PRESET_FILE_CALLS[0][0], read(pm.PRESET_FILE_CALLS[0][0], 4)) - esym['pk_serialize']
    assert [branch_target(s, read(s, 4)) for s, _, _ in pm.PRESET_FILE_CALLS] == [engine + esym[h] for _, _, h in pm.PRESET_FILE_CALLS]
    tables = struct.unpack('<2I', read(engine + esym['pk_writers'], 8))
    assert tables == ((module + sym['snaps_key_write']) | 1, (module + sym['snaps_key_found']) | 1), 'key 0x64 on the preset file engine'
    hooks = ((ms.FS_SELECT_CALL, 'snaps_select'), (ms.ACTION_SELECT_CALL, 'snaps_action_select'), (ms.NEXT_CUR, 'snaps_next_cur'),
             (ms.PREV_CUR, 'snaps_prev_cur'), (ms.CC_SELECT, 'snaps_cc_select'), (ms.CC_VALUE_CALL, 'snaps_cc_value'),
             *((s, 'snaps_cc_wrap') for s in ms.CC_WRAP_CALLS), (ms.EVENT_CALL, 'snaps_event'),
             *((s, 'snaps_layout_cur') for s in ms.LAYOUT_CUR_CALLS), *((s, 'snaps_layout_colour') for s in ms.LAYOUT_COLOUR_CALLS),
             (ms.LAYOUT_NAME_CALL, 'snaps_layout_name'), (ms.LAYOUT_RENAMED_CALL, 'snaps_layout_renamed'),
             (ms.LED_CUR_CALL, 'snaps_layout_cur'), (ms.LED_COLOUR_CALL, 'snaps_layout_colour'))
    assert [branch_target(s, read(s, 4)) for s, _ in hooks] == [module + sym[h] for _, h in hooks]
    for fn, before, after in ((ms.SELECT, 'snaps_selecting', None), (ms.PARSE, 'snaps_loaded', None),
                              *((fn, 'snaps_saving', 'snaps_saved') for fn, _ in ms.SERIALIZERS)):
        stub = branch_target(fn, read(fn, 4))
        assert chain_handlers(read, stub, 1, int(bool(after))) == ([module + sym[before]], [module + sym[after]] if after else [])
    tick = struct.unpack('<I', read(ms.TICK_LIT, 4))[0]
    assert tick & 1 and tick != ms.TICK
    assert chain_handlers(read, tick & ~1, 0, 1) == ([], [module + sym['snaps_tick']])


@pytest.mark.firmware
@pytest.mark.parametrize('env', [{}, {'HX_LONG_PRESS': '1'}], ids=['alone', 'with long press'])
def test_build_serves_snapshot_bank_sel_from_footswitches(env):
    """A virtual setting in Global Settings > Footswitches: after FS5 Function, or after long press's ten, whose pages stay put."""
    e0 = built_e0({'HX_MORE_SNAPSHOTS': '1', **env})
    assert_virtual(e0, ms, ms.SETTINGS[0])
    ids = [17, 97, 98, 99, *([IDS[f'long_press.{s.key}'] for s in long_press.SETTINGS] if env else []), 0xe6]
    assert struct.pack(f'<{len(ids)}H', *ids, ) + struct.pack('<H', pm.EMPTY_SLOT) * (-len(ids) % 3) in e0


DISPATCH, DISPATCH_END, DISPATCH_SWITCH = 0x28dd14a0, 0x28dd1880, 0x28dd14e0
TRAMPOLINE = 0x28740000
NEXT_FN, PREV_FN = 7, 8                     # footswitch functions SnpshtUp and SnpshtDn, as FS3..FS10 Function set them


@pytest.mark.firmware
@pytest.mark.parametrize('sel', [HOLD_SEL, TAP_SEL], ids=['hold', 'tap'])
@pytest.mark.parametrize('k', [3, 4])
def test_the_built_dispatch_crosses_the_banks_for_a_virtual_footswitch(m4emu, k, sel):
    """The built firmware's next and previous cases, entered at the dispatch's switch with its frame, as long press runs an FS6..FS10
    Function (and as a release of FS4 or FS5 reaches them): next on 3 goes to 4 and on 6 to 1, previous on 1 to 6. On Hold too:
    the steps within a bank are marked, so snaps_select does not hold them back as a press of snapshot k."""
    code, sym = m4emu.assemble('src/m4/more_snapshots.s', MODS, IDS)
    read, on = built({'HX_MORE_SNAPSHOTS': '1', 'HX_LONG_PRESS': '1'})
    assert {'more_snapshots', 'long_press'} <= set(on)
    mgr = Manager(m4emu, module_of(read, sym))
    mgr.m.load(DISPATCH, read(DISPATCH, DISPATCH_END - DISPATCH))
    mgr.m.stub(0x28d960a4, lambda m: m.reg('r0', MGR))
    # push {r4-r6,lr}; sub sp,#16; r4 k, r6 the object, r5 2k, r3 the function - 1; then the dispatch's switch
    mgr.m.load(TRAMPOLINE, bytes.fromhex('70b5 84b0 0446 0e46 6500 1346') + pm.thumb_bw(TRAMPOLINE + 12, DISPATCH_SWITCH))

    def release(fn):
        """A release of footswitch k with function fn, its press marked as the press case marks it."""
        mgr.m.u8(OBJ + 0x78 + k, 0)
        mgr.m.u8(OBJ + (0x5d if fn == NEXT_FN else 0x5e), 1)
        mgr.m.call(TRAMPOLINE, k, OBJ, fn - 1)
        return mgr.cur() + 3 * mgr.bank_b_live() + 1

    with_bank_b(mgr)
    mgr.settings[BANK_SWITCH] = sel
    assert [release(NEXT_FN) for _ in range(6)] == [2, 3, 4, 5, 6, 1]
    assert [release(PREV_FN) for _ in range(6)] == [6, 5, 4, 3, 2, 1]
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    mgr.m.u8(MGR + CUR, 2)
    assert release(NEXT_FN) == 1 and mgr.inits == [], 'with no bank B, next on 3 wraps to 1'


CC_HANDLER, CC_HANDLER_END = 0x28d9b120, 0x28d9b700


@pytest.mark.firmware
@pytest.mark.parametrize('sel', [HOLD_SEL, TAP_SEL], ids=['hold', 'tap'])
def test_the_built_cc_handler_selects_all_six_snapshots_by_cc_69(m4emu, sel):
    """The built firmware's CC handler (cc, value), from its entry: CC 69's 0..5 land on snapshots 1..6 from either bank, 6 and 7
    still do nothing, and next and previous still run through all six, whatever Snapshot BankSel says."""
    code, sym = m4emu.assemble('src/m4/more_snapshots.s', MODS, IDS)
    read, on = built({'HX_MORE_SNAPSHOTS': '1'})
    assert 'more_snapshots' in on and read(ms.CC_RANGE, 2) == ms.CC_RANGE_SIX
    mgr = Manager(m4emu, module_of(read, sym), bank_switch=sel)
    mgr.m.load(CC_HANDLER, read(CC_HANDLER, CC_HANDLER_END - CC_HANDLER))
    mgr.m.stub(ms.MANAGER_GET, lambda m: m.reg('r0', MGR))

    def cc(value):
        mgr.m.call(CC_HANDLER, 69, value)
        return mgr.cur() + 3 * mgr.bank_b_live() + 1

    assert [cc(v) for v in (4, 1, 5, 0, 3, 2)] == [5, 2, 6, 1, 4, 3]
    mgr.selects.clear()
    assert [cc(v) for v in (6, 7)] == [3, 3] and mgr.selects == [], '6 and 7 are ignored, as stock'
    assert [cc(8) for _ in range(6)] == [4, 5, 6, 1, 2, 3]
    assert [cc(9) for _ in range(6)] == [2, 1, 6, 5, 4, 3]


@pytest.mark.firmware
def test_build_draws_the_numbers_after_the_top_and_home_paints(m4emu):
    code, sym = m4emu.assemble('src/m4/more_snapshots.s', MODS, IDS)
    read, _ = built({'HX_MORE_SNAPSHOTS': '1'})
    module = module_of(read, sym)
    for lit, fn, handler in ((ms.TOP_PAINT_LIT, ms.TOP_PAINT, 'snaps_paint'), (ms.HOME_PAINT_LIT, ms.HOME_PAINT, 'snaps_home_paint')):
        stub = struct.unpack('<I', read(lit, 4))[0]
        assert stub & 1 and stub != fn
        stub &= ~1
        at = stub + len(pm.chain_cave(stub, stub, [], [stub])) - 12
        assert branch_target(at, read(at, 4)) == module + sym[handler]


def stock_images():
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    data, _ = pa.load_l6ia_from_any(stock)
    return pa.get_entry_swapped(data, 7), pa.get_entry_swapped(data, 8)


def pixels(e8, off, w, h):
    """{(x, y): pixel}, y counting up from the bottom, as the screen's column-major store."""
    px = struct.unpack_from(f'<{w * h}H', e8, off)
    return {(x, y): px[x * h + y] for x in range(w) for y in range(h)}


@pytest.mark.firmware
def test_the_number_covers_the_icon_digit_and_stays_inside_the_circle():
    """At the icon's place (top left 262, 237; anchor 6), the black box holds every white digit pixel of each snapshot icon and
    only black or digit pixels besides; hx28_boldFont's 4, 5 and 6, centred at x 291 from y 203, ink only inside the box. A lit
    camera (the labels') has a white circle and a dark digit: the box, white there, covers the digit and stays in the circle."""
    import image_store as im
    e7, e8 = stock_images()
    left, bottom = 262, 237 - 35
    box = {(x, y) for x in range(284, 300) for y in range(208, 230)}
    for name in (b'Icon_Snapshot1', b'Icon_Snapshot2', b'Icon_Snapshot3', b'Icon_Snapshot1Red', b'Icon_Snapshot2Red',
                 b'Icon_Snapshot3Red'):
        img = im.image(e7, e8, name)
        assert (img.width, img.height) == (52, 35)
        px = {(left + x, bottom + y): v for (x, y), v in pixels(e8, img.offset, 52, 35).items()}
        assert {p for p, v in px.items() if v == 0xffff} <= box, f'{name.decode()}: its digit is under the box'
        assert all(px[p] in (0, 0x0841, 0xffff) or im.pixel_rgb(px[p])[0] == im.pixel_rgb(px[p])[2] and sum(im.pixel_rgb(px[p])) > 600
                   for p in box), f'{name.decode()}: the box covers no part of the camera or its circle'
    _, table = im.font(e7, b'hx28_boldFont')
    for ch in '456':
        h, w, item = im.glyph(e7, table, ord(ch))
        off, _ = im.item(e8, item)
        ink = {(291 - w // 2 + x, 203 + y) for (x, y), v in pixels(e8, off, w, h).items() if v}
        assert ink <= box, f'{ch} inks outside the box'
    for name in (b'Icon_Snapshot1Sel', b'Icon_Snapshot2Sel', b'Icon_Snapshot3Sel'):
        img = im.image(e7, e8, name)
        assert (img.width, img.height) == (52, 35)
        px = {(left + x, bottom + y): v for (x, y), v in pixels(e8, img.offset, 52, 35).items()}
        disc = {(x, y) for x, y in px if (x - left - 29.5) ** 2 + (y - bottom - 16.5) ** 2 < 12 ** 2}
        assert {p for p in disc if px[p] != 0xffff} <= box, f'{name.decode()}: its dark digit is under the box'
        assert all((x - left - 29.5) ** 2 + (y - bottom - 16.5) ** 2 < 13.5 ** 2 for x, y in box), \
            f'{name.decode()}: the white box stays inside its white circle'


@pytest.mark.firmware
def test_without_the_flag_the_sites_stay_stock():
    read, on = built({})
    assert 'more_snapshots' not in on
    assert all(read(s, 4) == pm.thumb_bw(s, ms.SELECT) for s in (ms.FS_SELECT_CALL, ms.ACTION_SELECT_CALL, ms.CC_SELECT))
    assert read(ms.SELECT, 4) == ms.SELECT_STOCK and struct.unpack('<I', read(ms.TICK_LIT, 4))[0] == ms.TICK
    assert read(ms.EVENT_CALL, 4) == pm.bl(ms.EVENT_CALL, ms.SELECTED_BLOCK)
    assert all(read(s, 4) == pm.bl(s, ms.CUR_GET) for s in ms.LAYOUT_CUR_CALLS)
    assert all(read(s, 4) == pm.bl(s, ms.COLOUR_GET) for s in ms.LAYOUT_COLOUR_CALLS)
    assert read(ms.LAYOUT_NAME_CALL, 4) == pm.bl(ms.LAYOUT_NAME_CALL, ms.NAME_GET)
    assert read(ms.LAYOUT_RENAMED_CALL, 4) == pm.bl(ms.LAYOUT_RENAMED_CALL, ms.RENAMED_GET)
    assert read(ms.LED_CUR_CALL, 4) == pm.bl(ms.LED_CUR_CALL, ms.CUR_GET)
    assert read(ms.LED_COLOUR_CALL, 4) == pm.bl(ms.LED_COLOUR_CALL, ms.COLOUR_GET)
    assert read(ms.NEXT_CUR, 4) == pm.bl(ms.NEXT_CUR, ms.CUR_GET) and read(ms.PREV_CUR, 4) == pm.bl(ms.PREV_CUR, ms.CUR_GET)
    assert all(read(s, 4) == pm.bl(s, ms.MANAGER_GET) for s in (*ms.CC_WRAP_CALLS, ms.CC_VALUE_CALL))
    assert read(ms.CC_RANGE, 2) == ms.CC_RANGE_STOCK
    assert all(read(s, 4) == pm.bl(s, fn) for s, fn, _ in pm.PRESET_FILE_CALLS)
    assert read(ms.PARSE, 4) == ms.PARSE_STOCK and all(read(fn, 4) == stock for fn, stock in ms.SERIALIZERS)
    assert struct.unpack('<I', read(ms.TOP_PAINT_LIT, 4))[0] == ms.TOP_PAINT


EVERY = ('HX_BPM', 'HX_TAP_COLOR', 'HX_PRESET_COLOR', 'HX_GR', 'HX_BREATHING_LINE', 'HX_DSP_METER', 'HX_TUNER', 'HX_CLICK',
         'HX_LONG_PRESS', 'HX_REAL_NAMES', 'HX_USB_INPUT', 'HX_USB_MONITOR', 'HX_FX_GATE', 'HX_SCREEN_MIRROR')


@pytest.mark.firmware
def test_builds_alongside_every_other_feature():
    """No other feature writes over its sites: a clash fails the build (Patch.put)."""
    _, on = built({'HX_MORE_SNAPSHOTS': '1', **{f: '1' for f in EVERY}})
    assert {'bpm', 'dsp_meter', 'long_press', 'more_snapshots', 'tap_color', 'preset_color', 'tuner'} <= set(on)


HANDLER, HANDLER_END = 0x28dd1978, 0x28dd2360           # the footswitch event handler and its literals
DEFERRED, DEFERRED_END = 0x28dd18b0, 0x28dd1978         # the deferred dispatch the request task runs (item at the object's +0xb4)
TIMER_CB, TIMER_CB_END = 0x28dd048c, 0x28dd04d8         # the 30-tick timer's callback
TIMER_START, TIMER_STOP, OBJ_GET, DEFER = 0x28da6428, 0x28da6454, 0x28d96114, 0x28d96800
CRITICAL, CRITICAL_END, FUNCTIONS_GET = 0x28e24a90, 0x28e249a8, 0x28d9607c
FS_LEARN, CC_LEARN = 0x28dda360, 0x28ddf6dc             # the dispatch's learn of a footswitch press (lists, k), (controllers, k + 3, -)
COPY_SWAP, COPY_SWAP_HELD = 0x28d9668c, 0x28df02f4      # the touch copy or swap of snapshots (k, j), and its guard () -> 0
LEAVE_TUNER, MODE_BANK = 0x28d965d8, 0x28dd0f44
LAYOUT_LOOP, LAYOUT_LOOP_END = 0x28dc87cc, 0x28dc8c80   # the Home layout, its Snapshot-mode branch and its coloured path
CAMERA_TABLES = 0x28e3ab94                              # its three tables: +0x18 the cameras, +0x30 the lit (Sel) ones


class BuiltHandler(Manager):
    """The built footswitch event handler, its function dispatch, the 30-tick timer's callback and the deferred dispatch, in
    unicorn with the module where the build put it: the key task posts each event to the handler; the timer and the request
    task are run by hand (fire), so a test orders them as it likes."""

    def __init__(self, m4emu, env=None, bank_switch=HOLD_SEL):
        code, sym = m4emu.assemble('src/m4/more_snapshots.s', MODS, IDS)
        env = {'HX_MORE_SNAPSHOTS': '1', **(env or {})}
        e0 = built_e0(env)
        read = reader(e0)
        super().__init__(m4emu, module_of(read, sym), bank_switch)
        stock_end = pa._parse_e0_segments(stock_e0())[6]
        _, _, slen, dst, _ = pa._parse_e0_segments(e0)[6]
        cave = stock_end[3] + stock_end[2]
        self.m.load(cave, read(cave, dst + slen - cave))        # the module, long press's and the chain stubs, as built
        self.m.load(self.at, code)
        for lo, hi in ((HANDLER, HANDLER_END), (DISPATCH, DISPATCH_END), (DEFERRED, DEFERRED_END), (TIMER_CB, TIMER_CB_END)):
            self.m.load(lo, read(lo, hi - lo))
        self.m.load(SELECT, pm.chain_cave(SELECT, STOCK_SELECT, [self.at + self.sym['snaps_selecting']], []))
        self.timer, self.items, self.setters = None, [], []
        self.m.stub(TIMER_START, self._timer_start)
        self.m.stub(TIMER_STOP, lambda m: setattr(self, 'timer', None))
        self.m.stub(OBJ_GET, lambda m: m.reg('r0', OBJ))
        self.m.stub(DEFER, lambda m: self.items.append(m.reg('r0')))
        self.m.stub(CRITICAL)
        self.m.stub(CRITICAL_END)
        self.m.stub(FUNCTIONS_GET, lambda m: m.reg('r0', FS_FUNCTIONS - 4))
        self.learned, self.copies = [], []
        self.m.stub(FS_LEARN, lambda m: self._learn(m, 0))
        self.m.stub(CC_LEARN, lambda m: self._learn(m, 1))
        self.m.stub(COPY_SWAP_HELD, lambda m: m.reg('r0', 0))
        self.m.stub(COPY_SWAP, lambda m: self.copies.append((m.reg('r0'), m.reg('r1'))))
        self.m.stub(ms.MANAGER_GET, lambda m: m.reg('r0', MGR))
        self.m.stub(LEAVE_TUNER)
        self.m.stub(MODE_BANK)
        self.m.stub(pm.SETTER_CONTEXT, lambda m: m.reg('r0', 0x28128000))
        self.m.stub(pm.SETTER, self._setter)

    def _timer_start(self, m):
        assert (m.reg('r0'), m.reg('r1'), m.reg('r2')) == (OBJ + 0x88, 30, TIMER_CB | 1), 'the press waits 30 ticks'
        self.timer = TIMER_CB

    def _setter(self, m):
        pid, value = m.reg('r1'), m.u32(m.reg('r2') + 4)
        self.setters.append((pid, value))
        if pid == FS_MODE:
            self.settings[FS_MODE] = value
            self.mode([5, 6, 3])

    def _learn(self, m, which):
        """A learn takes footswitch k's press; it is done before the click comes, its flags cleared."""
        self.learned.append((which, m.reg('r1') - 3 * which))
        self.learning = [0, 0]

    def post(self, code, kind):
        """The key task's post of {1, code, -, -, kind} to the handler."""
        self.m.write(EVENT, bytes([1, code, 0, 0]) + struct.pack('<I', kind))
        self.m.call(HANDLER, EVENT, OBJ)

    def fire(self):
        """The 30-tick timer runs out, then the request task runs what it queued."""
        if self.timer:
            self.timer = None
            self.m.call(TIMER_CB, 0)
        while self.items:
            self.m.call(DEFERRED, self.items.pop(0))

    def tap(self, k, short=False):
        self.post(12 + k, PRESS)
        if not short:
            self.fire()
        self.post(12 + k, RELEASE)
        self.post(12 + k, CLICK)
        self.fire()

    def hold_fs(self, k):
        self.post(12 + k, PRESS)
        self.fire()
        self.post(12 + k, HOLD)
        self.post(12 + k, RELEASE)

    def foot_tap(self, k, short=False):
        """Footswitch k tapped by a foot, which touches its cap first and leaves it last: the key task posts the cap's click after
        its release, as for every key (tools/hx_devtest.py foot_tap sends none)."""
        self.post(9 + k, PRESS)
        self.tap(k, short)
        self.post(9 + k, RELEASE)
        self.post(9 + k, CLICK)

    def foot_hold(self, k, touch_first=True):
        """Footswitch k held by a foot: the cap's press with the switch's, both holds after 1 s (the cap's first, as
        tools/hx_devtest.py foot_hold sends them, or the switch's), the switch let go, then the cap."""
        self.post(9 + k, PRESS)
        self.post(12 + k, PRESS)
        self.fire()
        for code in ((9, 12) if touch_first else (12, 9)):
            self.post(code + k, HOLD)
        self.post(12 + k, RELEASE)
        self.post(9 + k, RELEASE)


@pytest.mark.firmware
def test_the_built_handler_holds_back_presses_and_selects_on_clicks(m4emu):
    """Hold: a press waits 30 ticks and its dispatch is held back; the click selects on the release, once, even for a tap shorter
    than the window; a hold of FS2 points the footswitches at bank B, and the next click crosses."""
    b = BuiltHandler(m4emu)
    bank_b = bank_b_ready(b)
    b.post(13, PRESS)
    assert b.timer == TIMER_CB and b.obj(PENDING) == 1
    b.fire()
    assert b.selects == [] and b.obj(PRESSED + 1) == 0, 'the deferred dispatch: held back'
    b.post(13, RELEASE)
    assert b.selects == []
    b.post(13, CLICK)
    assert [(new, old) for new, old, _, _ in b.selects] == [(1, 0)]
    b.selects.clear()
    b.tap(2, short=True)
    assert [(new, old) for new, old, _, _ in b.selects] == [(2, 1)], 'a short tap: once, on its click'
    b.selects.clear()
    b.tap(2)
    assert [(new, old) for new, old, _, _ in b.selects] == [(2, 2)], 'the lit one: stock select, which Reselect Snapshot handles'
    b.selects.clear()
    b.hold_fs(1)
    assert b.selects == [] and b.data(VIEW) == 1 and b.layouts == [1]
    b.tap(0)
    (new, _, _, new_rec), = b.selects
    assert (new, new_rec) == (0, bank_b[0]) and b.at_snapshot() == 4 and b.data(VIEW) == 1 and b.data(RELAYOUT) == 1
    b.tick()
    assert b.layouts[-1] == 1 and b.data(RELAYOUT) == 0


@pytest.mark.firmware
@pytest.mark.parametrize('first, second, mode', [(0, 1, 2), (1, 2, 2), (0, 2, SNAPSHOT_MODE), (1, 0, 2), (2, 1, 2)])
def test_the_built_handler_keeps_the_stock_combos(m4emu, first, second, mode):
    """FS1+FS2 and FS2+FS3 inside the window switch to Preset mode, its bank view; FS1+FS3 is dropped: neither press selects."""
    b = BuiltHandler(m4emu)
    b.post(12 + first, PRESS)
    b.post(12 + second, PRESS)
    b.fire()
    for k in (first, second):
        b.post(12 + k, RELEASE)
        b.post(12 + k, CLICK)
    b.fire()
    assert b.selects == [] and b.settings[FS_MODE] == mode
    assert b.setters == ([(FS_MODE, 2)] if mode == 2 else [])


@pytest.mark.firmware
def test_the_built_handler_selects_a_quick_tap_and_another_inside_its_window(m4emu):
    """FS1 let go inside its window, then FS3 pressed inside it: no combo, as FS1 is no longer pressed; each selects on its click."""
    b = BuiltHandler(m4emu)
    for code in (12, 14):
        for kind in (PRESS, RELEASE, CLICK):
            b.post(code, kind)
    b.fire()
    assert [new for new, _, _, _ in b.selects] == [0, 2] and b.settings[FS_MODE] == SNAPSHOT_MODE


@pytest.mark.firmware
@pytest.mark.parametrize('touch_first', [True, False], ids=['touch hold first', 'switch hold first'])
def test_the_built_handler_takes_a_foots_holds_and_taps(m4emu, touch_first):
    """A foot touches the cap with every press and lets it go last, so a touch, its hold and its release come with every hold
    and tap: FS2 held then FS1 tapped is 4; FS1 held then FS3 tapped is 3, a short tap too; the lit one again is stock select."""
    b = BuiltHandler(m4emu)
    bank_b = bank_b_ready(b)
    b.foot_hold(1, touch_first)
    assert b.selects == [] and b.data(VIEW) == 1 and b.layouts == [1], 'the hold, and the cap let go after it'
    b.foot_tap(0)
    (new, _, _, new_rec), = b.selects
    assert (new, new_rec) == (0, bank_b[0]) and b.at_snapshot() == 4 and b.data(VIEW) == 1
    b.selects.clear()
    b.foot_hold(0, touch_first)
    assert b.selects == [] and b.data(VIEW) == 0
    b.foot_tap(2, short=True)
    assert [new for new, _, _, _ in b.selects] == [2] and b.at_snapshot() == 3 and b.data(VIEW) == 0
    b.foot_tap(2)
    assert [(new, old) for new, old, _, _ in b.selects][1:] == [(2, 2)] and b.at_snapshot() == 3
    assert b.copies == [] and b.armed() == [0, 0, 0]


@pytest.mark.firmware
def test_the_built_handler_keeps_bank_a_held_with_bank_b_live(m4emu):
    """On 5, reached with the footswitches, a foot holds FS1: they stay on bank A, the labels laid out for it with no numbers, through
    the switch's and the cap's release, ticks and paints, two caps touched and one held, HX Edit's select, CC 69 into either bank,
    SnpshtUp and SnpshtDn, the Command Center, a save or HX Edit's Get edit buffer (the serializers' chain), a tap during its flips
    (which selects nothing), the tuner, another footswitch mode and the setting on Tap and back; FS1 tapped then selects 1."""
    b = BuiltHandler(m4emu)
    bank_b_ready(b)
    b.foot_hold(1)
    b.foot_tap(1)
    b.tick()
    assert b.at_snapshot() == 5 and b.data(VIEW) == 1
    b.layouts.clear()
    b.foot_hold(0)
    assert b.data(VIEW) == 0 and b.layouts == [0] and b.at_snapshot() == 5

    def away(**state):
        def run():
            was = b.view, b.settings[BANK_SWITCH], [b.m.read(FS_FUNCTIONS + 2 * k, 1)[0] for k in range(3)]
            b.view = state.get('view', b.view)
            b.settings[BANK_SWITCH] = state.get('sel', b.settings[BANK_SWITCH])
            b.mode(state.get('functions', was[2]))
            for _ in range(3):
                b.tick()
            b.view, b.settings[BANK_SWITCH] = was[:2]
            b.mode(was[2])
        return run

    gestures = [('touches', lambda: [b.post(c, t) for c, t in ((9, PRESS), (10, PRESS), (10, HOLD), (10, RELEASE), (9, RELEASE))]),
                ("HX Edit's select", lambda: b.m.call(SELECT, MGR, 2)), ('CC 69 into bank A', lambda: b.cc(1)),
                ('CC 69 into bank B', lambda: b.cc(3)), ('SnpshtUp', lambda: b.step(1)), ('SnpshtDn', lambda: b.step(-1)),
                ('the Command Center', lambda: b.call('snaps_action_select', MGR, 1)),
                ('a save or Get edit buffer', b.save),
                ("a tap during the serializer's flips", lambda: (b.call('snaps_saving', STREAM, HEADER), b.foot_tap(2),
                                                                 b.call('snaps_saved', STREAM, HEADER))),
                ('the tuner', away(view=TUNER_VIEW)), ('stomp mode', away(functions=[2, 2, 2])), ('tap', away(sel=TAP_SEL))]
    for what, gesture in gestures:
        gesture()
        for _ in range(3):
            b.tick()
        events, _ = b.paint('home', lit=NONE)
        assert b.data(VIEW) == 0 and set(b.layouts) == {0}, what
        assert not [e for e in events if e[0] == 'text'], f"{what}: no numbers over bank A's labels"
    assert b.at_snapshot() == 5 and b.copies == [(1, 0)] and len(b.saved) == 1
    b.foot_tap(0)
    assert b.at_snapshot() == 1 and b.data(VIEW) == 0


@pytest.mark.firmware
def test_the_built_handler_goes_back_across_the_banks_with_reselect_snapshot(m4emu):
    """Reselect Snapshot set to go back, with a foot: on 2, FS2 held and FS3 tapped is 6, FS3 again 2, FS2 again 6; FS1 held and
    FS1 tapped is 1, FS1 again 6. Within bank B a tap and its lit one again go back as stock does, a short tap too."""
    b = BuiltHandler(m4emu)
    bank_b_ready(b)
    b.settings[RESELECT] = 1
    b.foot_tap(1)
    b.foot_hold(1)
    b.foot_tap(2)
    assert b.at_snapshot() == 6
    seen = []
    for k in (2, 1):
        b.foot_tap(k)
        seen.append((b.at_snapshot(), b.data(VIEW)))
    assert seen == [(2, 0), (6, 1)]
    b.foot_hold(0)
    b.foot_tap(0)
    assert b.at_snapshot() == 1
    b.foot_tap(0)
    assert b.at_snapshot() == 6 and b.data(VIEW) == 1
    b.foot_tap(0)
    b.foot_tap(0)
    assert b.at_snapshot() == 6 and b.bank_b_live()
    b.foot_tap(2, short=True)
    assert b.at_snapshot() == 4 and b.copies == [] and b.armed() == [0, 0, 0]


@pytest.mark.firmware
def test_the_built_handler_leaves_the_bank_held_for_a_copy_or_swap(m4emu):
    """Two caps touched and one held: stock's snapshot copy or swap of the live bank's records; the footswitches stay on the bank
    held and the labels are not laid out."""
    b = BuiltHandler(m4emu)
    bank_b_ready(b)
    b.hold_fs(1)
    b.layouts.clear()
    b.post(9, PRESS)
    b.post(11, PRESS)
    b.post(11, HOLD)
    b.post(11, RELEASE)
    b.post(9, RELEASE)
    b.tick()
    assert b.copies == [(2, 0)] and b.data(VIEW) == 1 and b.layouts == [] and b.selects == []


@pytest.mark.firmware
def test_the_built_handler_on_tap_flips_as_before(m4emu):
    """Snapshot BankSel on Tap: nothing armed; a press selects at the deferred dispatch, the lit one flips there, a hold changes
    no bank shown, and clicks select nothing more."""
    b = BuiltHandler(m4emu, bank_switch=TAP_SEL)
    b.post(13, PRESS)
    b.fire()
    assert [(new, old) for new, old, _, _ in b.selects] == [(1, 0)] and b.armed() == [0, 0, 0]
    b.post(13, RELEASE)
    b.post(13, CLICK)
    b.fire()
    assert len(b.selects) == 1
    b.foot_tap(1)
    assert b.bank_b_live() and b.at_snapshot() == 5 and len(b.selects) == 2, 'the lit one: the flip, from the deferred dispatch'
    b.foot_hold(0)
    assert b.at_snapshot() == 4 and len(b.selects) == 3 and b.data(VIEW) == 1 and b.armed() == [0, 0, 0]


@pytest.mark.firmware
def test_the_built_handler_selects_overlapping_presses_in_release_order(m4emu):
    """FS1 held past its window, FS3 pressed and let go, then FS1: each selects on its click, the last one let go wins."""
    b = BuiltHandler(m4emu)
    b.post(12, PRESS)
    b.fire()
    b.post(14, PRESS)
    b.fire()
    b.post(14, RELEASE)
    b.post(14, CLICK)
    b.post(12, RELEASE)
    b.post(12, CLICK)
    b.fire()
    assert [new for new, _, _, _ in b.selects] == [2, 0] and b.cur() == 0


def cc_fs(b, k, *kinds):
    """A MIDI CC 49..51 message for footswitch k, as the request task runs it: [obj+0x6d] set while it posts kinds (press,
    release and click at once; with the footswitch momentary in the preset, the on-value's press or the off-value's release
    and click), with no touch."""
    b.obj(IMMEDIATE, 1)
    for kind in kinds:
        b.post(12 + k, kind)
    b.obj(IMMEDIATE, 0)
    assert b.timer is None and b.items == []


@pytest.mark.firmware
def test_the_built_handler_takes_cc_49_to_51_as_taps(m4emu):
    """MIDI CC 49..51 in the request task: the press dispatches at once and is held back, and the hook selects on it in the bank
    the footswitches select in, as stock selects on it, whether the release comes with it or with a later message."""
    b = BuiltHandler(m4emu)
    bank_b = bank_b_ready(b)
    cc_fs(b, 1, PRESS, RELEASE, CLICK)
    cc_fs(b, 1, PRESS, RELEASE, CLICK)
    assert [(new, old) for new, old, _, _ in b.selects] == [(1, 0), (1, 1)], 'then the lit one: stock select (Reselect Snapshot)'
    b.selects.clear()
    b.hold_fs(1)
    cc_fs(b, 2, PRESS, RELEASE, CLICK)
    (new, _, _, new_rec), = b.selects
    assert (new, new_rec) == (2, bank_b[2]) and b.at_snapshot() == 6 and b.data(VIEW) == 1
    b.selects.clear()
    cc_fs(b, 0, PRESS)
    assert [(new, old) for new, old, _, _ in b.selects] == [(0, 2)], 'momentary: on the on-value, as stock'
    cc_fs(b, 0, HOLD)
    cc_fs(b, 0, RELEASE, CLICK)
    assert len(b.selects) == 1 and b.data(VIEW) == 1, 'the hold and the off-value do nothing'


@pytest.mark.firmware
@pytest.mark.parametrize('learn', [0, 1], ids=['bypass assign', 'controller assign'])
def test_the_built_handler_leaves_a_learned_press_to_the_learn(m4emu, learn):
    """While a learn waits, the dispatch gives FS1..3's press to it and selects nothing (0x28dd14a8..0x28dd14be): neither the
    click nor the hold after it selects or changes the bank shown, after the learn is done."""
    b = BuiltHandler(m4emu)
    bank_b_ready(b)
    for gesture in (b.tap, b.hold_fs, b.foot_hold, lambda k: cc_fs(b, k, PRESS, RELEASE, CLICK)):
        b.learning[learn] = 1
        gesture(1)
    assert b.learned == [(learn, 1)] * 4
    assert b.selects == [] and b.data(VIEW) == 0 and b.layouts == []


@pytest.mark.firmware
@pytest.mark.parametrize('code, fn', [(15, NEXT_FN), (16, PREV_FN)])
def test_the_built_handler_steps_within_a_bank_from_fs4_and_fs5_on_hold(m4emu, code, fn):
    """SnpshtUp on FS4 and SnpshtDn on FS5 dispatch on the press and act on the release; Hold must not hold their select back."""
    b = BuiltHandler(m4emu)
    with_bank_b(b)
    b.settings[BANK_SWITCH] = HOLD_SEL
    b.go(1)
    b.m.u8(FS_FUNCTIONS + 2 * (code - 12), fn)
    b.post(code, PRESS)
    b.post(code, RELEASE)
    b.post(code, CLICK)
    b.fire()
    assert [(new, old) for new, old, _, _ in b.selects] == [(2 if fn == NEXT_FN else 0, 1)] and not b.bank_b_live()


@pytest.mark.firmware
def test_long_press_passes_snapshot_mode_events_to_the_hook(m4emu):
    """Built with long press, which owns the handler's entry: in Snapshot mode its lp_event passes every event to the stock handler,
    whose call at 0x28dd1986 is the hook's."""
    b = BuiltHandler(m4emu, {'HX_LONG_PRESS': '1'})
    bank_b = bank_b_ready(b)
    assert b.m.read(HANDLER, 4) != long_press.HANDLER_STOCK, "the b.w to long press's lp_event"
    b.tap(1)
    assert [(new, old) for new, old, _, _ in b.selects] == [(1, 0)]
    b.selects.clear()
    b.hold_fs(1)
    b.tap(2)
    (new, _, _, new_rec), = b.selects
    assert (new, new_rec) == (2, bank_b[2]) and b.at_snapshot() == 6


@pytest.mark.firmware
def test_the_built_layout_shows_the_bank_the_footswitches_select_in(m4emu):
    """The built Home layout's Snapshot-mode branch, through the nine hooks: the live bank lights the current snapshot's camera
    (the Sel image) and reads its records; pointed at the other bank, no camera or colour is lit and the records are that bank's:
    a renamed one's name instead of its camera, a coloured one's colour."""
    b = BuiltHandler(m4emu)
    read = reader(built_e0({'HX_MORE_SNAPSHOTS': '1'}))
    b.m.load(LAYOUT_LOOP, read(LAYOUT_LOOP, LAYOUT_LOOP_END - LAYOUT_LOOP))
    b.m.write(CAMERA_TABLES, read(CAMERA_TABLES, 0x3c))   # its tables: renamed labels' text, the cameras, the lit ones
    images, visible, names, colours = {}, {}, [], []
    b.m.stub(0x28e24c18, lambda m: images.__setitem__(m.reg('r0'), m.reg('r1')))         # setImage
    b.m.stub(0x28e24a98, lambda m: visible.__setitem__(m.reg('r0'), m.reg('r1')))        # an image's setVisible
    b.m.stub(0x28daad94, lambda m: names.append(m.read(m.reg('r1'), 11).split(b'\0')[0]))    # the name's copy
    b.m.stub(0x28dd8110, lambda m: (colours.append((m.reg('r1'), m.reg('r2'))), m.reg('r0', 0)))   # (lists, colour, lit)
    for fn in (0x28e24bc8, 0x28e24a28, 0x28e24bc0, 0x28dc6fe0, 0x28daad1c, 0x28d968c4, 0x28e24a68, 0x28e24b98, 0x28e24b28,
               0x28e24b00, 0x28dc6e9c, REDRAW):
        b.m.stub(fn, lambda m: m.reg('r0', 0))
    b.m.u8(HOME + 5, 1)                     # laid out, and not the other Snapshot-mode branch
    b.m.u8(HOME + 0x61, 0)
    bank_b_ready(b)
    b.go(1)
    shadow = b.at + b.sym['snaps_shadow']
    for i in range(3):
        for at, colour, renamed in ((record(i), 0, 0), (shadow + REC * i, 5 * (i == 1), int(i == 2))):
            b.m.u8(at + COLOUR, colour)
            b.m.u8(at + RENAMED, renamed)

    def run():
        images.clear()
        visible.clear()
        names.clear()
        colours.clear()
        b.m.call(LAYOUT_LOOP, HOME, 0)
        return [images.get(LABELS + 0x24 * i) for i in range(3)], [visible[LABELS + 0x24 * i] for i in range(3)], list(names)

    plain, sel = struct.unpack('<3I', read(CAMERA_TABLES + 0x18, 12)), struct.unpack('<3I', read(CAMERA_TABLES + 0x30, 12))
    assert run() == ([plain[0], sel[1], plain[2]], [1, 1, 1], [b'A1', b'A2', b'A3']) and colours == []
    b.data(VIEW, 1)
    assert run() == ([plain[0], plain[1], None], [1, 1, 0], [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6'])
    assert colours == [(5, 0)], "bank B's coloured snapshot 5, not lit"
    b.data(VIEW, 0)
    assert run()[0] == [plain[0], sel[1], plain[2]]


LED_COLOURS, FSW_GET, FSW_TYPE, LED_MODE, LED_SET, PALETTE = 0x28e3c498, 0x28d96094, 0x28de6634, 0x28db8260, 0x28db81fc, 0x28dd8030
RING_BRIGHTNESS = 0x19                      # LED Ring Brightness, which the refresh reads before it dims an unlit ring


@pytest.mark.firmware
def test_the_built_ring_refresh_lights_none_while_the_footswitches_point_at_the_other_bank(m4emu):
    """The built footswitch LED refresh (0x28dd0b3c) in Snapshot mode, through the two hooks: with the footswitches on the live
    bank, the current snapshot's ring lit in its colour (white for colour 0), the others dim in theirs (off for colour 0);
    pointed at the other bank, none lit, each ring dim in that bank's colour, as stock shows a snapshot not current, and off with
    LED Ring Brightness off; back on the live bank, lit again. The hold asks the tick, which refreshes. Tap: stock, whatever VIEW
    says."""
    b = BuiltHandler(m4emu)
    read = reader(built_e0({'HX_MORE_SNAPSHOTS': '1'}))
    b.m.load(ms.LED_REFRESH, read(ms.LED_REFRESH, 0x28dd0f44 - ms.LED_REFRESH))
    b.m.write(LED_COLOURS, read(LED_COLOURS, 0x18))          # its colour words: the white of a lit colour 0 among them
    rings = {}
    b.m.stub(FSW_GET, lambda m: m.reg('r0', 0x28128000))
    b.m.stub(FSW_TYPE, lambda m: m.reg('r0', 0))
    b.m.stub(LED_MODE, lambda m: rings.setdefault(m.reg('r0'), [None, None]).__setitem__(0, m.reg('r1')))
    b.m.stub(LED_SET, lambda m: rings.setdefault(m.reg('r0'), [None, None]).__setitem__(1, m.reg('r1') & 0xffffff))
    b.m.stub(PALETTE, lambda m: m.reg('r0', m.reg('r1') << 8 | m.reg('r2')))
    b.settings[RING_BRIGHTNESS] = 1
    bank_b_ready(b)
    b.go(1)
    shadow = b.at + b.sym['snaps_shadow']
    for i, (a, bb) in enumerate(((2, 5), (3, 0), (0, 7))):
        b.m.u8(record(i) + COLOUR, a)
        b.m.u8(shadow + REC * i + COLOUR, bb)

    def refresh(tick=False):
        rings.clear()
        if tick:
            b.tick()
        else:
            b.m.call(ms.LED_REFRESH, OBJ, 0)
        return [tuple(rings.get(k, (None, None))) for k in range(3)]

    white = struct.unpack('<I', read(0x28e3c4a8, 4))[0] & 0xffffff
    live = [(1, 0x200), (1, 0x301), (0, None)]          # colour 2 dim, the current colour 3 lit, colour 0 off
    assert refresh() == live
    b.hold_fs(1)
    assert refresh(tick=True) == [(1, 0x500), (0, None), (1, 0x700)], 'bank B shown: none lit, its colours dim'
    assert refresh(tick=True) == [(None, None)] * 3, 'refreshed once'
    b.settings[RING_BRIGHTNESS] = 0
    assert refresh() == [(0, None)] * 3, 'LED Ring Brightness off: unlit rings off, as stock'
    b.settings[RING_BRIGHTNESS] = 1
    b.hold_fs(0)
    assert refresh(tick=True) == live, 'back on the live bank: the current one lit again'
    b.cc(4)
    assert b.data(VIEW) == 0 and b.at_snapshot() == 5
    assert refresh(tick=True) == [(1, 0x200), (1, 0x300), (0, None)], 'bank B live, bank A shown: none lit, bank A dim'
    b.hold_fs(1)
    assert refresh(tick=True) == [(1, 0x500), (1, white), (1, 0x700)], 'bank B shown and live: 5 lit, white for colour 0'
    b.hold_fs(0)
    b.settings[BANK_SWITCH] = TAP_SEL
    assert refresh() == [(1, 0x500), (1, white), (1, 0x700)], 'Tap: stock, VIEW not read'


@pytest.mark.firmware
def test_stock_holds_back_the_editors_posts_while_its_count_is_up(m4emu):
    """The stock code the fix relies on, run in unicorn: 0x28d99728(1) adds one to the count at 0x281caa8c, (0) takes one off but
    not below 0, with no lock; while the count is above 0, 0x28d99820(event, data) and 0x28d99888() return 0 before they take an
    event; at 0 they take one of the queue 0x281caa28 (0x28d93884, with the fan-out 0x28d996bd), with data a block of the event
    pool through 0x28d93b14, which waits for one (wait 1, into 0x28d93954), and post it (0x28d93918). 0x28d99888's event is
    0x2102, with 0x40 bytes it makes itself."""
    read = reader(stock_e0())
    lo, hi = QUIET, 0x28d998f0
    m = m4emu.M4(read(lo, hi - lo), lo)
    event, data, buf = 0x28600000, 0x28600100, 0x28600200
    calls = []
    m.stub(0x28d93884, lambda m: (calls.append(('event', m.reg('r0'), *m.stack_args(2))), m.reg('r0', event)))
    m.stub(0x28d93b14, lambda m: (calls.append(('block', m.reg('r0'), m.reg('r1'))), m.reg('r0', 0)))
    m.stub(MEMCPY, lambda m: calls.append(('copy', m.reg('r0'), m.reg('r2'))))
    m.stub(0x28d93918, lambda m: (calls.append(('post', m.reg('r0'), m.reg('r1'))), m.reg('r0', 0)))
    m.u32(COUNT, 0)
    counts = []
    for on in (1, 1, 0, 0, 0):
        m.call(QUIET, on)
        counts.append(m.u32(COUNT))
    assert counts == [1, 2, 1, 0, 0]
    m.u32(COUNT, 1)
    assert m.call(0x28d99820, SWITCH_EV, data) == 0 and m.call(SELECTED_POST) == 0 and calls == []
    m.u32(COUNT, 0)
    for fn, args, ev in ((0x28d99820, (SWITCH_EV, data), SWITCH_EV), (SELECTED_POST, (), SELECTED_EV)):
        calls.clear()
        m.u32(event + 0x20, buf)
        m.u32(event + 0x30, 0)
        m.call(fn, *args)
        assert calls == [('event', 0x281caa28, 0x28d996bd, ev), ('block', event, 0x40), ('copy', buf, 0x40),
                         ('post', 0x281caa28, event)]
        assert m.u32(event + 0x30) == ev
    assert read(0x28d93b14, 6) == bytes.fromhex('0122') + pm.thumb_bw(0x28d93b16, 0x28d93954), 'movs r2,#1; b.w: wait 1'


@pytest.mark.firmware
def test_stock_select_posts_its_last_event_after_it_lets_d_go():
    """Stock select's posts, as the fix takes them: 0x2102 at 0x28de32d8, after D is let go at 0x28de32d4; the copy of an unused
    record with the count up (0x28de3294) and down (0x28de32c2) around it, as the module does around the whole select; a
    footswitch entry that changes posts 0x24112 under select's D (0x28de678e, its event at 0x28de67e0); an index above 2 leaves
    (0x28de2fe4) before any post, with -0x2e (0x28de36e2)."""
    read = reader(stock_e0())
    assert read(0x28de32d0, 12) == pm.bl(0x28de32d0, PRESET) + pm.bl(0x28de32d4, 0x28e02414) + pm.bl(0x28de32d8, SELECTED_POST)
    assert read(0x28de3294, 6) == bytes.fromhex('0120') + pm.bl(0x28de3296, QUIET)
    assert read(0x28de32c2, 6) == bytes.fromhex('0020') + pm.bl(0x28de32c4, QUIET)
    assert read(0x28de678e, 4) == pm.bl(0x28de678e, 0x28d99820) and struct.unpack('<I', read(0x28de67e0, 4))[0] == SWITCH_EV
    assert read(0x28de2fdc, 12) == bytes.fromhex('bbf1020f84f8a83900f27483'), 'cmp r11,#2; strb; bhi.w 0x28de36d0'
    assert read(0x28de3002, 8) == bytes.fromhex('bb48') + bytes.fromhex('0021') + pm.bl(0x28de3006, 0x28d99820), \
        'the first post (0x44113, no data) after the index check'
    assert read(0x28de36e2, 4) == bytes.fromhex('6ff02d05'), 'mvn r5, #0x2d'


@pytest.mark.firmware
def test_stock_refreshes_the_rings_with_the_handlers_object_and_not_in_the_tuner():
    """What snaps_tick's refresh copies: the registration 0x28dd27fc stores the footswitch handler and the tick (TICK_LIT) each
    with the handler's object (r4) as its argument, so the tick's second argument is the object the refresh takes; the message
    handler's refresh after a select (0x28dd26be) asks for the tuner view first and refreshes with (object, 0) only when it is
    not open."""
    read = reader(stock_e0())
    assert read(0x28dd281c, 2) == bytes.fromhex('474b') and struct.unpack('<I', read(0x28dd293c, 4))[0] == HANDLER | 1
    assert read(0x28dd2822, 4) == bytes.fromhex('c4e90234'), 'strd r3, r4, [r4, #8]: the handler and its object'
    assert read(0x28dd2830, 2) == bytes.fromhex('444a') and ms.TICK_LIT == 0x28dd2944
    assert read(0x28dd283a, 4) == bytes.fromhex('c4e90924'), 'strd r2, r4, [r4, #36]: the tick and the same object'
    assert read(0x28dd26be, 18) == (bytes.fromhex('0520') + pm.bl(0x28dd26c0, VIEW_IS) + bytes.fromhex('00289cd100212846')
                                    + pm.bl(0x28dd26cc, LED_REFRESH)), 'movs r0,#5; bl view_is; cmp; bne; movs r1,#0; mov r0,r5'


def code_refs(e0, word=None, call=None):
    """The ldr (literal) loads of word, or the bl calls of call, in Entry 0's code."""
    read, found = reader(e0), []
    for _, _, size, va, _ in pa._parse_e0_segments(e0):
        if va < 0x28d00000:
            continue
        blob = read(va, size)
        for i in range(0, size - 3, 2):
            h1, h2 = struct.unpack_from('<2H', blob, i)
            a = va + i
            if word is not None:
                if (h1 & 0xf800) == 0x4800:
                    t = ((a + 4) & ~3) + ((h1 & 0xff) << 2)
                elif (h1 & 0xff7f) == 0xf85f:
                    t = ((a + 4) & ~3) + ((h2 & 0xfff) if h1 & 0x80 else -(h2 & 0xfff))
                else:
                    continue
                if va <= t <= va + size - 4 and struct.unpack_from('<I', blob, t - va)[0] == word:
                    found.append(a)
            elif (h1 & 0xf800) == 0xf000 and (h2 & 0xd000) == 0xd000 and branch_target(a, blob[i:i + 4]) == call:
                found.append(a)
    return found


@pytest.mark.firmware
def test_the_editors_notify_listener_is_the_only_one_for_select_posts():
    """0x28d99820 and 0x28d99888 post to the queue 0x281caa28 with the fan-out 0x28d996bd, which hands an event to each listener
    on the list 0x281caa7c whose mask it matches. The list is loaded only by the fan-out, its set-up and the adder 0x28d997d0, and
    the adder is called only by the notify service (HX Edit), twice, with its listener 0x28e13a69, node 0x2844e8a0, mask 0x100.
    So holding these posts back leaves the unit's own screen and rings alone: they take other paths."""
    e0 = stock_e0()
    read = reader(e0)
    assert code_refs(e0, word=0x281caa7c) == [0x28d996c0, 0x28d9979c, 0x28d997e8]
    assert code_refs(e0, call=0x28d997d0) == [0x28e13a3c, 0x28e13ef6]
    for ldr_fn, ldr_node, mask in ((0x28e13a48, 0x28e13a4c, 0x28e13a38), (0x28e13f00, 0x28e13f04, 0x28e13ef2)):
        assert struct.unpack('<2I', read(ldr_fn, 4) + read(ldr_node, 4)) == (0x28e13a69, 0x2844e8a0)
        assert read(mask, 4) == bytes.fromhex('4ff48072'), 'mov.w r2, #0x100'
