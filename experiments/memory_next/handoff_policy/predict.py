"""Dispatch a format using only outcomes of different repositories."""
import csv
import hashlib
import json
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parent
ART=ROOT.parent/'handoff_debt'
ARMS=['raw_trace','structured_notes','summary_notes','repo_only']
LEVELS=[('succ',),('pred','succ'),('pred','succ','kind')]

def csvrows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def dump(n,v):(ROOT/n).write_text(json.dumps(v,ensure_ascii=False,indent=1)+'\n',encoding='utf8')
def repo(r):return r['instance'].rsplit('-',1)[0]
def fit(train,scores):
    base={a:sum(scores[r[a]] for r in train)/len(train) for a in ARMS}
    tables=[]
    for cols in LEVELS:
        cells=defaultdict(list)
        for r in train:cells[tuple(r[c] for c in cols)].append(r)
        tables.append({k:(len(v),{a:sum(scores[r[a]] for r in v) for a in ARMS}) for k,v in cells.items()})
    return base,tables
def predict(model,r):
    prob,tables=model
    probs=[prob]
    for cols,t in zip(LEVELS,tables):
        cell=t.get(tuple(r[c] for c in cols))
        if cell:
            n,w=cell
            prob={a:(w[a]+20*prob[a])/(n+20) for a in ARMS}
        probs.append(prob)
    best=lambda x:max(ARMS,key=x.get)
    return best(probs[0]),best(probs[1]),best(probs[3])
def main():
    design=csvrows(ART/'assignments.csv')
    outcomes=csvrows(ART/'arm_outcomes.csv')
    locks={};predictions=[]
    for held in sorted(set(map(repo,design))):
        train=[r for r in design if repo(r)!=held]
        test=[r for r in design if repo(r)==held]
        # Only expose training IDs/outcomes to fitting. No evaluation labels needed to rank actions at prediction time.
        ids={r[a] for r in train for a in ARMS}
        scores={u['run_id']:int(u['official_known']=='1' and u['official_resolved']=='1') for u in outcomes if u['run_id'] in ids}
        assert set(scores)==ids and not ids & {r[a] for r in test for a in ARMS}
        model=fit(train,scores)
        locks[held]={'n_train':len(train),'n_test':len(test),'n_train_issues':len({r['instance'] for r in train}), 'train_repos':sorted({repo(r) for r in train}), 'train_ids_sha256':hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest()}
        for r in test:
            constant,recipient,full=predict(model,r)
            predictions.append({**{c:r[c] for c in ['instance','pred','succ','checkpoint','kind']},'group':held,'constant':constant,'recipient':recipient,'candidate':full})
    dump('folds.json',locks);dump('decisions.json',predictions)
    files=[ROOT/n for n in ['PROTOCOL.md','predict.py','folds.json','decisions.json']]+[ART/'assignments.csv',ART/'arm_outcomes.csv']
    dump('lock.json',{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
    print(len(locks),'held-out projects;',len(predictions),'assignments')
if __name__=='__main__':main()

