"""tools/m4asm.py's precomputed modules (HX_M4_CACHE) and tools/m4cache.py, which makes them at a release for the web page."""
import json
import os

import pytest

import m4asm
import m4cache


def sources(d, **files):
    d.mkdir()
    for name, text in files.items():
        (d / name).write_text(text)
    return d


def test_key_is_the_sources_not_their_paths(tmp_path):
    a = sources(tmp_path / "a", **{"x.s": "nop\n", "y.inc": ".equ Y, 1\n"})
    b = sources(tmp_path / "b", **{"x.s": "nop\n", "y.inc": ".equ Y, 1\n"})
    assert m4asm.key(a / "x.s", (a,)) == m4asm.key(b / "x.s", (b,))


def test_key_follows_every_neighbour(tmp_path):
    a = sources(tmp_path / "a", **{"x.s": "nop\n", "y.inc": ".equ Y, 1\n", "notes.txt": "1"})
    k = m4asm.key(a / "x.s", (a,))
    (a / "notes.txt").write_text("2")                  # not a source
    assert m4asm.key(a / "x.s", (a,)) == k
    (a / "y.inc").write_text(".equ Y, 2\n")
    assert m4asm.key(a / "x.s", (a,)) != k


def test_cached_module(tmp_path, monkeypatch):
    a = sources(tmp_path / "a", **{"x.s": "nop\n"})
    cache = tmp_path / "m4cache.json"
    cache.write_text(json.dumps({"modules": {m4asm.key(a / "x.s", (a,)): {"code": "00bf", "symbols": {"go": 0}}}}))
    monkeypatch.setenv(m4asm.CACHE, str(cache))
    monkeypatch.setattr(m4asm, "CLANG", "/nonexistent/clang")
    assert m4asm.assemble_module(str(a / "x.s"), (a,)) == (b"\x00\xbf", {"go": 0})
    (a / "x.s").write_text("bx lr\n")
    with pytest.raises(SystemExit, match="no code for x.s"):
        m4asm.assemble_module(str(a / "x.s"), (a,))


def test_web_flags_are_every_feature():
    assert set(m4cache.web_flags()) == {"HX_TUNER", "HX_BPM", "HX_DSP_METER", "HX_BREATHING_LINE", "HX_LONG_PRESS",
                                        "HX_MORE_SNAPSHOTS", "HX_TAP_COLOR", "HX_PRESET_COLOR", "HX_CC_TAP", "HX_LABEL_COLOR",
                                        "HX_EXP_DISPLAY"}


def test_web_options_are_the_opt_in_features():
    assert m4cache.web_options() == ["HX_REAL_NAMES"]


def test_web_dsp_are_the_features_sharing_block_3():
    assert m4cache.web_dsp() == ["HX_GR", "HX_FX_GATE", "HX_GATE_SC", "HX_CLICK", "HX_USB_MONITOR"]


def test_make_pins_every_combination_that_fits(monkeypatch):
    import block3
    monkeypatch.delenv(m4asm.CACHE, raising=False)
    monkeypatch.setattr(m4cache, "web_flags", lambda: ["HX_B", "HX_A"])
    monkeypatch.setattr(m4cache, "web_options", lambda: ["HX_X"])
    monkeypatch.setattr(m4cache, "web_dsp", lambda: ["HX_D", "HX_E"])
    monkeypatch.setattr(block3, "SLOTS", (2, 0))
    monkeypatch.setattr(block3, "cost", {"HX_D": 30, "HX_E": 40}.get)
    monkeypatch.setattr(block3, "words", {2: 50, 0: 100}.get)
    built = {}

    def built_md5(stock, flags, cache=None):
        built[m4cache.combo_key(flags)] = json.load(open(cache))["modules"]
        return m4cache.combo_key(flags)

    def modules(stock, flags, nam=True, out=None):
        out[m4cache.combo_key(flags)] = nam
        return out
    monkeypatch.setattr(m4cache, "built_md5", built_md5)
    monkeypatch.setattr(m4cache, "modules", modules)
    cache = m4cache.make("stock.hxf", "v1")
    assert cache["features"] == ["HX_B", "HX_A"] and cache["options"] == ["HX_X"]
    assert cache["dsp"] == {"features": ["HX_D", "HX_E"], "slots": [2, 0], "room": {"2": 50, "0": 100},
                            "cost": {"HX_D": 30, "HX_E": 40}}
    want = sorted(m4cache.combo_key(["HX_A", "HX_B", f"HX_NAM_SLOTS={s}"] + d + o) for s in (2, 0)
                  for d in ([], ["HX_D"], ["HX_E"], ["HX_D", "HX_E"]) if not (s == 2 and len(d) == 2) for o in ([], ["HX_X"]))
    assert sorted(cache["md5"]["HX_Stomp"]) == want
    # every combination's modules, NAM A2 Lite's image but with 0 slots, and each build reads them all, as the page does
    assert cache["modules"] == {k: "HX_NAM_SLOTS=0" not in k for k in want}
    assert built == {k: cache["modules"] for k in want}


def test_modules_assembles_a_module_once(monkeypatch):
    seen = []

    def assemble(src, include=()):
        seen.append(src)
        return b"\x00\xbf", {"go": 0}

    def menu_entries(load, env):
        assert os.environ["HX_GR"] == "1" and os.environ["HX_NAM_SLOTS"] == "2" and "HX_OLD" not in os.environ
        assert env == {"HX_GR": "1", "HX_NAM_SLOTS": "2"}
        for src in ("a.s", "b.s", "a.s"):
            assert m4asm.assemble_module(src) == (b"\x00\xbf", {"go": 0})
    monkeypatch.setenv("HX_OLD", "1")
    monkeypatch.setattr(m4asm, "assemble_module", assemble)
    monkeypatch.setattr(m4asm, "key", lambda src, include=(): src)
    monkeypatch.setattr(m4cache, "image", lambda stock, nam: b"")
    monkeypatch.setattr(m4cache.pm, "menu_entries", menu_entries)
    out = m4cache.modules("stock.hxf", ["HX_GR", "HX_NAM_SLOTS=2"], out={"b.s": {"code": "00bf", "symbols": {"go": 0}}})
    assert seen == ["a.s"] and sorted(out) == ["a.s", "b.s"]
    assert m4asm.assemble_module is assemble and os.environ["HX_OLD"] == "1" and "HX_GR" not in os.environ


@pytest.mark.parametrize("cache", [None, "m4cache.json"])
def test_built_md5_sets_valued_flags(monkeypatch, tmp_path, cache):
    seen = {}

    def run(argv, env, **kw):
        seen.update(env)
        (tmp_path / "out.hxf").write_bytes(b"x")
        return type("R", (), {"returncode": 0, "stdout": "ALL OK", "stderr": ""})()
    monkeypatch.setenv(m4asm.CACHE, "stale.json")
    monkeypatch.setattr(m4cache.subprocess, "run", run)
    monkeypatch.setattr(m4cache.tempfile, "TemporaryDirectory", lambda: _Dir(tmp_path))
    m4cache.built_md5("stock.hxf", ["HX_GR", "HX_NAM_SLOTS=0"], cache)
    assert seen["HX_GR"] == "1" and seen["HX_NAM_SLOTS"] == "0"
    assert seen.get(m4asm.CACHE) == (cache and os.path.abspath(cache))


def test_built_md5_stops_at_a_failed_build(monkeypatch, tmp_path):
    # a page combination whose module isn't in the cache stops the release here, with m4asm's reason
    def run(argv, env, **kw):
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "m4asm: x has no code for bpm.s"})()
    monkeypatch.setattr(m4cache.subprocess, "run", run)
    monkeypatch.setattr(m4cache.tempfile, "TemporaryDirectory", lambda: _Dir(tmp_path))
    with pytest.raises(SystemExit, match="HX_GR failed:\n.*no code for bpm.s"):
        m4cache.built_md5("stock.hxf", ["HX_GR"], "m4cache.json")


class _Dir:
    def __init__(self, path):
        self.path = str(path)

    def __enter__(self):
        return self.path

    def __exit__(self, *a):
        return False


def test_make_refuses_a_cache_build(monkeypatch):
    monkeypatch.setenv(m4asm.CACHE, "m4cache.json")
    with pytest.raises(SystemExit, match="unset HX_M4_CACHE"):
        m4cache.make("stock.hxf")


def test_release_repo():
    import release
    assert release.repo("https://github.com/wisemandenny/hxtra.git") == "wisemandenny/hxtra"
    assert release.repo("git@github.com:wisemandenny/hxtra.git") == "wisemandenny/hxtra"
    with pytest.raises(SystemExit):
        release.repo("https://example.com/hxtra.git")


@pytest.mark.parametrize("tag, text, ok", [("v1.0.0", "v1.0.0", True), ("v1.0.1", "v1.0.0", False),
                                           ("v1.0.0", "HXtra", True), ("1.0.0", "HXtra", False),
                                           ("v1.1.0-rc.1", "HXtra", True)])
def test_release_version(tag, text, ok):
    import release
    if ok:
        release.check_version(tag, text)
    else:
        with pytest.raises(SystemExit):
            release.check_version(tag, text)
