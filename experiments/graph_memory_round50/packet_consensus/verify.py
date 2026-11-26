from grade_packets import grade,analysis,D,read,sha
from run import PROTOCOL
if __name__=="__main__":
    assert sha(D/"PROTOCOL_RU.md")==PROTOCOL
    assert sha(D/"run.py")==read(D/"forecast-seal.json")["code"]
    obs=grade()
    assert obs==read(D/"outcomes.json.gz")
    assert analysis(obs)==read(D/"results.json")
    from cost_match import REG,study_data,STREAM
    assert sha(D/"BUDGET_CONTROL_RU.md")==REG
    assert sha(D/"budget-packets.json.gz")==read(D/"budget-seal.json")["forecasts"]
    from pathlib import Path
    import hashlib
    costs=read(D.parent/"matched_reader/pool.json.gz");spans=study_data(STREAM,"judgments.json.gz")
    additional=read(D/"budget-outcomes.json.gz");count=0
    for q,(t,panels) in read(D/"budget-packets.json.gz").items():
        gold=spans[hashlib.sha256(q.encode()).hexdigest()]
        total=sum(w for w,ids in gold)
        for cp,packets in enumerate(panels):
            for name,ids in packets.items():
                token=sum(costs[q]["c"][i] for i in ids)
                covered=sum(w for w,src in gold if set(ids).intersection(src))
                assert additional[q][1][cp][name]==[int(covered==total),covered/total,token]
                count+=1
    print("Regraded all original packets, bootstrap intervals and",count,"matched-budget packets.")

