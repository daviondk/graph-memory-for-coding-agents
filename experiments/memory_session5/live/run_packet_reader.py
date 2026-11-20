"""Run a separately sealed SWE-smith pilot; this script never reads grader targets."""
import argparse,json,sys,time
from pathlib import Path
import common,infer
from common import stable,digest
def main():
    p=argparse.ArgumentParser()
    p.add_argument('packet_file',type=Path);p.add_argument('output_dir',type=Path);p.add_argument('--sha',required=True);p.add_argument('--max-tokens',type=int,default=320);args=p.parse_args()
    raw=args.packet_file.read_bytes();assert digest(raw)==args.sha
    if args.packet_file.suffix=='.gz':
        import gzip
        raw=gzip.decompress(raw)
    try:
        jobs=json.loads(raw)
    except ValueError:jobs=[json.loads(ln) for ln in raw.splitlines() if ln.strip()]
    if isinstance(jobs,dict):jobs=jobs['assignments']
    assert all(isinstance(j['messages'],list) and all(m['role'] in ('system','user') for m in j['messages']) for j in jobs)
    common.ROOT=args.output_dir.resolve();infer.ROOT=common.ROOT;common.ROOT.mkdir(exist_ok=True,parents=True)
    common.save('input_receipt.json',{'sha':args.sha,'n':len(jobs),'cap':args.max_tokens,'pilot':True})
    ordered=sorted(jobs,key=lambda j:digest('swe5-pilot|'+stable([j['id'],j['arm']])))
    out=[]
    for j,job in enumerate(ordered):
        k,answer=infer.call(job['messages'],args.max_tokens)
        out.append({'id':job['id'],'arm':job['arm'],'request_sha':k,'answer':answer})
        if j%12==11:print(j+1,'of',len(jobs),flush=True)
    common.save('predictions.json',out)
    common.save('prediction_lock.json',{f.relative_to(common.ROOT).as_posix():digest(f.read_bytes()) for f in sorted(common.ROOT.rglob('*')) if f.is_file() and f.name not in ('prediction_lock.json','run.log')})
    print('sealed',len(out),flush=True)
if __name__=='__main__':main()
