"""Independent full-view checksum test at the derived displacement, with original view/action links."""
from collections import Counter,defaultdict
import re
import json
import pyarrow.parquet as pq
from data import D,RAW,read,save,sha,h,raw_events,split
from detector import gate
from examine import display,ROW,R38_OMIT

REDACTION=re.compile(r"(?i)(?:\[|<)(?:redacted|REDACT)(?:[_ :\-]|>|\])")


def match_requests(rows,events):
    wanted=defaultdict(dict);lookup={}
    for r in rows:
        raw=events[r["rid"]][r["view"]]
        key=raw["action_id"],raw.get("tool_call_id")
        wanted[r["rid"]][key]=r["view"]
    observed={}
    for s in read(RAW/"files.json")["events"]:
        path=RAW/s["file"];assert sha(path)==s["sha"]
        for batch in pq.ParquetFile(path).iter_batches(columns=["run_id","event_index","event_type","event_json"],batch_size=384):
            for j,(rid,at,typ) in enumerate(zip(batch.column(0).to_pylist(),batch.column(1).to_pylist(),batch.column(2).to_pylist())):
                if typ!="ActionEvent":
                    continue
                if rid not in lookup:
                    lookup[rid]=h(rid)
                run=lookup[rid]
                if run not in wanted:
                    continue
                raw=json.loads(batch.column(3)[j].as_py()).get("raw",{})
                key=(raw.get("id"),raw.get("tool_call_id"))
                if key not in wanted[run]:
                    continue
                view=wanted[run][key];cmd=raw["action"]
                assert cmd["command"]=="view" and cmd["path"]==events[run][view]["observation"]["path"] and at<view
                assert (run,view) not in observed
                observed[run,view]=cmd.get("view_range")
    assert len(observed)==sum(map(len,wanted.values()))
    return observed


def main():
    assert (D/"prediction-seal.json").is_file()
    rows,test=split()
    raw=raw_events(rows)
    requested=match_requests(rows,raw)
    cnt=Counter();cases=[];displacements=[]
    for r in rows:
        rid=r["rid"];view=r["view"]
        obs=raw[rid][view]["observation"]
        before=raw[rid][r["receipt"]]["observation"]["old_content"].split("\n")
        vv,_,_=display(obs)
        accept,diag=gate(obs)
        cnt["view_action_links"]+=1
        if diag["cut"] is None:
            continue
        cut=diag["cut"]
        prefix={n:s for n,s in vv.items() if n<cut}
        suffix={n:s for n,s in vv.items() if n>=cut}
        positions=defaultdict(list)
        for n,s in enumerate(before,1):
            positions[s].append(n)
        anchored=Counter()
        for n,s in suffix.items():
            if len(s.strip())>=5 and len(positions[s])==1:
                anchored[positions[s][0]-n]+=1
        d,nanchor=anchored.most_common(1)[0]
        assert d>0 and nanchor>=2
        prefix_ok=sum(n<=len(before) and s==before[n-1] for n,s in prefix.items())
        aligned=sum(1<=n+d<=len(before) and s==before[n+d-1] for n,s in suffix.items())
        unshifted=sum(n<=len(before) and s==before[n-1] for n,s in suffix.items())
        raw_text="\n".join(p["text"] for p in obs["content"] if isinstance(p,dict) and isinstance(p.get("text"),str))
        marker_contents=[m[2] for line in raw_text.splitlines() if (m:=ROW.fullmatch(line)) and R38_OMIT.search(m[2])]
        numbers=[int(v) for line in marker_contents for v in re.findall(r"(?<!\w)\d+(?!\w)",line)]
        vr=requested[rid,view]
        finite=isinstance(vr,(list,tuple)) and len(vr)==2 and isinstance(vr[1],int) and vr[1]>0
        end=vr[1] if finite else len(before)
        cnt.update(dict(clipped_views=1,prefix_rows=len(prefix),prefix_literal=prefix_ok,
            tail_rows=len(suffix),tail_literal_unshifted=unshifted,tail_literal_shifted=aligned,
            explicit_finite_request=int(finite),dominant_maps_to_requested_end_or_eof=int(max(suffix)+d==end),
            marker_reports_true_displacement=int(d in numbers),native_redaction_marked_views=int(any(REDACTION.search(s) for s in before)),
            display_redaction_marked_views=int(bool(REDACTION.search(raw_text))),unique_tail_anchor_rows=nanchor))
        cases.append([rid,r["event"],h(r["issue"]),int(r["issue"] in test),d,nanchor,len(anchored),len(prefix),prefix_ok,
            len(suffix),aligned,unshifted,finite,max(suffix)+d==end,len(numbers),d in numbers])
        displacements.append(d)
    save(D/"suffix-check.json",dict(counts=cnt,minimum_displacement=min(displacements),maximum_displacement=max(displacements),
        unique_joined_view_requests=len(requested),clipped_cases=cases))
    print(dict(cnt),min(displacements),max(displacements))


if __name__=="__main__":
    main()
