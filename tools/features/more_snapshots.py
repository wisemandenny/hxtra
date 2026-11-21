"""More snapshots: a second bank of snapshots, 4-6, on the three snapshot footswitches (src/m4/more_snapshots.s). With Snapshot BankSel
on Hold (the default), holding FS1 for 1 s points the footswitches at snapshots 1-3 and holding FS2 at 4-6, a tap selects on its
release, and they stay on that bank until a hold, a tap or a preset load moves them, no label or ring lit while it is not the bank
heard; the lit one with Reselect Snapshot set to go back goes back across the banks too. On Tap, pressing the lit snapshot footswitch
again flips between 1-3 and 4-6. In 4-6 the snapshot icon at the top right and the footswitch labels show 4, 5 or 6. Once a preset
has a bank B, the next and previous snapshot footswitches and MIDI CC 69 run through all six: next on 3 goes to 4, next on 6 to 1,
previous on 1 to 6, previous on 4 to 3. MIDI CC 69's values 0..2 select snapshots 1..3 and 3..5 snapshots 4..6, from either bank."""
from features import Setting

FLAG = 'HX_MORE_SNAPSHOTS'
MENU = 'Footswitches'
# Hold: a 1 s hold of FS1 or FS2 picks the bank the snapshot footswitches select in, and a tap selects on its release; Tap: the lit
# one again flips the bank, as before the setting (both in src/m4/more_snapshots.s)
SETTINGS = (Setting('bank_switch', b'BankSel\nSnapshot', (b'Hold', b'Tap')),)

SELECT = 0x28de2f90                 # (manager, index): recalls a snapshot; chained before, for the snapshot it leaves
SELECT_STOCK = bytes.fromhex('2de9 f04f')                         # push.w {r4-r11,lr}
# The tail call of select (b.w) the footswitch functions reach (0x28dd14a0: 14 snapshot k for footswitch k, as Snapshot mode sets
# them [verified on unit], and 7, 8 next and previous), and the snapshot action's (0x28de59a8: the Command Center's snapshot k)
FS_SELECT_CALL, ACTION_SELECT_CALL = 0x28dd1640, 0x28de59d8
# Footswitch next and previous (the dispatch's cases 7 and 8) read the current snapshot at these calls of 0x28de3750, then wrap it in 0..2
NEXT_CUR, PREV_CUR, CUR_GET = 0x28dd1628, 0x28dd16dc, 0x28de3750
# MIDI CC 69 (0x28d9b120): its calls of the manager getter only where 8 (next) wraps 2 to 0 and 9 (previous) 0 to 2, and its select
CC_WRAP_CALLS, MANAGER_GET, CC_SELECT = (0x28d9b676, 0x28d9b6d8), 0x28d960a4, 0x28d9b5de
# CC 69's cmp r1, #2 before its select of the value: #5 sends 3..5 there too, which stock ignores; that path alone calls the manager
# getter at CC_VALUE_CALL, as next and previous within a bank select 0..2 through the same tail call
CC_RANGE, CC_RANGE_STOCK, CC_RANGE_SIX, CC_VALUE_CALL = 0x28d9b5a2, bytes.fromhex('0229'), bytes.fromhex('0529'), 0x28d9b63a
PARSE, PARSE_STOCK = 0x28de42c4, bytes.fromhex('2de9 f04f')     # the preset's snapshots into the manager; push.w {r4-r11,lr}
# The preset serializers: each copies the blocks, with their live values, then calls the snapshot writer 0x28de3c9c; a load takes the
# live values as its current snapshot's. 0x28dea8c4 (push.w {r4-r8,lr}) is the one a save on the unit took [verified on unit],
# 0x28deacf4 (push.w {r4-r11,lr}) the other save path's and HX Edit's (0x28e1c5b2). They are the writer's only callers.
SERIALIZERS = ((0x28dea8c4, bytes.fromhex('2de9 f041')), (0x28deacf4, bytes.fromhex('2de9 f04f')))
FILE_KEY = 0x64                     # bank B's key in the preset file, through tools/patch_menu.py's preset keys
TOP_PAINT_LIT, TOP_PAINT = 0x28d96d90, 0x28dca359              # the top view's paint (preset number, name, snapshot icon), as registered
HOME_PAINT_LIT, HOME_PAINT = 0x28d96e28, 0x28dc8d39            # the Home view's paint (footswitch labels), as registered
# The footswitch event handler 0x28dd1978's call of the selected block's getter, which every event reaches with the event in r4 and the
# handler's object in r5 (long press's own_entry takes only the handler's first 4 bytes, and its stock trampoline comes back before it)
EVENT_CALL, SELECTED_BLOCK = 0x28dd1986, 0x28df0280
# The footswitch tick (fspv-tick, class 3, in the key task), as registered: it lays the labels out after a move between the banks or a
# click that moves the footswitches' bank, from any task (CC 69 and CC 49..51 come from the request task, where select's own layout
# may run before the move is whole), after a hold away from Home, and after a preset load that takes Hold's footswitches off bank B
TICK_LIT, TICK = 0x28dd2944, 0x28dd1015
# The Snapshot-mode label layout (0x28dc87cc's loop at 0x28dc89d4 and its coloured path at 0x28dc8c2c): its reads of the current
# snapshot, and of snapshot k's colour (record +0x254), name (+0x255) and renamed flag (+0x24c)
LAYOUT_CUR_CALLS = (0x28dc8a02, 0x28dc8a16, 0x28dc8a60, 0x28dc8c42)
LAYOUT_COLOUR_CALLS, COLOUR_GET = (0x28dc89e6, 0x28dc89f4, 0x28dc8c38), 0x28de2f80
LAYOUT_NAME_CALL, NAME_GET = 0x28dc8a2c, 0x28de3864
LAYOUT_RENAMED_CALL, RENAMED_GET = 0x28dc8a3e, 0x28de3874
# The footswitch LED refresh 0x28dd0b3c's Snapshot case (function 14, 0x28dd0bae): its read of the current snapshot, and its read of
# a snapshot's colour for a ring that is not the current one (the current one's, 0x28dd0daa, is the live bank's)
LED_REFRESH, LED_CUR_CALL, LED_COLOUR_CALL = 0x28dd0b3c, 0x28dd0bb2, 0x28dd0bc2


def apply(p):
    m = p.module('src/m4/more_snapshots.s')
    p.own_call(FS_SELECT_CALL, SELECT, "the footswitch functions' call of select", m['snaps_select'])
    p.own_call(ACTION_SELECT_CALL, SELECT, "the snapshot action's call of select", m['snaps_action_select'])
    p.own_call(NEXT_CUR, CUR_GET, "footswitch next's read of the current snapshot", m['snaps_next_cur'])
    p.own_call(PREV_CUR, CUR_GET, "footswitch previous's read of the current snapshot", m['snaps_prev_cur'])
    for site in CC_WRAP_CALLS:
        p.own_call(site, MANAGER_GET, f"MIDI CC 69's call of the manager getter at {site:#x}, where it wraps", m['snaps_cc_wrap'])
    p.own_call(CC_SELECT, SELECT, "MIDI CC 69's call of select", m['snaps_cc_select'])
    p.own_call(CC_VALUE_CALL, MANAGER_GET, "MIDI CC 69's call of the manager getter before its select of the value", m['snaps_cc_value'])
    p.expect(CC_RANGE, CC_RANGE_STOCK, "MIDI CC 69's range of snapshot values")
    p.put(CC_RANGE, CC_RANGE_SIX, "MIDI CC 69's values 3..5, snapshots 4..6")
    p.chain_entry(SELECT, SELECT_STOCK, before=m['snaps_selecting'])
    p.chain_entry(PARSE, PARSE_STOCK, before=m['snaps_loaded'])
    p.preset_key(FILE_KEY, m['snaps_key_write'], m['snaps_key_found'])
    for fn, stock in SERIALIZERS:
        p.chain_entry(fn, stock, before=m['snaps_saving'], after=m['snaps_saved'])
    p.chain_ptr(TOP_PAINT_LIT, TOP_PAINT, after=m['snaps_paint'])
    p.chain_ptr(HOME_PAINT_LIT, HOME_PAINT, after=m['snaps_home_paint'])
    p.own_call(EVENT_CALL, SELECTED_BLOCK, "the footswitch event handler's call of the selected block's getter", m['snaps_event'])
    p.chain_ptr(TICK_LIT, TICK, after=m['snaps_tick'])
    for site in LAYOUT_CUR_CALLS:
        p.own_call(site, CUR_GET, f"the Snapshot-mode label layout's read of the current snapshot at {site:#x}", m['snaps_layout_cur'])
    for site in LAYOUT_COLOUR_CALLS:
        p.own_call(site, COLOUR_GET, f"the Snapshot-mode label layout's read of a snapshot's colour at {site:#x}",
                   m['snaps_layout_colour'])
    p.own_call(LAYOUT_NAME_CALL, NAME_GET, "the Snapshot-mode label layout's read of a snapshot's name", m['snaps_layout_name'])
    p.own_call(LAYOUT_RENAMED_CALL, RENAMED_GET, "the Snapshot-mode label layout's test for a renamed snapshot",
               m['snaps_layout_renamed'])
    p.own_call(LED_CUR_CALL, CUR_GET, "the footswitch LED refresh's read of the current snapshot", m['snaps_layout_cur'])
    p.own_call(LED_COLOUR_CALL, COLOUR_GET, "the footswitch LED refresh's read of an unlit snapshot's colour",
               m['snaps_layout_colour'])
