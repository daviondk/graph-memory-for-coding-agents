"""Replay one query using retained Git events and check it against the sealed R56 predictions."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
sys.path.insert(0, str(ROUND / "shared_evidence"))
from retain import Retained

CASES = {
    "gain": "ce8c37876bfe5920d38223d9cbad652d85085006",
    "loss": "1e5933dfc65d48594d7e1f95b29bb19418b56f2e",
}


def read(name):
    with gzip.open(ROUND / name, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def locate(cases, prefix):
    matches = [(repo, row) for repo, rs in cases.items() for row in rs if row["sha"].startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"SHA должен соответствовать одному запросу панели. Число совпадений {len(matches)}.")
    return matches[0]


def projected_ranking(mem, anchor, counts, names, events):
    votes = mem.score(events)
    candidates = (file_id for file_id in range(len(names)) if file_id != anchor)
    ordering = sorted(candidates, key=lambda i: (-votes[i], -counts[i], i))
    return {
        "decoded_events": len(events),
        "decoded_members": sum(len(mem.events[t]) for t in events),
        "top8": [{"path": names[i], "votes": votes[i], "recent": counts[i]} for i in ordering[:8]],
    }


def build(repo, row, stream):
    mem = Retained(8, "last", repo)
    ids = {}
    freq = Counter()
    timeline = []
    # Rank strictly from commits that precede the target.
    for t, (commit, raw) in enumerate(stream[:row["t"]]):
        paths = raw if len(raw) <= 64 else []
        codes = [ids.setdefault(path, len(ids)) for path in paths]
        if t >= 32:
            freq.subtract(timeline[t - 32])
        freq.update(codes)
        timeline.append(codes)
        mem.ingest(codes, paths, commit, t)
    sha, changed_paths = stream[row["t"]]
    assert sha == row["sha"] and len(changed_paths) == row["m"] and int(sha, 16) % 11 == 0
    known = changed_paths[(int(sha, 16) // 11) % len(changed_paths)]
    anchor = ids.get(known, -1)
    assert anchor == row["a"]
    names = list(ids)
    own = [t for _, t in mem.owned.get(anchor, [])]
    shared = sorted(mem.incident.get(anchor, ()))
    policies = {mode: projected_ranking(mem, anchor, freq, names, ts) for mode, ts in (("own", own), ("shared", shared))}
    # Compare the already ranked outputs with held-out paths.
    heldout = set(changed_paths) - {known}
    for mode, policy in policies.items():
        hits = [r["path"] for r in policy["top8"] if r["path"] in heldout]
        source = row["methods"]["last_" + mode]
        assert (len(hits), policy["decoded_events"], policy["decoded_members"]) == (source[0], source[3], source[4])
        policy["hits"] = hits
    added = []
    for t in sorted(set(shared) - set(own)):
        members = sorted(names[i] for i in mem.events[t])
        owners = sorted(names[i] for i in mem.events[t] if any(key == t for _, key in mem.owned[i]))
        assert owners and known not in owners and known in members
        added.append({"commit": stream[t][0], "owners": owners, "members": members,
                      "heldout_overlap": sorted(heldout.intersection(members))})
    return {"repo": repo, "commit": sha, "observed_file": known, "targets": sorted(heldout),
            "strategies": policies, "shared_only_events": added}


def display(result):
    print(result["repo"], result["commit"])
    print("Раскрытый файл", result["observed_file"])
    print("Фактические сопутствующие изменения", ", ".join(result["targets"]))
    for mode, label in (("own", "Собственные события"), ("shared", "Все сохранившиеся события файла")):
        p = result["strategies"][mode]
        print(f"\n{label}. Прочитано событий {p['decoded_events']}, записей участников {p['decoded_members']}.")
        for i, r in enumerate(p["top8"], 1):
            print(f"  {i:>2}  {r['votes']:>3}  {r['path']}" + ("  [попадание]" if r["path"] in p["hits"] else ""))
    extra = result["shared_only_events"]
    supporting = [e for e in extra if e["heldout_overlap"]]
    print(f"\nДругие файлы удержали ещё {len(extra)} событий. Из них {len(supporting)} содержат искомые пути.")
    for e in supporting:
        print(" ", e["commit"][:12], " · ", e["owners"][0], "(один из владельцев)")


def main():
    parser = argparse.ArgumentParser(description="Повторное использование событий Git на длинной панели R56.")
    parser.add_argument("case", nargs="?", default="gain", help="gain, loss или уникальный префикс SHA из длинной панели")
    parser.add_argument("--json", action="store_true", help="Включить все дополнительные события и владельцев")
    parser.add_argument("--all", action="store_true", help="Сверить все запросы длинной панели с журналом")
    args = parser.parse_args()
    streams = read("event_intersection/long-events.json.gz")
    reference = read("shared_evidence/long8-queries.json.gz")
    if args.all:
        count = 0
        for repo, rows in reference.items():
            for row in rows:
                build(repo, row, streams[repo])
                count += 1
        print(f"Проверены {count} запросов и {count * 2} ранжирования.")
        return
    try:
        repo, row = locate(reference, CASES.get(args.case, args.case.lower()))
    except ValueError as error:
        parser.error(str(error))
    result = build(repo, row, streams[repo])
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        display(result)


if __name__ == "__main__":
    main()
