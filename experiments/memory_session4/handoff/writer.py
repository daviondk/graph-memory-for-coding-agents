"""Reference writer with local, conservative evidence of test timing; no access to grader outputs."""
import re
from collections import Counter
from common import *
TEST=re.compile(r'(?:^|[;&|\n]\s*|^\s*)(?:(?:cd [^\n;&|]{1,100}\s*&&\s*)|(?:[\w./-]+=\S+\s+))*((?:(?:(?:[\w./-]*/)?(?:python(?:3(?:\.\d+)?)?)\s+(?:-m\s+)?)(?:pytest\b|unittest\b|(?:[.\w/-]*/)?runtests\.py\b|(?:[.\w/-]*/)?manage\.py\s+test\b|(?:[.\w/-]*/)?(?:test[_-]|repro)[\w./-]*\.py\b)|(?:[\w./-]*/)?(?:pytest|py\.test|tox)\b|(?:\./)?(?:tests/)?runtests\.py\b|bin/test\b)[^\n;&|]*)',re.I)
WRITE=re.compile(r'(?:\b(?:apply_patch|patch|mv|cp|rm|touch|tee|perl\s+-\w*i|sed\s+-\w*i)\b|\.write(?:_text|_bytes)?\s*\(|open\([^\n]{1,220}?,\s*["\x27][wax+]|shutil\.(?:move|copy)|(?:^|[^=>])>(?![=&])\s*[^\s])',re.I)
def excerpt(t,b):
    return t if len(t)<=b else t[:(b-20)*2//3]+'\n… excerpt …\n'+t[-(b-20)//3:]
def patch_paths(diff):
    return {s.strip()[2:] for s in re.findall(r'^(?:\+\+\+|---) (\S+)',diff,re.M) if s.startswith(('a/','b/'))}
def mutation(cmd,paths):
    if not WRITE.search(cmd):return None
    cleaned=re.sub(r'(?:[0-9]*>\s*(?:/dev/null|/tmp/[\w./-]+)|[0-9]*>&[0-9])','',cmd)
    if not WRITE.search(cleaned):return None
    return 'path' if any(x in cleaned for x in paths) else 'unknown'
def check_event(cmd,e):
    # Only shell command lines; commands in arbitrary Python/code heredocs cannot become test evidence.
    top=cmd.split('<<',1)[0] if '<<' in cmd else cmd
    candidates=list(TEST.finditer(top))
    if not candidates:return None
    m=candidates[-1];norm=' '.join(m[1].split()).strip();norm=re.split(r'\s+[0-9]*>',norm)[0]
    if not norm or len(norm)>1600:return None
    d=e['diag'] or ''
    # A failing assertion or diagnostic overrides a wrapper's success code.
    if re.search(r'\b[1-9]\d* (failed|errors?)\b|FAILED\s*\(|ModuleNotFoundError|ImportError|TimeoutExpired',d,re.I):out='fail'
    elif re.search(r'\b[1-9]\d* passed\b|(?:^| )OK(?: |$)',d):out='pass'
    else:
        # Pipelines, compound trailing commands, and multiple forwarded tests confound final rc attribution.
        rem=top[m.end():].strip()
        ambiguous=bool(rem) or len(candidates)!=1 or ('<<' in cmd)
        out='ambiguous' if ambiguous or e['rc'] is None else ('pass' if e['rc']==0 else 'fail')
    return {'command':norm,'rc':e['rc'],'diag':d,'out':out,'visible':bool(e['visible_sha'])}
def project(r):
    paths=patch_paths(r['patch']);writes=[];events=[];seen={}
    for j,t in enumerate(r['turns']):
        # Candidate observations in a single parallel tool batch are unordered, represented by group.
        g=t['group'];mut=mutation(t['cmd'],paths)
        if mut:writes.append((g,mut))
        e=check_event(t['cmd'],t)
        if e and e['visible']:
            previous=seen.get(e['command'])
            paired=bool(previous and previous['out']=='fail' and e['out']=='pass' and any(previous['g']<w<g and m=='path' for w,m in writes))
            e.update(g=g,j=j,paired=paired);events.append(e);seen[e['command']]=e
    for e in events:
        later=[m for w,m in writes if w>=e['g']]
        e['state']='afterwards-path-edit' if 'path' in later else 'unattributed-write' if later else 'no-later-write-detected'
        e['fresh']=int(not later)
    def grade(e):
        if not e:return 0
        return {'pass':1,'fail':-1,'ambiguous':0}[e['out']]
    last=events[-1] if events else {}
    fresh=[e for e in events if e['fresh']];fr=fresh[-1] if fresh else {}
    witness=sorted(events,key=lambda e:(int(e['paired'] and e['fresh']),e['fresh'],int(e['out']!='ambiguous'),int(e['paired']),e['g'],e['j']),reverse=True)[:2]
    # Preserve actual displayed diagnostics, not assistant judgements. All policies share caps.
    def render(items,tag):
        def line(e):
            cmd=excerpt(e['command'],105).replace('\n',' ')
            diag=excerpt(e['diag'],88).replace('\n',' ') if e['diag'] else 'no summary'
            flags=('; '+e['state']+('; same command failed before a detected patch-file edit' if e['paired'] else '')) if tag else ''
            return f"{cmd} | reported rc={e['rc']}, {e['out']}; {diag}{flags}"
        return excerpt('\n'.join(line(e) for e in items),450)
    score=2 if any(e['paired'] and e['fresh'] for e in witness) and grade(fr)>0 else grade(fr)
    return {'count':len(events),'n_writes':len(writes),'n_path_writes':sum(m=='path' for _,m in writes),
        'paired':sum(e['paired'] for e in events),'fresh':len(fresh),'last':grade(last),'fresh_rank':grade(fr),'witness_rank':score,
        'latest_note':render(events[-2:],False),'witness_note':render(witness,True),'events':events}
def main():
    rows={}
    for m in MODELS:
        for f in sorted((ROOT/'records'/m).glob('*.gz')):
            r=read(f.relative_to(ROOT));rows[m+'|'+r['issue_id']]=project(r)
    assert len(rows)==1441
    write('receipts.json.gz',rows)
    print('trajectories',len(rows),'tests',sum(x['count'] for x in rows.values()),'with a witnessed change',sum(x['paired']>0 for x in rows.values()))
if __name__=='__main__':main()
