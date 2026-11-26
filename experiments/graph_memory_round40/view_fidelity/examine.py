"""Decode raw display and native strings as inert data; outputs contain numbers, hashes and categories only."""
from bisect import bisect_left
from collections import Counter,defaultdict
import re
import sys
import unicodedata
from data import D,W,RAW,SPAN,split,fixed,raw_events,h,sha,read,save

ROW=re.compile(r" *([0-9]+)\t(.*)")
OMIT=re.compile(r"(?i)(?:<|\[|\.{3}|…|^\s*\()\s*(?:response\s+|output\s+|content\s+)?(?:truncat(?:ed|ion)|clipped|omitted|redacted|scrubbed)|(?:lines?|characters?|bytes?)\s+(?:omitted|truncated|removed)")
R38_OMIT=re.compile(r"<response clipped>|<NOTE:|\\.\\.\\.truncated",re.I)


def path_id(path):
    return h(path.removeprefix("/testbed/").removeprefix("/workspace/"))


def display(obs):
    path=obs["path"]
    assert obs["command"]=="view" and not obs["is_error"]
    full="\n".join(p["text"] for p in obs["content"] if isinstance(p,dict) and isinstance(p.get("text"),str))
    rows={};headers=0;active=False
    for line in full.splitlines():
        if "cat -n" in line and line.rstrip().endswith("on "+path+":"):
            headers+=1
            active=True
            continue
        if active:
            m=ROW.fullmatch(line)
            if not m:
                active=False
            elif not R38_OMIT.search(m[2]):
                num=int(m[1])
                assert num not in rows or rows[num]==m[2]
                rows[num]=m[2]
    return rows,headers,bool(OMIT.search(full) or R38_OMIT.search(full))


def classify(v,at,old,positions,anchors):
    if at<=len(old) and v==old[at-1]:
        return "literal",0
    matches=positions.get(v,[])
    if matches:
        i=bisect_left(matches,at)
        checks=matches[max(0,i-2):i+2]
        near=min(checks,key=lambda n:abs(n-at))
        corroborated=[p for p in matches if p-at in anchors and anchors[p-at]>=2 and p!=at]
        if len(corroborated)==1:
            return "shift_with_two_unique_anchors",corroborated[0]-at
        if len(matches)==1 and v.strip():
            return "elsewhere_unique",near-at
        return "elsewhere_ambiguous",near-at
    if at>len(old):
        return "beyond_before_end",None
    native=old[at-1]
    if "".join(v.split())=="".join(native.split()):
        return "whitespace_only",None
    if unicodedata.normalize("NFKC",v)==unicodedata.normalize("NFKC",native):
        return "unicode_equivalence",None
    if min(len(v),len(native))>=4:
        if native.startswith(v) or native.endswith(v):
            return "display_part_of_native",None
        if v.startswith(native) or v.endswith(native):
            return "native_part_of_display",None
    return "other",None


def resolve_views(schedule):
    owner={}
    for rid,row in schedule.items():
        latest={}
        for e in row["events"]:
            if e[1]=="reset":
                latest={}
            elif e[1]=="view":
                latest[e[2]]=e[0]
            else:
                if e[2] in latest:
                    owner[rid,e[0]]=latest.pop(e[2])
    return owner


def feature_rows(rows,raw,plans,visible,schedule):
    output={}
    owner=resolve_views(schedule)
    for r in rows:
        rid=r["rid"];at=r["view"]
        ob=raw[rid][at]["observation"]
        assert path_id(ob["path"])==r["path"] and owner[rid,r["event"]]==at
        vv,headers,is_clipped=display(ob)
        known=visible[rid][str(at)]
        assert [[n,h(s),len(s.encode()),int(n+1 in vv)] for n,s in sorted(vv.items())]==known
        assert headers>=1
        numbers=sorted(vv);first,last=numbers[0],numbers[-1]
        gap=len(numbers)!=last-first+1
        byte_lower={};amount=first-1
        previous=first
        for n in numbers:
            amount+=n-previous
            byte_lower[n]=amount
            amount+=len(vv[n].encode())
            previous=n
        facts=[]
        for i in r["eligible"]:
            path,lo,hi,*_=plans[rid][str(r["event"])][i]
            assert path==r["path"]
            for n in range(lo,hi+1):
                value=vv[n]
                facts.append(dict(n=n,selected=int(i in r["old"]),full_reuse_selected=int(i in r["old"] and r["range_reuse"]),
                    lower=byte_lower[n],display_length=len(value.encode()),clip=int(is_clipped),gaps=int(gap),
                    edge=int(n==first or n==last),empty=int(not value.strip()),header_count=headers,
                    starts_at_one=int(first==1),line_probe_hash=h(value),view_first=first,view_last=last,
                    previous_view_gap=r["event"]-at))
        output[rid,r["event"]]=(vv,facts)
    return output


def run(stage):
    rows,test=split()
    selected=[r for r in rows if (r["issue"] in test)==(stage=="holdout")]
    plans,visible,schedule=fixed()
    raw=raw_events(selected)
    public=feature_rows(selected,raw,plans,visible,schedule)
    records=[];relations=[];counts=Counter();offsets=Counter();sizes=Counter();bycase=[]
    for r in selected:
        rid=r["rid"];event=r["event"];ob=raw[rid][r["receipt"]]["observation"]
        ac=raw[rid][event];edit=ac["action"];va=raw[rid][r["view"]]["observation"]
        assert ob["command"]==edit["command"]=="str_replace" and not ob["is_error"]
        assert edit["path"]==ob["path"]==va["path"] and ac["id"]==raw[rid][r["receipt"]]["action_id"]
        assert ac.get("tool_call_id")==raw[rid][r["receipt"]].get("tool_call_id")
        pre,post=ob["old_content"],ob["new_content"]
        old,new=edit["old_str"],edit["new_str"]
        assert old.strip() and pre.count(old)==1 and pre.replace(old,new,1)==post
        before,after=pre.split("\n"),post.split("\n")
        assert len(after)-len(before)==r["delta"]
        vv,facts=public[rid,event]
        positions=defaultdict(list)
        for j,line in enumerate(before,1):
            positions[line].append(j)
        anchors=Counter()
        for n,line in vv.items():
            ix=positions.get(line,())
            if len(ix)==1 and len(line.strip())>=5:
                anchors[ix[0]-n]+=1
        row_case=Counter()
        for f in facts:
            n=f["n"];v=vv[n];new_at=n+r["delta"] if n>r["end"] else n
            category,off=classify(v,n,before,positions,anchors)
            exact=category=="literal"
            actual=0<new_at<=len(after) and v==after[new_at-1]
            assert exact==actual
            row_case[category]+=1
            pair=(rid,event)
            if not exact:
                if off is not None:
                    offsets[off]+=1
                counts["missing_same_address_in_bounds" if n<=len(before) else "missing_same_address_beyond"]+=1
                counts["bad_before_marker"]+=int(bool(OMIT.search(pre)))
                sizes[len(pre)]+=1
            records.append([rid,event,h(r["issue"]),f,category,off,int(n<=len(before)),len(before)])
        counts.update(row_case);counts["pairs"]+=1
        if sum(row_case.values())>row_case["literal"]:
            counts["mismatch_pairs"]+=1
            # Counters and lengths characterize possible serialized limits without publishing text.
            bycase.append([len(pre),len(before),min(vv),max(vv),len(vv),int(bool(OMIT.search(pre))),int(bool(OMIT.search(post)))])
        relations.append([rid,event,h(r["issue"]),dict(row_case)])
    save(D/(stage+"-verified.json.gz"),records)
    save(D/(stage+"-case-diagnostics.json.gz"),relations)
    save(D/(stage+"-diagnosis.json"),dict(counts=counts,offsets=offsets,common_bad_snapshot_lengths=sizes.most_common(12),
        snapshots=bycase,raw_manifest=sha(RAW/"files.json"),native_seal=sha(SPAN/"scored.json.gz"),
        protocol=sha(D/"PROTOCOL_RU.md"),issue_aliases=sorted({h(r["issue"]) for r in selected})))
    print(stage,dict(counts),offsets.most_common(9),sizes.most_common(9))


if __name__=="__main__":
    run(sys.argv[1])
