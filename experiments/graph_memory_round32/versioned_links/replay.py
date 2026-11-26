"""Replay catalog-dependent reads at fixed serialized LRU capacity."""
from collections import Counter, OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import json
import sys
import zlib

ROOT = Path(__file__).resolve().parent
TRANSFER = ROOT.parent / "observed_transfer"
sys.path.insert(0, str(TRANSFER))
from transfer import SRC, Evidence, E5, Tokenizer, catalog, ranks, words, tie, get, put, sha, pq


def encode(obj):
    return zlib.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(), 6)


def decode(blob):
    return json.loads(zlib.decompress(blob))


@lru_cache(100000)
def hashed(gram):
    h = sha256(gram.encode()).digest()
    return (1 << (int.from_bytes(h[:2], "big") % 512)) | (1 << (int.from_bytes(h[2:4], "big") % 512))


@lru_cache(20000)
def signature(seq):
    return bloom(seq)


def bloom(seq):
    bits = 0
    for i, word in enumerate(seq):
        bits |= hashed(word)
        if i:
            bits |= hashed(seq[i-1] + " " + word)
    return bits


@lru_cache(180000)
def windows(text, phrase):
    if not phrase or sum(map(len, phrase)) < 3:
        return []
    n = len(phrase)
    return [sorted(set(text[max(0,i-12):i+n+12])) for i in range(len(text)-n+1) if text[i:i+n] == phrase]


@dataclass
class Question:
    qid: str
    title: str
    revision: str
    snippet: str
    tokens: int
    addresses: dict
    question_words: set
    idf: dict
    gold: int


def project():
    pred = get(TRANSFER / "predictions.json.gz")
    plan = get(TRANSFER / "plan.json")
    assert sha(SRC) == plan["source"]
    assert sha(TRANSFER/"predictions.json.gz") == get(TRANSFER/"seal.json")["predictions"]
    tok = Tokenizer.from_file(str(E5/"tokenizer.json"))
    output = []
    for batch in pq.ParquetFile(SRC).iter_batches(batch_size=256, columns=["_id","question","context"]):
        for item in batch.to_pylist():
            q = item["_id"]
            question = item["question"]
            context = json.loads(item["context"])
            previous = pred[q]
            order = previous["order"]; seed = previous["seed"]
            titles = [context[i][0] for i in order]
            terms, idf, scores = catalog(question,titles)
            prior = ranks(scores(question))
            assert seed == min(prior, key=prior.get)
            fulltext = " ".join(context[order[seed]][1])
            snip, cost = Evidence(order,[c[1] for c in context],tok).open(seed)
            assert cost == previous["tokens"]
            addresses = {j:(tuple(terms[j]),prior[j]) for j in range(len(order)) if j!=seed}
            query = {v for v in set(words(question)) - set(terms[seed]) if len(v)>2}
            output.append(Question(q,titles[seed],sha256(fulltext.encode()).hexdigest(),snip,cost,addresses,query,idf,previous["next"]["local_static"]))
    assert len(output) == len(pred) == 12576 and len({r.qid for r in output}) == len(output)
    return output


def select(q, records):
    def weight(w):
        return sum(q.idf.get(t,1.) for t in sorted(q.question_words.intersection(w)))
    def key(j):
        phrase, rank = q.addresses[j]
        entries = records.get(" ".join(phrase), [])
        return (not entries, -max(map(weight,entries),default=0), rank, j)
    return min(q.addresses,key=key)


@lru_cache(40000)
def lex(text):
    return tuple(words(text))


@lru_cache(40000)
def makeblob(mode,text):
    return encode(text if mode in ("raw","title_only") else lex(text))


@lru_cache(40000)
def parse(blob):
    loaded = decode(blob)
    return lex(loaded) if isinstance(loaded,str) else tuple(loaded)


def entries(q, tokens):
    return {" ".join(p):windows(tokens,p) for p,_ in q.addresses.values()}


def update(q, mode, blob):
    if mode in ("raw","normalized","title_only"):
        miss = blob is None
        if miss:
            blob = makeblob(mode,q.snippet)
        return select(q,entries(q,parse(blob))), blob, miss
    if blob:
        bits, known = decode(blob)
        bits = int(bits,16)
    else:
        bits, known = 0, {}
    phrases = set(p for p,_ in q.addresses.values())
    def possible(p):
        return bool(p) and sum(map(len,p))>=3 and (mode=="memo" or bits & signature(p)==signature(p))
    unknown = [p for p in phrases if " ".join(p) not in known and possible(p)]
    miss = blob is None or bool(unknown)
    if miss:
        tokens = lex(q.snippet)
        if not blob and mode=="bloom":
            bits = signature(tokens)
        for phrase in sorted(phrases):
            key = " ".join(phrase)
            if key not in known and possible(phrase):
                known[key] = windows(tokens,phrase)
        blob = encode((format(bits,"x"),known))
    return select(q,known), blob, miss


class Cache:
    def __init__(self, budget):
        self.budget = budget
        self.data = OrderedDict()
        self.size = 0
        self.peak = 0
        self.writes = 0

    def store(self,key,blob):
        cost = len(key)+len(blob)
        original = self.data.pop(key,None)
        if original is not None:
            self.size -= len(key)+len(original)
        if cost > self.budget:
            return
        while self.data and self.size + cost > self.budget:
            old, value = self.data.popitem(last=False)
            self.size -= len(old)+len(value)
        self.data[key] = blob
        self.size += cost
        self.peak = max(self.peak,self.size)
        if original != blob:
            self.writes += cost


def run(rows,order,mode,kib):
    budget = kib*1024 if kib else 10**12
    cache = Cache(budget); trace=[]; errors=0
    for i in order:
        row = rows[i]
        # Fixed-length title digest; full revision digest follows it in version-aware arms.
        key = tie(row.title)
        if mode != "title_only":
            key += bytes.fromhex(row.revision)
        answer, new, miss = update(row, mode, cache.data.get(key))
        errors += answer != row.gold
        assert mode=="title_only" or answer==row.gold,(row.qid,mode,kib)
        cache.store(key,new)
        trace.append((i,int(miss),answer))
    return trace,{"reads":sum(miss for _,miss,_ in trace),"wordpieces":sum(rows[i].tokens*miss for i,miss,_ in trace),
                  "ending_bytes":cache.size,"peak_bytes":cache.peak,"write_bytes":cache.writes,"errors":errors}


def main():
    plan={"protocol":sha(ROOT/"PROTOCOL_RU.md"),"program":sha(Path(__file__)),"input":sha(TRANSFER/"predictions.json.gz"),
          "source":sha(SRC),"order":"parquet physical rows and sha256(id)","budgets_KiB":[64,256,1024,4096,0],"bloom_bits":512}
    put(ROOT/"plan.json",plan)
    rows=project()
    meta=[[q.qid,tie(q.title).hex(),q.revision,q.tokens,q.gold] for q in rows]
    put(ROOT/"events.json.gz",meta)
    tables={}; seen_versions={}; catalog_changes=0; repeat=0; revisions=0
    for r in rows:
        key=(r.title,r.revision); addr=frozenset(p for p,_ in r.addresses.values())
        if key in seen_versions:
            repeat+=1;catalog_changes+=int(addr!=seen_versions[key])
        seen_versions[key]=addr
    prior={}
    for r in rows:
        if r.title in prior and r.revision!=prior[r.title]:revisions+=1
        prior[r.title]=r.revision
    for label,order in [("file",list(range(len(rows)))),("hash",sorted(range(len(rows)),key=lambda i:tie(rows[i].qid)))]:
        output={}
        for mode in ("raw","normalized","memo","bloom","title_only"):
            output[mode]={}
            for k in plan["budgets_KiB"]:
                trace, stats=run(rows,order,mode,k)
                output[mode][str(k)]=stats
                # Store reads and second-document selections in the published sequence.
                put(ROOT/f"{label}-{mode}-{k}.json.gz",[[m,a] for _,m,a in trace])
        tables[label]=output
        print(label,output["raw"]["256"],output["bloom"]["256"],flush=True)
    put(ROOT/"results.json",{"n":len(rows),"distinct_titles":len(prior),"distinct_keys":len(seen_versions),"same_key_repeats":repeat,
            "changed_catalog_on_repeat":catalog_changes,"title_revision_transitions":revisions,"arms":tables})
if __name__=="__main__":
    main()
