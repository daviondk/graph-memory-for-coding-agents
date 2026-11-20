"""Blind chronological retrieval; labels and target patches are never inputs."""
import collections
import datetime
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import time

from prepare import ROOT, load_inputs, save, sha, stamp

ARMS=['issue256','issue192','edit64','card','placebo','recency','separate']
MASK=re.compile(r'https?://\S+|\b[\w.-]+__[\w.-]+-\d+\b|\B#\d+\b|\b[0-9a-f]{32,64}\b|\b(?:PR|issue|pull[ -]request|ticket|GH|bug|changeset)\s*[-:#]?\s*\d{2,}\b|\b(?:pulls?|issues?|tickets?)/\d+\b|\b(?:commit|revision|changeset)\s+[0-9a-f]{7,40}\b',re.I)
IDENT=re.compile(r'[A-Za-z_][A-Za-z_0-9]*')
STOP=set('self def return if elif else as with void string bool true false this const int long double array type print exception none import from for not that the into this then an and of in at or by continue break class public private protected static function let var async await try catch raise new is to a on fixture using use it you'.split())


def words(s,n):
    return MASK.sub(' ',s or '').split()[:n]


def edit_words(patch):
    seen=set()
    paths=[];anchors=[];added=[];removed=[]
    for line in (patch or '').splitlines():
        if line.startswith('diff --git '):
            m=re.search(r'\s[b]/(.+?)"?$',line)
            if m: paths.extend(words(m[1],8))
        elif line.startswith('@@'):
            anchor=re.sub(r'^@@[^@]*@@','',line)
            anchors.extend(IDENT.findall(anchor))
        elif line.startswith('+') and not line.startswith('+++'):
            added.extend(IDENT.findall(line[1:]))
        elif line.startswith('-') and not line.startswith('---'):
            removed.extend(IDENT.findall(line[1:]))
    ans=[]
    for term in paths+anchors+added+removed:
        if len(term)<2 or term.lower() in STOP or term in seen:continue
        seen.add(term); ans.append(term)
        if len(ans)==64:break
    return ans


def lexical(words_):
    out=collections.Counter()
    for w in words_:
        for term in re.findall(r'[A-Za-z0-9_]+',w):
            out[term.lower()]+=1
            pieces=re.sub(r'([a-z])([A-Z])',r'\1 \2',term).replace('_',' ').lower().split()
            if len(pieces)>1:out.update(pieces)
    return out


def rank_tokens(docs,q,keys):
    n=len(docs)
    if not n:return []
    lengths=[sum(d.values()) for d in docs]
    avg=sum(lengths)/n or 1.0
    matched=[q.keys()&d.keys() for d in docs]
    df=collections.Counter(t for m in matched for t in m)
    scale={t:math.log1p((n-df[t]+.5)/(df[t]+.5))*min(c,2) for t,c in q.items()}
    scores=[]
    for d,l,terms in zip(docs,lengths,matched):
        normal=1.2*(.25+.75*l/avg)
        scores.append(math.fsum(scale[t]*d[t]*2.2/(d[t]+normal) for t in terms))
    return sorted(range(n),key=lambda j:(-scores[j],keys[j]))


def author_clock(q,r,times):
    item=times[q['repo']]
    def opened(n):
        return item.get(str(n),{}).get('open')
    observed=[opened(r['pull_number']),*[x['open'] for x in r['issue_clock']]]
    supplied=stamp(q['created_at'])
    known=[d for d in observed+[supplied] if d]
    return min(known) if known else None, bool(observed[0] and all(observed[1:])), bool(r['issue_numbers'])


def run():
    t0=time.perf_counter()
    docs,queries,_=load_inputs()
    times=json.loads((ROOT/'github_times.json').read_text(encoding='utf8'))
    refs=json.loads((ROOT/'case_refs.json').read_text(encoding='utf8'))
    ids=sorted(docs)
    base={}; e={}; ix={}
    state={}
    bytes_=collections.Counter()
    for iid in ids:
        d=docs[iid]
        base[iid]=words(d['problem_statement'],256)
        e[iid]=edit_words(d['patch'])
        store={'issue256':base[iid], 'issue192':base[iid][:192], 'edit64':e[iid], 'card':base[iid][:192]+e[iid]}
        ix[iid]={k:lexical(ls) for k,ls in store.items()}
        for k,ls in store.items():
            bytes_[k]+=len(' '.join(ls).encode('utf8'))
        state[iid]=(d['repo'], times[d['repo']].get(iid.rsplit('-',1)[1],{}).get('merge'))
    write_seconds=time.perf_counter()-t0
    elapsed=collections.Counter()
    order=sorted(ids,key=lambda i:hashlib.sha256(('donor|20261116|'+i).encode()).digest())
    out=ROOT/'blind_ranks.jsonl.gz'
    with gzip.open(out,'wt',encoding='utf8',compresslevel=6) as f:
        for qi,q in sorted(queries.items()):
            cutoff,validated,issue_refs=author_clock(q,refs[qi],times)
            qtok=lexical(words(q['problem_statement'],280))
            for scope in ['repo_time','all_time','repo_release']:
                keys=[i for i in ids if i!=qi and (scope=='all_time' or state[i][0].lower()==q['repo'].lower()) and
                      (scope=='repo_release' or (state[i][1] and cutoff and state[i][1]<cutoff))]
                allowed=set(keys)
                shift=[i for i in order if i in allowed and e[i]]
                donor={}
                if len(shift)>1:
                    donor={i:shift[(n+1)%len(shift)] for n,i in enumerate(shift)}
                clocks={'target':qi,'repo':q['repo'],'scope':scope,'cutoff':cutoff,'all_open_validated':validated,'has_issue_refs':issue_refs,
                        'candidates':len(keys),'placebo_eligible':len(donor),'ranks':{}}
                for arm in ARMS:
                    ts=time.perf_counter()
                    if arm=='recency':
                        chosen=sorted(keys,key=lambda i:(state[i][1] or '',i),reverse=True)
                    elif arm=='separate':
                        ordinal={k:{doc:j for j,doc in enumerate(clocks['ranks'][k],1)} for k in ['issue192','edit64']}
                        chosen=sorted(keys,key=lambda i:(-(2/(12+ordinal['issue192'][i])+1/(12+ordinal['edit64'][i])),i))
                    else:
                        if arm=='placebo':
                            tokens=[]
                            for i in keys:
                                other=e.get(donor.get(i),[])
                                appendix=(other*((len(e[i])+len(other)-1)//len(other)))[:len(e[i])] if other else []
                                tokens.append(ix[i]['issue192']+lexical(appendix))
                        else:
                            tokens=[ix[i][arm] for i in keys]
                        chosen=[keys[j] for j in rank_tokens(tokens,qtok,keys)]
                    clocks['ranks'][arm]=chosen
                    elapsed[scope+'/'+arm]+=time.perf_counter()-ts
                f.write(json.dumps(clocks,ensure_ascii=False,separators=(',',':'))+'\n')
    save('run_cost.json',{'write_seconds':write_seconds,'rank_seconds':dict(elapsed),'bytes_input_text_fields':dict(bytes_),'total_seconds':time.perf_counter()-t0,'mean_edit_words':statistics.mean(map(len,e.values())),'empty_edit_fields':sum(not x for x in e.values()),'mode':'local CPU, one ranking process; caches warm; no LLM calls; text payload before tokenization'})
    frozen={n:sha((ROOT/n).read_bytes()) for n in ['PROTOCOL.md','CLOCK_ADDENDUM.md','prepare.py','date_fallback.py','issue_dates.py','rank.py','score.py','source.json','github_times.json','case_refs.json','issue_dates.json','html_clock_evidence.json','blind_ranks.jsonl.gz','run_cost.json']}
    save('blind_freeze.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':frozen})
    print('locked',len(queries),'queries',time.perf_counter()-t0,flush=True)


if __name__=='__main__':run()

