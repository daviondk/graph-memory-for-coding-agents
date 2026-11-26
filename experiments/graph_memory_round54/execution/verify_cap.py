"""Audit the 768-token sensitivity without rerunning completed primary outputs."""
from study import *
def main():
    reg=get("cap-registration.json");seal=get("cap-answer-seal.json");receipt=get("cap-grade-seal.json")
    checks=[(reg,"code","cap.py"),(reg,"protocol","CAP_PROTOCOL_RU.md"),(seal,"answers","cap-answers.json.gz"),
        (seal,"registration","cap-registration.json"),(seal,"checks","cap-token-replay.json.gz"),(receipt,"records","cap-records.json.gz"),
        (receipt,"tests","cap-unittest.json.gz"),(receipt,"results","cap-results.json"),(receipt,"primary","grade-seal.json")]
    for doc,k,file in checks:assert doc[k]==sha(D/file)
    primary=get("answers.json.gz");extended=get("cap-answers.json.gz");log=get("cap-token-replay.json.gz")
    assert set(extended)=={k for k,v in primary.items() if v["stop"]=="limit"}
    for k,v in extended.items():
        assert v['code'].startswith(primary[k]['code']) and log[k]['short_ids']==log[k]['long_ids'][:384] and len(log[k]['short_ids'])==384
    ctx=get("contexts.json.gz");old=get("records.json.gz");new=get("cap-records.json.gz");result=get("cap-results.json");raw=get("cap-unittest.json.gz")
    changes={}
    for q,r in ctx.items():
        for arm,(_i,h,_n) in r["refs"].items():
            if h not in extended:assert new[q][arm]==old[q][arm]
            else:
                key=q+"|"+h;v=raw['raw'].get(key,{})
                assert new[q][arm]['pass1']==int(v.get('passed',False) and v.get('run')==new[q][arm]['total'])
                if old[q][arm]!=new[q][arm]:changes.setdefault(q,{})[arm]=[old[q][arm],new[q][arm]]
    for arm in ARMS:assert sum(r[arm]['pass1'] for r in new.values())==result['summaries'][arm]['passed']
    report=dict(original_unique=len(primary),extended=len(extended),verified_native_prefixes=len(extended),replayed_eos=len(reg["eos"]),
                changed_records=changes,verified_methods=len(ctx),code=sha(Path(__file__)))
    put("cap-audit.json",report);print(len(changes),"methods with changed detailed records")
if __name__=="__main__":main()
