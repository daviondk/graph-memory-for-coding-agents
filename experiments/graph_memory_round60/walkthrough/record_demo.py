"""Record and verify the local last-copy demo with offline browser snapshots and English speech."""
import argparse
from contextlib import closing
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import expect, sync_playwright

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
PAGE = HERE.parent / "demo/index.html"
RECORDER = EXP / "graph_memory_round59/walkthrough/record_demo.py"
spec = spec_from_file_location("prior_recorder", RECORDER)
previous = module_from_spec(spec)
spec.loader.exec_module(previous)
media = previous.media
DEMO_SHA = "c4e60cb5ffdad9dfa04b462f4757970be314b28296e18422866855f8871ab254"


def capture(work):
    shots, actions, receipts, network, errors = {}, [], {}, [], []
    with sync_playwright() as pw, closing(pw.chromium.launch(channel="msedge", headless=True)) as browser:
        page = browser.new_page(viewport={"width": media.WIDTH, "height": media.HEIGHT},
                                device_scale_factor=1, reduced_motion="reduce", offline=True)
        page.add_init_script("(" + previous.POINTER + ")()")
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda req: network.append(req.url) if req.url.startswith(("http:", "https:")) else None)
        page.goto(PAGE.as_uri())
        def scene(key, steps, selector, expected, focus):
            control = page.locator(steps[0][0])
            control.scroll_into_view_if_needed()
            control.hover()
            before = key + "-before.png"
            page.screenshot(path=work/before)
            for handle, value in steps:
                control = page.locator(handle)
                control.hover()
                if value is None:
                    control.click()
                else:
                    control.select_option(value)
                actions.append((handle, value))
            expect(page.locator(selector)).to_contain_text(expected)
            end = page.locator(focus)
            end.evaluate("e => e.scrollIntoView({block:'center',behavior:'instant'})")
            end.hover()
            after = key + "-after.png"
            page.screenshot(path=work/after)
            shots[key] = [before, after]
            receipts[key] = page.locator(selector).inner_text()
        scene("first", [("#first", None)], "#history", "A copy remains available.", "#bodies")
        expect(page.locator("#copy-0-1")).to_contain_text("Resident")
        scene("last", [("#last", None)], "#union", "E = {13}", "#union")
        expect(page.locator("#status")).to_contain_text("1 missing body")
        scene("two", [("#two", None)], "#union", "E = {13, 45}", "#packets")
        expect(page.locator("#status")).to_contain_text("2 missing bodies")
        scene("answer", [("#ask", None)], "#access", "0 posting requests · 2 fresh bodies", "#queryPane")
        scores = page.locator("#answer tr").all_text_contents()
        assert scores == ["test_reader.py5", "store.py4", "test_cache.py4", "schema.py4"]
        scene("quiet", [("#rule", "quiet"), ("#two", None)], "#status", "Fallback · |R ∪ E| = 6 of 8.", "#status")
        expect(page.locator("#union")).to_contain_text("E = {}")
        scene("fallback", [("#ask", None)], "#access", "1 posting request · 2 fresh bodies", "#queryPane")
        assert scores == page.locator("#answer tr").all_text_contents()
        scene("small", [("#goData", None)], "#rows", "9,213", "#rows")
        assert page.locator("#cohort").input_value() == "new"
        assert page.locator("#density").input_value() == "B" and page.locator("#cap").input_value() == "1024"
        scene("large", [("#large", None)], "#rows", "4,322", "#rows")
        assert page.locator("#cap").input_value() == "4096"
        assert [page.locator("#rows tr").nth(i).locator("td").nth(1).inner_text() for i in (0,3)] == ["4,322"] * 2
        scene("limit", [("#goLimits", None), ("#span", "4")], "#short", "5,468", "#timeRows")
        expect(page.locator("#timeRows")).to_contain_text("71.06")
        expect(page.locator("#timeRows")).to_contain_text("41.53")
        assert not network and not errors
    return ({"rendered_frames": shots, "focus_bounds": {}},
            {"actions": [list(s) for s in actions], "receipts": receipts,
             "scores": scores, "external_requests": network, "errors": errors})


def input_hashes():
    paths = [PAGE, HERE/"scenes.json", RECORDER, previous.R58, EXP/"graph_memory_round55/demo_video/record.py",
             EXP/"graph_memory_round55/demo_video/capture.py", EXP/"graph_memory_round55/demo_video/speak.ps1"]
    return {p.relative_to(EXP).as_posix(): sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in paths}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    verify = parser.parse_args().verify
    assert sha256(PAGE.read_bytes()).hexdigest() == DEMO_SHA
    hashes = input_hashes()
    scenes = json.loads((HERE/"scenes.json").read_bytes())
    manifest = HERE/"verification.json"
    with TemporaryDirectory(dir=HERE, prefix="capture-") as td:
        work = Path(td)
        frames, evidence = capture(work)
        voice, lengths = media.voice(work, scenes)
        if verify:
            expected = json.loads(manifest.read_bytes())
            timeline = expected["scenes"]
            assert hashes == expected["inputs"] and evidence == expected["ui"] and voice == expected["voice"]
            assert lengths == [s["frames"] for s in timeline]
            for key, title, line in scenes:
                media.artwork(work, frames["rendered_frames"][key][-1], title, line, "final-"+key+".png")
        else:
            timeline = media.compose(work, HERE, frames, scenes, lengths)
        result = media.verify_media(work, HERE, timeline)
        duration = float(result["ffprobe"]["format"]["duration"])
        assert 60 <= duration <= 120 and len(result["verified_scenes"]) == len(scenes)
        if verify:
            for key in ("file_sha256", "captions_sha256"):
                assert result[key] == expected[key]
        else:
            result.update(inputs=hashes, ui=evidence, scenes=timeline, voice=voice)
            manifest.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(f"Verified {duration:.2f}s, {len(scenes)} scenes, {len(evidence['actions'])} actions.")


if __name__ == "__main__":
    main()
