"""Re-evaluate high-impact terminal inversions and measure the FP32 score gaps."""
from collections import defaultdict
from unittest.mock import patch
from shared import D, OFF, SEEDS, ARMS, read, sha, save


def main():
    # Native imports set device masking before the checkpoint or forward touches CUDA.
    import native
    api = native.api
    api.torch.set_num_threads(2)
    api.torch.set_num_interop_threads(1)
    assert not api.torch.cuda.is_available()
    evidence = read(D / "forecast-seal.json")["terminal_differences"]
    byq = defaultdict(set)
    for q, key, length, rank, strict, ff in evidence:
        if rank < 5 or not strict or not ff:
            byq[q].add(key)
    if not byq:
        save(D / "terminal-numeric.json", dict(required_questions=0,details=[],seal=sha(D/"forecast-seal.json")))
        print("no top-five or packet deviations")
        return
    split = read(OFF / "split.json.gz")["test"]
    qs = defaultdict(set)
    for r in split:
        if r["q"] in byq:
            qs[r["t"]].add(r["q"])
    relevant_texts = {r["q"] for r in split if r["t"] in qs}
    txt = {r["id"]:r["query"] for _,r in api.pilot.stream(api.pilot.Q) if r["id"] in relevant_texts}
    tok = api.pilot.offsets(api.pilot.Tokenizer.from_file(str(api.pilot.CACHE/"tokenizer.json")))
    def chunk(s):
        return api.pilot.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64)
    needed = {int(k.split("/")[0]) for arms in byq.values() for k in arms}
    models={s:native.native_inputs(s) for s in needed}
    result=[]
    for sh in range(8):
        ids,costs,expected=native.indexes(sh)
        present=set(ids).intersection(byq)
        if not present:
            continue
        canonical={}
        for seed in needed:
            for arm in ARMS:
                key=f"{seed}/{arm}"
                pub=OFF/f"seed-{seed}"/arm
                ref=pub/f"picks-{sh}.json.gz"
                assert sha(ref) == next(v["sha"] for v in read(pub/"forecast-seal.json")["receipts"] if v["file"]==ref.name)
                canonical[key]={r["q"]:r["graph"] for r in read(ref) if r["q"] in present}
        src=api.RAW/f"trajectories-{sh:05d}.jsonl"
        assert sha(src)==read(D/f"forecast-{sh}-seal.json")["source"]
        sealed={q:r for q,t,c,r in read(D/f"forecast-{sh}.json.gz") if c==100}
        for _, raw in api.pilot.stream(src):
            t=raw["session_id"]
            if t not in qs:
                continue
            tr=native.adapt_isetrace_record(native.parse_isetrace_record(raw),source_revision=api.pilot.RAW[1])
            graph=native.prefix_graph(tr,native.midstep(tr)[1],chunk)
            # Preserve the original per-trajectory batching including its other questions.
            qnames=[r["q"] for r in split if r["t"]==t]
            texts={q:txt[q] for q in qnames}
            for q in qs[t]:
                for key in sorted(byq[q]):
                    seed_s,arm=key.split("/")
                    seed=int(seed_s)
                    db,lookup,nets=models[seed]
                    values={}
                    def capture(batch, scores):
                        all_scores=api.inf.split_batch_node_scores(batch,scores)
                        for label,pairs in all_scores.items():
                            values[label]=dict(pairs)
                        return {label:[k for k,_ in sorted(pairs,key=lambda x:(-x[1],x[0]))] for label,pairs in all_scores.items()}
                    with patch.object(api.old,"orders",capture):
                        out=native.score_graph(graph,texts,{seed:(db,lookup,{arm:nets[arm]})},defaultdict(float))
                    index={name:i for i,name in enumerate(ids[q])}
                    order=[index[n] for n in out[q][key]]
                    assert order==sealed[q][key]
                    gpu=canonical[key][q]
                    pos={node:i for i,node in enumerate(gpu)}
                    vv=values[q]
                    inverted=[abs(vv[ids[q][a]]-vv[ids[q][b]]) for i,a in enumerate(order)
                              for b in order[i+1:] if pos[a]>pos[b]]
                    assert inverted
                    result.append(dict(q=q,arm=key,inversions=len(inverted),max_gap=max(inverted),min_gap=min(inverted)))
    assert len(result)==sum(map(len,byq.values()))
    save(D/"terminal-numeric.json",dict(required_questions=len(byq),details=result,seal=sha(D/"forecast-seal.json")))
    print("terminal gaps",len(result),max(r["max_gap"] for r in result))


if __name__=="__main__":
    main()
