"""Identify every genuine whole-response checksum failure with its recorded path and conflicting coordinates."""
from experiment import D,locations,mem,rows,write
from optimistic import addresses
from experiment import dec
out=[];overlap={}
for p in "ABC":
    projects=set()
    for j in range(8):
        inp,answer,*_=locations(p,j)
        for x,y,tape,stats in zip(rows(inp),rows(answer),rows(D/f"opt_raw_{p}_{j}.jsonl.gz"),rows(D/f"opt_cost_{p}_{j}.jsonl.gz"),strict=True):
            issue,repo,t,path,vr,ss=x;projects.add(repo.lower())
            if not stats[7]:continue
            old=mem(ss["lru"],path,vr);current=dict(y[2]);req=dec(tape[2][tape[3]["optim"][0]])
            wrong=[(n,t-old[n][1]) for n in sorted(set(current)&addresses(req)) if old[n][0]!=current[n].encode()]
            assert wrong
            out.append({"panel":p,"issue":issue,"repo":repo,"t":t,"path":path,"range":vr,"stale_coordinates_and_age":wrong,"rows_reused":stats[6],"extra_bytes_of_second_request_and_reply":stats[10]})
    overlap[p]=projects
write(D/"stale_cases.json",{"panels":{p:sorted(rs) for p,rs in overlap.items()},"A_C_shared_repositories":sorted(overlap['A']&overlap['C']),"B_C_shared_repositories":sorted(overlap['B']&overlap['C']),"cases":out})
print(len(out),[(r["panel"],r["issue"],r["t"],r["path"],r["stale_coordinates_and_age"][:3]) for r in out if r["panel"]=="C"])
