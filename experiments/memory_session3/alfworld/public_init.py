"""Fresh environment reset: expose only the instruction and public starting actions to the writer."""
from concurrent.futures import ProcessPoolExecutor
from engine import *
def initial(row):
    env=create(DATA/row['episode']);s=env.reset()
    result={'episode':row['episode'],'observation':s.feedback,'commands':sorted(s.admissible_commands)}
    env.close()
    return result
if __name__=='__main__':
    r=json.loads((ROOT/'roster.json').read_bytes())['valid_unseen']
    with ProcessPoolExecutor(2) as p:outs=list(p.map(initial,r))
    (ROOT/'initial.json').write_text(json.dumps(outs,indent=1))

