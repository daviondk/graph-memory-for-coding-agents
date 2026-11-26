"""Capture two actual console states for the paper. Optional build tool using Playwright."""
import argparse
import json
from contextlib import ExitStack
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
from demo import child

D = Path(__file__).resolve().parent
Q = "e6b3d0834b130dd9a2b7015d"


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    extracted = (D / "apps/session").is_dir()
    session = D / "apps/session/serve.py" if extracted else D.parent / "trace_demo/serve.py"
    churn = D / "apps/churn/demo/server.py" if extracted else D.parents[1] / "graph_memory_round53/churn/demo/server.py"
    cli.add_argument("--session", type=Path, default=session)
    cli.add_argument("--churn", type=Path, default=churn)
    cli.add_argument("--output", type=Path, default=D / "captures", help="Directory for the two rendered figures")
    args = cli.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with ExitStack() as resources:
        session = resources.enter_context(child(args.session))
        churn = resources.enter_context(child(args.churn))
        p = resources.enter_context(sync_playwright())
        b = p.chromium.launch(headless=True)
        resources.callback(b.close)
        page = b.new_page(viewport={"width": 780, "height": 950}, device_scale_factor=1.4)
        page.goto(session)
        page.select_option("#case", Q)
        page.select_option("#method", "memory_rrf")
        page.select_option("#version", "1")
        with urlopen(session + "/api/state?q=" + Q + "&method=memory_rrf&version=1") as res:
            expected = json.load(res)["selected"]["path"]
        page.wait_for_function("s => document.querySelector('#selected').textContent === s", arg=expected)
        page.click("#evaluate")
        page.wait_for_selector("#audit:visible")
        panel = page.locator(".grid article").first
        panel.screenshot(path=str(args.output / "session-read.png"), animations="disabled")
        page.goto(churn)
        page.locator("#version").fill("17")
        page.locator("#version").dispatch_event("input")
        page.wait_for_function("document.querySelector('#raw').textContent.includes('3') && document.querySelector('#vv').textContent.trim() === '17'")
        upper = page.locator(".twocol").bounding_box()
        lower = page.locator("#events").bounding_box()
        clip = {"x": upper["x"], "y": upper["y"], "width": upper["width"],
                "height": lower["y"] + lower["height"] - upper["y"] + 5}
        page.screenshot(path=str(args.output / "withdrawal.png"), clip=clip, animations="disabled")
        print("Captured one ranked-file receipt and the two q11 SQL plans' winners.")


if __name__ == "__main__":
    main()
