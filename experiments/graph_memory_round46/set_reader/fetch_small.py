"""Fetch the checked CRC-free GGUF reranker conversion once to D, without staging a second file."""
import hashlib
from pathlib import Path
import shutil
import time
import requests

CACHE = Path("D:/CodexResearch/x20-r46-small-reranker")
NAME = "Qwen3-Reranker-0.6B-Q4_K_M.gguf"
REPO = "gorse-io/Qwen3-Reranker-0.6B-GGUF"
REV = "7af0c7c371b5ad3daf771ce4f6d091a4d38c799a"
SIZE = 396476320
DIGEST = "5290f5b9a2636be40baf807feafcfb222e0c4670a083fb3447d87993566190a9"


def main():
    CACHE.mkdir(exist_ok=True)
    final = CACHE / NAME
    partial = CACHE / (NAME + ".part")
    if final.exists():
        with final.open("rb") as file:
            assert hashlib.file_digest(file, "sha256").hexdigest() == DIGEST
        return
    cursor = partial.stat().st_size if partial.exists() else 0
    assert shutil.disk_usage(CACHE).free - (SIZE - cursor) >= 4 * (2**30)
    session = requests.Session()
    url = f"https://huggingface.co/{REPO}/resolve/{REV}/{NAME}"
    with partial.open("ab") as out:
        while cursor < SIZE:
            end = min(cursor + 16*2**20, SIZE) - 1
            for attempt in range(4):
                try:
                    # Separate links by requested byte interval to avoid stale ranged CDN responses.
                    with session.get(url, params={"download":"true","offset":cursor},
                                     headers={"Range":f"bytes={cursor}-{end}"}, stream=True, timeout=60) as response:
                        response.raise_for_status()
                        assert response.headers.get("Content-Range") == f"bytes {cursor}-{end}/{SIZE}"
                        for block in response.iter_content(2**20):
                            out.write(block)
                            cursor += len(block)
                    assert cursor == end + 1
                    out.flush()
                    if (cursor // (16*2**20)) % 8 == 0 or cursor == SIZE:
                        print("download",cursor,"/",SIZE,flush=True)
                    break
                except (requests.RequestException, AssertionError):
                    if attempt == 3:
                        raise
                    time.sleep(attempt + 1)
    with partial.open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").hexdigest() == DIGEST
    partial.rename(final)
    print("validated",DIGEST,flush=True)


if __name__ == "__main__":
    main()
