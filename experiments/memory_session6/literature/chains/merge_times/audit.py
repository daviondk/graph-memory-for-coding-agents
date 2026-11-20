"""Independently reconstruct all published merge timestamps from saved metadata only."""
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def load(p):
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def date(s):return datetime.fromisoformat(s.replace('Z','+00:00'))
def main():
    roster=load(ROOT/'roster.json')
    archived=load(ROOT/'history_times.json')
    verified=load(ROOT/'verified_times.json')
    assert set(roster)==set(archived)==set(verified)
    known={}
    for p in (ROOT/'archive').glob('*.gz'):
        rec=load(p)
        repo=p.name.removesuffix('.json.gz').replace('__','/')
        assert "repo_name='"+repo+"'" in rec['query']
        for r in rec['lines']:
            first,last=int(r['first_merge']),int(r['last_merge'])
            if first>0 and first==last:timestamp=last
            elif first==last==0:timestamp=int(r['first_merged_event'])
            else:continue
            known[repo,int(r['number'])]=datetime.fromtimestamp(timestamp,timezone.utc)
    api={p.stem:load(p) for p in (ROOT/'rest').glob('*.json')}
    n_check=0
    for k,v in verified.items():
        meta=roster[k];repo=meta['repo'];pr=meta['pr']
        a=known.get((repo,pr));assert (date(archived[k]['merged_at']) if archived[k]['merged_at'] else None)==a
        if k in api:
            obj=api[k];assert obj['url']==f'https://api.github.com/repos/{repo}/pulls/{pr}' and obj['number']==pr
            given=date(obj['merged_at'])
            if a:
                assert given==a or (archived[k]['method']=='merged_close_event_upper_bound' and given<=a)
                n_check+=1
        else:given=a
        assert given is not None and date(v['merged_at'])==given and given>=date(meta['created_at'])
    assert (len(verified),len(known),len(api),n_check)==(592,551,47,6)
    print('PASS 592 merge times, 551 archived events and 47 original REST replies including six cross-checks.')
if __name__=='__main__':main()
