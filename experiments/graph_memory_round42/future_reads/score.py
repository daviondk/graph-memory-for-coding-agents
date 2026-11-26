from collections import Counter
from data import *

PAIRS=(("local","range"),("local","content"),("local","ast"),("local","edges"),("union","local"),("union","range"))


def pair_bounds(seen_a,seen_b,A,B,closed):
    d=int(seen_a)-int(seen_b)
    if closed or (seen_a and seen_b):return [d,d]
    if seen_a:return [0 if B else 1,1]
    if seen_b:return [-1,0 if A else -1]
    return [-int(bool(B-A)),int(bool(A-B))]


def main():
    cols=read(D/"packets.json.gz");tape=read(D/"requests.json.gz")
    binds=read(D/"request-seal.json");assert binds["requests"]==sha(D/"requests.json.gz") and set(cols)==set(tape["windows"])
    scored={}
    for key,row in cols.items():
        state=tape["windows"][key];views=[tape["by_run"][row["run"]][str(i)] for i in state["reads"]]
        packet_sets={};receipt=set(map(tuple,row["receipt"]))
        for m in METHODS:
            mc={(n,d):sz for n,d,sz in row["by_method"][m]}
            packet_sets[m]=set(mc)-receipt
        demand=Counter(views=len(views),closed=int(state["closed"]),censored=int(not state["closed"]))
        arms={m:Counter() for m in METHODS}
        for v in views:
            needs={(n,d):sz for n,d,sz in v};assert len(needs)==len(v)
            all_lines=set(needs);already=all_lines&receipt;want=all_lines-receipt
            demand.update(dict(lines=len(v),bytes=sum(needs.values()),receipt_lines=len(already),
                receipt_bytes=sum(needs[j] for j in already),receipt_complete=int(not want),novel_views=int(bool(want)),
                novel_lines=len(want),novel_bytes=sum(needs[j] for j in want)))
            for m in METHODS:
                # The occurrence must match both current line and literal content, under the original byte budget.
                supplied=packet_sets[m]&want;c=arms[m]
                c.update(dict(novel_lines=len(supplied),novel_bytes=sum(needs[j] for j in supplied),
                                 views_with_gain=int(bool(supplied)),combined_lines=len(already)+len(supplied),
                                 full_with_receipt=int(not(want-supplied)),extra_full_views=int(bool(want) and not(want-supplied))))
        demand["observed_demand"]=int(bool(views));demand["observed_novel"]=int(demand["novel_views"]>0)
        for m,c in arms.items():
            c["hit"]=int(c["novel_lines"]>0);c["upper"]=int(c["hit"] or (not state["closed"] and bool(packet_sets[m])))
            c["possible_units"]=len(packet_sets[m]);c["positive_capacity"]=int(bool(packet_sets[m]))
        bounds={m+"_minus_"+b:pair_bounds(arms[m]["hit"],arms[b]["hit"],packet_sets[m],packet_sets[b],state["closed"]) for m,b in PAIRS}
        scored[key]=dict(held=row["held"],issue=row["issue"],repo=row["repo"],group=row["group"],stop=state["stop"],demand=demand,arms=arms,bounds=bounds)
    save("outcomes.json.gz",scored)
    save("score-seal.json",dict(outcomes=sha(D/"outcomes.json.gz"),schedules=sha(D/"request-seal.json"),program=sha(D/"score.py")))
    print("Scored",len(scored),"strict-demand windows.")
if __name__=="__main__":main()

