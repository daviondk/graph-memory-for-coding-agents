"""Strictly project observed history and buggy source into the solver's input artifact."""
from common import *
def main():
    lock=read('input_lock.json')
    assert freeze(lock['files'])==lock['files']
    bundle={}
    for r in read('roster.json'):
        if r['eligible']:
            f=read('fixtures/'+r['name']+'.json')
            bundle[r['name']]={'buggy_source':f['buggy_source'],'memory':f['memory']}
            assert not {n['key'] for n in f['notes']} & {c['key'] for c in f['cases'] if c['part']=='future'}
    save('solver_inputs.json',bundle)
    paths=['project.py','solver_inputs.json','schedule.json','solve.py','grade.py','PROTOCOL.md','input_lock.json']
    save('solver_lock.json',{'utc':utc(),'files':freeze(paths)})
if __name__=='__main__':main()

