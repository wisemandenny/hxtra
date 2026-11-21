# Phones block and HP Block

Send/Return > Phones > Phones sends its input to the headphones only, and Phones Monitor's third value, HP Block, makes the phones play the Phones blocks and nothing else (`HX_PHONES_BLOCK`, `tools/patch_phones.py`, `tools/features/phones_block.py`, `src/m4/phones_block.s`, `src/sharc/phones.asm`, `src/sharc/phones_send.asm`). How the outputs work: [sharc/usb-routing.md](../sharc/usb-routing.md). Status tags as in [conventions.md](../conventions.md).

## The DSP side [verified on unit, 2026-11]

- **The phones' gains** are the root graph's members 132 and 133: Level gains `0x80` working in place on the buffers the phones' writers `0x2aab` (members 134, 135) read. The Volume knob drives them.
- **Path blocks run after the writers**: the harness's members (144 on) come after 134/135 in the root graph. So a Phones block's send for this block reaches the bus only after the writers have run. If the writer cleared the bus, it threw the send away before the gain saw it: the unit gave silence with only the test tone [verified on unit: test builds 14 and 15]. Now the phones' gain takes its channel of the bus and clears it (`ENTRY_80`). The writer clears it only while nobody takes it (`ENTRY_2AAB`, mode off or the gain not yet learnt). The bus content is one block late, which costs 16 samples.
- **Which gain is the phones'**: `ENTRY_80` keeps the last two calls' (I0, I2). `ENTRY_2AAB` matches its input I1 to an I2 there and learns that I0 as its channel's gain (PH_GAIN). Moving an amp in and out of its path sent it to the phones exactly when it should [verified on unit: test build 16].
- **The mode** rides in USB Input Trim, as USB Monitor's does. The M4 sends trim + 1000 × (mode + 6), and the wrapped control function of `0x80` takes a pid 1 value above 5500 apart. That is above USB Monitor's codes (1000..4000), but both wrap the same function, so the features conflict (`CONFLICTS`).
- **The kernel** (`phones_send.asm`) adds in × Level into both channels of the bus and writes in × Dry Thru out; at −60 dB or below, each is 0.

## The setting [verified offline, unicorn: tests/test_phones_block.py]

- Phones Monitor is stock ID `0x9e` (phonesSelect): 1 Main L/R, 2 Send. The feature REPLACES it with a virtual setting (ID `0xe6`, container 112 bits 2..3) in its slot: Main L/R, Send, HP Block.
- `ph_sync` runs after the slot repaint `0x28dceb30` and the page repaint `0x28dce854`. A turn of the virtual setting writes the stock one as its knob would (`0x28e1f8f4`, source 1): Send for Send, Main L/R for Main L/R and for HP Block, so the phones carry Main if the DSP never hears of the mode. Otherwise, at the first paint or after a change from HX Edit, the stock setting decides: Send makes this Send, and Main L/R makes it Main L/R unless it is HP Block.
- **The mode's sends** use the context and app of the last destination send `0x28df5760`, kept by a handler before it and sent again by one after it. That covers the boot and each preset. A turn of the setting sends it too. The trim's handle is found only with that context and app. With the app instance from `0x28d92a98()` or from the settings sender, the lookup failed (−4) [verified on unit].

## History

The first unit builds (on HXtra v1.2.1) added HP Block to the stock Phones Monitor itself. They patched the virtual settings engine's limits jump, the I/O store record's max and the value-text table, and swapped HP Block (3) for Main L/R (1) around the app parameter send `0x28df35e8`. Upstream's REPLACES does the same with no fixed addresses into HXtra's own code, so this tree uses it. The DSP side is unchanged from test build 16.
