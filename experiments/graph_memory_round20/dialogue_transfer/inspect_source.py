from collections import Counter
import hashlib, json
from pathlib import Path
p=Path("D:/CodexResearch/x20-longmemeval-dretr/longmemeval_s_cleaned.json")
x=json.loads(p.read_bytes())
print(len(x), sorted(x[0]), sorted(x[0]["haystack_sessions"][0][0]))
print("turn keys", Counter(tuple(sorted(r)) for q in x for s in q["haystack_sessions"] for r in s))
print("marker types",Counter((type(r.get("has_answer")).__name__, str(r.get("has_answer"))[:5]) for q in x for s in q["haystack_sessions"] for r in s))
print("roles",Counter(r["role"] for q in x for s in q["haystack_sessions"] for r in s))
print("total sessions",sum(len(q["haystack_sessions"]) for q in x))
