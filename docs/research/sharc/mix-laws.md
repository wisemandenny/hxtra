# Mix and Blend laws in stock blocks

How stock models turn a Mix or Blend knob into the two gains of their mixer. Source: `tools/sharc/pmap.py` on stock 3.80.0 (the six distortions with a Blend or Mix knob, and `--category modulation`, 29 models), 2026-11-19. All [verified offline]; nothing here was measured on the unit.

## Mechanism [verified offline]

- The mixer is `0x89` or `0x84`, two inputs into one buffer, pid 1 and pid 2 the gains of its two inputs in dB (−120 dB = off). Bronze Master mixes with `0x222` (two inputs, pids 1 and 2 from Blend; **[hypothesis]** dB like the other two, from its tables and init 0 / −3.2).
- Each gain comes from the knob through its own op `0x3` curve: 9 values at knob 0, 1/8, .., 1, linear in dB between them ([model-blobs.md](model-blobs.md)). So a law is two 9-point dB tables. Between 0 and 1/8 the gain runs from −120 dB to the second value linearly in dB: on the Line 6 law the wet part is −80 dB at 5 % and −41 dB at 10 %.
- Below, "dry" is the input that is at 0 dB with the knob at 0.

## The Line 6 law [verified offline]

Dry 0, 0, 0, 0, −3, −6, −12, −21, −120 dB; wet the mirror image. The dry part stays full up to 3/8, both are −3 dB at 1/2, the wet part is full from 5/8.

- Used by Chorus, Script Mod Phase, Courtesan Flange, Gray Flanger, Harmonic Flanger, Deluxe Phaser, Harmonic Tremolo, PlastiChorus, Dynamix Flanger (on `0x84`) and the Megaphone (distortion).
- Variants: Bitcrusher −27/−15 dB instead of −21/−12 at 1/8 and 2/8; 70s Chorus and Bubble Vibrato end the wet part at −2 dB; FlexoVibe −60 dB ends and −40/−20 on the falling side; 4-Voice Chorus, U-Vibe, Pitch Vibrato, AM Ring Mod, Warble-Matic, Random S/H and Ampeg Liquifier have their own tables; Poly Detune writes only the wet gain.
- Sum (computed from the tables, 1/64 steps): for two equal, fully correlated signals 0 to +3.5 dB (peak at 3/8 and 5/8), for equal uncorrelated ones 0 to +1.0 dB.
- The Megaphone also lowers its Level with Mix and Focus (op `0x6`, a 3 × 3 table, then a curve to 0 .. −9.42 dB). **[hypothesis]** a loudness compensation; op `0x6` is not traced.

## Pedal models [verified offline]

| Model | Knob | Effect at 5 / 10 / 25 / 50 / 75 % (dB) | Dry at 25 / 50 / 75 % (dB) | Ends | Sum correlated / uncorrelated |
|---|---|---|---|---|---|
| Ampeg Scrambler | Blend | −46.1 / −32.2 / −15.6 / −8.1 / −3.9 | −2.8 / −7.5 / −14.6 | dry +0.66 at 0, wet −1.14 at 1; −60 off | −1.9..+0.5 / −4.9..+0.5 |
| ZeroAmp Bass DI | Blend | −59.8 / −39.5 / −22.6 / −7.5 / −1.1 | −1.4 / −8.6 / −24.2 | −80 / −75 off | −2.1..0 / −5.1..0 |
| Obsidian 7000 | Blend | −81.6 / −43.1 / −13.6 / −6.6 / −2.6 | −2.2 / −6.2 / −13.0 | −120 off | −1.6..−0.1 / −3.4..−0.1 |
| Bronze Master | Blend | −11.6 / −11.1 / −9.8 / −7.5 / −5.2 | −0.8 / −4.5 / −8.2 | dry +3 → −12, wet −12 → −3: never one alone | −0.6..+4.2 / −3.5..+2.9 |

- The first three come close to an amplitude-linear crossfade (correlated sum within 2 dB of flat), as a passive blend pot would; they look like curves fitted to the pedals. Their dry inputs are not the plain block input: the Scrambler's passes the shared input stage (`0x102`, `0x832`), the ZeroAmp's three `0x102` filters.
- Bronze Master's Blend is linear in dB on both sides and only shifts the balance.
- For comparison, an amplitude-linear law (1 − m, m) through the same 9-point dB curve: correlated −0.8..0, uncorrelated −3.0..−0.1 dB. A truly linear law needs the gain computed in amplitude and then converted (op `0x28`, linear → dB, [model-blobs.md](model-blobs.md#map-ops-verified-offline-unless-tagged)), not a 9-point table. Stock does this: Smart Harmony's Mix sets its `0x89` with wet = `0x28`(min((2m)³, 1)) and dry = `0x28`(min((2(1 − m))³, 1)), so −18.06 dB on the fading side at m = 0.25 and both at 0 dB at m = 0.5; the Volume Pedal's Position goes through `0x28` to its `0x80` (−12.04 dB at 0.25) [verified offline, `tools/sharc/pmap.py --sweep`]. Op `0x28` feeds 129 writers in 33 stock models (filter, modulation, synth, reverb, pitch, volume, delay), none of them a distortion.

## Modulation models without a Mix knob

60s Bias Trem, Optical Trem, Tremolo, Double Take, Bleat Chop Trem, Pebble Phaser, Retro Reel.
