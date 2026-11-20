"""After primary grading, enumerate which stamp fields distinguish the actually observed changes."""
import gzip,hashlib,itertools,json
from pathlib import Path
D=Path(__file__).resolve().parent
def load(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
FIELDS=["mtime_ns","size","device","inode","status_change"]
out={}
for fs in ("ext4","tmpfs","ntfs"):
    for panel in ("controlled","released"):
        if fs=="ntfs":
            if panel=="controlled":
                src=load(D.parent/"ledger"/"pair_states.json")
            else:
                src=[r for r in load(D.parent/"ledger"/"natural/scores.json.gz") if r["arm"]=="ntfs_change"]
            rows=[([r["before"][k] for k in ("mtime","size","dev","ino","change")],
                   [r["after"][k] for k in ("mtime","size","dev","ino","change")],r["old_sha"]!=r["new_sha"]) for r in src]
        else:
            rows=[(r["stored"],r["after"],r["truth"]!=r["before"]) for r in load(D/fs/"metrics.json.gz") if r["arm"]=="ctime_id" and r["panel"]==panel]
        values=[]
        for n in range(1,len(FIELDS)+1):
            for mask in itertools.combinations(range(len(FIELDS)),n):
                equal=[(all(a[i]==b[i] for i in mask),changed) for a,b,changed in rows]
                values.append({"fields":[FIELDS[i] for i in mask],"hit":sum(s for s,c in equal),"stale":sum(s and c for s,c in equal)})
        out[fs+"/"+panel]={"n":len(rows),"all_masks":values,"minimum_single_fields_without_false_reuse":[v for v in values if len(v["fields"])==1 and not v["stale"]]}
(D/"field_ablation.json").write_text(json.dumps(out,indent=1))
print([(panel,r["minimum_single_fields_without_false_reuse"]) for panel,r in out.items()])
