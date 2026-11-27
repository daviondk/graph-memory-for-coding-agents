"""Capture the three genuine, offline SQL replay result cards for the working paper."""
from pathlib import Path
from playwright.sync_api import sync_playwright

here = Path(__file__).resolve().parent
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 1000}, device_scale_factor=2, offline=True)
    page = context.new_page()
    page.goto((here.parent / "seed_pair/demo.html").as_uri())
    page.locator("#cards .card").first.wait_for()
    assert page.locator("#caseInfo h2").inner_text() == "dask/dask"
    assert [page.locator("#cards .card").nth(j).locator(".hit").count() for j in range(3)] == [0, 2, 3]
    assert all(page.locator("#cards .card").nth(j).locator("li").count() == 8 for j in range(3))
    page.locator("#cards").screenshot(path=str(here / "dask-replay.png"))
    browser.close()
