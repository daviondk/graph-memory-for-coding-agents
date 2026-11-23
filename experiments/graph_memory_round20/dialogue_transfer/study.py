"""Query-blind LRE transfer at turn granularity. CPU only. Exports text-free coordinates."""
import collections
import gzip
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import unicodedata
from pathlib import Path
from types import SimpleNamespace

for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[k] = "1"
import numpy as np
import scipy
import sklearn
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent
REF = Path(os.environ.get("LRE_REPO", "D:/CodexResearch/x20-lre-reference"))
LO = Path(os.environ.get("LOCOMO_FILE", str(REF / "data/reference-locomo10.json")))
TARGET = Path(os.environ.get("LONGMEMEVAL_FILE", "D:/CodexResearch/x20-longmemeval-dretr/longmemeval_s_cleaned.json"))
PREV = Path(os.environ.get("R19_EDGE_STUDY", str(ROOT.parent.parent / "graph_memory_round19/locomo_edges/study.py")))
REV = "1aa51d672d772b27a272cab1393cd9968c13d158"
TARGET_SHA = "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"
LO_SHA = "79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4"
PROTOCOL = "95fbf1a99ad55f53efa28277c44a8dd499853487d1b16d34f6e7338837a473bb"
ARMS = ("original", "edge", "shifted")
sys.path.insert(0, str(REF))
from experiments.conversational_qa import dataset as ds, lre_qa as native
spec = importlib.util.spec_from_file_location("prior_edge_protocol", PREV)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
BASE_KEYS = list(native.TRAJ_KEYS)

def hashbytes(x):
    return hashlib.sha256(x).hexdigest()

def digest(s):
    return hashbytes(s.encode("utf8"))

def sha(p):
    with open(p, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def norm(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())

def sig(turns):
    return digest(json.dumps([(r, norm(t)) for r, t in turns], separators=(",", ":"), ensure_ascii=False))

def save(name, obj):
    path = ROOT / name
    if name.endswith(".gz"):
        payload = gzip.compress(json.dumps(obj, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode(), compresslevel=5, mtime=0)
    else:
        payload = (json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf8")
    if path.exists():
        assert path.read_bytes() == payload, "Attempt to overwrite divergent " + name
    else:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(payload)
        tmp.replace(path)

class Components:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        self.p[max(a, b)] = min(a, b)

class Corpus:
    def __init__(self, data):
        self.qkeys, self.hist, self.idsets, self.sess, self.raw_ids = [], [], [], {}, collections.defaultdict(set)
        self.qraw = {}
        for q in data:
            qh = digest(q["question_id"])
            assert qh not in self.qraw
            self.qraw[qh] = q
            h, keyset = [], set()
            for rid, turns in zip(q["haystack_session_ids"], q["haystack_sessions"], strict=True):
                pairs = tuple((x["role"], x["content"]) for x in turns)
                k = sig(pairs)
                self.sess.setdefault(k, pairs)
                h.append(k)
                tag = "i" + digest(rid)
                self.raw_ids[k].add(tag)
                keyset.update((tag, "c" + k))
            self.qkeys.append(qh)
            self.hist.append(h)
            self.idsets.append(keyset)
        self.edges = {k: edge_arrays(pairs) for k, pairs in self.sess.items()}

    def gold(self, qh):
        return [[int(turn.get("has_answer") is True) for turn in s] for s in self.qraw[qh]["haystack_sessions"]]

def edge_arrays(pairs):
    ts = [SimpleNamespace(text=t, speaker=r) for r, t in pairs]
    prevs = ts[:-1]
    return np.array([[prior.edge(t, prevs[i-1] if i else None),
                      prior.edge(t, prevs[(i-1 + len(prevs)//2) % len(prevs)] if i else None)]
                     for i, t in enumerate(ts)], dtype=float).reshape(len(ts), 2, 7)

def lo_training(target_norm):
    rows, _ = ds.load_groups("locomo", locomo_path=str(LO))
    groups = ds.conv_groups(ds.load_locomo(str(LO)))
    lookup, sessions = {}, set()
    for cid, members in groups.items():
        bysession = collections.defaultdict(list)
        for t in members[0].turns:
            bysession[t.session_num].append(t)
        for ts in bysession.values():
            pairs = [(t.speaker, t.text) for t in ts]
            sessions.add(sig(pairs))
            for i, (t, arr) in enumerate(zip(ts, edge_arrays(pairs), strict=True)):
                lookup[(str(cid), t.dia_id)] = arr
    keep = [r for r in rows if norm(r.text) not in target_norm]
    e = np.stack([lookup[r.group, r.key] for r in keep])
    return keep, e, len(rows) - len(keep), sessions, len(groups)

def numeric(rows):
    return np.array([[r.traj[k] for k in BASE_KEYS] for r in rows], dtype=float)

def features(base, e, arm):
    if arm == "original":
        return base
    return np.hstack((base, e[:, 0 if arm == "edge" else 1]))

def fitted(rows, e):
    vec = TfidfVectorizer(stop_words="english", min_df=1, max_features=10000)
    xt = vec.fit_transform([r.text for r in rows])
    base = numeric(rows)
    models = {}
    for arm in ARMS:
        a = features(base, e, arm)
        sc = StandardScaler().fit(a)
        x = hstack([xt, csr_matrix(sc.transform(a))]).tocsr()
        model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=0)
        model.fit(x, [r.label for r in rows])
        models[arm] = (sc, model)
    return vec, models

def external_predictions(c, rows, e):
    vec, models = fitted(rows, e)
    # TF-IDF and static feature contributions are identical for repeated text.
    # Cache sparse TF-IDF matrices per distinct source session, never vocabulary fitted on target.
    xtext = {k: vec.transform([t for _, t in pairs]) for k, pairs in c.sess.items() if pairs}
    static = {k: np.array([[ds._traj_features(t, 0, 1, {})[z] for z in BASE_KEYS[2:]]
                            for _,t in pairs], dtype=float) for k,pairs in c.sess.items()}
    from scipy.sparse import vstack
    out = []
    for qh, seq in zip(c.qkeys, c.hist, strict=True):
        seq = [k for k in seq if c.sess[k]]
        n = sum(len(c.sess[k]) for k in seq)
        idx = np.arange(n, dtype=float)
        base = np.column_stack((idx / n, 1.0 / (n-idx), np.vstack([static[k] for k in seq])))
        ed = np.concatenate([c.edges[k] for k in seq])
        xt = vstack([xtext[k] for k in seq], format="csr")
        scores = {}
        for arm, (sc, model) in models.items():
            a = features(base, ed, arm)
            x = hstack([xt, csr_matrix(sc.transform(a))]).tocsr()
            scores[arm] = model.predict_proba(x)[:,1].tolist()
        out.append(dict(id=qh, scores=scores))
    # Parity of external estimator with authors' independently called scorer,
    # tested on mixed target turns with synthetic labels that have no effect on held predictions.
    probe_sess = next(k for k in c.hist[0] if len(c.sess[k]) > 1)
    target_rows = [ds.Row(t, i % 2, "check", str(i), ds._traj_features(t, i, len(c.sess[probe_sess]), {}))
                   for i, (_,t) in enumerate(c.sess[probe_sess])]
    delta = {}
    for arm, (sc, model) in models.items():
        keys = BASE_KEYS if arm == "original" else BASE_KEYS + list(prior.EXTRA)
        native.TRAJ_KEYS = keys
        joint = []
        for group, rs, es in [("train", rows, e), ("check", target_rows, c.edges[probe_sess])]:
            for r, num in zip(rs, features(numeric(rs), es, arm), strict=True):
                joint.append(ds.Row(r.text, r.label, group, r.key, dict(zip(keys, num, strict=True))))
        preds, _ = native.lre_scores(joint, fuse=True, dedup=False)
        a = features(numeric(target_rows), c.edges[probe_sess], arm)
        x = hstack([xtext[probe_sess], csr_matrix(sc.transform(a))]).tocsr()
        delta[arm] = float(max(abs(model.predict_proba(x)[:,1]-preds[-len(target_rows):])))
        assert delta[arm] < 1e-12, delta
    native.TRAJ_KEYS = BASE_KEYS
    return out, delta

def panel(c):
    comp, owner = Components(), {}
    chosen, used = [], set()
    for qh, ids in sorted(zip(c.qkeys, c.idsets, strict=True)):
        comp.find(qh)
        for i in ids:
            if i in owner:
                comp.union(qh, owner[i])
            else:
                owner[i] = qh
        if not ids & used:
            chosen.append(qh)
            used |= ids
    return chosen, {q:comp.find(q) for q in c.qkeys}

def domain(c):
    # Native has_answer masks may differ across questions on an identical source.
    gold = {k:np.zeros(len(p), dtype=np.int8) for k,p in c.sess.items()}
    families = []
    for qh, hist in zip(c.qkeys, c.hist, strict=True):
        positive_sessions = []
        for k, ys in zip(hist, c.gold(qh), strict=True):
            gold[k] |= ys
            if any(ys):
                positive_sessions.append(k)
        families.append(positive_sessions)
    keys = sorted(k for k, y in gold.items() if 0 < y.sum() < len(y))
    cset = set(keys)
    comp, owner = Components(), {}
    for k in keys:
        comp.find(k)
        for i in c.raw_ids[k]:
            if i in owner:
                comp.union(k, owner[i])
            else:
                owner[i] = k
    for arr in families:
        valid = [k for k in arr if k in cset]
        for k in valid[1:]:
            comp.union(k, valid[0])
    domain_rows, all_ed, group_ids, spans, labels = [], [], {}, {}, {}
    for k in keys:
        p = c.sess[k]
        group_ids[k] = comp.find(k)
        rows = [ds.Row(t, int(y), group_ids[k], str(i), ds._traj_features(t, i, len(p), {}))
                for i, ((_,t), y) in enumerate(zip(p, gold[k], strict=True))]
        i = len(domain_rows)
        domain_rows.extend(rows)
        spans[k] = slice(i, i+len(p))
        labels[k] = gold[k].tolist()
        all_ed.append(c.edges[k])
    ec = len(set(group_ids.values()))
    if ec < 2:
        return [], {}, {}, {"n_components":ec, "conditional_sessions":len(keys)}
    x = np.concatenate(all_ed)
    base = numeric(domain_rows)
    pred, removed = {}, {}
    gs = np.array([r.group for r in domain_rows])
    folds = {}
    for fold, (_,te) in enumerate(GroupKFold(n_splits=min(5,ec)).split(base, groups=gs)):
        for g in set(gs[te]):
            assert g not in folds
            folds[g] = fold
    for arm in ARMS:
        keys_in = BASE_KEYS if arm == "original" else BASE_KEYS + list(prior.EXTRA)
        native.TRAJ_KEYS = keys_in
        tab = [ds.Row(r.text, r.label, r.group, r.key, dict(zip(keys_in, a, strict=True)))
               for r,a in zip(domain_rows, features(base,x,arm),strict=True)]
        pred[arm], removed[arm] = native.lre_scores(tab, fuse=True, dedup=True, cv_splits=5)
    native.TRAJ_KEYS = BASE_KEYS
    assert len(set(removed.values())) == 1
    predictions = [dict(id=k, scores={a:pred[a][spans[k]].tolist() for a in ARMS}) for k in keys]
    return predictions, labels, group_ids, dict(conditional_sessions=len(keys), turns=len(domain_rows),
          positives=sum(map(sum,labels.values())), n_components=ec, removed=removed, fold_of_component=folds)

def main():
    assert sha(TARGET)==TARGET_SHA and sha(LO)==LO_SHA and sha(ROOT/"PROTOCOL_RU.md")==PROTOCOL
    assert subprocess.check_output(["git","-C",str(REF),"rev-parse","HEAD"],text=True).strip()==REV
    lock = dict(protocol=PROTOCOL, dataset=TARGET_SHA, locomo=LO_SHA, LRE_revision=REV, study=sha(Path(__file__)),
                earlier_edge=sha(PREV), lre_dataset=sha(REF/"experiments/conversational_qa/dataset.py"),
                lre_classifier=sha(REF/"experiments/conversational_qa/lre_qa.py"), sklearn=sklearn.__version__,
                scipy=scipy.__version__, numpy=np.__version__, python=sys.version)
    save("input-lock.json",lock)
    c = Corpus(json.loads(TARGET.read_bytes()))
    target_norm = {norm(t) for pairs in c.sess.values() for _,t in pairs}
    train, e, removed, lo_sessions, n_groups = lo_training(target_norm)
    chosen, cg = panel(c)
    coordinates = dict(histories=dict(zip(c.qkeys,c.hist,strict=True)), selected=chosen,
                components=cg, size={k:len(p) for k,p in c.sess.items()}, aliases={k:sorted(v) for k,v in c.raw_ids.items()})
    save("split.json.gz", coordinates)
    print("panels",len(c.qkeys),len(c.sess),len(chosen),len(set(cg.values())), "train rows",len(train),"removed",removed,flush=True)
    out, delta = external_predictions(c, train, e)
    save("external-forecast.json.gz",out)
    save("external-forecast-lock.json",dict(predictions=sha(ROOT/"external-forecast.json.gz"),
        split=sha(ROOT/"split.json.gz"), input=sha(ROOT/"input-lock.json"), native_parity_max_abs=delta))
    gold = {q:[y for s in c.gold(q) for y in s] for q in c.qkeys}
    save("external-gold.json.gz",gold)
    print("frozen external predictions",len(out),flush=True)
    learned, y, gc, dinfo = domain(c)
    save("domain-forecast.json.gz",learned)
    save("domain-forecast-lock.json",dict(predictions=sha(ROOT/"domain-forecast.json.gz"), input=sha(ROOT/"input-lock.json")))
    save("domain-gold.json.gz",y)
    save("domain-groups.json",gc)
    qc = collections.Counter(cg.values())
    meta = dict(source_dialogues=n_groups, train_turns=len(train), train_gold=sum(r.label for r in train), removed_train=removed,
                source_sessions=len(lo_sessions), cross_corpus_same_session=len(lo_sessions & set(c.sess)),
                target_unique_session=len(c.sess), target_session_occurrences=sum(map(len,c.hist)), target_turns=sum(map(len,gold.values())),
                total_positive=sum(map(sum,gold.values())), no_gold=sum(not any(a) for a in gold.values()), target_histories=len(c.qkeys),
                target_strict=len(chosen), components=sorted(qc.values(),reverse=True), within=dinfo)
    save("design-actual.json",meta)
    print("completed",len(learned),dinfo["n_components"],flush=True)

if __name__ == "__main__":
    main()
