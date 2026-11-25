"""Audit transfer of native candidate identity and FP32 ranks without using evidence labels."""
from collections import defaultdict
import hashlib
import sqlite3

import holdout as h


def main():
    files, texts, groups = h.inv.group()
    ranked = h.ROOT if hasattr(h, "ROOT") else h.D.parent
    source = ranked / "residual_graph/dev500-pu-dense-ranks.json.gz"
    index = defaultdict(dict)
    for row in h.load(source):
        index[row["t"]][row["q"]] = row["rr"]
    connection = h.database()
    encoder = h.Lookup(connection, "ft")
    retriever = h.DenseTaskRetriever(encoder=encoder, device="cpu")
    trajectories = 0
    prior_queries = 0
    exact_node_lists = 0
    nodes = 0
    max_error = 0.0
    for f in files:
        raw = h.load(f)
        t = raw["t"]
        if t not in index:
            continue
        previous = h.load(h.WD / "projection/dev" / (t + ".json.gz"))["pool"]
        items = []
        for z, old in zip(raw["pool"], previous, strict=True):
            m, sp = z["metadata"], z["source_spans"][0]
            key = (h._argument_chunk_node_id if m["node_kind"] == "content.tool_argument" else h._output_chunk_node_id)(m["call_id"], m["chunk_index"])
            new = h.TextCandidate(item_id=key, text=raw["fields"][sp["event_id"]][sp["char_start"]:sp["char_end"]], source_spans=z["source_spans"], metadata=m)
            assert new.model_dump(mode="json") == old
            items.append(new)
        trajectories += 1
        for q, text in raw["q"]:
            if q not in index[t]:
                continue
            prior_queries += 1
            request = h.TextRankingRequest(task_id=q, query_text=text, candidates=tuple(items))
            ranks = retriever.rank(request)
            old = index[t][q]
            assert len(ranks) == len(old)
            ids = [r.node_id for r in ranks]
            assert ids == [r["node_id"] for r in old]
            exact_node_lists += 1
            nodes += len(ids)
            max_error = max(max_error, max(abs(r.score-v["score"]) for r,v in zip(ranks,old,strict=True)))
    assert trajectories == 53 and prior_queries >= 53 and prior_queries == exact_node_lists and max_error < 2e-6
    gpu = sqlite3.connect(h.inv.DB.as_uri()+"?mode=ro",uri=True,timeout=120)
    known = {k for k, in gpu.execute("select k from vectors where prec='ft'")}
    choices = [(k,v) for k,v in texts.items() if k in known]
    choices.sort(key=lambda a: hashlib.sha256(b"external-cpu-fp32-audit"+a[0]).digest())
    queries = [(k,t) for k,t in choices if t.startswith("query: ")][:8]
    short = [(k,t) for k,t in choices if t.startswith("passage: ") and len(t) < 300][:12]
    long = [(k,t) for k,t in choices if t.startswith("passage: ") and len(t) >= 1200][:12]
    selected = queries + short + long
    # All extra-dev query embeddings may be absent from the original GPU database.
    assert len(short)==len(long)==12 and len({k for k,_ in selected})==len(selected)
    import torch
    from graph_memory.embeddings import load_sentence_transformer
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    model = load_sentence_transformer(str(h.WD/"model"), device="cpu").eval()
    observed = model.encode([t for _,t in selected], batch_size=8, normalize_embeddings=True, show_progress_bar=False)
    reference = h.np.stack([h.np.frombuffer(gpu.execute("select v from vectors where k=? and prec='ft'",(k,)).fetchone()[0],dtype="<f4") for k,_ in selected])
    angles = h.np.sum(reference*observed,axis=1) / (h.np.linalg.norm(reference,axis=1)*h.np.linalg.norm(observed,axis=1))
    difference = h.np.abs(reference-observed)
    assert h.np.isfinite(observed).all() and float(angles.min())>.99999 and float(difference.max())<1e-4
    h.save(h.D/"rank-identity.json",{"shared_trajectories":trajectories,"native_reference":h.sha(source),"reference_model":h.sha(h.WD/"model/model.safetensors"),"old_queries":prior_queries,"exact_node_order":exact_node_lists,"total_ranked_units":nodes,"max_abs_score_error":max_error,"mixed_fp32_sample":{"sample_key_hashes":[k.hex() for k,_ in selected],"requested_queries":8,"available_queries":len(queries),"short_passages":len(short),"long_passages":len(long),"min_cosine":float(angles.min()),"max_abs_component_error":float(difference.max()),"mean_abs_component_error":float(difference.mean())},"code":h.sha(h.D/"rank_identity.py")})
    print('prior query lists identical',prior_queries,'max rank score difference',max_error,'FP32 sample',len(selected),flush=True)

if __name__=="__main__":
    main()

