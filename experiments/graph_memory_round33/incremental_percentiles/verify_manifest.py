import json,gzip,hashlib
from pathlib import Path
D=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rd(p):return json.loads(p.read_bytes())
manifest=rd(D/"manifest.json")
for f,h in manifest.items():assert sha(D/f)==h,f
lock=rd(D/"fixture-lock.json");chk=rd(D/"equivalence.json");native=rd(D/"native-results.json");again=rd(D/"native-repeat.json")
assert all(sha(D/k)==h for k,h in lock["files"].items())
assert chk["by_state"]==sha(D/"by-state.json.gz") and native["fixture_plan"]==sha(D/"fixture-lock.json")
assert chk["states"]==native["states"]==364 and chk["question_states"]==native["question_states"]==514
assert again["source"]==sha(D/"native-results.json")
print(f"Verified {len(manifest)} files, {native['states']} as-of states and {native['question_states']} query-state orders.")