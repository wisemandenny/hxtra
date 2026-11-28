"""Tuner Activation (Hold or Press), Lock Tuner Settings (Off or On) and the note names (Flats or Sharps), on a third page of the tuner's
own settings (src/m4/tuner.s)."""
import image_store
from features import Setting
import patch_menu as pm

FLAG = 'HX_TUNER'
ORDER = 0
MENU = False
SETTINGS = (     # labels and values as src/m4/tuner.s draws them
    Setting('activate', b'Activate', (b'Hold', b'Press')),
    Setting('lock', b'Lock', (b'Off', b'On')),
    Setting('notes', b'Notes', (b'Flats', b'Sharps')),
)

# The tap in the footswitch case for function TAP/Tunr is a tail call; Press mode turns it into a tuner request.
TAP_SITE, TAP_CORE = 0x28dd1656, 0x28d9bfa8
GUARD, REQUEST_TUNER = 0x28d96134, 0x28d96588

# The tuner's settings (Output, Refrnc, Type, Trails, Offsets): knob turns are handled at TURN_FN, and a knob press resets the
# item to its default in one of three cases of the event handler. Lock Tuner Settings On skips both; page changes stay.
TURN_FN, TURN_FN_STOCK, TURN_FN_CONT = 0x28d916d4, bytes.fromhex('f8b5 4678'), 0x28d916d8      # push {r3-r7,lr}; ldrb r6,[r0,#1]
RESET_SITES = {0x28d917fa: 2, 0x28d9183e: 1, 0x28d91854: 0}                       # site: the knob it resets
RESET_STOCK, RESET_RET = bytes.fromhex('91f8 7430'), 0x28d9176e     # ldrb.w r3,[r1,#0x74]; pop {r3,r4,r5,pc}

# The view has four pages of three knobs, the page at [view+0x74]; these settings are a fifth, page 4. Paging and the page dots go
# by each page's place in the order instead, where page 4 is third (SHOWN_AT) and the string pages follow it.
PAGE, PAGES, SHOWN_AT = 4, 5, 2      # third, ahead of the per-string offsets, which few players use, so these are quick to reach
NEXT_PAGE, NEXT_PAGE_STOCK = 0x28d91784, bytes.fromhex('022b')                    # cmp r3,#2: the last page with a next one
PAGE_READ = bytes.fromhex('91f8 7430')                                            # ldrb.w r3,[r1,#0x74]
NEXT_READ, PREV_READ = 0x28d91780, 0x28d917c2                                     # the next- and previous-page cases' reads of it
PAGE_STORE, PAGE_STORE_STOCK = 0x28d917ca, bytes.fromhex('0125 2046')            # movs r5,#1; mov r0,r4: before both cases' store
DOTS_READ, DOTS_READ_STOCK = 0x28dccd52, bytes.fromhex('94f8 7400')              # ldrb.w r0,[r4,#0x74]: the page dots' current one
PAGE_CLAMPS, PAGE_CLAMP_STOCK = (0x28dcca6c, 0x28dccfd4), bytes.fromhex('032b')  # cmp r3,#3: the paint and redraw zero pages above
PAGE_DOTS, PAGE_DOTS_STOCK = 0x28dccd4c, bytes.fromhex('0420')                    # movs r0,#4: the page indicator's count
PAINT = 0x28dcca60                                                                # (view): takes the widget lock itself
PAINT_SWITCH, PAINT_SWITCH_STOCK = 0x28dcca8e, bytes.fromhex('032b 68d8')        # cmp r3,#3; bhi end: the paint's switch on the page
PAINT_TBH, PAINT_END = 0x28dcca92, 0x28dccb64
STEPS = 0x28dfe2d8                                  # (raw knob delta) -> detents, as the stock turn counts them
SHOW, VALUE_TEXT, POSITION, LABEL = 0x28dc6598, 0x28dc654c, 0x28dc648c, 0x28dc63d0   # (knob, shown / text / 0.0f..1.0f / text)
LABEL_COLOR = 'src/m4/label_color.s'               # its label_any colours the page's labels when label_color is built
KNOB_COLOURS = ((0x28dc6454, 0xffffff), (0x28dc651c, 0x6b6b6b), (0x28dc6534, 0x4d4d4d), (0x28dc6504, 0xb1b1b1),
                (0x28dc6568, 0xb1b1b1))           # (knob, colour), as the stock paints a knob that can be turned

# The note: on a new one, the tuner's update (0x28dcd7f8) keeps it at LAST_NOTE, reads its letter's image from a table of 12 words by
# the note mod 12 at NOTE_READ (r2 the table, r5 the note mod 12, r0 the letter's image widget), sets the letter widget's image, then
# shows the flat's image widget (ACCIDENTAL, Tuner_Flat) by a table of 12 bytes, FLATS: 1 on the five notes it names as the letter
# above with a flat. With Sharps, tuner_note reads the letter below on those five instead, and gives ACCIDENTAL the SHARP picture.
NOTE_READ, NOTE_READ_STOCK, NOTE_CONT = 0x28dcd82a, bytes.fromhex('52f8 2510'), 0x28dcd82e    # ldr.w r1,[r2,r5,lsl #2]
FLATS, ACCIDENTAL, LAST_NOTE = 0x28e3b478, 0x28d8d9b4, 0x2800226c
SET_IMAGE = 0x28e24c18                              # (image widget, Entry 7 index): its size from the image
TUNER_FLAT = 0x19f                                  # Tuner_Flat, 10 x 28: ACCIDENTAL's image as the tuner's constructor sets it
SHARP = (       # 10 x 28, grey 0..f, drawn for it: two upright strokes and two rising bars, as thick as Tuner_Flat's line
    '0000000000', '0000008100', '000000f300', '008100f300', '00f300f300', '00f300f300', '00f300f300', '00f300f300',
    '00f300f678', '00f67bfffc', '6bfffffb62', 'cffb63f300', '53f300f300', '00f300f300', '00f300f300', '00f300f300',
    '00f300f8ab', '00f8aefffc', '8efffef830', 'cef830f300', '20f300f300', '00f300f300', '00f300f300', '00f300f300',
    '00f3000000', '00f3000000', '0000000000', '0000000000',
)


def sharp_pixels():
    """SHARP as the image store keeps a picture: RGB565, column by column from the bottom."""
    w, h = len(SHARP[0]), len(SHARP)
    out = bytearray()
    for x in range(w):
        for y in reversed(range(h)):
            v = int(SHARP[y][x], 16) * 17
            out += image_store.pixel(v, v, v).to_bytes(2, 'little')
    return bytes(out)


def label_inc(label_any=None):
    return f'.equ LABEL_COLOUR_FN, {(label_any or KNOB_COLOURS[0][0]) | 1:#x}\n'


def sharp_inc(sharp):
    return f'.equ SHARP_IMAGE, {sharp:#x}\n'


def apply(p):
    e7 = p.entry(7)
    flat = image_store.image_at(e7.data, p.entry(8).data, TUNER_FLAT)
    if (flat.width, flat.height) != (len(SHARP[0]), len(SHARP)):
        raise SystemExit(f'patch-menu: tuner: image {TUNER_FLAT:#x} is {flat.width}x{flat.height}, not Tuner_Flat\'s 10x28')
    sharp = p.add_image(TUNER_FLAT, flat.width, flat.height, sharp_pixels())
    lc = p.modules.get(LABEL_COLOR)
    m = p.module('src/m4/tuner.s', inc={'tuner_label.inc': label_inc(lc and lc['label_any']), 'tuner_sharp.inc': sharp_inc(sharp)})
    p.own_call(TAP_SITE, TAP_CORE, 'the tap-tempo call', m['tuner_tap'])
    p.own_entry(TURN_FN, TURN_FN_STOCK, 'the tuner settings knob handler', m['tuner_turn_hook'])
    p.expect(RESET_RET, b'\x38\xbd', 'the tuner event handler epilogue')
    for site, knob in RESET_SITES.items():
        p.expect(site, RESET_STOCK, 'a tuner settings reset case')
        p.put(site, pm.thumb_bw(site, m[f'tuner_reset{knob}']), 'a tuner settings reset case')
    p.expect(PAINT_SWITCH, PAINT_SWITCH_STOCK, 'the tuner settings\' paint switch')
    p.put(PAINT_SWITCH, pm.thumb_bw(PAINT_SWITCH, m['tuner_switch']), 'the tuner settings\' paint switch')
    for site, stock, handler in ((NEXT_READ, PAGE_READ, 'tuner_next_page'), (PREV_READ, PAGE_READ, 'tuner_prev_page'),
                                 (PAGE_STORE, PAGE_STORE_STOCK, 'tuner_store_page'), (DOTS_READ, DOTS_READ_STOCK, 'tuner_dots')):
        p.expect(site, stock, 'the tuner settings\' page order')
        p.put(site, pm.thumb_bw(site, m[handler]), 'the tuner settings\' page order')
    p.expect(NEXT_PAGE, NEXT_PAGE_STOCK, 'the tuner settings\' next page')
    p.put(NEXT_PAGE, bytes([PAGE - 1, 0x2b]), 'the tuner settings\' next page')
    for site in PAGE_CLAMPS:
        p.expect(site, PAGE_CLAMP_STOCK, 'the tuner settings\' page clamp')
        p.put(site, bytes([PAGE, 0x2b]), 'the tuner settings\' page clamp')
    p.expect(PAGE_DOTS, PAGE_DOTS_STOCK, 'the tuner settings\' page count')
    p.put(PAGE_DOTS, bytes([PAGES, 0x20]), 'the tuner settings\' page count')
    p.expect(NOTE_READ, NOTE_READ_STOCK, 'the tuner\'s read of a note\'s letter')
    p.put(NOTE_READ, pm.thumb_bw(NOTE_READ, m['tuner_note']), 'the tuner\'s read of a note\'s letter')
