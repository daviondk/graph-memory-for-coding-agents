"""Generate fixed repository snapshots, actual prior search traces and blinded trial inputs."""
import ast
import hashlib
import itertools
import json
from pathlib import Path
import random
import shlex
import shutil
import subprocess
import sys
import sysconfig

ROOT = Path(__file__).resolve().parent
SEED = 460731
CLIP = 4
PAIRS = [
    ("base64", "b32decode"), ("bisect", "bisect_left"), ("bz2", "compress"),
    ("colorsys", "hsv_to_rgb"), ("copyreg", "_reconstructor"), ("difflib", "ndiff"),
    ("filecmp", "cmp"), ("fnmatch", "fnmatchcase"), ("gettext", "dgettext"),
    ("heapq", "nlargest"), ("linecache", "getline"), ("shlex", "quote"),
]
MECHANISMS = ("working_directory", "file_glob", "hidden_directory", "output_clipping")
SHARDS = ("core", "adapters", "extensions", "compat")
IDS = ("A", "B", "C", "D")
COMMON = ["rg", "--color", "never", "--sort", "path", "--line-number"]
ARMS = ("summary", "raw", "structured")


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_rg(repo, cwd, argv):
    args = [shutil.which("rg") or "rg", *argv[1:]]
    result = subprocess.run(args, cwd=repo / cwd, capture_output=True, encoding="utf-8", check=False)
    if result.returncode not in (0, 1) or result.stderr:
        raise ValueError((argv, result.returncode, result.stderr))
    return result.returncode, result.stdout.splitlines()


def old_probe(repo, directory, symbol, mechanism, incomplete):
    # Complete scans cover the whole shard; an incomplete probe can miss a definition.
    scan_dir = directory + "/surface" if mechanism == "working_directory" else directory
    patharg = ("." if incomplete else "..") if mechanism == "working_directory" else "."
    visibility = ["--hidden", "--no-ignore"]
    glob = ["--glob", "*.py"]
    if mechanism == "hidden_directory" and incomplete:
        visibility.remove("--hidden")
    if mechanism == "file_glob" and incomplete:
        glob += ["--glob", "!**/generated/**"]
    argv = [*COMMON, *visibility, *glob, "--fixed-strings", "--", symbol, patharg]
    rc, lines = run_rg(repo, scan_dir, argv)
    event = dict(cwd=scan_dir, argv=argv, exit_code=rc, row_limit=CLIP,
                 rows_produced=len(lines), rows_shown=min(CLIP, len(lines)), stdout=lines[:CLIP])
    return event, lines


def transcript(events):
    blocks = []
    for e in events:
        blocks.append("\n".join([
            "cwd=" + e["cwd"], "$ " + shlex.join(e["argv"]),
            *e["stdout"],
            "[tool] exit_code={exit_code} row_limit={row_limit} rows_produced={rows_produced} rows_shown={rows_shown}".format(**e)
        ]))
    return "\n\n".join(blocks)


def parse_transcript(content):
    events = []
    for block in content.split("\n\n"):
        lines = block.splitlines()
        counters = dict(token.split("=", 1) for token in lines[-1].removeprefix("[tool] ").split())
        events.append(dict(cwd=lines[0].removeprefix("cwd="), argv=shlex.split(lines[1][2:]),
                           stdout=lines[2:-1], **{k: int(v) for k, v in counters.items()}))
    return events


def command_choices(options):
    return "\n".join(f"{key}  " + shlex.join(argv) for key, argv in options.items())


def question(case, note):
    return (
        f"You are resuming a maintenance investigation in a Python monorepo. Locate the top-level implementation "
        f"of the Python function {case['symbol']} for a code reviewer. A documentation mention or import is insufficient. "
        "Previous searches ran against exactly the same checkout. A repository search service charges one read per "
        "directory shard; you have one read left. Choose which command to execute. Each candidate returns all its matching "
        "definition lines. Earlier reads could have used other options or displayed fewer lines. You cannot inspect "
        "the checkout or run commands yourself. Use the handoff below.\n\nHandoff\n" + note +
        "\n\nCommands available from repository root\n" + command_choices(case["options"]) +
        '\n\nReturn only one JSON object such as {"choice":"A"}, using the letter of your chosen command.'
    )


def make_fixture(index, module, symbol, mechanism, target_dir, ambiguous, correct_position, rng):
    case_id = f"s{index + 1:02}"
    repo = ROOT / "fixtures" / case_id
    lib = Path(sysconfig.get_path("stdlib")) / (module + ".py")
    subdir = {"working_directory": "runtime", "file_glob": "generated",
              "hidden_directory": ".overlay", "output_clipping": "z_runtime"}[mechanism]
    src_rel = f"{target_dir}/{subdir}/{module}.py"
    dst = repo / src_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copyfile(lib, dst)
    declaration = next(n.lineno for n in ast.parse(dst.read_bytes()).body if isinstance(n, ast.FunctionDef) and n.name == symbol)
    open_shards = [target_dir]
    if ambiguous:
        open_shards.append(rng.choice([s for s in SHARDS if s != target_dir]))
    for shard in SHARDS:
        surface = repo / shard / "surface"
        surface.mkdir(parents=True, exist_ok=True)
        # Synthetic API manifests document the symbol but never define it.
        count = rng.randint(1, 3)
        if mechanism == "output_clipping" and shard in open_shards:
            count = 6
            if shard != target_dir:
                # Tie all clip telemetry in the two-shard uncertainty condition.
                count += sum(symbol in line for line in dst.read_text(encoding="utf-8").splitlines())
        refs = [f"public_entry_{n} = ({symbol!r}, 'api-v{n + 1}')" for n in range(count)]
        (surface / "api_manifest.py").write_text("\n".join(refs) + "\n", encoding="utf-8")
    old_order = list(SHARDS)
    rng.shuffle(old_order)
    events, full = [], []
    for shard in old_order:
        e, lines = old_probe(repo, shard, symbol, mechanism, shard in open_shards)
        assert all(f"def {symbol}(" not in row for row in e["stdout"])
        events.append(e)
        full.append(dict(event=e, complete_stdout=lines))
    presentation = [s for s in SHARDS if s != target_dir]
    rng.shuffle(presentation)
    presentation.insert(correct_position, target_dir)
    options = {key: [*COMMON, "--hidden", "--no-ignore", "--glob", "*.py", "--",
                     f"^def {symbol}\\(", shard] for key, shard in zip(IDS, presentation)}
    expected = f"{src_rel}:{declaration}:"
    oracle_passes = []
    for key, argv in options.items():
        rc, rows = run_rg(repo, ".", argv)
        if any(row.replace("\\", "/").removeprefix("./").startswith(expected) for row in rows):
            oracle_passes.append(key)
    assert len(oracle_passes) == 1
    case = dict(id=case_id, symbol=symbol, options=options, module=module, mechanism=mechanism,
                unresolved_shards=open_shards, ambiguous=ambiguous,
                target_path=src_rel, target_line=declaration, file_sha256=digest(dst), oracle_choice=oracle_passes[0])
    raw = transcript(events)
    structured = json.dumps(events, indent=1, ensure_ascii=False)
    assert parse_transcript(raw) == json.loads(structured) == events
    dump(ROOT / "traces" / (case_id + ".json"), full)
    return case, {"summary": f"Previous repository searches found references to {symbol}. No implementation line "
                  "was visible in their returned excerpts.", "raw": raw, "structured": structured}


def main():
    rng = random.Random(SEED)
    pairs = PAIRS.copy()
    rng.shuffle(pairs)
    # A Latin rectangle distributes target directory across mechanism and symbol;
    # every directory appears three times over the twelve tasks.
    configs = [(MECHANISMS[m], SHARDS[(m + r) % 4], r == 2) for r, m in itertools.product(range(3), range(4))]
    rng.shuffle(configs)
    positions = list(range(4)) * 3
    rng.shuffle(positions)
    cases, reqs, allocation = [], [], []
    for i, ((module, symbol), (mechanism, target_dir, ambiguous)) in enumerate(zip(pairs, configs)):
        case, notes = make_fixture(i, module, symbol, mechanism, target_dir, ambiguous, positions[i], rng)
        cases.append(case)
        for arm in ARMS:
            request_id = f"q{rng.getrandbits(64):016x}"
            prompt = question(case, notes[arm])
            reqs.append(dict(id=request_id, prompt=prompt))
            allocation.append(dict(id=request_id, case=case["id"], arm=arm, memory_chars=len(notes[arm]), prompt_chars=len(prompt)))
    rng.shuffle(reqs)
    dump(ROOT / "cases.json", cases)
    dump(ROOT / "allocation.json", allocation)
    (ROOT / "requests.jsonl").write_text("".join(json.dumps(req, ensure_ascii=False) + "\n" for req in reqs), encoding="utf-8")
    license_path = ROOT / "COPYING-CPython.txt"
    if not license_path.exists():
        shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", license_path)
    dump(ROOT / "provenance.json", dict(source="Unmodified installed CPython standard-library modules",
         version=sys.version, url="https://github.com/python/cpython/tree/v3.14.4/Lib",
         license="COPYING-CPython.txt", generated="Layout and each surface/api_manifest.py are synthetic.",
         ripgrep=subprocess.check_output(["rg", "--version"], encoding="utf-8").splitlines()[0],
         seed=SEED, parity_checked_cases=len(cases), source_count=len(pairs)))


if __name__ == "__main__":
    main()
