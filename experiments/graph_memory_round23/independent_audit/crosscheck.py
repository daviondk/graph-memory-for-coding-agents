"""Verify issued receiver rows and count paired positive/negative *trajectories*."""
from collections import Counter,defaultdict
from audit import *
def main():
    origin=load(D/"recomputed.json.gz");nums=load(D/"numerical.json")
    p=RECEIVE/"per-query.json.gz";reference=load(p)["rows"];assert set(origin)==set(reference)
    gold=load(OFF/"gold-spans.json.gz");count=0;clusters={}
    for i in range(8):
        reg={s["t"]:{tuple(a):e for e,a in enumerate(s["addresses"])} for s in load(R22/f"no-next-decisions-{i}.json.gz")}
        bookings=load(OPEN/f"reads-{i}.json.gz");recvs=load(RECEIVE/f"receiver-{i}.json.gz")
        for r in load(CAUSE/f"receipts-{i}.json.gz"):
            q,t=r["q"],r["t"];gs=[(reg[t][z["event_id"],z["json_pointer"]],z["char_start"],z["char_end"]) for z in gold[q]]
            w=recvs[q];sender=r["arms"]["ratio/merged"]["paid"]["2048"];ow=bookings[q]["read"]["ratio/merged/bm25"]
            actual={"sender":list(metrics(gs,sender[2])[:3]),"receiver":list(metrics(gs,w["shown"])[:3]),
                    "sender_read":open_metrics(gs,ow)[:3],"receiver_read":open_metrics(gs,w["opened"])[:3]}
            assert actual==reference[q]["values"] and reference[q]["cost"]==[w["tokens_in"],w["raw"],w["tokens_internal"],sender[0],w["opened"][3],ow[3]]
            count+=len(actual)
    matrix=Counter((a["v"]["short_intact"],a["v"]["receiver_intact"],a["v"]["sender_intact"]) for a in origin.values())
    for left,right in (("sender_intact","receiver_intact"),("anchor_lex","anchor_first"),("augment_anchor_lex","augment_anchor_first"),("augment_anchor_lex","augment_bm_sender"),("bm_sender","bm_receiver")):
        delta=defaultdict(int)
        for a in origin.values():delta[a["t"]]+=a["v"][left]-a["v"][right]
        nonzero=np.asarray([n for n in delta.values() if n])
        if len(nonzero)<=18:
            flips=np.array([[1 if (k>>i)&1 else -1 for i in range(len(nonzero))] for k in range(2**len(nonzero))]);xs=flips@nonzero
            prob=float(np.mean(abs(xs)>=abs(sum(nonzero))));exact=True
        else:
            rng=np.random.default_rng(481);exceed=0;n=100000
            for i in range(100):exceed+=sum(abs((rng.integers(2,size=(1000,len(nonzero)))*2-1)@nonzero)>=abs(sum(nonzero)))
            prob=(1.+exceed)/(n+1);exact=False
        clusters[left+"-"+right]={"positive_clusters":int(sum(nonzero>0)),"negative_clusters":int(sum(nonzero<0)),"clusters_with_net_change":len(nonzero),"p_signflip_two_sided":prob,"exact":exact}
    save(D/"receiver-check.json",{"matched":count,"upstream_perq":sha(p),"source":sha(Path(__file__)),"cluster_sensitivity":clusters,"joint_counts_short_client_sender":{str(k):v for k,v in matrix.items()}})
if __name__=="__main__":main()

