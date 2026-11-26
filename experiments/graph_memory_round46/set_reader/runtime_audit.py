"""Inspect local CPU reranker slot records and cross-check with native API usage."""
from pathlib import Path
from hashlib import sha256
import gzip,json,re,sys
D=Path(__file__).resolve().parent
def main():
    path=Path(sys.argv[1]) if len(sys.argv)>1 else Path('D:/CodexResearch/x20-r46-small-reranker/cpu-scorer.log')
    raw=path.read_bytes();g=[(int(x),int(y)) for x,y in re.findall(rb'stop processing: n_tokens = (\d+), truncated = (\d+)',raw)]
    with gzip.open(D/'reranker-scores.json.gz','rt') as f: rows=json.load(f)
    total=sum(x['usage']['total_tokens'] for x in rows.values())
    assert len(g)==sum(len(x['indices']) for x in rows.values())==192 and sum(x for x,y in g)==total
    lens=[a for x in rows.values() for a in x['token_roundtrips']]
    out=dict(pairs=len(g),prompt_tokens=total,truncated_pairs=sum(y for x,y in g),maximum_pair_tokens=max(x for x,y in g),
             mean_pair_tokens=total/len(g),text_encodings=len(lens),exact_encodings=sum(a==b==n for a,b,n in lens),log_hash=sha256(raw).hexdigest())
    (D/'runtime-audit.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf8')
    print(out)
if __name__=='__main__':main()

