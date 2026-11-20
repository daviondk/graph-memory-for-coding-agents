"""Post hoc descriptive comparison against the earlier menu-based actor on matched games."""
import collections,csv,gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()))
def main():
    by_pair=collections.defaultdict(list)
    for f in sorted((ROOT/'eval').glob('*.gz')):
        text=read(f);old=read(ROOT.parent/'traces'/f.name)
        for arm,menu in [('none','none'),('cursor','cursor'),('full','full'),('trained','raw')]:
            o=next(x for x in old if x['arm']==menu);t=next(x for x in text['records'] if x['arm']==arm)
            assert o['episode']==text['episode']
            oc=[x['command'] for x in o['steps']];tc=[x[0] for x in t['steps']]
            by_pair[arm].append({'episode':text['episode'],'old_ok':int(o['steps'][-1]['won']),'new_ok':int(t['steps'][-1][2]),
                'old_steps':len(oc),'new_steps':len(tc),'identical':oc==tc})
    assert all(len(v)==134 for v in by_pair.values())
    stats={}
    for arm,rows in by_pair.items():
        stats[arm]={'n':len(rows),'identical_action_sequence':sum(r['identical'] for r in rows),
            'menu_wins':sum(r['old_ok'] for r in rows),'text_wins':sum(r['new_ok'] for r in rows),
            'menu_only':sum(r['old_ok']>r['new_ok'] for r in rows),'text_only':sum(r['old_ok']<r['new_ok'] for r in rows),
            'mean_new_minus_old_steps':sum(r['new_steps']-r['old_steps'] for r in rows)/len(rows)}
    (ROOT/'interface_comparison.json').write_text(json.dumps(stats,indent=1),encoding='utf8')
    print(stats)
if __name__=='__main__':main()
