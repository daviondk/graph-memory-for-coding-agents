"""Capture the actual default checkpoint selection and its measured traffic."""
from pathlib import Path
from playwright.sync_api import sync_playwright

here=Path(__file__).resolve().parent
with sync_playwright() as p:
    browser=p.chromium.launch(channel="chrome",headless=True)
    page=browser.new_page(viewport={"width":1190,"height":900},device_scale_factor=2,offline=True)
    page.goto((here.parent/"demo/index.html").as_uri())
    assert page.locator("#total").inner_text().replace(",","").replace(" ","")=="82907B"
    assert page.locator("#nreads").inner_text()=="196"
    # Crop the visible original controls and observed metrics without restyling.
    a=page.locator("#restart > .box").first.bounding_box()
    b=page.locator("#restart > .stats").bounding_box()
    assert a and b
    page.screenshot(path=str(here/"restart-screen.png"),clip={"x":a["x"],"y":a["y"],
        "width":a["width"],"height":b["y"]+b["height"]-a["y"]})
    browser.close()
