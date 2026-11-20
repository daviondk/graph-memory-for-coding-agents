"""Extract hashed lexical bags. Never interpret source statements or patch content as code."""
import io
import re
import sys
from collections import Counter,defaultdict
from functools import lru_cache
from pathlib import PurePosixPath
import pyarrow.parquet as pq
import requests
from common import HERE,WRITE,digest,ident,load,save
sys.path.insert(0,str(WRITE))
from project import DENY,EXPECTED,REV,URL,h

WORD=re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
CAMEL=re.compile(r'[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+')
STOP=set("""about above after again against all also am an and any are as at be because been before being below between both but by can could did do does doing down during each either else ever every few for from further had has have having he her here hers herself him himself his how i if in into is it its itself just like may me might more most must my myself neither nor not now of off on once only or other our ours ourselves out over own same shall she should since so some such than that the their theirs them themselves then there these they this those through to too under until up upon us use used using very was we well were what when where whether which while who whom why will with within without would you your yours yourself yourselves""".split())
EXCLUDE={'tests','test','testing','vendor','vendors','vendored','third_party','generated'}
HEADER=re.compile(r'^diff --git a/[^\s]+ b/([^\s]+)\s*$',re.M)


@lru_cache(50000)
def hashes(identifier):
    terms={identifier.casefold()}
    for piece in identifier.split('_'):
        terms.add(piece.casefold())
        terms.update(m.group().casefold() for m in CAMEL.finditer(piece))
    return tuple(sorted(ident('lexical-cue-v1#'+t) for t in terms if 3<=len(t)<=48 and not t.isnumeric() and t not in STOP))


def bag(txt):
    out=Counter()
    for m in WORD.finditer(txt):out.update(hashes(m.group()))
    return dict(out)


def project_previous(item,repo):
    # Historical patch headers are only admitted for the current prefix's completed prior tasks.
    files={}
    for p in HEADER.findall(item['patch'] or ''):
        raw=PurePosixPath(p);parts=raw.parts;name=parts[-1].casefold()
        if (not name.endswith('.py') or name.startswith('test_') or name.endswith('_test.py') or name=='conftest.py' or
            any(x.casefold() in EXCLUDE for x in parts) or DENY.search(p.replace('_',' '))):
            continue
        files[h(repo+'#'+p)]={'folder':h(repo+'#dir#'+'/'.join(parts[:-1])),
                              'words':sorted(bag(' '.join((*parts[:-1],raw.stem))))}
    assert files
    return files


def main():
    locked=load(WRITE/'decision_lock.json')
    assert digest((WRITE/'decisions.json.gz').read_bytes())==locked['hashes']['decisions.json.gz']
    roster=load(WRITE/'decisions.json.gz')
    assert len(roster)==len({(r['repo'],r['issue']) for r in roster})==374
    positions=defaultdict(list)
    for r in roster:positions[r['sequence']].append(r)
    reply=requests.get(URL,timeout=100)
    reply.raise_for_status();assert digest(reply.content)==EXPECTED
    table=pq.ParquetFile(io.BytesIO(reply.content))
    # Arrow's nested-column decoder materializes the list. Selection happens before reading any target edit into an extractor.
    cols=['continuous_id','repo','bug_fixes.list.element.swebench_instance_id','bug_fixes.list.element.problem_statement','bug_fixes.list.element.patch']
    result=[];sequence_count=0
    for batch in table.iter_batches(batch_size=8,columns=cols):
        for row in batch.to_pylist():
            sequence=h(row['continuous_id'])
            if sequence not in positions:continue
            sequence_count+=1
            for spec in positions[sequence]:
                t=spec['previous_tasks'];repo=row['repo'];assert repo==spec['repo']
                items=row['bug_fixes'];current=items[t]
                assert h(repo+'#issue#'+current['swebench_instance_id'])==spec['issue']
                assert not DENY.search(current['problem_statement'] or '')
                history=[]
                for item in items[:t]:
                    text=item['problem_statement'] or ''
                    assert not DENY.search(text)
                    history.append({'issue':h(repo+'#issue#'+item['swebench_instance_id']),'terms':bag(text),'files':project_previous(item,repo)})
                assert spec['issue'] not in {s['issue'] for s in history}
                assert sorted({p for old in history for p in old['files']})==spec['seen']
                query=sorted(bag(current['problem_statement'] or ''))
                result.append(dict(repo=ident('repo#'+repo),issue=spec['issue'],sequence=sequence,prefix=t,history=history,query=query,
                                   expected_cache=spec['policies']['8/confirmation']['keys']))
    assert len(result)==374 and sequence_count==len(positions)
    save(HERE/'features.json.gz',sorted(result,key=lambda r:(r['repo'],r['issue'])))
    save(HERE/'source.json',dict(revision=REV,url=URL,parquet_sha256=EXPECTED,write_roster_sha256=locked['hashes']['decisions.json.gz'],
                               selected_targets=len(result),selected_sequences=sequence_count,repo_clusters=len({r['repo'] for r in result}),
                               features_sha256=digest((HERE/'features.json.gz').read_bytes())))
    print('Projected only hashed input features for',len(result),'target/prefix pairs.')

if __name__=='__main__':main()
