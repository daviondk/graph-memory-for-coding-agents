"""Pinned released split, project inputs and original encoder from round 8."""
from pathlib import Path
import sys,os,json,hashlib
ROOT=Path(__file__).resolve().parent
R8=Path(os.getenv('R8_RETRIEVAL_DIR',str(ROOT.parents[1]/'graph_memory_round8'/'retrieval')))
sys.path.append(str(R8))
from acquire import CACHE,index,member,MODEL,REV,SOURCE
MODEL_SHAS={k:v['sha256'] for k,v in json.loads((R8/'model_manifest.json').read_text()).items()}
LOC_SPLIT='c44cf3b74e07ca642cec841b471a9939907c12a7'
def h(s):return hashlib.sha256(s if isinstance(s,bytes) else s.encode()).hexdigest()
def load_json(p):return json.loads(p.read_text(encoding='utf8'))
def write_json(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=1),encoding='utf8')
def official_ids():
    import pyarrow.parquet as pq,requests
    path=CACHE/('locbench-test-'+LOC_SPLIT+'.parquet')
    if not path.exists():
        u=f'https://huggingface.co/datasets/czlll/Loc-Bench_V1/resolve/{LOC_SPLIT}/data/test-00000-of-00001.parquet'
        r=requests.get(u,timeout=90);r.raise_for_status();path.write_bytes(r.content)
    ids=pq.read_table(path,columns=['instance_id']).column('instance_id').to_pylist()
    assert len(set(ids))==len(ids)
    return set(ids),h(path.read_bytes())
def base(t):return 'datasets/loc-bench-function_'+t+'/'
def inputs(t):
    q=member(base(t)+'queries.jsonl')
    rows=[json.loads(x) for x in q.splitlines()]
    assert len(rows)==1 and rows[0]['_id']==t
    return rows[0]['text'],h(q)
if __name__=='__main__':
    ids,sha=official_ids()
    archived={p.split('loc-bench-function_')[1].split('/')[0] for p in index() if p.startswith('datasets/loc-bench-function_') and p.endswith('/corpus.jsonl')}
    used={f.stem for f in (R8/'loc_predictions').glob('*.json')}
    print(len(archived),len(ids),len(archived&ids),'earlier released',len(used&ids),sorted(used-ids))
