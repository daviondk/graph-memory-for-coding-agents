from collections import Counter
from common_run import D, R, cases, hashfile, now, save, writegz
import pyarrow.parquet as pq

paths = [R / n for n in ("paired_roster.json", "strict_roster.json", "repo_author_retriever.py", "repo_author_run_repobench_r.py", "repo_author_similarity.py", "repo_author_archive_utils.py", "strict_binary.py")]
paths += [D / n for n in ("PROTOCOL_RU.md", "repo_unixcoder.py", "common_run.py", "prepare.py", "infer.py")]
paths += sorted((D/"weights").glob("*"))
frozen = {"utc":now(), "files":{p.relative_to(D.parent).as_posix():hashfile(p) for p in paths}}
assert frozen["files"]["encoder/weights/pytorch_model.bin"] == "6732b60037b086557e4c731c3748c99b4fec735d9ffe3c4c70061fd142e6b9d9"
save("method_lock.json", frozen)
packets = []
different = Counter()
hashes = {}
for path, panel, mapping in cases():
    hashes[path.name] = hashfile(path)
    offset = 0
    for batch in pq.ParquetFile(path).iter_batches(columns=["repo_name","code","context"], batch_size=128):
        for ix in sorted(i for i in mapping if offset <= i < offset + len(batch)):
            row = batch.slice(ix - offset, 1).to_pylist()[0]
            queries = {}
            for n in [3, 10]:
                q = "\n".join(row["code"].splitlines()[-n:])
                alt = "\n".join(row["code"].split("\n")[-n:])
                queries[str(n)] = q
                different[str(n)] += int(q != alt)
                if q != alt:
                    queries[str(n)+"a"] = alt
            packets.append(dict(panel=panel, idx=mapping[ix], project=row["repo_name"], queries=queries, candidates=row["context"]))
        offset += len(batch)
assert len(packets) == len({(p["panel"],p["idx"]) for p in packets}) == 320
counts = dict(Counter(p["panel"] for p in packets))
assert list(counts.values()).count(80) == 4
writegz(D/"blind.jsonl.gz", packets)
texts = {s for p in packets for s in [*p["queries"].values(),*p["candidates"]]}
receipt = {"utc":now(),"counts":counts,"projects":len({p["project"] for p in packets}),"candidate_slots":sum(len(p["candidates"]) for p in packets),"unique_texts":len(texts),"different_author_crop":dict(different),"inputs":hashes,"blind_sha":hashfile(D/"blind.jsonl.gz")}
save("inputs_receipt.json",receipt)
print(receipt, flush=True)

