"""web/firmware-worker.js, the Stomp-only browser build alongside the Stomp and XL CLI:
it pins the same Stomp MD5s and loads every file the build reads; with HX_STOMP_HXF set, its
copy of the repository builds the features from a release's M4 code (tools/m4cache.py) as
the repository does with clang."""
import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

import block3
import m4asm
import m4cache

ROOT = Path(__file__).resolve().parent.parent
WORKER = (ROOT / "web/firmware-worker.js").read_text()


def js_object(name):
    body = re.search(name + r" = \{(.*?)\};", WORKER, re.S).group(1)
    return dict(re.findall(r'"(\w+)": "(\w+)"', body))


def py_dict(path, name):
    """A module-level value of literals, or of names of such values assigned before it."""
    tree = ast.parse((ROOT / path).read_text())
    env = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            try:
                env[n.targets[0].id] = eval(compile(ast.Expression(n.value), path, "eval"), {"__builtins__": {}}, dict(env))
            except Exception:
                continue
            if n.targets[0].id == name:
                return env[name]
    raise KeyError(name)


# The stock HX Stomp XL and HX Effects 3.80.0 files, which upstream builds and HXtra refuses
NOT_HX_STOMP = {"329e3a26d60d3de1988b6785fa833ee1": "HX_Stomp_XL", "7c2ebdf1bffb6bcc5f89dda97f91e40c": "HX_Effects"}


def test_stock_md5_as_build_py():
    stock = py_dict("build.py", "STOCK_MD5")
    assert js_object("STOCK_MD5") == {md5: unit for md5, unit in stock.items() if unit == "HX_Stomp"}


def test_hx_stomp_only():
    # No build for anyone without an HX Stomp
    assert py_dict("build.py", "STOCK_MD5") == {
        "a2cd8f4ae56f49415380270ebc484bf1": "HX_Stomp",
        "329e3a26d60d3de1988b6785fa833ee1": "HX_Stomp_XL",
    }
    assert set(py_dict("build.py", "KERNEL")) == set(py_dict("build.py", "STEPS")) == {"HX_Stomp", "HX_Stomp_XL"}
    assert not NOT_HX_STOMP.keys() & js_object("STOCK_MD5").keys()
    assert set(js_object("BUILT_MD5")) == set(js_value("KERNEL")) == set(js_value("STEPS")) == {"HX_Stomp"}
    assert "HX_Effects" not in WORKER and "HX_Stomp_XL" not in WORKER and "--effects" not in WORKER


def test_worker_refuses_another_file_as_the_page_expects():
    # the page shows fw.wrongText for an error with "not the stock" in it
    refusal = re.search(r'throw new Error\("(This is not the stock[^"]*)"', WORKER).group(1)
    assert "HX Stomp 3.80.0" in refusal and "HXtra is for the HX Stomp only" in WORKER
    assert "/not the stock/.test(m.text)" in (ROOT / "web/index.html").read_text()


@pytest.mark.parametrize("md5", ["7c2ebdf1bffb6bcc5f89dda97f91e40c", None], ids=["HX_Effects", "other"])
def test_build_py_refuses_another_unit(tmp_path, monkeypatch, md5):
    spec = importlib.util.spec_from_file_location("hxtra_build", ROOT / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    stock = tmp_path / "stock.hxf"
    stock.write_bytes(b"not firmware")
    if md5:
        monkeypatch.setattr(build.hashlib, "md5", lambda b: types.SimpleNamespace(hexdigest=lambda: md5))
    md5 = md5 or hashlib.md5(b"not firmware").hexdigest()
    monkeypatch.setattr(build, "run", lambda *a: pytest.fail(f"ran {a[1:]}"))
    monkeypatch.setattr(sys, "argv", ["build.py", str(stock), "-o", str(tmp_path / "out.hxf"), "--no-check"])
    with pytest.raises(SystemExit) as e:
        build.main()
    assert f"MD5 {md5}, not stock HX Stomp or HX Stomp XL 3.80.0 firmware" in str(e.value)
    assert not (tmp_path / "out.hxf").exists()


def test_build_py_accepts_xl(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("hxtra_build_xl", ROOT / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    stock = tmp_path / "stock-xl.hxf"
    stock.write_bytes(b"not firmware")
    monkeypatch.setattr(build.hashlib, "md5", lambda _data: types.SimpleNamespace(hexdigest=lambda: "329e3a26d60d3de1988b6785fa833ee1"))
    monkeypatch.setenv("HX_NAM_SLOTS", "0")
    monkeypatch.setattr(build.os, "replace", lambda *_args: None)
    monkeypatch.setattr(build.os, "remove", lambda *_args: None)
    calls = []
    monkeypatch.setattr(build, "run", lambda *args: calls.append(args[1:]) or "ALL OK")
    monkeypatch.setattr(sys, "argv", ["build.py", str(stock), "-o", str(tmp_path / "out.hxf"), "--no-check"])
    build.main()
    menu = next(args for args in calls if args[0] == "tools/patch_menu.py")
    assert menu[-2:] == ("--device", "HX_Stomp_XL")


def js_value(name):
    """A var whose value is a JSON string, list or object."""
    body = re.search(r"var " + name + r" = (.*?);\n", WORKER, re.S).group(1)
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", body))


def test_build_steps_as_build_py():
    for name in ("KERNEL", "STEPS"):
        assert js_value(name) == {"HX_Stomp": py_dict("build.py", name)["HX_Stomp"]}, name
    assert int(re.search(r"var E3_MAX = (\w+);", WORKER).group(1), 0) == py_dict("build.py", "E3_MAX")


def test_kernel_slots_as_build_py():
    # build.py's kernel(unit, slots): "--slots" for fewer than 3, nothing for 3
    assert 'KERNEL[unit].concat(slots === 3 ? [] : ["--slots", String(slots)]' in WORKER
    spec = importlib.util.spec_from_file_location("hxtra_build", ROOT / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    assert build.kernel("HX_Stomp", 3) == build.KERNEL["HX_Stomp"]
    assert build.kernel("HX_Stomp", 2) == build.KERNEL["HX_Stomp"] + ["--slots", "2"]


def test_built_md5_as_firmware_test():
    pinned = py_dict("tests/test_firmware.py", "BUILT_MD5")
    assert js_object("BUILT_MD5") == {"HX_Stomp": pinned["HX_STOMP_HXF"]}


def test_sources_cover_the_build():
    listed = set(listed_sources())
    assert all((ROOT / p).is_file() for p in listed)
    # every module the build's scripts import, and every file they open next to themselves
    need = {"tools/hxf.py", "tools/l6ia.py", "tools/l6ia_verify.py", "tools/patch_amp.py", "tools/kit_patch_amp.py",
            "tools/sharc/nam_lite.py",
            "tools/sharc/nam_multi.py", "tools/sharc/nam_multi_kernel.asm",
            *(f"tools/features/{f.name}" for f in (ROOT / "tools/features").glob("*.py")),
            "tools/patch_click.py", "build.py", "src/sharc/click.asm",      # the Metronome: patch_click.py reads both
            "tools/patch_gate.py", "src/sharc/fx_gate.asm",                 # the gate in the FX Loop and Return blocks
            "tools/patch_sidechain.py", "src/sharc/gate_sc.asm",            # the Noise Gate's Input Sidechain
            "tools/patch_comp.py", "src/sharc/frame_probe.asm"}             # the GR meter's knobs and DSP code
    for d in ("tools", "tools/sharc"):
        for f in listed:
            if not f.endswith(".py"):
                continue
            for mod in re.findall(r"^\s*import (\w+)", (ROOT / f).read_text(), re.M):
                if (ROOT / d / f"{mod}.py").is_file():
                    need.add(f"{d}/{mod}.py")
            for name in re.findall(r"""['"](\w+\.(?:json|asm))['"]""", (ROOT / f).read_text()):
                if (ROOT / d / name).is_file() and d == str(Path(f).parent):
                    need.add(f"{d}/{name}")
    assert need - {"tools/sharc/nam_a2.asm"} <= listed


def listed_sources():
    return re.findall(r'"((?:tools/|src/)?[\w/.]+\.\w+)"', WORKER.split("var SOURCES")[1].split("];")[0])


def test_sources_have_every_m4_source():
    # m4asm.key hashes every source next to a module, so the page needs all of them, as at the release
    m4 = {f"src/m4/{f.name}" for f in (ROOT / "src/m4").iterdir() if f.suffix in m4asm.SOURCE_TYPES}
    assert {p for p in listed_sources() if p.startswith("src/m4/")} == m4


def test_page_lists_the_web_options():
    # opt-in features: a checkbox each, hidden until the release's cache offers it, unticked
    page = (ROOT / "web/index.html").read_text()
    boxes = re.findall(r'<div class="feat" data-option="(\w+)" hidden><label><input type="checkbox"> ', page)
    assert sorted(boxes) == sorted(m4cache.web_options())


def page_dsp():
    """The DSP features' boxes ({flag: ticked}), the NAM slot counts (the one picked first) and whether NAM's box is ticked."""
    page = (ROOT / "web/index.html").read_text()
    boxes = dict(re.findall(r'<div class="feat" data-dsp="(\w+)" hidden><label><input type="checkbox"( checked)?> ', page))
    slots = re.findall(r'<input type="radio" name="slots" value="(\d)"( checked)?>', page)
    nam = re.search(r'<div class="feat" id="nam"><label><input type="checkbox" id="namOn"( checked)?> ', page)
    return {f: bool(c) for f, c in boxes.items()}, sorted(((bool(c), int(v)) for v, c in slots), reverse=True), bool(nam.group(1))


def test_page_lists_the_dsp_features_and_slot_counts():
    import block3
    # NAM's box unticked is 0 slots, the radios the rest
    boxes, slots, _ = page_dsp()
    assert sorted(boxes) == sorted(m4cache.web_dsp())
    assert sorted([v for _, v in slots] + [0]) == sorted(block3.SLOTS)


def test_page_default_is_two_nam_slots_and_every_dsp_feature_and_fits():
    # The default (issue #111): 2 NAM slots with the GR meter, the Metronome and the FX Loop gate
    import block3
    boxes, slots, nam = page_dsp()
    picked = slots[0][1]
    assert nam and slots[0][0] and not slots[1][0] and picked == 2
    assert all(boxes.values())
    assert block3.fits(picked, [f for f, on in boxes.items() if on])


def test_download_is_named_by_the_release():
    # the built file downloads as "HXtra_v1.2.0.hxf", the page names it the same before the build, and no copy names the old file
    page = (ROOT / "web/index.html").read_text()
    assert 'var name = "HXtra" + (cache && cache.release ? "_" + cache.release : "") + ".hxf";' in WORKER
    assert 'post({ type: "done", unit: unit, file: name,' in WORKER
    assert '$("fwName").textContent = "HXtra_" + release + ".hxf";' in page
    assert "_HXtra.hxf" not in page
    assert page.count("<code>HXtra</code>") == len(re.findall(r'"faq\.a5":', page))


def test_page_anchors_are_readable():
    # every section a link can land on is named in words, and each step's nav link points at one
    page = (ROOT / "web/index.html").read_text()
    sections = re.findall(r'<section class="step[^"]*" id="([^"]+)"', page)
    assert all(re.fullmatch(r"[a-z]+(-[a-z]+)*", s) for s in sections), sections
    assert set(re.findall(r'<a href="#([^"]+)" id="nav\d">', page)) <= set(sections)
    assert len(sections) == page.count("<section class=\"step")


def test_page_moves_old_anchors_to_their_names():
    # #s1..#s6 from links shared before the steps were named go to the step's section, as numbered then
    # (Select features, step 2 since #111, never had one)
    page = (ROOT / "web/index.html").read_text()
    old = dict(re.findall(r'(s\d): "([a-z-]+)"', re.search(r"var named = \{(.*?)\}", page).group(1)))
    nav = dict(re.findall(r'<a href="#([^"]+)" id="nav(\d)">', page))
    assert old == {"s1": "get-ready", "s2": "build", "s3": "try-without-installing", "s4": "install", "s5": "convert-captures",
                   "s6": "play-nam"}
    assert set(old.values()) <= set(nav) and nav["options"] == "2"


def test_site_root_keeps_the_anchor():
    # wisemandenny.github.io/hxtra/#install lands on the page's install step
    site = (ROOT / ".github/workflows/pages.yml").read_text()
    assert 'location.replace("web/" + location.hash)' in site


def page_combo(slots, leave_out=()):
    """The flags of the page's combination with every feature and DSP feature that fits but leave_out, at slots NAM slots."""
    dsp = [f for f in m4cache.web_dsp() if f not in leave_out]
    while not block3.fits(slots, dsp):
        dsp.pop(0)
    return m4cache.web_flags() + dsp + [m4cache.slots_flag(slots)]


# the default selection, then one of each kind the v1.2.0 cache lacked a module for (issue #163)
PAGE_COMBOS = {"default": (2, ()), "no GR": (2, ("HX_GR",)), "no Metronome": (2, ("HX_CLICK",)),
               "no USB Monitor": (2, ("HX_USB_MONITOR",)), "3 NAM slots": (3, ()), "no NAM, no DSP": (0, tuple(m4cache.web_dsp()))}


def test_page_combos_are_offered():
    offered = {m4cache.combo_key(c) for c in m4cache.combos()}
    assert all(m4cache.combo_key(page_combo(*c)) in offered for c in PAGE_COMBOS.values())


@pytest.mark.firmware
@pytest.mark.parametrize("combo", PAGE_COMBOS)
def test_page_copy_builds_features_from_the_cache(tmp_path, combo):
    stock = os.environ.get("HX_STOMP_HXF")
    if not stock:
        pytest.skip("HX_STOMP_HXF is not set")
    flags = page_combo(*PAGE_COMBOS[combo])
    nam = m4cache.flag_env(flags)[block3.VAR] != "0"
    cache = tmp_path / "m4cache.json"
    cache.write_text(json.dumps({"modules": m4cache.modules(stock, flags, nam)}))      # what m4cache.make keeps for it
    page = tmp_path / "repo"
    for p in listed_sources():
        (page / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / p, page / p)
    env = {k: v for k, v in os.environ.items() if not k.startswith("HX_")}
    env.update(m4cache.flag_env(flags))
    base = m4cache.nam_base(stock, str(tmp_path)) if nam else stock     # what build.py, and the page, give patch_menu.py
    out = {}
    for name, root, extra in (("clang", ROOT, {}), ("cache", page, {"HX_M4_CACHE": str(cache)})):
        out[name] = tmp_path / f"{name}.l6ia"
        r = subprocess.run([sys.executable, str(root / "tools/patch_menu.py"), base, str(out[name])],
                           env={**env, **extra}, cwd=root, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
    assert out["cache"].read_bytes() == out["clang"].read_bytes()


def worker_driver(repo):
    """The worker's DRIVER as Python, with the page's /repo at `repo`."""
    lines = WORKER.split("var DRIVER = [")[1].split('].join("\\n");')[0]
    return "\n".join(ast.literal_eval("[" + lines + "]")).replace("/repo", str(repo))


@pytest.mark.parametrize("script", ["tools/patch_menu.py", "tools/patch_amp.py"])
def test_worker_runs_each_script_with_its_folder_on_sys_path(tmp_path, script):
    # A 0-slot build runs patch_menu.py first, before patch_amp.py had put tools/ on sys.path: "No module named 'features'"
    page = tmp_path / "repo"
    for p in listed_sources():
        (page / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / p, page / p)
    code = worker_driver(page) + f"\nprint(run([{script!r}, '--help']).splitlines()[0])"
    r = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.startswith("usage:")


def test_pages_publishes_every_source():
    # the page fetches each of SOURCES from the site, which has only what .github/workflows/pages.yml copies there
    site = ROOT / ".github/workflows/pages.yml"
    copied = [p for line in re.findall(r"^\s*cp -r (.*) _site/", site.read_text(), re.M) for p in line.split()]
    assert [p for p in listed_sources() if not any(p == c or p.startswith(c + "/") for c in copied)] == []
