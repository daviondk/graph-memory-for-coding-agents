"""Stage verified CPU-only members of the Ollama ZIP and the original nomic model."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.request
import zipfile


TAG = "v0.40.5"
ZIP_NAME = "ollama-windows-amd64.zip"
ZIP_SHA = "5134ce7e3bc8e94d0494721c799ec293b429450d0c52461b0ee3647dd3bb4bb7"
ZIP_SIZE = 1471226485
REGISTRY = "https://registry.ollama.ai/v2/library/nomic-embed-text"
EXPECTED_MODEL = "970aa74c0a90ef7482477cf803618e776e173c007bf957f635f1015bfcfef0e6"


def download(url, dst, size, digest, piecesize=8 << 20):
    if not dst.exists():
        tmp = dst.with_suffix(".partial")
        if not tmp.exists() or tmp.stat().st_size != size:
            with tmp.open("wb") as handle:
                handle.truncate(size)
        signed_url = None
        if url.startswith("https://github.com/"):
            probe = urllib.request.Request(url + f"?single={int(time.time())}", headers={"Range": "bytes=0-0"})
            with urllib.request.urlopen(probe, timeout=40) as handle:
                assert handle.status == 206
                signed_url = handle.geturl()
        def piece(index):
            start = index * piecesize
            end = min(size, start + piecesize) - 1
            with tmp.open("rb") as old:
                old.seek(start)
                head = old.read(min(64, end - start + 1))
                old.seek(max(start, end - 63))
                tail = old.read(min(64, end - start + 1))
            if any(head) and any(tail):
                return
            for attempt in range(6):
                try:
                    piece_url = (signed_url + f"&xpos={start}") if signed_url else (url + f"?recall_range={index}&attempt={attempt}")
                    req = urllib.request.Request(piece_url,
                                                 headers={"Range": f"bytes={start}-{end}"})
                    with urllib.request.urlopen(req, timeout=70) as resp:
                        if resp.status == 206:
                            assert resp.headers["Content-Range"] == f"bytes {start}-{end}/{size}"
                        else:
                            assert resp.status == 200 and start == 0 and end == size - 1
                        chunk = resp.read()
                    assert len(chunk) == end - start + 1
                    with tmp.open("r+b") as out:
                        out.seek(start)
                        out.write(chunk)
                    return
                except Exception:
                    if attempt == 5:
                        raise
                    time.sleep(attempt + 1)
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(piece, range((size + piecesize - 1) // piecesize)))
        tmp.replace(dst)
    with dst.open("rb") as handle:
        assert dst.stat().st_size == size and hashlib.file_digest(handle, "sha256").hexdigest() == digest


def main():
    arg = argparse.ArgumentParser()
    arg.add_argument("destination", type=Path)
    root = arg.parse_args().destination.resolve()
    root.mkdir(parents=True, exist_ok=True)
    def runtime():
        binary = root / ZIP_NAME
        download(f"https://github.com/ollama/ollama/releases/download/{TAG}/{ZIP_NAME}", binary, ZIP_SIZE, ZIP_SHA)
        members = {}
        with zipfile.ZipFile(binary) as z:
            for m in z.infolist():
                if m.is_dir():
                    continue
                name = m.filename
                # Exclude all hardware-accelerator libraries from the installed runtime.
                if any(w in name.lower() for w in ["cuda", "vulkan", "rocm", "mlx", "cublas", "ggml-hip"]):
                    continue
                parts = Path(name).parts
                assert not Path(name).is_absolute() and ".." not in parts
                path = root / "bin" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with z.open(m) as read, path.open("wb") as write:
                    shutil.copyfileobj(read, write)
                with path.open("rb") as read:
                    members[name] = hashlib.file_digest(read, "sha256").hexdigest()
        return members
    def model():
        path = root / "models" / "manifests" / "registry.ollama.ai" / "library" / "nomic-embed-text" / "latest"
        raw = urllib.request.urlopen(REGISTRY + "/manifests/latest", timeout=30).read()
        manifest = json.loads(raw)
        assert manifest["layers"][0]["digest"] == "sha256:" + EXPECTED_MODEL
        for layer in [manifest["config"], *manifest["layers"]]:
            sha = layer["digest"]
            store = root / "models" / "blobs" / sha.replace(":", "-")
            store.parent.mkdir(parents=True, exist_ok=True)
            download(REGISTRY + "/blobs/" + sha, store, layer["size"], sha.split(":")[1])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return manifest
    with ThreadPoolExecutor(max_workers=2) as ex:
        r = ex.submit(runtime)
        m = ex.submit(model)
        result = {"ollama": TAG, "release_zip_sha256": ZIP_SHA, "cpu_members": r.result(), "manifest": m.result()}
    (root / "staging.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Verified CPU runtime {TAG}, model {EXPECTED_MODEL}, {len(result['cpu_members'])} runtime files.")


if __name__ == "__main__":
    main()
