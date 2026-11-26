"""Certify at least 3 public history objects per repository without exposing archived conversations."""
from screen import *
import urllib.parse as u
HF='11164976b4f920cdb0d0cd570ca572e49acea1e8'
def get(url):
    data=subprocess.check_output(['curl.exe','--fail','--retry','2','--silent','--show-error','--max-time','45','-H','User-Agent: VibeMemBench-replication',url])
    return json.loads(data)
def main():
    s=json.loads((D/'screen.json').read_text());by={r['instance_id']:r for r in rows()}
    for a in s['selected']:
        r=by[a['instance']];base=r['base_commit'];hist=V/'benchmark/history/python'/r['repo'].replace('/','__')
        rec=[]
        for p in sorted(hist.glob('*/*.traj.json'),key=lambda f:int(f.parent.name.rsplit('-',1)[1])):
            id=p.parent.name; n=int(id.rsplit('-',1)[1])
            if id==r['instance_id']:continue
            repo=r['repo'];pr_url=f'https://api.github.com/repos/{repo}/pulls/{n}';pr=get(pr_url)
            merge=pr['merge_commit_sha']
            path='history/python/'+p.resolve().relative_to((V/'benchmark/history/python').resolve()).parent.as_posix()
            tree_url=f'https://huggingface.co/api/datasets/Tongyi-ConvAI/VibeMemBench/tree/{HF}/'+u.quote(path,safe='/')
            pinned={q['path'].split('/')[-1]:q for q in get(tree_url)}[p.name]
            b=p.read_bytes();local=hashlib.sha256(b).hexdigest()
            valid=pinned.get('lfs',{}).get('oid')==local if pinned.get('lfs') else pinned['oid']==hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
            assert valid
            compare=f'https://api.github.com/repos/{repo}/compare/{merge}...{base}?per_page=1';match=get(compare)
            isanc=bool(pr['merged_at'] and match['merge_base_commit']['sha']==merge)
            target=int(r['instance_id'].rsplit('-',1)[1]);hits=len(re.findall(rf'(?i)(?:[#/]|__{re.escape(repo.split("/")[-1])}-){target}\b',b.decode('utf8')))
            rec.append(dict(id=id,public_object=tree_url,bytes=len(b),sha256=local,verified_hf=valid,pr=pr_url,merge=merge,compare=compare,ancestor=isanc,target_id_hits=hits,accepted=isanc and not hits))
            if sum(x['accepted'] for x in rec)>=3:break
        save(D/'evaluator'/r['instance_id']/'history-minimum.json',rec)
        print(r['instance_id'],sum(x['accepted'] for x in rec),len(rec),flush=True)
if __name__=='__main__':main()