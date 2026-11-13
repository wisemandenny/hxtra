"""Metronome: how the Metronome block (tools/patch_click.py, HX_CLICK=1) looks and assigns. In the signal flow it takes the teal pictures of
Volume/Pan, lit when on, dim when off (src/m4/metronome.s), and its block category is Metronome, with Icon_Tempo. Bypass Assign,
controller assignment and the footswitches treat it as a plain effect, not as the looper its browser category makes it."""
import struct

import image_store
import patch_menu as pm

FLAG = 'HX_CLICK'

# Looper's slot category (0x12) draws the looper's grey pictures with the looper's on/off, so the Metronome gets Volume/Pan's
SLOT_CATEGORY, SLOT_CATEGORY_STOCK = 0x28dd3042, bytes.fromhex('9df8 1020')    # ldrb.w r2, [sp, #0x10]

# A model without Entry 3 meta 'category' is block category 0x19, Unknown, otherwise only app, harness and mic models
CATEGORIES, METRONOME = 0x28e2815c, 0x19    # 0x2c-byte records {name[0x11], short[0xb], colour, dim colour, icon, icon off}
UNKNOWN_STOCK = bytes.fromhex('556e6b6f776e0000000000000000000000556e6b6f776e00000000008080800080808000de000000de000000')
NAME = b'Metronome'                 # tools/patch_click.py DISPLAY
COLOURS = (0x3cceb5, 0x21665d)      # Volume, Send, Return and FX Loop's
ICON_OFF_DIMMED = 0.39              # Icon_Tempo has no off picture: dimmed as the strip icons are

# Its browser category is Looper's (0x12), and these loads feed the firmware's looper tests: hide Bypass Assign's MIDI In, keep its
# footswitch knob on None, refuse a MIDI CC bypass, run a looper on a footswitch press, drop its assignments on a block change.
# (site, its stock ldrb.w reg, [sp, #off], the module's stand-in, what the site is)
LOOPER_TESTS = (
    (0x28dbb352, '9df84830', 'metronome_cat_r3_48', 'Bypass Assign redraw: the footswitch knob scale'),
    (0x28dbb644, '9df84830', 'metronome_cat_r3_48', 'Bypass Assign redraw: MIDI In shown'),
    (0x28dbbc64, '9df82030', 'metronome_cat_r3_20', 'Bypass Assign knob refresh: MIDI In shown'),
    (0x28dbc186, '9df82030', 'metronome_cat_r3_20', 'Bypass Assign turn: a footswitch down'),
    (0x28dbc200, '9df82030', 'metronome_cat_r3_20', 'Bypass Assign turn: a footswitch up'),
    (0x28dbc250, '9df82030', 'metronome_cat_r3_20', 'Bypass Assign turn: past the last footswitch'),
    (0x28dd11aa, '9df82830', 'metronome_cat_r3_28', "a footswitch press: its blocks' toggle"),
    (0x28ddf44c, '9df83830', 'metronome_cat_r3_38', 'controller assign: a MIDI CC allowed'),
    (0x28de02fc, '9df83420', 'metronome_cat_r2_34', "a block change: a looper's bypass assignments dropped"),
)


def apply(p):
    m = p.module('src/m4/metronome.s')
    p.expect(SLOT_CATEGORY, SLOT_CATEGORY_STOCK, "the signal flow's slot category load")
    p.put(SLOT_CATEGORY, pm.bl(SLOT_CATEGORY, m['metronome_slot']), "the signal flow's slot category load")
    for site, stock, stub, what in LOOPER_TESTS:
        p.expect(site, bytes.fromhex(stock), what)
        p.put(site, pm.bl(site, m[stub]), what)

    e7, e8 = p.entry(7), p.entry(8)
    icon = pm.ICONS['Icon_Tempo']
    im = image_store.image_at(e7.data, e8.data, icon)
    off = p.add_image(icon, im.width, im.height, image_store.scaled(e8.read(im.offset, im.length), ICON_OFF_DIMMED))
    rec = CATEGORIES + 0x2c * METRONOME
    p.expect(rec, UNKNOWN_STOCK, 'the Unknown block category')
    p.put(rec, NAME.ljust(0x11, b'\0') + NAME.ljust(0xb, b'\0') + struct.pack('<4I', *COLOURS, icon, off),
          'the Unknown block category, as Metronome')
