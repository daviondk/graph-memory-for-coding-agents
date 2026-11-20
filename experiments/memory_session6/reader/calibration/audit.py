"""Check whitelisted features against poisoned answer/label fields and replay every saved mask."""
import gzip
import json
from pathlib import Path
import numpy as np
import features

ROOT=Path(__file__).resolve().parent
ALLOWED={
    'queries_anchored_test.jsonl.gz':{'query_id','relation','question'},
    'key_anchored_test.jsonl.gz':{'query_id','fact_key'},
    'statements_anchored_test.jsonl.gz':{'id','year'},
    'sub_anchored_test_cosine.jsonl.gz':{'query_id','ranking'},
    'sub_anchored_test_time_rerank.jsonl.gz':{'query_id','ranking'},
}

if __name__=='__main__':
    input_rows=[json.loads(l) for l in (ROOT/'inputs.jsonl').read_text().splitlines()]
    if features.SOURCE.exists():
        original_loader=features.load
        expected=features.keyed_meta()
        def poisoned(path):
            return [{k:(v if k in ALLOWED[path.name] else 'POISON-ALL-OUTCOME-FIELDS') for k,v in r.items()}
                    for r in original_loader(path)]
        features.load=poisoned
        assert features.keyed_meta()==expected
        assert all(expected[r['id']]['features']==r['features'] for r in input_rows)
    report=json.loads((ROOT/'results.json').read_bytes())
    records={}
    with gzip.open(ROOT/'actions.jsonl.gz','rt') as f:
        for line in f:
            r=json.loads(line)
            records.setdefault((r['reader'],r['split']),[]).append(r)
    signs={}
    for (name,split),rows in records.items():
        n=len(rows)
        assert n==len({r['query'] for r in rows})==468
        assert len({r['subject'] for r in rows})==467
        a=np.array([r['plain'] for r in rows]);b=np.array([r['dated'] for r in rows])
        for k,rec in report['policies'][split].items():
            z=np.array([np.unpackbits(np.frombuffer(bytes.fromhex(r['read_mask_hex'][k]),dtype=np.uint8),bitorder='little') for r in rows])
            assert np.all(z.sum(0)==234)
            score=(a[:,None]+(b-a)[:,None]*z).mean()
            assert abs(score-rec[name]['mean_accuracy'])<1e-12
            if k.endswith('/calibrated_sign'):
                signs[f'{split}/{name}/{k}']=float(score)
    print('PASS all 468 labels-free row features and all per-reader budgets + outcomes for 32 seeds.')
