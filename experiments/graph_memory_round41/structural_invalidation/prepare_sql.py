"""Rebuild real symbol identities independently, selecting 64 cases without outcomes."""
from shared import *
from policies import index_python


def main():
    pred=read(D/"predictions.json.gz");spec=read(D/"forecast-seal.json")
    assert spec["results"]==sha(D/"predictions.json.gz")
    assert sha(D/"SQL_CHECK_RU.md")=="4687b5141d8711e00da35357c8013df9c4a8b3da58791b84965650755a71ad92"
    all_events,plans,_=inputs()
    order=sorted(all_events,key=lambda row:h("r41-ast-sql/"+case_id(row)))
    subset=[r for flag in (True,False) for r in [z for z in order if bool(z["held"])==flag][:32]]
    assert len(subset)==64
    rows={}
    for k,row,py,old,new in stream(subset):
        path=row["path"];symbol="symbol:"+path+":"
        before=index_python(old) if py else {"valid":False}
        after=index_python(new) if py else {"valid":False}
        parses=before["valid"] and after["valid"]
        same=set()
        if parses:
            seq=before["unique"];later=after["unique"]
            same={idx for idx in seq if idx in later and seq[idx][3]==later[idx][3]}
            changed=[symbol+"WHOLE"]+sorted(symbol+idx for idx in seq.keys()-same)
        else:
            changed=["file:"+path]
        inp=[];expected=[]
        inc,_=plans[row["run"]][str(row["at"])]
        for idx,p,lo,hi,size,_,_ in inc:
            if idx not in row["old"]:continue
            ent="file:"+p
            if p==path and parses:
                enclose=[n for n in before["nodes"] if n[0]<=lo<=hi<=n[1]]
                width=min((n[1]-n[0] for n in enclose),default=-1)
                smallest=[n for n in enclose if n[1]-n[0]==width]
                tag=smallest[0][2] if len(smallest)==1 and smallest[0][2] in seq else "WHOLE"
                ent=symbol+tag
            if p==path and str(idx) not in pred[k]["maps"]["ast"]:expected.append(idx)
            inp.append(dict(slot=idx,entity=ent,low=lo,high=hi,bytes=size))
        rows[k]=dict(blocks=inp,changed=changed,held=row["held"],expected=sorted(expected))
    assert len(rows)==64
    save("sql-input.json.gz",rows);save("sql-input-seal.json",dict(file=sha(D/"sql-input.json.gz"),
        forecast=sha(D/"forecast-seal.json"),protocol=sha(D/"SQL_CHECK_RU.md"),program=sha(D/"prepare_sql.py")))
    print("Sealed 64 actual symbol change projections and original selected blocks.")


if __name__=="__main__":main()

