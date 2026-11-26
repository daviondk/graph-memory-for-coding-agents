"""Build the R54 offline artifact by extending the verified R53 archive."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

D = Path(__file__).resolve().parent
PREVIOUS = D.parents[1] / "graph_memory_round53/submission/candidate.zip"
PIN = "b37e68ae564c51513f0523015752f3ed271ae008a7647602a1bcd247a0caabaa"
DOCS = ("paper.tex", "paper.pdf", "sources.bib", "README.md", "DATA_SOURCES.md",
        "demo.py", "start.html", "verify_candidate.py", "session-read.png", "withdrawal.png", "capture.py", "replay_topk.py")
SESSION = ("serve.py", "index.html", "trace.sqlite", "audit.sqlite", "test_console.py", "README.md")
EVIDENCE = {
    "multi_read": ("results.json", "verification.json", "core.py"),
    "cutoff": ("results.json", "correctness.json", "cutoff_store.py"),
    "reserve": ("results.json", "classic-results.json", "partial-results.json", "reserve_store.py", "partial.py", "classic.py"),
    "git_history": ("results.json", "extension-results.json"),
    "code_links": ("results.json",),
    "next_read": ("results.json", "explicit-results.json", "fusion-results.json"),
    "execution": ("results.json", "cap-results.json"),
}


def digest(data):
    return sha256(data).hexdigest()


def inventory(files):
    return (json.dumps({name: digest(data) for name, data in files.items()}, sort_keys=True, indent=2) + "\n").encode()


def predecessor():
    assert digest(PREVIOUS.read_bytes()) == PIN
    with ZipFile(PREVIOUS) as archive:
        names = archive.namelist()
        assert len(set(names)) == len(names)
        files = {name: archive.read(name) for name in names}
    expected = json.loads(files.pop("CONTENT_SHA256.json"))
    assert expected == {name: digest(data) for name, data in files.items()}
    return files


def extension():
    files = {"apps/session/" + name: (D.parent / "trace_demo" / name).read_bytes() for name in SESSION}
    files["tox-replay.html"] = (D.parent / "case_replay/index.html").read_bytes()
    files["evidence/workload.json.gz"] = (D.parents[1] / "graph_memory_round53/churn/workload.json.gz").read_bytes()
    for study, names in EVIDENCE.items():
        for name in names:
            files["evidence/" + study + "/" + name] = (D.parent / study / name).read_bytes()
    return files


def compile_paper(files):
    with TemporaryDirectory(dir=D) as temp:
        dst = Path(temp)
        (dst / "edit.png").write_bytes(files["edit.png"])
        for name in ("paper.tex", "sources.bib", "session-read.png", "withdrawal.png"):
            shutil.copyfile(D / name, dst / name)
        subprocess.run(["tectonic", "paper.tex"], cwd=dst, check=True)
        shutil.copyfile(dst / "paper.pdf", D / "paper.pdf")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-paper", action="store_true")
    args = parser.parse_args()
    files = predecessor()
    if args.build_paper:
        compile_paper(files)
    files.update({name: (D / name).read_bytes() for name in DOCS})
    files.update(extension())
    files["app-inputs.json"] = inventory({name: data for name, data in files.items() if name.startswith("apps/")})
    files["CONTENT_SHA256.json"] = inventory(files)
    with ZipFile(D / "candidate.zip", "w") as archive:
        for name, data in sorted(files.items()):
            member = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            member.compress_type = ZIP_DEFLATED
            member.external_attr = 0o100644 << 16
            archive.writestr(member, data)
    print(len(files), "members", digest((D / "candidate.zip").read_bytes()))


if __name__ == "__main__":
    main()
