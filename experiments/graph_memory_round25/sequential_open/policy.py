"""Pure scheduling functions. Only the visible fragments and field lengths are inputs."""
from collections import Counter, defaultdict
from functools import lru_cache
import math
import re

WORDS = re.compile(r"[^\W_]+", re.UNICODE)

def terms(text):
    return Counter(WORDS.findall(text.casefold()))

def lexical_features(tokenizer):
    @lru_cache(maxsize=384)
    def features(text):
        offsets = tokenizer.encode(text, add_special_tokens=False).offsets
        chunks = []
        for start in range(0, len(offsets), 128):
            left = offsets[start][0] if start else 0
            right = offsets[start + 128][0] if start + 128 < len(offsets) else len(text)
            chunks.append((left, terms(text[left:right])))
        if not chunks:
            chunks.append((0, terms(text)))
        tail = offsets[-128][0] if len(offsets) > 128 else 0
        return chunks, terms(text[tail:])
    return features

def rank(wanted, state, features):
    windows = []
    tails = []
    freq = Counter()
    field_lengths = []
    for index, (field, left, text) in enumerate(state):
        blocks, tail = features(text)
        tails.append(tail)
        for offset, bag in blocks:
            windows.append((index, field, left + offset, bag))
            field_lengths.append(sum(bag.values()))
            freq.update(wanted & bag.keys())
    n = len(windows)
    mean_length = sum(field_lengths) / n or 1
    weights = {w: math.log1p((n - df + .5)/(df + .5)) for w,df in freq.items()}
    def score(bag):
        norm = 1.2 * (.25 + .75 * sum(bag.values()) / mean_length)
        return sum(weights[w] * bag[w] * 2.2 / (bag[w] + norm)
                   for w in sorted(weights.keys() & bag.keys()))
    windows.sort(key=lambda w: -score(w[3]))
    return [(i,e,pos) for i,e,pos,_ in windows], sorted(range(len(tails)),key=lambda i: -score(tails[i]))

def choose(method, state, lengths, calls, wanted, frozen, features):
    eligible = {i for i,(e,l,text) in enumerate(state) if l + len(text) < lengths[e]}
    if not eligible:
        return None
    if method == "first":
        idx = min(eligible)
    elif method == "frozen":
        idx = next(i for field,offset in frozen for i,(e,l,text) in enumerate(state)
                   if i in eligible and e == field and l <= offset < l + len(text))
    else:
        windows, tail_order = rank(wanted,state,features)
        if method == "tail":
            idx = next(i for i in tail_order if i in eligible)
        else:
            if method == "balanced":
                lowest = min(calls[state[i][0]] for i in eligible)
                eligible = {i for i in eligible if calls[state[i][0]] == lowest}
            elif method != "any":
                raise ValueError(method)
            idx = next(i for i,_,_ in windows if i in eligible)
    field,left,text = state[idx]
    return field, left + len(text)

def observe(state, field, left, new_text):
    """Materialize connected received intervals, asserting literal consistency at overlaps."""
    assert new_text
    pending = [(a,text,i) for i,(e,a,text) in enumerate(state) if e == field]
    pending.append((left,new_text,len(state)))
    combined = []
    for start, text, priority in sorted(pending):
        if combined and start <= combined[-1][0] + len(combined[-1][1]):
            prev, body, rank = combined[-1]
            offset = start - prev
            overlap = min(len(text),len(body) - offset)
            assert body[offset:offset+overlap] == text[:overlap]
            combined[-1] = (prev, body + text[overlap:], min(rank,priority))
        else:
            combined.append((start,text,priority))
    all_fragments = [(i,(e,a,text)) for i,(e,a,text) in enumerate(state) if e != field]
    all_fragments.extend((i,(field,a,text)) for a,text,i in combined)
    return [s for _,s in sorted(all_fragments)]

