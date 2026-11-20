"""Acquire paired terminal observations for a separate agent on disjoint historical IDs."""
import concurrent.futures
import gzip
import hashlib
import json
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
AP = WORK / 'graph_memory_round5/action_probe'
sys.path.insert(0, str(AP))
import acquire


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ext = HERE / 'external'
    ext.mkdir(exist_ok=True)
    assert not (ext / 'roster_lock.json').exists()
    veto = {r['id'] for d in ['graph_memory_round5/writer', 'graph_memory_round5/action_transfer']
            for r in json.loads((WORK / d / 'receipts.json').read_bytes())}
    tasks = {}
    receipt = {}
    for d in ['graph_memory_round3/real_swe','graph_memory_round3/real_swe_followup','graph_memory_round4/writer']:
        parent = WORK / d
        receipt.update({r['id']:r for r in json.loads((parent/'receipts.json').read_bytes())})
        for f in sorted(parent.glob('source_*.jsonl.gz')):
            for q in acquire.rr(f):
                if q['instance'] not in veto:
                    tasks[q['instance']] = q
    ordered = sorted(tasks, key=lambda i: hashlib.sha256(('r6-version-claude|'+i).encode()).digest())
    groups=defaultdict(list)
    for i in ordered:
        groups[tasks[i]['official_repo']].append(i)
    ids=[v[j] for j in range(len(ordered)) for _,v in sorted(groups.items()) if j<len(v)][:48]
    assert len(ids)==48
    manifest = [dict(id=i,repo=tasks[i]['official_repo'],url=receipt[i]['url'],sha=receipt[i]['source_sha256']) for i in ids]
    (ext/'roster_lock.json').write_text(json.dumps(dict(utc=acquire.stamp(),acquisition_code=sha(Path(__file__)),manifest=manifest),indent=1))

    def one(r):
        for j in range(2):
            try:
                with urllib.request.urlopen(r['url'],timeout=35) as fp:
                    raw=fp.read(48*1024**2+1)
                assert len(raw)<=48*1024**2 and hashlib.sha256(raw).hexdigest()==r['sha']
                pair,ct=acquire.extract(tasks[r['id']],raw)
                return pair,dict(bytes=len(raw),terminal=ct)
            except OSError as e:
                if j: return None,dict(error=str(e))
                time.sleep(0.5)
    allct={}
    with concurrent.futures.ThreadPoolExecutor(8) as pool, gzip.open(ext/'source.gz','wt',encoding='utf8') as sources, gzip.open(ext/'terminal.gz','wt',encoding='utf8') as pairs:
        for r,(pair,ct) in zip(manifest,pool.map(one,manifest),strict=True):
            allct[r['id']]=ct
            if pair:
                acquire.write(sources,tasks[r['id']])
                acquire.write(pairs,pair)
    (ext/'receipts.json').write_text(json.dumps(allct,indent=1))
    (ext/'sources_lock.json').write_text(json.dumps(dict(utc=acquire.stamp(),files={f.name:sha(f) for f in [ext/'source.gz',ext/'terminal.gz',ext/'receipts.json',ext/'roster_lock.json']}),indent=1))
    print('received',sum('bytes' in ct for ct in allct.values()),'of',len(ids))


if __name__=='__main__':
    main()
