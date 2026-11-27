"""Verify identities, before-write ranks and every post-restart byte from the source streams."""
import argparse
from collections import Counter, defaultdict, deque
from hashlib import sha256
import json

from run_transfer import ARMS, GROUPS, HERE, WORKLOADS, load, save, source
from audit import chosen as independent_selection, width


def verify_case(stream, workload, stored):
    names = {}
    events = []
    for sha, raw in stream:
        members = tuple(names.setdefault(p, len(names)) for p in raw) if len(raw)<=64 else ()
        if len(members)>=2:
            events.append(members)
    fence = len(events)//2
    weights = [sum(map(width,x)) for x in events]
    selected = {mode:independent_selection(events[:fence],cap,policy)
                for mode,(policy,cap) in ARMS.items()}
    assert stored["events"]==len(events) and stored["fence"]==fence
    for mode,(js,sz,wr) in selected.items():
        obs = stored["arms"][mode]["summary"]
        assert (len(js),sz,wr,int(mode!="cold")*20)==(obs["selected"],obs["useful"],obs["written"],obs["receipt"])
    prefix = defaultdict(list)
    after = defaultdict(list)
    known = {mode:set() for mode in ARMS}
    seen = set()
    window = deque(maxlen=32)
    q = post = j = 0
    oracle = sha256()
    summary = {mode:Counter() for mode in ARMS}
    for t,(sha,raw) in enumerate(stream):
        paths = raw if len(raw)<=64 else []
        h = int(sha,16)
        use = (len(paths)>=2 and ((workload=="B" and t>=64) or
               (workload=="long" and t>=len(stream)//2 and not h%11)))
        if use:
            name = paths[(h if workload=="B" else h//11)%len(paths)]
            f = names[name] if names[name] in seen else -1
            assert stored["ids"][q]==[t,sha,name]
            frequency = Counter(m for members in window for m in members)
            incident = prefix.get(f,[])
            counts = Counter(g for idx in incident for g in events[idx])
            ranks = sorted((g for g in seen if g!=f),key=lambda g:(-counts[g],-frequency[g],g))[:8]
            ranks = [[g,counts[g]] for g in ranks]
            oracle.update(json.dumps([sha,f,ranks],separators=(",",":")).encode()+b"\n")
            if j>=fence:
                live = {event for items in after.values() for event in items[-8:]}
                earlier = {event for event in incident if event<fence}
                later = set(incident)-earlier
                hot = live & later
                for mode,(pinned,_,_) in selected.items():
                    restored = pinned & earlier
                    consult = f not in known[mode] or hot!=later
                    if consult and earlier==restored:
                        known[mode].add(f)
                    missing = (later-hot)|(earlier-restored)
                    assert consult or not missing
                    post_bytes = sum(map(width,incident)) if consult else 0
                    body_bytes = sum(weights[e] for e in missing)
                    row = [1 if post<10 else 2,int(consult),(len(missing)+399)//400,post_bytes,
                           len(missing),body_bytes,len(restored),len(hot)]
                    assert stored["arms"][mode]["work"][q]==row,(t,mode,f)
                    summary[mode].update(postings=post_bytes,bodies=body_bytes)
                post+=1
            q+=1
        codes = tuple(names[p] for p in paths)
        window.append(codes);seen.update(codes)
        if len(codes)>=2:
            assert codes==events[j]
            for f in codes:
                prefix[f].append(j)
                if j>=fence:after[f].append(j)
            j+=1
    assert len(stored["ids"])==q and oracle.hexdigest()==stored["oracle"]
    for mode in ARMS:
        obs = stored["arms"][mode]["summary"]
        assert q==obs["queries"] and post==obs["post"]
        assert summary[mode]["bodies"]==obs["body_bytes"] and summary[mode]["postings"]==obs["posting_bytes"]
        assert obs["charged"]==2*selected[mode][2]+20*int(mode!="cold")+sum(summary[mode].values())
    return dict(queries=q,post=post,exact_rank_digest=oracle.hexdigest(),
                audited_post_records=post*len(ARMS),checked_sqlite_ranks=q*len(ARMS))


def main():
    parser = argparse.ArgumentParser();parser.add_argument("--verify",action="store_true")
    verify = parser.parse_args().verify
    raw = load(HERE/"runs.json.gz")["projects"]
    out = {}
    for group in GROUPS:
        data,heads = source(group)
        for repo,stream in sorted(data.items()):
            key = group+"/"+repo
            assert heads[repo]["head"]==raw[key]["head"]
            out[key] = {w:verify_case(stream,w,raw[key]["workloads"][w]) for w in WORKLOADS}
    if verify:assert out==load(HERE/"audit.json")
    else:save(HERE/"audit.json",out)
    ranks = sum(s["checked_sqlite_ranks"] for case in out.values() for s in case.values())
    checks = sum(s["audited_post_records"] for case in out.values() for s in case.values())
    print(ranks,"SQLite rank checks;",checks,"independently audited post-restart resource records.")


if __name__=="__main__":
    main()
