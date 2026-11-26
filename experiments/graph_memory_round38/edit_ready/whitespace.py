"""Apply the stricter interpretation of whitespace-only replacement before first-run selection."""
from collections import Counter
from common import D, get, save, sha
from score import summarize


def main():
    raw, scored = get(D/"native-audit.json"), get(D/"scored.json.gz")
    excluded = set(map(tuple, raw["equal_after_removing_whitespace"]))
    seen = set()
    rows = []
    for row in sorted(scored["records"], key=lambda r: (r["run"], r["at"])):
        if (row["run"], row["at"]) in excluded:
            continue
        updated = row.copy()
        prefix = row["part"].split("_")[0]
        updated["part"] = prefix + ("_later" if row["run"] in seen else "_first")
        seen.add(row["run"])
        rows.append(updated)
    results = {p: summarize([r for r in rows if r["part"] == p], scored["methods"], p == "main_first")
               for p in sorted({r["part"] for r in rows})}
    save(D/"whitespace-strict.json", dict(excluded=len(excluded), strata=results, total=len(rows),
                                          scored=sha(D/"scored.json.gz"), native_audit=sha(D/"native-audit.json")))
    print({p: (s["operations"], s["methods"]["focus-64"]["complete"], s["methods"]["tail-64"]["complete"], s["contrast"])
           for p, s in results.items()})


if __name__ == "__main__":
    main()
