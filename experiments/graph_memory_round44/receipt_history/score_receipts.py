"""Evaluate source truth and actual subsequent demand only after every writer has frozen."""
import time
import pyarrow.parquet as pq
from rec_data import *
from grade import stream
D=HERE;save=store_file


def main():
    start=time.perf_counter();pred=read(D/"forecasts.json.gz");fs=read(D/"forecast-seal.json")
    assert fs["forecasts"]==sha(D/"forecasts.json.gz")
    fut=signed(F,"requests.json.gz");base=signed(F,"packets.json.gz");cases=signed(G,"selections.json.gz");out={}
    for k,row,before,after in stream(cases):
        z=pred[k];p=base[k];window=fut["windows"][k];receipt=set(map(tuple,p["receipt"]))
        vv=[{(n,d):sz for n,d,sz in fut["by_run"][row["run"]][str(i)]} for i in window["reads"]]
        want=Counter()
        for v in vv:want.update({x:1 for x in v.keys()-receipt})
        tested=[]
        for old,new,dg,size in z["candidates"]:
            b=1<=old<=len(before) and h(before[old-1])==dg
            a=1<=new<=len(after) and h(after[new-1])==dg
            assert (new,dg) not in receipt
            tested.append((bool(b),bool(a),want[(new,dg)],size,(new,dg)))
        arms={};sets={}
        for mode,rec in z["arms"].items():
            wire,n,blobs,body,_=rec["wire"]
            assert wire==8+50*n+2*blobs+body
            ar={};sets[mode]={}
            for output in ("all","read"):
                ii=rec[output];assert len(ii)==len(set(ii))
                corr=[tested[j] for j in ii];valid={v[4] for v in corr if v[1]}
                assert len(valid)==sum(v[1] for v in corr)
                sets[mode][output]=valid
                obs=Counter(slots=len(ii),bad_old=sum(not v[0] for v in corr),bad_new=sum(not v[1] for v in corr),
                      hit=int(any(v[1] and v[2] for v in corr)),novel_lines=sum(v[2] for v in corr if v[1]),
                      novel_bytes=sum(v[2]*v[3] for v in corr if v[1]),raw_bytes=sum(v[3]+1 for v in corr),
                      possible=int(bool(valid)),full_with_receipt=sum((set(v)-receipt)<=valid for v in vv),
                      extra_full_views=sum(bool(set(v)-receipt) and (set(v)-receipt)<=valid for v in vv))
                obs["upper"]=int(obs["hit"] or (not window["closed"] and bool(valid)))
                ar[output]=dict(obs)
            assert ar["read"]["raw_bytes"]==rec["emitted_bytes"]<=2048
            arms[mode]=ar
        bounds={}
        for m,b in (("joint_8192","views_8192"),("joint_unlimited","views_unlimited"),("receipts_8192","views_8192"),("joint_2048","views_2048")):
            dat={}
            for t in ("all","read"):
                ma=arms[m][t]["hit"];mb=arms[b][t]["hit"];A=sets[m][t];B=sets[b][t]
                if window["closed"] or ma and mb:iv=[ma-mb]*2
                elif ma:iv=[int(not B),1]
                elif mb:iv=[-1,-int(not A)]
                else:iv=[-int(bool(B-A)),int(bool(A-B))]
                dat[t]=iv
            bounds[m+"_minus_"+b]=dat
        out[k]=dict(held=p["held"],issue=p["issue"],group=p["group"],repo=p["repo"],run=row["run"],closed=window["closed"],views=len(vv),
                    demand=int(bool(want)),demand_lines=sum(want.values()),arms=arms,paired_bounds=bounds,
                    checks=[[int(a),int(b),n] for a,b,n,sz,pair in tested])
    save("outcomes.json.gz",out);save("grade-seal.json",dict(rows=sha(D/"outcomes.json.gz"),forecasts=sha(D/"forecast-seal.json"),future=sha(F/"requests.json.gz"),
              source=sha(RAW/"files.json"),program=sha(D/"score_receipts.py"),seconds=time.perf_counter()-start))
    print("Checked current and historical source bytes plus future requests for",len(out),"edits.")

if __name__=="__main__":main()

