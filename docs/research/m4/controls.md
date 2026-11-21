# Front-panel controls and shortcuts

What each control of the HX Stomp does in the stock 3.80 UI, every button combination the HX Stomp 3.80 Owner's Manual (English) gives, and how to send each from a computer with [USB input](../features/usb-input.md) (`tools/hx_input.py`, a build with `HX_USB_INPUT=1`). Status tags as in [conventions.md](../conventions.md): a shortcut taken from the manual and not yet sent over USB is **[hypothesis]**; one the devtest or a session has driven over USB is **[verified on unit]**.

## The controls

| control (manual) | `hx_input` name | key code (class 1) | turn (class 2) |
|---|---|---|---|
| FS1, FS2, FS3 (TAP/TUNER by default) | `fs1`..`fs3` | 12..14; touch 9..11 | |
| FS4, FS5 (the EXP 1/2, FS 4/5 jack, tip and ring) | `fs4`, `fs5` | 15, 16 | |
| Knobs 1..3, under the screen | `knob1`..`knob3` | 0..2 | 0..2 |
| **Upper Knob** (block select, preset select) | `knob4` | 3 | 3 |
| **Lower Knob** (model) | `knob5` | 4 | 4 |
| VIEW (the house icon, "home") | `view` | 5 | |
| ACTION | `action` | 6 | |
| PAGE◀, PAGE▶ | `page_left`, `page_right` | 7, 8 | |
| VOLUME | not sendable: class 4, and it sets only the headphone level ([usb-input.md](../features/usb-input.md)) | | |

The Upper and Lower Knob roles are [verified on unit] (`knob4` steps the Edit view's block and Global Settings' sections, `knob5`'s press opens the model browser). The manual's "Menu" icon (☰) means PAGE◀ and PAGE▶ pressed together.

## Sending a combination

The firmware's own code that recognises two keys down together has not been looked for; the known-good way is to put the presses in the key queue back to back, as a hand would. Every event goes through the key queue (`0x28db88fc`) and the UI event post (`0x28db8830`), so a sent event reaches the UI exactly as a real one ([m4/footswitches.md](footswitches.md#functions-and-events)).

`tools/hx_input.py` takes controls joined by `+` as pressed together: `press`, `hold` and `touch` send every press in one request, then every release in one request.

```sh
python3 tools/hx_input.py press view+action         # the Save Preset screen
python3 tools/hx_input.py press page_left+page_right # the Menu
python3 tools/hx_input.py hold fs1+fs2              # both held, both holds after 1 s, both released
```

From a script: `Input(ctl).press('view+action')`, or `u.press('view+action')` in `tools/hx_devtest.py`.

- **Together** (VIEW + ACTION, PAGE◀ + PAGE▶, Upper + Lower Knob, FS1 + FS2): `press('a+b')`. `Unit.both_pages` sends the Menu this way [verified on unit, every devtest run since 2026-11-13].
- **Twice** (quick save): the same chord again after the screen has changed (the devtest's `settle`, 0.3..0.6 s). The queue drops a key event equal to one still in it, so the two chords need at least `GAP_S` between them.
- **Hold one, click another** (hold ACTION, press a knob): `hx_input.key` builds single events; send ACTION's press, wait `CLICK_S`, `Input.press('knob1')`, then ACTION's release and type 3. [hypothesis] that the order matters; send them in that order.
- **Hold** (a knob, a footswitch, two footswitches): the firmware makes the hold (type 5) from its own timer of a key held down, which a sent press does not start, so the host sends type 5 itself after `HOLD_S` (1 s), then the release with no type 3: `Input.hold`. `hold('fs1+fs2')` holds two together. [hypothesis] for two keys.
- **Press and turn** (a knob): the knob's press, then `Input.turn` on the same knob, then its release and type 3. [hypothesis]
- **Touch** (FS1..FS3's caps): `Input.touch` for a brief touch. `touch('fs1+fs2')` touches two together. A **touch hold** is the touch code's press, `HOLD_S`, its type 5, then its release, as `t_global_eq` does [verified on unit, "Assign block to FS?" in the Edit view]. A foot pressing a footswitch also touches its cap: `foot_hold` in `tools/hx_devtest.py` sends both.

## Anywhere

| shortcut | what it does | status |
|---|---|---|
| VIEW | back to Home from the Menu, Global Settings and the tuner; on Home it toggles Play view and Edit view | [verified on unit] |
| VIEW | closes an action panel, cancels the model list | [hypothesis] |
| **VIEW + ACTION** together | opens the **Save Preset** screen (below) | by hand [verified on unit, 2026-11-16]; over USB [hypothesis] |
| **VIEW + ACTION** together, twice | **quick save**: the edits saved over the current preset, same name and place | [hypothesis] |
| **PAGE◀ + PAGE▶** together | opens the **Menu** (below) | [verified on unit] |
| **ACTION + PAGE▶** together | opens the tuner | [hypothesis] |
| **Upper + Lower Knob** (`knob4` + `knob5`) together | **All Bypass**: "Analog [or DSP] bypass! Press any switch."; any footswitch press ends it | [hypothesis] |
| ACTION | the action panel of the selected block or of the screen (below); held alone it does nothing useful, nor does VIEW held | by hand [verified on unit, 2026-11-16] |
| Knob 3 / Knob 1 in a dialog | OK / Cancel | [hypothesis] |

- **Saving writes the eMMC.** In a plain RAM run (`hxboot`, `writes: ram`) a save stays in SDRAM and is gone at power-off; in a `--writes pass` run it overwrites the real preset ([conventions.md](../conventions.md)). The devtest never saves: a test that saves runs in a plain RAM run, or saves to a spare preset place.
- **The Save Preset screen**: Upper Knob turn moves the cursor; Knob 2 turn changes the character, its press cycles upper case, lower case, 0, space; PAGE▶ then Knob 1 deletes a character, PAGE▶ then Knob 2 inserts a space; Lower Knob turn picks the preset place to write (any of 126); Knob 3 Save, Knob 1 Cancel. [hypothesis]
- **All Bypass in Analog mode** routes the inputs to the outputs through relays with no processing, so USB audio and DSP checks mean nothing until a footswitch ends it. Global Settings > Preferences > Bypass Type picks Analog (default) or DSP.
- **The Menu**: page 1 Bypass Assign (Knob 1), Controller Assign (Knob 2), Command Center (Knob 3); PAGE▶ to page 2: Global Settings (Knob 2) and Global EQ. [verified on unit]: the Bypass Assign tile, and page 2 with Global Settings under Knob 2 and Global EQ. The rest is the manual's [hypothesis]; it says Knob 3 for both Command Center and Global EQ, and the unit shows Global EQ on page 2, so Global EQ is likely page 2's Knob 3. The devtest finds a tile by its label and presses the knob under it (`knob_under`), which survives a different layout.

## Play view (Home), by footswitch mode

PAGE◀ and PAGE▶ on Home step the footswitch mode through Stomp, Scroll, Preset and Snapshot (setting 21); PAGE◀ from Stomp is Snapshot [verified on unit]. Upper Knob turn selects a preset; its press opens the **preset list** (Knob 1 turn reorders the preset, Knob 2 turn picks snapshot 1..3; ACTION on a snapshot, then Knob 2, renames it, PAGE▶ there sets its LED colour with Knob 3).

| mode | shortcut | what it does | status |
|---|---|---|---|
| Stomp | FS1, FS2 | toggle their blocks | [verified on unit] |
| Stomp | touch FS1 or FS2 again and again | steps through the blocks assigned to it | [hypothesis] |
| Stomp, Scroll | FS3 (TAP) pressed again and again | tap tempo (40 BPM at the lowest) | [verified on unit] |
| Stomp, Scroll | **hold FS3** (TAP) | the tuner; any footswitch press leaves it | [verified on unit] |
| Stomp, Scroll | touch FS3 (TAP) | the tempo panel for a moment (Knob 2 Tempo, Knob 3 BPM) | [hypothesis] |
| Stomp | **touch hold two footswitches** | "swap assignments" dialog; Knob 3 OK | [hypothesis] |
| Scroll | FS1, FS2 | previous, next preset | [hypothesis] |
| Scroll | **hold FS1 + FS2** | toggles FS1/FS2 between Preset Up/Down and Snapshot Up/Down | [hypothesis] |
| Preset | FS1..FS3 | load preset A, B, C of the bank | [hypothesis] |
| Preset, Snapshot | **FS1 + FS2** together | queues the previous bank (its presets flash); a footswitch then loads one | [hypothesis] |
| Preset, Snapshot | **FS2 + FS3** together | queues the next bank | [hypothesis] |
| Snapshot | FS1..FS3 | snapshot 1..3; with [More snapshots](../features/more-snapshots.md) the lit one again flips to 4..6 | [verified on unit] |
| Snapshot | **touch hold one, brief touch of another** | "copy snapshot" over the second; Knob 3 OK | [hypothesis] |
| Snapshot | **touch hold two footswitches** | "swap snapshots" dialog; Knob 3 OK | [hypothesis] |

- A footswitch's touch selects only when Global Settings > Footswitches > Stomp Select is Touch (the default) or Both.
- HXtra changes some holds: [Long press](../features/long-press.md) gives each footswitch a Hold function, and the [tuner page](../features/tuner-page.md)'s Tuner Activation decides how TAP opens the tuner. Check those settings before relying on a stock hold.

## Edit view

| shortcut | what it does | status |
|---|---|---|
| Upper Knob turn | selects a block (empty slots too) | [verified on unit] |
| Upper Knob press | bypasses or enables the selected block | [hypothesis] |
| Lower Knob turn | changes the selected block's model **at once**; on an empty slot it creates a block | [verified on unit] |
| Lower Knob press | opens the model list: Lower Knob turn moves, its press or PAGE▶ goes in, PAGE◀ back a level, VIEW cancels | [verified on unit] (in, the turn) |
| **Lower Knob press and turn** | skips through model subcategories without the list | [hypothesis] |
| Knob 1..3 turn | the parameter above it; PAGE◀/PAGE▶ for the block's other pages | [verified on unit] (in Global Settings and Bypass Assign) |
| Knob 1..3 press | resets the parameter to its default; on a time or speed parameter it toggles ms/Hz and note values; on a button-like label it presses the button | reset [verified on unit] |
| **hold Knob 1..3** | Controller Assign for that parameter | [hypothesis] |
| **Knob 1..3 press and turn** | assigns the parameter to the Snapshots controller (its value turns white) | [hypothesis] |
| **hold ACTION, press Knob 1..3** | removes that parameter's controller, Snapshots included | [hypothesis] |
| **touch hold FS1 or FS2** (FS3 when it is Stomp 3), Stomp mode | "Assign block to FS?" for the selected block: Knob 2 Merge/Replace, Knob 3 OK | [verified on unit] |

**ACTION on a block** (the block is picked up; ACTION again or VIEW drops it) [hypothesis]:
- Page 1: Upper Knob turn moves the block; Knob 1 Path (A or B), Knob 2 Copy Block, Knob 3 Paste Block (paste works in another preset too).
- PAGE▶: Knob 1 Clear Block, Knob 2 Clear All Blocks (then Knob 3 OK), Knob 3 Snapshot Bypass (On/Off).
- PAGE▶ again: Knob 1 Add to Favorites (then Lower Knob picks a place, Knob 2 Replace, Knob 3 Add New), Knob 2 Factory Default, Knob 3 User Default.
- On the Mixer (where the paths merge): Knob 1 Path B sends path B to its own output.

## Other screens' ACTION panels [hypothesis]

| screen | ACTION, then |
|---|---|
| Global Settings | Knob 1 Factory Settings, Knob 3 OK: **resets every Global Setting** (HXtra's feature settings likely with them). Never in a test. |
| Global EQ | Knob 1 Reset EQ, Knob 3 OK. On the screen itself, Upper Knob press turns Global EQ on/off, its turn picks the band, Knobs 1..3 set it. |
| Bypass Assign | on a block: Knob 1 Clear Assignments; Knob 2 Clear All Assignments, Knob 3 OK |
| Controller Assign | on a block: Knob 1 Clear Controller; Knob 2 Clear All Controllers (EXP 1 wah and EXP 2 volume too), Knob 3 OK. PAGE▶ then Knob 3 Learn. |
| Command Center | Knob 1 Copy Command, Knob 2 Copy All Commands, Knob 3 Paste; PAGE▶: Knob 1 Clear Command, Knob 2 Clear All Commands, Knob 3 OK |
| Favorites (in the model list) | Clear, Reorder (a turn) and Rename Favorite |

## Looper on a footswitch

The 1 Switch Looper's footswitch: press records, plays, then toggles play and overdub; hold 1 s while playing undoes [verified offline, footswitches.md], again redoes [hypothesis]. A quick double press stops when its second press comes within 20 ticks (200 ms) of the first press, while a press on a playing loop starts an overdub 21 ticks after its release, so a second press between the two overdubs instead of stopping (HXtra's Looper DblPress keeps the window open until the overdub); a hold while stopped erases only as the second press of a double press, so a press and hold on a stopped loop plays it for the second it is held, then erases it [verified offline, by disassembly; this note had "hold while stopped erases" and the window unknown]: [footswitches.md](footswitches.md#the-1-switch-loopers-footswitch-verified-offline). The Shuffling Looper: press records, plays, then reshuffles; double press stops; hold erases [hypothesis]. Over USB a double press is two `Input.press` calls (`CLICK_S` + `GAP_S` apart).

## Out of reach

- The VOLUME knob and the expression pedals: the host sends only keys and knob turns.
- Power-on combinations: the manual gives none, and the application, which reads the key queue, is not running yet.
