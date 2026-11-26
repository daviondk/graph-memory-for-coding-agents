"""Create sealed sequential forecasts from the address-only projection."""
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "code_visibility"
EXPECTED = "b4527e3337e2d567495d4836f440b56cb59605dec84dfff6cb0368c6924c7449"
CAP = 128
NAMES = ("F", "K", "T", "H", "Tstar", "C")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(path.read_bytes())


def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def save(filename, data):
    path = ROOT / filename
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(gzip.compress(raw, compresslevel=6, mtime=0) if path.suffix == ".gz" else raw)
    return sha(path)


def top(path, mapping, limit):
    ordered = sorted(mapping, key=lambda n: (digest(f"R37-128|{path}|{n}".encode()), n))
    return {n: mapping[n] for n in ordered[:limit]}


def parse(rows, origin):
    result = {n: (s, origin) for n, s in rows}
    assert len(rows) == len(result)
    return result


def advance(path, states, edit, sequence):
    observed = top(path, parse(edit["rows"], sequence), CAP)
    free = CAP - len(observed)

    def eligible(before, relocate):
        pool = {}
        for n, value in before.items():
            if relocate:
                k = edit["k"]
                if k is None or k <= n <= k + edit["old_breaks"]:
                    continue
                if n > k + edit["old_breaks"]:
                    n += edit["delta"]
            assert n > 0 and n not in pool
            if n not in observed:
                pool[n] = value
        return pool

    pools = {m: eligible(states[m], m in ("T", "Tstar", "C")) for m in NAMES if m != "F"}
    matched = min(free, len(pools["H"]), len(pools["Tstar"]))
    after = {"F": dict(observed)}
    for m, pool in pools.items():
        after[m] = top(path, pool, matched if m in ("Tstar", "H") else free) | observed
    assert len(after["H"]) == len(after["Tstar"])
    assert all(len(s) <= CAP and all(s[n] == v for n, v in observed.items()) for s in after.values())
    return after


def predict(path, first_read, edits):
    # Inputs are an actual prior view and visible confirmations through the current step.
    initial = top(path, parse(first_read, 0), CAP)
    state = {name: dict(initial) if name not in ("C", "F") else {} for name in NAMES}
    sizes = []
    for step, edit in enumerate(edits, start=1):
        state = advance(path, state, edit, step)
        sizes.append({name: len(view) for name, view in state.items()})
    return {m: [[n, *v] for n, v in sorted(view.items())] for m, view in state.items()}, sizes


def project(data):
    flow = defaultdict(Counter)
    forecasts, targets = {}, {}
    for rid, run in data.items():
        cohort = "main" if run["subset"] in ("predecessors", "main_takeovers") else "secondary"
        count = flow[cohort]
        count["runs"] += 1
        previous, barrier = {}, -1
        for at, kind, *fields in run["events"]:
            if kind == "barrier":
                barrier = at
                continue
            path = fields[0]
            snapshot = previous.get(path)
            if kind != "read":
                assert kind in ("write_start", "edit", "other")
                if snapshot is not None:
                    snapshot["events"].append((at, kind, fields[1:]))
                continue
            count["views"] += 1
            observed = fields[1]
            previous[path] = {"at": at, "rows": observed, "events": []}
            if snapshot is None:
                continue
            count["pairs"] += 1
            events = snapshot["events"]
            edits = [(i, a[0], a[1]) for i, k, a in events if k == "edit"]
            if len(edits) < 2:
                continue
            count["two_or_more_receipts"] += 1
            if any(k == "other" for _, k, _ in events):
                continue
            count["only_replacements"] += 1
            if not snapshot["rows"] or not observed:
                continue
            count["nonempty_views"] += 1
            starts = [i for i, k, _ in events if k == "write_start"]
            if not all(e["matched"] for _, e, _ in edits):
                continue
            count["all_matched"] += 1
            if starts != [e["action_index"] for _, e, _ in edits]:
                continue
            count["exact_write_starts"] += 1
            prev_at = snapshot["at"]
            if not all(left < e["action_index"] < idx < at
                       for left, (idx, e, _) in zip([prev_at] + [i for i, _, _ in edits], edits)):
                continue
            window = "strict" if barrier < prev_at else "opaque"
            count[window] += 1
            key = digest(f"{rid}|{prev_at}|{at}".encode())
            assert key not in forecasts
            visible = [{k: e[k] for k in ("rows", "k", "old_breaks", "delta")} for _, e, _ in edits]
            states, sizes = predict(path, snapshot["rows"], visible)
            forecasts[key] = dict(rid=rid, repo=run["repo"], issue=run["issue"], cohort=cohort,
                                  window=window, path_sha=digest(path.encode()), first=prev_at, last=at,
                                  operations=[i for i, _, _ in edits], shifts=[e["delta"] for _, e, _ in edits],
                                  anchors=[e["k"] is not None for _, e, _ in edits], sizes=sizes, states=states)
            targets[key] = {"rows": observed, "native_audits": [a for _, _, a in edits]}
    return forecasts, targets, flow


def main():
    source = SOURCE / "events.json.gz"
    assert sha(source) == EXPECTED == read(SOURCE / "source-seal.json")["projection"]
    forecasts, targets, flow = project(read(source))
    seal = dict(input=EXPECTED, protocol=sha(ROOT/"PROTOCOL_RU.md"), predictor=sha(Path(__file__)),
                forecasts=save("forecasts.json.gz", forecasts), targets=save("targets.json.gz", targets),
                flow=flow, cap=CAP)
    save("forecast-seal.json", seal)
    print(json.dumps(flow))


if __name__ == "__main__":
    main()
