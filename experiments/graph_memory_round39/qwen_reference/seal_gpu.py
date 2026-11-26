"""Verify already completed per-state receipts, including the low-verbosity server log, before opening labels."""
from gpu_reference import *


def main():
    cache=CACHE/"runs-r39-gpu-v1"
    panel=read(ROOT/"panel.json")["states"]
    expected={p:sha(ROOT/p) for p in ("panel.json","reference.py","gpu_reference.py","BACKENDS_RU.md","PROTOCOL_RU.md")}
    expected.update(model=DIGEST,runtime=sha(EXE))
    assert sha(CACHE/NAME)==DIGEST
    original=read(R34/"features.json.gz")
    results={}
    receipts={}
    for q in sorted(panel,key=lambda k:panel[k]["position"]):
        f=cache/(hashlib.sha256(q.encode()).hexdigest()+".json")
        row=read(f)
        assert row["sign"]==expected and row["state_id"]==q
        v=row["data"]
        assert set(v["scores"])==set(original[q]["ids"])
        assert len(v["lengths"])==len(v["scores"])+1 and v["seconds"]>0
        assert all(np.isfinite(s) and abs(s)<=1.0001 for s in v["scores"].values())
        for seq in v["ranks"].values():
            assert len(seq)==len(set(seq))==8 and set(seq)<=set(v["scores"])
        results[q]=v
        receipts[q]=sha(f)
    assert len(results)==10
    txt=(cache/"server.log").read_text(encoding="utf8",errors="replace")
    assert "model loaded" in txt and "n_slots = 4" in txt and NAME in txt
    savepath=ROOT/"gpu-qwen-reference.json"
    write(savepath.name,results)
    write("gpu-forecast-seal.json",dict(inputs=expected,reference=sha(savepath),
         hardware="NVIDIA GeForce RTX 3090, llama.cpp GPU layers requested = 99, CUDA_VISIBLE_DEVICES = 0",
         receipts=receipts,server_log=sha(cache/"server.log"),seal_program=sha(Path(__file__)),
         telemetry={"progress_states_at_snapshot":6,"measured_gpu_load_pct":96,"measured_global_vram_MiB":8629,
                    "temperature_celsius":79,"shared_mutex":"Local\\CodexResearchGraphMemoryFiveSeed"},
         note="Default server logging omitted the per-layer offload line, so GPU dispatch is established from launch args and concurrent hardware telemetry, not a verified layer count."))
    print("Sealed",len(receipts),"independent per-state token/score receipts before grading.")

if __name__=="__main__":
    main()
