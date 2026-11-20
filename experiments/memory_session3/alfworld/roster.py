from pathlib import Path
import hashlib,json,zipfile
from collections import Counter
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parents[3]
DATA=BASE/'x20-session3-alfgames'/'json_2.1.1'
KINDS=('pick_and_place_simple','look_at_obj_in_light','pick_clean_then_place_in_recep','pick_heat_then_place_in_recep','pick_cool_then_place_in_recep','pick_two_obj_and_place')
def build():
    with zipfile.ZipFile(BASE/'x20-session3-alfmeta.zip') as meta:
        result={}
        for split in ('train','valid_unseen'):
            roster=[]
            for g in sorted((DATA/split).glob('*/*/game.tw-pddl')):
                path=g.relative_to(DATA).as_posix()
                if 'movable' in path or 'Sliced' in path:continue
                key='json_2.1.1/'+path.replace('game.tw-pddl','traj_data.json')
                try:m=json.loads(meta.read(key))
                except KeyError:continue
                if m['task_type'] not in KINDS or not json.loads(g.read_bytes()).get('solvable'):continue
                roster.append({'episode':path,'family':m['task_type'],'floorplan':str(m['scene']['scene_num']),'game_sha':hashlib.sha256(g.read_bytes()).hexdigest()})
            roster.sort(key=lambda r:hashlib.sha256(('s3-alfworld-'+r['episode']).encode()).hexdigest())
            result[split]=roster[:39] if split=='train' else roster
    (ROOT/'roster.json').write_text(json.dumps(result,indent=1))
    print({s:(len(v),dict(Counter(r['family'] for r in v))) for s,v in result.items()})
if __name__=='__main__':build()
