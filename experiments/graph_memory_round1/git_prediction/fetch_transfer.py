import concurrent.futures
import json
import subprocess
from pathlib import Path

from run import HERE, git

REPOS = ["psf/requests", "urllib3/urllib3", "pypa/packaging", "pypa/build",
         "pytest-dev/pluggy", "tox-dev/tox", "sphinx-doc/sphinx", "django/asgiref",
         "encode/httpx", "psf/black"]


def fetch(repo):
    name = repo.replace("/", "__")
    directory = HERE / "transfer_mirrors" / name
    url = f"https://github.com/{repo}.git"
    errors = []
    for attempt in range(2):
        ret = subprocess.run(["git", "clone", "--bare", "--single-branch", "--depth=240",
                              "--no-tags", "--filter=blob:none", url, str(directory)],
                             capture_output=True, timeout=180)
        if ret.returncode == 0:
            return {"repo": name, "remote": url, "sha": git(directory, "rev-parse", "HEAD").decode().strip(),
                    "n_first_parent": int(git(directory, "rev-list", "--count", "--first-parent", "HEAD")),
                    "shallow": git(directory, "rev-parse", "--is-shallow-repository").decode().strip()}
        errors.append(ret.stderr.decode(errors="replace"))
    return {"repo": name, "errors": errors}


if __name__ == "__main__":
    (HERE / "transfer_mirrors").mkdir(exist_ok=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        records = list(ex.map(fetch, REPOS))
    (HERE / "transfer_pins.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(json.dumps(records, indent=2))
