"""Clip fixed responses to a common pairwise cap, then join benchmark evidence."""
import runpy
from select_read import c,D
def prepare():
    lock=c.read(D/"forecast-seal.json");assert c.checksum(D/"actions.json.gz")==lock["predictions"]
    tok=c.tok();v=c.get_views();docs={i:r[2] for i,r in enumerate(v["documents"])}
    out={}
    def trim(action,cap):
        _,(e,l,h,n),_=action
        prefix=f"[{e}:{l}] ";s=prefix+docs[e][l:h]
        enc=tok.encode(s,add_special_tokens=False);assert len(enc.ids)==n
        cut=enc.offsets[cap][0] if n>cap else len(s)
        while True:
            charge=len(tok.encode(s[:cut],add_special_tokens=False).ids)
            if charge<=cap:break
            cut-=1
        assert cut>=len(prefix)
        return [e,l,l+cut-len(prefix),charge]
    for q,r in c.read(D/"actions.json.gz").items():
        pairs={}
        for control in ("bm25","first_positive"):
            first=r["actions"]["rank_novelty"];second=r["actions"][control]
            cap=min(first[1][3],second[1][3]) if first and second else 0
            pairs[control]=[cap,trim(first,cap) if cap else None,trim(second,cap) if cap else None]
        out[q]=pairs
    return c.save(D/"cost-actions.json.gz",out)
def evaluate(digest):
    assert c.checksum(D/"cost-actions.json.gz")==digest
    sc=runpy.run_path(str(D.parent/"transfer/score.py"),run_name="md_labels");goals,_=sc["labels"](c.get_views());union=sc["union"];overlap=sc["overlap"]
    src=c.read(D/"actions.json.gz");cut=c.read(D/"cost-actions.json.gz")
    ret={}
    for control in ("bm25","first_positive"):
        rows=[]
        for q,p in cut.items():
            gt=union(goals[q][0]);n=sum(h-l for e,l,h in gt)
            mem=src[q]["base"];cap,a,b=p[control]
            vals=[int(overlap(gt,union(mem+([piece[:3]] if piece and piece[1]<piece[2] else [])))==n) for piece in (a,b)]
            costs=[piece[3] if piece else 0 for piece in (a,b)]
            rows.append([*vals,*costs,cap])
        ret[control]={"n":len(rows),"hits":[sum(r[j] for r in rows) for j in (0,1)],
         "average_tokens":[sum(r[j] for r in rows)/len(rows) for j in (2,3)],"unequal_final":sum(r[2]!=r[3] for r in rows),
         "wins":sum(r[0]>r[1] for r in rows),"losses":sum(r[0]<r[1] for r in rows)}
    c.save(D/"cost-results.json",{"actions":digest,"protocol":c.checksum(D/"COST_CONTROL_RU.md"),"pairs":ret});print(ret)
if __name__=="__main__":evaluate(prepare())
