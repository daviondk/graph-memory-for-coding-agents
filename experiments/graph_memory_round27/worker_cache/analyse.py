"""Validate decisions and aggregate process-boundary traffic and latency."""
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median,fmean
ROOT=Path(__file__).resolve().parent
def quantile(sample,p):
    data=sorted(sample);i=(len(data)-1)*p
    low=int(i);return data[low]+(i-low)*(data[min(low+1,len(data)-1)]-data[low])
def compute():
    receipt=json.loads((ROOT/"receipt.json").read_bytes())
    data=(ROOT/"responses.json.gz").read_bytes()
    assert hashlib.sha256(data).hexdigest()==receipt["responses"]
    rows=json.loads(gzip.decompress(data))
    assert len(rows)==receipt["actual"]==22176
    assert len(set(receipt["worker_pids"])|{receipt["parent"]})==5
    groups=defaultdict(lambda:defaultdict(list));decisions={}
    for rep,method,cap,route,sid,q,w,win,wire,payload,miss,ns,ns_total in rows:
        assert decisions.setdefault((sid,q),win)==win
        groups[f"{method}/{cap}/{route}"][sid,q].append((wire,payload,miss,ns/1000,ns_total/1000,w))
    assert len(decisions)==receipt["distinct"]==528
    stats={}
    for key,queries in groups.items():
        assert len(queries)==528
        pairs=[]
        for values in queries.values():
            assert len(values)==3
            assert all(x[:3]==values[0][:3] and x[-1]==values[0][-1] for x in values)
            pairs.append([median(item[i] for item in values) for i in range(6)])
        balance=Counter(int(r[-1]) for r in pairs);assert list(sorted(balance.values()))==[132]*4
        stats[key]={"requests":528,"mean_sql_bytes":fmean(r[0] for r in pairs),
                    "mean_payload_bytes":fmean(r[1] for r in pairs),"misses":int(sum(r[2] for r in pairs)),
                    "p50_service_us":median(r[3] for r in pairs),"p50_rpc_us":median(r[4] for r in pairs),
                    "p95_rpc_us":quantile([r[4] for r in pairs],.95)}
    return stats
if __name__=="__main__":
    stats=compute()
    (ROOT/"results.json").write_text(json.dumps(stats,sort_keys=True,indent=2)+"\n",encoding="utf8")
    for key,row in sorted(stats.items()):
        print(key,*(round(row[k],1) for k in ("mean_sql_bytes","mean_payload_bytes","misses","p50_rpc_us","p95_rpc_us")))

