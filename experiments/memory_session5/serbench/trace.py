"""Transparent write/read budget experiment. All source data is inert text."""
import gzip, json, math, re, sys
from collections import Counter,defaultdict
from features import ROOT,digest,terms
from train import read,project,lines,fit,pred,np
from tokenizers import Tokenizer
TOKENIZER=ROOT.parent/'packets/qwen_tokenizer.json'
ENC=Tokenizer.from_file(str(TOKENIZER))
# Disable any padding/truncation stored in source tokenizer.
ENC.no_padding();ENC.no_truncation()
PATH=re.compile(r"(?<![\w./-])((?:[\w./\\-]+[/\\])?[\w.-]+\.(?:py|js|jsx|ts|tsx|cpp|c|cc|hpp|h|rs|go|java|rb|cs|kt|sh|yaml|yml|json|toml|md|txt|html|css|scala|php|vue|xml|cfg|ini))(?:[:#](?:L)?(\d+)(?:[-:](?:L)?(\d+))?)?",re.I)
ARMS=('empty','tail','head','uniform','arguments','addresses','complete')
def ids(s):return ENC.encode(s,add_special_tokens=False).ids
def text(x):return x if isinstance(x,str) else json.dumps(x,ensure_ascii=False)
def locs(s):
    out={}
    for m in PATH.finditer(s):
        p=m.group(1).replace('\\','/').lower().strip('./');lo=int(m.group(2) or 0);hi=int(m.group(3) or lo)
        out.setdefault(p,set()).add((lo,hi))
    return out
def writes(row):
    events=row['trajectory_prefix']
    actions=[text(x.get('action_input') or '') for x in events]
    outputs=[text(x.get('tool_output') or '') for x in events]
    serial=[a+'\n'+o for a,o in zip(actions,outputs)]
    full='\n'.join(serial);raw=ids(full)
    all_addresses=[]
    for action,output in reversed(list(zip(actions,outputs))):
        refs=[m.group(0) for m in PATH.finditer(action+'\n'+output)]
        refs=list(dict.fromkeys(refs))[:8]
        all_addresses.append(' '.join(refs)+' '+ENC.decode(ids(action)[:24],skip_special_tokens=False))
    lim=192
    unif='\n'.join(ENC.decode(ids(s)[-max(1,lim//max(1,len(serial))):],skip_special_tokens=False) for s in serial)
    memory={'empty':[],'tail':raw[-lim:],'head':raw[:lim],'uniform':ids(unif)[:lim],
            'arguments':ids('\n'.join(reversed(actions)))[:lim],'addresses':ids('\n'.join(all_addresses))[:lim],'complete':raw}
    # Count actual transmitted IDs; decode exactly those IDs, including special spellings.
    return {k:(ENC.decode(v,skip_special_tokens=False),len(v)) for k,v in memory.items()}
def qfeat(query,cs):
    q=set(terms(query));paths=locs(query);basename={p.rsplit('/',1)[-1] for p in paths}
    feats=[]
    for x in cs:
        tokens,path,pterms,lo,hi=x
        p=path.lower().replace('\\','/').strip('./');bn=p.rsplit('/',1)[-1];qt=tokens&q
        candidates=paths.get(p,())
        bounded=[(a,b) for a,b in candidates if a>0]
        distance=min((max(0,a-hi,lo-b) for a,b in bounded),default=None)
        feats.append([math.log1p(len(qt)),len(qt)/max(1,len(q)),len(qt)/max(1,len(tokens)),len(pterms&q)/max(1,len(pterms)),float(bn in basename),float(p in paths),float(distance==0),0 if distance is None else 1/(1+distance/50)])
    return np.array(feats)
def run():
    folds={r['state_id']:r['outer_fold'] for r in [json.loads(l) for l in gzip.open(ROOT/'cal_folds.jsonl.gz','rt')]}
    labels={r['state_id']:{z for g in r['required_evidence_groups'] for z in g['acceptable_evidence_ids']} for r in read('cal500','labels')}
    matrix=[];meta=[]
    for row in read('cal500','items'):
        sid=row['state_id'];cs=sorted(row['candidate_evidence'],key=lambda c:digest(sid+'|'+c['evidence_id']))
        visible=set(row['observed_evidence_ids']);cs=[c for c in cs if c['evidence_id'] not in visible]
        keys=[c['evidence_id'] for c in cs]
        candidates=[(set(terms(c.get('content_excerpt'))),str(c.get('source_path') or ''),set(terms(c.get('source_path'))),int(c.get('line_start') or 0),int(c.get('line_end') or 0)) for c in cs]
        if not candidates:raise ValueError(sid)
        query=' '.join(text(row.get(key) or '') for key in ('issue','information_need','current_subgoal'))
        q=qfeat(query,candidates);size=np.array([[math.log1p(len(c[0]))] for c in candidates])
        w=writes(row);y=np.array([int(e in labels[sid]) for e in keys])
        arms={name:np.column_stack([size,q,qfeat(m,candidates)]) for name,(m,length) in w.items()}
        matrix.append((sid,keys,folds[sid],y,arms));meta.append({'state_id':sid,'qwen_token_counts':{a:int(v[1]) for a,v in w.items()},'prefix_actions':len(row['trajectory_prefix'])})
    predictions=[];models={}
    for fold in range(5):
        y=np.concatenate([y for sid,keys,f,y,arms in matrix if f!=fold])
        for a in ARMS:
            X=np.vstack([arms[a] for sid,keys,f,_,arms in matrix if f!=fold]);model=fit(X,y)
            models[f'{fold}/{a}']=model
            for sid,keys,f,_,arms in matrix:
                if f!=fold:continue
                scores=pred(model,arms[a]);best=np.argsort(-scores,kind='stable')[:8]
                predictions.append({'state_id':sid,'method':a,'ranked_evidence_ids':[keys[i] for i in best]})
    lines(ROOT/'trace_predictions.jsonl.gz',predictions);lines(ROOT/'trace_cost.jsonl.gz',meta)
    (ROOT/'trace_models.json').write_text(json.dumps(models))
    import hashlib
    files=['TRACE_PROTOCOL.md','trace.py','trace_models.json','trace_predictions.jsonl.gz','trace_cost.jsonl.gz']
    (ROOT/'trace_lock.json').write_text(json.dumps({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},indent=2))
if __name__=='__main__':run()
