"""After sealing selections, check literal line contents and within-block LF bytes on the edited path."""
from collections import Counter
from shared import D,NAT,SPAN,read,sha,save,raw_events,signed
from examine import display,path_id


def main():
    assert read(D/"selection-seal.json")["selection"]==sha(D/"selections.json.gz")
    selection=read(D/"selections.json.gz");plans=read(D/"guarded-plans.json.gz")
    raw=raw_events([dict(rid=r["run"],event=r["at"],receipt=r["receipt"],view=r["view"]) for r in selection])
    orig=signed(NAT,"plans.json.gz")
    checked=[];total=Counter()
    for row in selection:
        run,at=row["run"],row["at"]
        ev=raw[run];ob=ev[row["receipt"]]["observation"];ac=ev[at]["action"];view=ev[row["view"]]["observation"]
        assert not ob["is_error"] and ob["command"]==ac["command"]=="str_replace" and ob["path"]==view["path"]==ac["path"]
        assert path_id(ob["path"])==row["path"] and ev[at]["id"]==ev[row["receipt"]]["action_id"]
        assert ev[at].get("tool_call_id")==ev[row["receipt"]].get("tool_call_id")
        pre,post=ob["old_content"],ob["new_content"]
        assert pre.count(ac["old_str"])==1 and pre.replace(ac["old_str"],ac["new_str"],1)==post
        before,after=pre.split("\n"),post.split("\n")
        assert len(after)-len(before)==row["delta"]
        literal,_,_=display(view)
        inc,rem=plans[run][str(at)]
        keep={b[0]:b[-1] for b in inc}
        removed={b[0]:b[-1] for b in rem}
        v=Counter();eligible=set()
        for idx,(path,lo,hi,size,utility) in enumerate(orig[run][str(at)]):
            if path!=row["path"]:
                continue
            actual_view=keep.get(idx,removed.get(idx))
            if actual_view is None:
                assert idx in removed
                v["unresolved_target_blocks"]+=1
                continue
            assert actual_view==row["view"]
            outside=lo>row["end"] or hi<row["start"]
            if outside and idx in keep:
                eligible.add(idx)
            block_bytes=0
            for n in range(lo,hi+1):
                text=literal[n]
                # One LF is charged to the preceding line only within this displayed block.
                lf=int(n<hi)
                cost=len(text.encode())+lf
                block_bytes+=cost
                ok=n<=len(before) and before[n-1]==text and (not lf or n<len(before))
                def note(label,correct):
                    v[label+"_lines"]+=1;v[label+"_bytes"]+=cost
                    if not correct:
                        v[label+"_wrong_lines"]+=1;v[label+"_wrong_bytes"]+=cost
                note("target",ok)
                note("retained" if idx in keep else "removed",ok)
                if idx in row["old"]:
                    note("selected_before",ok)
                if outside and idx in keep:
                    new=n+row["delta"] if n>row["end"] else n
                    post_ok=1<=new<=len(after) and after[new-1]==text and (not lf or new<len(after))
                    note("survivors_after",post_ok)
                    if idx in row["interval"]:
                        note("selected_after",post_ok)
                    if row["same"] and idx in row["old"]:
                        note("fully_reused_selected_after",post_ok)
            assert block_bytes==size
        assert all(i in eligible for i in row["interval"] if orig[run][str(at)][i][0]==row["path"])
        total.update(v);checked.append([run,at,dict(v)])
    save(D/"checked-text.json.gz",checked)
    save(D/"text-check.json",dict(counts=total,rows=len(selection),sealed=sha(D/"selection-seal.json"),
        evidence=sha(D/"checked-text.json.gz"),raw_manifest=sha(__import__("data").RAW/"files.json")))
    print(dict(total))


if __name__=="__main__":
    main()
