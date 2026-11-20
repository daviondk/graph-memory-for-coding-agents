"""Exploratory target path audit: distinguish obvious reproduction/temporary names, tests and other paths."""
import re,gzip,json
from pathlib import PurePosixPath
from collections import defaultdict
from context import D,rows,stream,future,save
import grade
def category(path):
    s=path.lower();p=PurePosixPath(s);stem=p.stem
    if re.search(r'(?:reproduc|^repro(?:_|$)|reproducer|^temp_|^tmp_|^demo(?:_|$)|^scratch(?:_|$))',stem):return "explicit_scratch_name"
    if "tests" in p.parts or "test" in p.parts or stem.startswith("test_") or stem.endswith("_test") or stem=="conftest":return "test_named"
    return "other_path"
def main():
    for root in (D,D/"replication"):
        tagged=defaultdict(list);tag={}
        for k in range(8):
            for o in rows(root/f"source_{k}.jsonl.gz"):
                for t in range(4,len(o["events"]),4):
                    q=future(o["events"],t)
                    if q and q[2]:tag[o["instance"],t]=category(q[0])
        for r in rows(root/"expansion_scores.jsonl.gz"):
            if r[2]==512:tagged[tag[r[0],r[1]]].append(r)
        result={};arms=["r2f","typed","old_balanced","iso_balanced"];grade.A=("r2f","typed")
        for c,subs in tagged.items():
            summary={"n":len(subs),"arms":{a:sum(r[-1][a][0] for r in subs) for a in arms},"vs_original":{}}
            for a in arms[1:]:
                small=[[*v[:-1],{"r2f":v[-1]["r2f"],"typed":v[-1][a]}] for v in subs]
                summary["vs_original"][a]=grade.metrics(small)["typed_minus"]["r2f"]
            result[c]=summary
        (root/"target_sensitivity.json").write_text(json.dumps(result,indent=1))
if __name__=="__main__":main()
