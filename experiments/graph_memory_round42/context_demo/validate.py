from pathlib import Path
import json
from server import query,SCENARIOS,MODES
D=Path(__file__).resolve().parent
if __name__=="__main__":
    ref=json.loads((D/"reference.json").read_bytes());n=0;lines=0
    for case in SCENARIOS:
        for mode in MODES:
            for cap in (512,1024,2048):
                r=query(case,mode,cap,True)
                assert sum(b["bytes"] for b in r["blocks"] if b["id"] in r["selected"])<=cap
                assert not r["audit"]["mismatches"]
                lines+=r["audit"]["lines"]
                if cap==2048:
                    assert r["prior"]==ref[case]["prior"] and r["selected"]==ref[case][mode]
                n+=1
    print(n,"responses checked;",lines,"selected-line checks.")
