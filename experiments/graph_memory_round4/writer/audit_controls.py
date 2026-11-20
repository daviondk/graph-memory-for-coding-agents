"""Verify constant baselines byte-for-byte against the open R3 replay and scores."""
from collections import Counter
from shared import D,A,B,rows,save,sha
def main():
    report={}
    for panel,orig in (("A",A),("B",B)):
        dest=D/("panel_"+panel);ev=Counter();hit=Counter()
        ctrls=("lru","point","typed","mixed") if panel=="B" else ("lru","point","typed")
        for k in range(8):
            for new,old in zip(rows(dest/f"events_{k}.gz"),rows(orig/f"events_{k}.jsonl.gz"),strict=True):
                assert new[:2]==old[:2];od={z[0]:z[2:] for z in old[2]}
                for a in ctrls:
                    digest,before,size,drop,npack,_=new[-1][a];sha_old,sz,pre,dr,attempt=od[a]
                    assert (digest,size,before,drop,npack)==(sha_old,sz,pre,dr,attempt);ev[a]+=1
        for new,old in zip(rows(dest/"scored.jsonl.gz"),rows(orig/"scored.jsonl.gz"),strict=True):
            assert new[:4]==old[:4]
            for a in ctrls:
                assert new[-1][a]==old[-1][a];hit[a]+=1
        report[panel]=dict(exact_event_states=ev,same_graded_actions=hit)
    save(D/"controls_audit.json",report);print(report)
if __name__=="__main__":main()
