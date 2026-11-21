# Build HXtraXL 1.0 on Windows

Build from the original HX Stomp XL 3.80.0 file. Use Python with numpy and Pillow, Git, and LLVM clang. Run the commands from the HXtraXL repository root. Adjust the two local paths to match your computer.

```powershell
$stock = 'C:\path\to\HX_Stomp_XL_v3.80.0_0x103966115.hxf'
$env:HX_CLANG = 'C:\Program Files\LLVM\bin\clang.exe'
git clone https://github.com/wisemandenny/hxtra.git xl/work/hxtra
git -C xl/work/hxtra checkout --detach 2c1685fc339ec03fbedfab01e16e6c3326259a71
git -C xl/work/hxtra apply --check ../../hxtra-xl-tools.patch
git -C xl/work/hxtra apply ../../hxtra-xl-tools.patch
git clone https://github.com/nocaseguy/hx-stomp-nam-lite.git xl/work/nam
git -C xl/work/nam checkout --detach aa5f5a81f6353cf2b6c532109fd0e620b1b6191e
py -3 xl/work/rebuild-xl-nam-baseline.py $stock xl/work/nam-xl-two-slot.l6ia
py -3 xl/work/build-xl-offline.py --nam-slots 2 --settings-menu --tap-ring --tuner --bpm --breathing-line --dsp-meter --hold-tuner --metronome --gr-play --fx-gate --input-sidechain --usb-routing --preset-color --tap-command --label-color --output xl/work/1.0.l6ia
py -3 xl/outputs/package-xl-review-candidate.py $stock xl/work/1.0.l6ia xl/outputs/HXtraXL_1.0.hxf
```

Expected archive SHA-256: `5bb4fe550170f11d6ae399dc67003381fb97b0a6569890e3f921b25bb0e11f06`

Expected HXF SHA-256: `5b7352088607ed7a18ba38e9ac0e5f7ecd6e04105a675ac68dba3d24fd662dc2`

The XL build uses a pinned HXtra tools checkout with the XL compatibility patch applied. The shared tools in the main checkout remain at the upstream revision. The scripts write local build files. Keep firmware images, presets and personal captures out of commits.
