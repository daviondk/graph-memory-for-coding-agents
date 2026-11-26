"""Check the live SQL query path for every withdrawal mask against the exported full order."""
from collections import Counter
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import sqlite3
from serve import query

HERE = Path(__file__).resolve().parent


def run():
    panel = json.loads((HERE / "cases.json").read_bytes())["questions"]
    cases_digest = sha256()
    counts = Counter()
    with sqlite3.connect((HERE / "evidence.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("pragma integrity_check").fetchone() == ("ok",)
        assert {r[0] for r in db.execute("select q from pairs")} == {c["q"] for c in panel}

    for c in panel:
        n = len(c["titles"])
        docs = range(n)
        full = {edge: frozenset(divmod(edge, 16)) for edge in c["full"]}
        assert len(full) == len(c["full"]) == n*(n-1)//2
        assert set(full.values()) == {frozenset(p) for p in combinations(docs, 2)}
        assert c["raw"] == c["full"][:6] and len(c["gold"]) == 2
        winners = set()
        for mask in range(1 << n):
            lost = frozenset(i for i in docs if mask & (1 << i))
            eligible = [e for e, members in full.items() if members.isdisjoint(lost)]
            expected = next(iter(eligible), None)
            s = query(c["q"], sorted(lost))
            assert s["winner"] == expected and s["empty"] == (expected is None)
            subset = s["certificate"]
            if expected is not None:
                expected_raw = expected not in c["raw"]
                assert s["raw_fallback"] == expected_raw
                if len(lost) <= 2:
                    winners.add(expected)
                    assert not s["tree_fallback"]
                    counts["raw_fallback_up_to_two"] += expected_raw
                if subset is not None:
                    assert len(subset) <= 2 and set(subset) <= lost and not s["tree_fallback"]
                    assert next(e for e, dep in full.items() if dep.isdisjoint(subset)) == expected
                else:
                    assert s["tree_fallback"]
                    for k in range(3):
                        for smaller in combinations(sorted(lost), k):
                            e = next(e for e, dep in full.items() if dep.isdisjoint(smaller))
                            assert not full[e].isdisjoint(lost)
            else:
                assert not s["raw_fallback"] and not s["tree_fallback"] and subset is None
            counts["masks"] += 1
            counts["empty"] += s["empty"]
            counts["up_to_two"] += len(lost) <= 2
            counts["outside_nonempty"] += len(lost) > 2 and expected is not None
            counts["outside_certified"] += len(lost) > 2 and subset is not None
            counts["tree_fallback"] += s["tree_fallback"]
            counts["raw_fallback"] += s["raw_fallback"]
            cert = "-" if subset is None else ".".join(map(str, subset))
            record = [c["q"], mask, expected if expected is not None else -1, cert, int(s["tree_fallback"]), int(s["raw_fallback"]), int(s["empty"])]
            cases_digest.update(("|".join(map(str, record))+"\n").encode())
        assert winners == set(c["tree"]) and len(c["tree"]) == len(winners)

    return dict(questions=len(panel), **counts, all_states_sha256=cases_digest.hexdigest())


if __name__ == "__main__":
    out = run()
    (HERE / "verification.json").write_text(json.dumps(out, indent=2)+"\n", encoding="utf8")
    print(json.dumps(out))
