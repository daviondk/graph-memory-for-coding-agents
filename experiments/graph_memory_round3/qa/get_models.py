"""Verify or retrieve the exact, versioned ONNX weights in the experimental manifest."""
import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

here = Path(__file__).resolve().parent
manifest = json.loads((here / "models.json").read_text(encoding="utf8"))
pins = {
    "encoder": "751bff37182d3f1213fa05d7196b954e230abad9",
    "reader": "bdbb0a5e9c617c3c7ea9f3cbaf2be3ad871bcd7d",
}


def verify_or_fetch(model):
    name, revision = model["key"], model["commit"]
    assert revision == pins[name]
    folder = here / "models" / name
    folder.mkdir(parents=True, exist_ok=True)
    for spec in model["artifacts"]:
        path = folder / spec["file"]
        url = spec["url"]
        assert url.startswith(f"https://huggingface.co/{model['repo']}/resolve/{revision}/")
        if path.is_file():
            data = path.read_bytes()
        else:
            with urllib.request.urlopen(url, timeout=90) as response:
                data = response.read()
        if len(data) != spec["bytes"] or hashlib.sha256(data).hexdigest() != spec["sha256"]:
            raise ValueError(f"{path.name}: file does not match frozen SHA-256 and size")
        if not path.is_file():
            temporary = path.with_suffix(".partial")
            temporary.write_bytes(data)
            temporary.replace(path)
        print(name, path.name, len(data), revision, flush=True)


if __name__ == "__main__":
    with ThreadPoolExecutor(2) as executor:
        list(executor.map(verify_or_fetch, manifest))
