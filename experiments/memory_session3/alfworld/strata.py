from collections import Counter
from pathlib import Path
import csv,json
P=Path(__file__).resolve().parent
def main():
    tr={r['floorplan'] for r in json.loads((P/'roster.json').read_bytes())['train']}
    r=list(csv.DictReader((P/'transfer_per_episode.csv').open(encoding='utf8')))
    gs={}
    for x in r:
        bucket=('new_floor_official_unseen' if x['episode'].startswith('valid_unseen/') else 'in_our_train' if x['floorplan'] in tr else 'outside_our_train_official_seen')
        gs.setdefault(bucket,{}).setdefault(x['arm'],{})[x['episode']]=(int(x['won']),int(x['capped_steps']),x['floorplan'])
    out={}
    for bucket,arm in gs.items():
        base=arm['all_static']; block={}
        for a,v in arm.items():
            assert base.keys()==v.keys()
            block[a]={'n':len(v),'floors':len({y[2] for y in v.values()}),'won':sum(y[0] for y in v.values()),'mean_steps':sum(y[1] for y in v.values())/len(v),'win_vs_static':sum(v[k][0]>base[k][0] for k in v),'lose_vs_static':sum(v[k][0]<base[k][0] for k in v),'step_difference_vs_static':sum(v[k][1]-base[k][1] for k in v)/len(v)}
        out[bucket]=block
    assert [out[k]['all_static']['n'] for k in ('in_our_train','outside_our_train_official_seen','new_floor_official_unseen')]==[47,93,134]
    (P/'transfer_strata.json').write_text(json.dumps(out,indent=1))
    print({k:v['room_miss'] for k,v in out.items()})
if __name__=='__main__':main()
