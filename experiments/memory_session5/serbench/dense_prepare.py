import gzip,json,hashlib
from trace import writes,ROOT
from train import read,lines
PFX='Represent this sentence for searching relevant passages: '
def main():
    texts={};skeleton=[]
    def add(t):
        k=hashlib.sha256(t.encode('utf-8')).hexdigest();texts[k]=t;return k
    for row in read('cal500','items'):
        w=writes(row)
        current='\n'.join([row.get('information_need') or '',row.get('current_subgoal') or '',row.get('issue') or ''])
        queries={'issue':PFX+row['issue'],'state':PFX+current}
        for k in ['addresses','tail','arguments']:queries[k]=PFX+w[k][0]+'\n'+current
        cs=sorted(row['candidate_evidence'],key=lambda c:hashlib.sha256((row['state_id']+'|'+c['evidence_id']).encode()).digest())
        skeleton.append({'state_id':row['state_id'],'candidates':[(c['evidence_id'],add((c.get('source_path') or '')+'\n'+(c.get('content_excerpt') or ''))) for c in cs],
                         'queries':{k:add(t) for k,t in queries.items()}})
    keys=sorted(texts);lookup={v:i for i,v in enumerate(keys)}
    for s in skeleton:
        s['candidates']=[(k,lookup[v]) for k,v in s['candidates']];s['queries']={k:lookup[v] for k,v in s['queries'].items()}
    lines(ROOT/'dense_inputs.jsonl.gz',skeleton)
    # Stored only locally; the distributed records contain source hashes and numerical vectors.
    lines(ROOT/'dense_texts.jsonl.gz',({'sha256':k,'text':texts[k]} for k in keys))
    print('unique inputs',len(keys),'states',len(skeleton))
if __name__=='__main__':main()
