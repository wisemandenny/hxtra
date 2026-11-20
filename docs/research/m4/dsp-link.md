# The M4 to DSP link [verified on unit]

The SPI frames between the SHARC and the M4, and how the DSP sends its own values in a frame's tail. Status tags as in [conventions.md](../conventions.md).

- Framed 1 KB (256-word) SPI/DMA frames. Word 0 is magic `0xFACEF00D`, word 255 is trailer `0xD00FECAF`, payload from word 2.
- The M4 receive callback is reached through a literal at `0x28da6134` (stock value `0x10001095`; `r1` = RX buffer). Hooking it by replacing the literal and tail-calling the stock address works.
- The M4 sees halfword-swapped words: `ror #16` to read them.
- Most frames are empty. Words ~70..254 are unused filler.
- **The DSP can send data to the M4 by writing into the frame tail.** A SHARC routine scanned DSP memory (internal `0x80000..0x100000`, DDR2 `0x200000..0x330000`, 256 words per call) for `0xFACEF00D` with `0xD00FECAF` at +255, wrote `0x600DF00D` at word 200, a tag at 201 and a call counter at 202, and all three arrived at the M4. Word 203 onward is free. This is the transport for DSP-measured values (for example gain reduction), and it needs no knowledge of Line 6's own message formats.
- **What the DSP writes into the tail stays there** [verified offline: disassembly]. The link's DMA handler (`0x175ffa..0x176016`) has the send callback `0x173d12` refill one of two fixed buffers, `R8 = DM(0xc4cc5) + k * DM(0xc4cc7)` with k = 0 or 1. Into that buffer the callback writes word 0 (`0x173e75`), word 1 (`0x173e7b`) and the trailer at length - 1 (`0x173e8c`). Through `I5`, when set, it writes a magic, a header and a trailer again (`0x173e80`, `0x173e82`, `0x173e93`): `I5` is `DM(2, DM(9, I2))` (`0x173dc5`), or on the path that skips that load `I3 + M5` (`0x173d9b`; `I3` holds the buffer), the buffer itself if `M5` is 0. The queued messages go from word 2 (`0x1745b2`) of the same choice: their pointer is set at `0x173db8` or `0x173dc7`, beside `I5`. Nothing writes between the last message and the trailer. Once the code writing the tail stops running, the M4 keeps receiving its last words: a marker alone does not say the writer still runs (the GR meter, issue #176). Not traced: what `DM(2, DM(9, I2))` points to [hypothesis: a second copy of the frame], and the inside of `0x1745b2`.
- Searching Line 6's existing message traffic for a meter value ("needle in a haystack") was tried and abandoned.

Frame words the GR meter uses (200..253): [features/gr-meter.md](../features/gr-meter.md).
