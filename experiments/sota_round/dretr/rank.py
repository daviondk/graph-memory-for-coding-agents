"""Frozen, label-blind session rankers for LongMemEval-S."""
import argparse
import ast
import functools
import hashlib
import json
import re
import time
from pathlib import Path

import numpy as np
import snowballstemmer
from rank_bm25 import BM25Okapi


HERE = Path(__file__).resolve().parent
DATA_SHA = "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"
WORDS = re.compile(r"[^\W_]+", re.UNICODE)
STEMMER = snowballstemmer.stemmer("english")


def upstream_symbol(name, env):
    # Load a single, verbatim definition to avoid importing unrelated OpenAI/vLLM
    # dependencies from the authors' combined GPU and lexical command-line runner.
    path = HERE / "upstream" / "run_retrieval.py"
    tree = ast.parse(path.read_text("utf-8"))
    symbol = next(node for node in tree.body if getattr(node, "name", None) == name)
    namespace = env.copy()
    exec(compile(ast.Module([symbol], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


BASELINE = upstream_symbol("DenseRetrievalMaster", dict(np=np, BM25Okapi=BM25Okapi))


@functools.lru_cache(maxsize=100_000)
def stem(word):
    return STEMMER.stemWord(word)


def tokenize(text):
    return [stem(word) for word in WORDS.findall(text.casefold())]


def vector_key(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Embeddings:
    def __init__(self, directory):
        self.lookup = {}
        self.matrices = []
        for i, tag in enumerate(("session", "extra-turn")):
            info = json.loads((directory / f"vectors-{tag}.json").read_text("utf-8"))
            matrix = np.load(directory / f"vectors-{tag}.npy", mmap_mode="r")
            assert matrix.shape == (len(info["keys"]), 768)
            self.matrices.append(matrix)
            self.lookup.update((k, (i, j)) for j, k in enumerate(info["keys"]))

    def get(self, text):
        i, j = self.lookup[vector_key(text)]
        return self.matrices[i][j]

    def scores(self, texts, query):
        return np.stack([self.get(text) for text in texts]) @ query


def order(scores):
    return np.argsort(-np.asarray(scores), kind="stable")


def ranks(permutation):
    result = np.empty(len(permutation), dtype=int)
    result[permutation] = np.arange(1, len(permutation) + 1)
    return result


def rerank(coarse, evidence_scores):
    size = len(evidence_scores)
    evidence_ranks = ranks(order(evidence_scores))
    scores = 1 / (10 + np.arange(1, size + 1)) + 0.8 / (10 + evidence_ranks)
    return np.r_[coarse[:size][order(scores)], coarse[size:]]


def rank(question, sessions, embeddings):
    contents = [" ".join(session) for session in sessions]
    flat_turns = [turn for session in sessions for turn in session]
    tokens = [tokenize(turn) for turn in flat_turns]
    offsets = np.cumsum([0] + [len(s) for s in sessions])
    session_tokens = [sum(tokens[a:b], []) for a, b in zip(offsets, offsets[1:])]
    query_tokens = tokenize(question)
    bm25 = BASELINE.run_flat_retrieval(None, question, "flat-bm25", contents)
    normalized = order(BM25Okapi(session_tokens).get_scores(query_tokens))
    query_vector = embeddings.get(question)
    dense = order(embeddings.scores(contents, query_vector))
    coarse = order(1 / (10 + ranks(normalized)) + 1 / (10 + ranks(dense)))
    shortlisted = coarse[:12]

    turn_index = BM25Okapi(tokens)
    # One single-term contribution vector per unique query token. Query repetitions
    # remain repeated in the sum, as in rank_bm25's get_scores.
    contributions = {term: turn_index.get_scores([term]) for term in dict.fromkeys(query_tokens)}
    lexical_scores = sum((contributions[term] for term in query_tokens), np.zeros(len(tokens)))

    shared_choices = []
    position_choices = []
    for sid in shortlisted:
        first, stop = offsets[sid:sid + 2]
        if first == stop:
            shared_choices.append([])
            position_choices.append([])
            continue
        strongest = int(first + np.argmax(lexical_scores[first:stop]))
        chosen = [strongest]
        if stop - first > 1:
            covered = set(tokens[strongest])
            residual = lexical_scores[first:stop].copy()
            for term in query_tokens:
                if term in covered:
                    residual -= 0.5 * contributions[term][first:stop]
            residual[strongest - first] = -np.inf
            chosen.append(int(first + np.argmax(residual)))
        shared_choices.append(chosen)
        position_choices.append(sorted(set([first, stop - 1])))

    # Each bounded arm reads only its chosen vectors. The exhaustive control is
    # computed separately, with no signal flowing back into either bounded arm.
    def probe(choices):
        return [max(embeddings.scores([flat_turns[i] for i in indices], query_vector),
                    default=-np.inf) if indices else -np.inf for indices in choices]

    witness = rerank(coarse, probe(shared_choices))
    position = rerank(coarse, probe(position_choices))
    all_turn_scores = embeddings.scores(flat_turns, query_vector)
    all_session_max = np.array([max(all_turn_scores[a:b], default=-np.inf)
                                for a, b in zip(offsets, offsets[1:])])
    results = dict(bm25_official=bm25, bm25_normalized=normalized, contriever_session=dense,
                   flat_fusion=coarse, witness=witness, position_control=position,
                   contriever_turn_max=order(all_session_max),
                   exhaustive_rerank=rerank(coarse, all_session_max[shortlisted]))
    costs = dict(sessions=len(sessions), user_turns=len(tokens), candidates=len(shortlisted),
                 witness_probes=sum(map(len, shared_choices)), candidate_turns=sum(len(sessions[i]) for i in shortlisted))
    return {k: v.tolist() for k, v in results.items()}, costs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cache", type=Path)
    parser.add_argument("--out", type=Path, default=HERE / "ranks.jsonl")
    args = parser.parse_args()
    dataset = args.cache / "longmemeval_s_cleaned.json"
    assert hashlib.file_digest(dataset.open("rb"), "sha256").hexdigest() == DATA_SHA
    records = json.loads(dataset.read_text("utf-8"))
    rows = [(r["question"], [[t["content"] for t in s if t["role"] == "user"]
                            for s in r["haystack_sessions"]]) for r in records]
    del records
    embeddings = Embeddings(args.cache)
    start = time.perf_counter()
    with args.out.open("w", encoding="utf-8") as f:
        for i, (question, sessions) in enumerate(rows):
            ranking, costs = rank(question, sessions, embeddings)
            for value in ranking.values():
                assert sorted(value) == list(range(len(sessions)))
            f.write(json.dumps(dict(row=i, query_sha256=vector_key(question), ranks=ranking,
                                    costs=costs), separators=(",", ":")) + "\n")
            if i % 100 == 0:
                print(i, f"{time.perf_counter() - start:.1f} seconds", flush=True)
    print(f"{len(rows)} queries ranked in {time.perf_counter() - start:.2f} seconds", flush=True)


if __name__ == "__main__":
    main()
