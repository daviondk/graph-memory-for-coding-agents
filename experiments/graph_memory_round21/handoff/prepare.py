"""Build private packets and held-out evaluator labels from the pinned public corpus."""
import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / 'protocol.json').read_text(encoding='utf8'))
CACHE = Path('D:/CodexResearch/x20-wikicontradict')
MODEL = Path('D:/CodexResearch/x20-isetrace-runtime/e5-base-v2')
MODEL_HASH = 'd0d559c47d5f71b1d280b13b62a2657f3e3bc70c0786f9ab91a36545e6a8f693'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')


def cid(s):
    return sha(s.encode())[:16]


def words(s):
    return re.findall(r"[^\W_]+", s.lower(), flags=re.UNICODE)


def encode(texts, model_dir, cache):
    import torch
    from transformers import AutoModel, AutoTokenizer
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    assert sha((model_dir/'model.safetensors').read_bytes()) == MODEL_HASH
    tok = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    model = AutoModel.from_pretrained(model_dir, local_files_only=True).cpu().eval()
    vectors = []
    with torch.inference_mode():
        for start in range(0, len(texts), 8):
            items = texts[start:start+8]
            inputs = tok(items, truncation=True, max_length=512, padding=True, return_tensors='pt')
            features = model(**inputs).last_hidden_state
            mask = inputs['attention_mask'].unsqueeze(-1)
            mean = (features * mask).sum(1) / mask.sum(1)
            vectors.extend(torch.nn.functional.normalize(mean, p=2, dim=1).numpy())
    arr = np.array(vectors, dtype=np.float32)
    np.save(cache, arr)
    return arr


def prepare(cache, model):
    cache.mkdir(parents=True, exist_ok=True)
    src = cache / 'wiki.csv'
    url = f"https://huggingface.co/datasets/ibm-research/Wikipedia_contradict_benchmark/resolve/{CONFIG['revision']}/{CONFIG['corpus']}"
    if not src.exists():
        urlretrieve(url, src)
    assert sha(src.read_bytes()) == CONFIG['sha256']
    with src.open(encoding='utf-8-sig', newline='') as f:
        records = list(csv.DictReader(f))
    assert len(records) == len({r['question_ID'] for r in records}) == 253
    texts, owners = {}, defaultdict(set)
    for r in records:
        for k in ('context1', 'context2'):
            s = r[k].strip()
            h = cid(s)
            assert texts.setdefault(h, s) == s
            owners[h].add(r['WikipediaArticleTitle'].strip().casefold())
    hashes = sorted(texts)
    sentences = ['passage: ' + texts[h] for h in hashes] + ['query: ' + r['question'].strip() for r in records]
    fingerprint = sha(json.dumps([MODEL_HASH,sentences], ensure_ascii=False).encode())
    vec_file = cache / (fingerprint + '.npy')
    embeddings = np.load(vec_file) if vec_file.exists() else encode(sentences, model, vec_file)
    assert embeddings.shape == (len(sentences), 768) and np.isfinite(embeddings).all()
    pvec = embeddings[:len(hashes)]
    cosine = embeddings[len(hashes):] @ pvec.T
    projection = np.random.default_rng(2107).standard_normal((768,128)).astype(np.float32)
    sketches = np.packbits((pvec - pvec.mean(axis=0)) @ projection > 0, axis=1)
    bows = [Counter(words(texts[h])) for h in hashes]
    df = Counter(w for row in bows for w in row)
    lens = np.array([sum(row.values()) for row in bows])
    scale = 1.2*(.25+.75*lens/lens.mean())
    packets, labels = [], []
    for i, r in enumerate(records):
        q = r['question_ID']
        truth = [cid(r[k].strip()) for k in ('context1','context2')]
        article = r['WikipediaArticleTitle'].strip().casefold()
        valid = [j for j,h in enumerate(hashes) if h not in truth and article not in owners[h]]
        terms = set(words(r['question']))
        lex = np.array([sum(math.log1p((len(hashes)-df[t]+.5)/(df[t]+.5)) * 2.2*bows[j][t]/(bows[j][t]+scale[j]) for t in sorted(terms) if t in bows[j]) for j in range(len(hashes))])
        ranks = [sorted(valid,key=lambda j:(-v[j],hashes[j])) for v in (lex,cosine[i])]
        distractors = []
        for pair in zip(*ranks):
            for j in pair:
                if hashes[j] not in distractors:
                    distractors.append(hashes[j])
                if len(distractors) == 10:
                    break
            if len(distractors) == 10:
                break
        distractors.sort(key=lambda h: cid(f'partition:{q}:{h}'))
        workers = []
        for k, gold in enumerate(truth):
            cand = distractors[k*5:(k+1)*5]+[gold]
            cand.sort(key=lambda h: cid(f'slot:{q}:{k}:{h}'))
            worker = []
            for h in cand:
                j = hashes.index(h)
                worker.append(dict(id=h, text=texts[h], cos=int(np.clip(np.rint(cosine[i,j]*32767),-32768,32767)), bm=float(lex[j]), sketch=sketches[j].tobytes().hex()))
            workers.append(worker)
        packets.append(dict(case=q, workers=workers))
        labels.append(dict(case=q, gold=truth, article=cid(article), different=r['samepassage'].strip()=='Different', explicit=r['contradictType'].strip()=='Explicit'))
    dump(cache/'packets.json',packets)
    dump(cache/'gold.json',labels)
    dump(ROOT/'input-lock.json',dict(corpus=CONFIG['sha256'], source_rows=len(records), unique_texts=len(hashes), model_sha=MODEL_HASH, model_revision='f52bf8ec8c7124536f0efb74aca902b2995e5bcd', torch_device='cpu', projection_seed=2107, embeddings_array_sha256=sha(embeddings.tobytes()), packets_sha=sha((cache/'packets.json').read_bytes()), evaluator_sha=sha((cache/'gold.json').read_bytes()), dependencies={n:__import__('importlib.metadata',fromlist=['version']).version(n) for n in ('numpy','torch','transformers','tokenizers')}))


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--cache', type=Path,default=CACHE)
    p.add_argument('--model', type=Path,default=MODEL)
    args=p.parse_args()
    prepare(args.cache,args.model)

