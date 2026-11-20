import gzip,statistics
from collections import Counter,defaultdict
import numpy as np
from writer import HERE,rows,pack,jsonbytes,read,save
def main():
    by=defaultdict(list)
    for k in range(8):
        for stem in ("cuts","rich_cuts"):
            for i,t,states in rows(HERE/f"{stem}_{k}.jsonl.gz"):
                for tag,b,digest,x in states:
                    textonly=[[p,[[lo,ls] for lo,age,ls in runs]] for p,info,runs in x[2]]
                    nlines=sum(len(lines_) for p,info,runs in x[2] for lo,age,lines_ in runs)
                    by[f"{tag}@{b}"].append([len(pack(x)),len(jsonbytes(x)),len(pack(textonly)),nlines])
    sizes={}
    for k,rows_ in by.items():
        a=np.array(rows_);sizes[k]={"mean_compressed":a[:,0].mean(),"mean_uncompressed":a[:,1].mean(),"mean_counterfactual_with_line_addresses_but_without_metadata":a[:,2].mean(),"mean_lines":a[:,3].mean(),"ratio_of_mean_raw_to_compressed":a[:,1].sum()/a[:,0].sum()}
    main_t=read(HERE/"timing.json");rich=read(HERE/"rich_timing.json");events=sum(j["events"] for j in main_t);tt=Counter()
    for v in main_t:tt.update(v["transition_ns"])
    tt["rich_lru"]=sum(v["transition_ns"] for v in rich)
    timings={k:v/(2*events)/1e6 for k,v in tt.items()}
    save("size_audit.json",dict(checkpoints=sum(len(v) for v in by.values()),sizes=sizes,mean_wall_ms_per_transition_local_parallel=timings))
if __name__=="__main__":main()
