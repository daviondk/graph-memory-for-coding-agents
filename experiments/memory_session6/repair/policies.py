from common import *
def allocation(items,prefix):
    ids=[r['id'] for r in items]
    changed={r['id'] for r in items if r['changed']}
    k=len(ids)//2
    assert len(changed)==k
    blind=set(sorted(ids,key=lambda i:sha('blind6|'+str(i)))[:k])
    ranked=sorted(ids,key=lambda i:(-prefix[i]['ambiguity'],sha('uncertain6|'+str(i))))
    uncertain=set(ranked[:k])
    hybrid=set([i for i in ranked if i in changed][:k*3//4]+[i for i in ranked if i not in changed][:k//4])
    controls={'version_note':(changed,'note'),'blind_note':(blind,'note'),'uncertainty_note':(uncertain,'note'),
              'hybrid_note':(hybrid,'note'),'version_raw':(changed,'raw'),'blind_raw':(blind,'raw'),
              'never_note':(set(),'note'),'never_raw':(set(),'raw'),'always_current':(set(ids),'raw')}
    return {a:{i:('current' if i in rereads else carrier) for i in ids} for a,(rereads,carrier) in controls.items()}

