"""Rebuild the two-slot NAM baseline from the original XL 3.80.0 HXF."""
import argparse
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

NAM = Path(__file__).resolve().parent / "nam"
sys.path.insert(0, str(NAM))
import build

STOCK = "ce1439e17ebe86a2f6a72dace5091ded45c27aa2e5b05ada4c5d639b6852c2d6"
BASELINE = "ebf672a660be7a5195199cb19e6667213780acc8ce72768c70eec01f711c2503"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = args.stock.resolve()
    if sha256(source.read_bytes()).hexdigest() != STOCK:
        parser.error("Expected the stock HX Stomp XL 3.80.0 file.")

    def run(script, *arguments):
        subprocess.run([sys.executable, script, *map(str, arguments)], cwd=NAM, check=True)

    with TemporaryDirectory() as temp:
        scratch = Path(temp)
        asm = scratch / "nam.asm"
        run(*build.KERNEL["HX_Stomp_XL"], "--slots", 2, "-o", asm)
        for index, (operation, *options) in enumerate(build.STEPS["HX_Stomp_XL"]):
            target = scratch / f"stage-{index}.l6ia"
            run("tools/patch_amp.py", operation, source, target, *options)
            source = target
        image = scratch / "nam.l6ia"
        run("tools/patch_amp.py", "patch", source, image, "--asm", asm)
        contents = image.read_bytes()
    digest = sha256(contents).hexdigest()
    if digest != BASELINE:
        raise SystemExit(f"Rebuilt baseline differs from the tested baseline: {digest}")
    with args.output.open("xb") as out:
        out.write(contents)
    print(f"Reproduced the two-slot NAM baseline: {digest}")


if __name__ == "__main__":
    main()
