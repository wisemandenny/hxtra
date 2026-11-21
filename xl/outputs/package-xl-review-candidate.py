"""Package the verified XL 3.80 review candidate without accessing hardware."""
import argparse
from hashlib import md5, sha256
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import zlib

TOOLS = Path(__file__).resolve().parent.parent / "work" / "hxtra" / "tools"
sys.path.insert(0, str(TOOLS))
import hxf
import l6ia

STOCK_SHA256 = "ce1439e17ebe86a2f6a72dace5091ded45c27aa2e5b05ada4c5d639b6852c2d6"
CANDIDATE_SHA256 = "5bb4fe550170f11d6ae399dc67003381fb97b0a6569890e3f921b25bb0e11f06"


def archive_end(archive):
    last = l6ia.parse(archive)[-1]
    return last["payload_off"] + last["payload_len"]


def decode_package(package):
    chunks = hxf._chunks(package)
    if [chunk[0] for chunk in chunks] != [b"HEAD", b"dinf", b"dinf", b"data"]:
        raise SystemExit("Unexpected HXF chunk layout")
    head, primary, trailer, payload = (chunk[3] for chunk in chunks)
    archive = zlib.decompress(payload)
    end = archive_end(archive)
    size, digest = struct.unpack(">I16s", head[16:36])
    if size != len(archive) or digest != md5(archive).digest():
        raise SystemExit("Invalid HXF payload size or MD5")
    if struct.unpack(">H", head[10:12])[0] != 0x000b:
        raise SystemExit("HXF model is not HX Stomp XL")
    if struct.unpack(">IIII", primary) != (0, 0x10000, 0, end):
        raise SystemExit("Invalid primary HXF data region")
    if struct.unpack(">IIII", trailer) != (5, 0x10000, end, len(archive) - end):
        raise SystemExit("Invalid HXF trailer region")
    return head, archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    stock = args.stock.read_bytes()
    candidate = args.archive.read_bytes()
    if sha256(stock).hexdigest() != STOCK_SHA256:
        raise SystemExit("Expected the verified stock Line 6 HX Stomp XL 3.80.0 donor")
    if sha256(candidate).hexdigest() != CANDIDATE_SHA256:
        raise SystemExit("Expected the reviewed XL candidate archive")
    subprocess.run([sys.executable, str(TOOLS / "l6ia_verify.py"), str(args.archive)], check=True)

    stock_head, stock_archive = decode_package(stock)
    if candidate[archive_end(candidate):] != stock_archive[archive_end(stock_archive):]:
        raise SystemExit("Candidate updater trailer differs from stock")
    dsp_entry = l6ia.parse(candidate)[2]
    if dsp_entry["payload_len"] > 0x80000:
        raise SystemExit("Entry 2 exceeds its 512 KiB slot")

    with TemporaryDirectory() as directory:
        staging = Path(directory) / "candidate.hxf"
        hxf.pack(args.archive, staging, args.stock)
        package = staging.read_bytes()
        head, unpacked = decode_package(package)
        if head[:16] != stock_head[:16] or unpacked != candidate:
            raise SystemExit("HXF failed model/version or payload round-trip verification")
        with args.output.open("xb") as output:
            output.write(package)

    print(f"Candidate Entry 2: {dsp_entry['payload_len']} / {0x80000} bytes")
    print(f"HXF SHA-256: {sha256(package).hexdigest()}")


if __name__ == "__main__":
    main()
