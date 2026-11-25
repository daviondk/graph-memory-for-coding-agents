"""Measure resident mmap + actual indexed receipt reads against the original prefix and full postings."""
from pathlib import Path
from statistics import median
from time import perf_counter_ns
import mmap,struct
import numpy as np
from predict import P,D,NULL,get,save
def main(p):
    offsets=get(P/(p+"-offsets.json.gz"));sources=get(P/(p+"-prefix.json.gz"));nexts=get(P/(p+"-targets.json.gz"))
    active={r["id"]:r["events"] for r in sources};probes=[];eventsets={};t0=perf_counter_ns()
    for q,ev in active.items():
        eventsets[q]=[{(path,l,sha) for path,lines in e["r"] for l,sha,_ in lines} for e in ev]
    prep_sets=perf_counter_ns()-t0
    keys=(P/(p+"-keys.bin")).read_bytes();full=(P/(p+"-full.bin")).read_bytes();keyrows={};bitaddr={};bits=bytearray();f=0;ix=bytearray();t0=perf_counter_ns()
    for q,o in sorted(offsets.items(),key=lambda v:v[1]["start"]):
        catalog={};i=o["start"];stride=max(1,(len(o["events"])+7)//8);bitaddr[q]=(len(bits),stride,i)
        for j in range(i,i+o["n"]):
            base=68*j;k=(keys[base:base+32].hex(),struct.unpack_from("<I",keys,base+32)[0],keys[base+36:base+68].hex());catalog[k]=j
            ix.extend(struct.pack("<I",f));n=struct.unpack_from("<I",full,f)[0];posting=struct.unpack_from("<"+"I"*n,full,f+4);bits.extend(sum(1<<e for e in posting).to_bytes(stride,"little"));f+=4*n+4
        keyrows[q]=catalog
    assert f==len(full);prep_idx=perf_counter_ns()-t0;(P/(p+"-full-offsets.bin")).write_bytes(ix);(P/(p+"-bits.bin")).write_bytes(bits)
    for r in nexts:
        q=r["id"];ev=active[q];workers=[e["w"] for e in ev]
        for path,lo,hi in r["future"]:
            target=((path,lo[0],lo[1]),(path,hi[0],hi[1]))
            masks=[{i for i,w in enumerate(workers) if w==wk} for wk in sorted(set(workers))] if p=="swe" else [{i} for i in range(len(ev))]
            for drop in masks:probes.append((q,target,drop,sum(1<<d for d in drop)))
    files={a:open(P/(p+"-"+a+".bin"),"rb") for a in ["distinct_worker","full","full-offsets","bits"]};maps={a:mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) for a,f in files.items()}
    def lookup(method):
        outputs=[]
        for q,pair,drop,dropmask in probes:
            def ranked(k):
                if method=="source_scan":return any(k in obs for i,obs in enumerate(eventsets[q]) if i not in drop)
                j=keyrows[q].get(k)
                if j is None:return False
                if method=="bits":
                    start,stride,base=bitaddr[q];off=start+stride*(j-base);return bool(int.from_bytes(maps["bits"][off:off+stride],"little") & ~dropmask)
                if method=="two":
                    x,y=struct.unpack_from("<II",maps["distinct_worker"],8*j)
                    return x not in drop or y!=NULL and y not in drop
                f=struct.unpack_from("<I",maps["full-offsets"],4*j)[0];n=struct.unpack_from("<I",maps["full"],f)[0]
                return any(i not in drop for i in struct.unpack_from("<"+"I"*n,maps["full"],f+4))
            outputs.append(all(ranked(k) for k in pair))
        return outputs
    names=["source_scan","full","two","bits"];reference=lookup("source_scan")
    for name in names:assert lookup(name)==reference
    times={n:[] for n in names}
    for k in range(33):
        rot=names[k%len(names):]+names[:k%len(names)]
        if (k//len(names))%2:rot=rot[::-1]
        for n in rot:
            st=perf_counter_ns();v=lookup(n);elapsed=perf_counter_ns()-st;assert v==reference
            times[n].append(elapsed/len(v))
    for m in maps.values():m.close()
    for o in files.values():o.close()
    rec=dict(n_probes=len(probes),trues=sum(reference),runs=33,ns_per_pair={n:dict(p50=median(z),p95=float(np.quantile(z,.95))) for n,z in times.items()},shared_quote_key_bytes=len(keys),single_compact_bytes=len(keys)//68*4,actual_two_bytes=(P/(p+"-distinct_worker.bin")).stat().st_size,full_data_bytes=len(full),actual_full_random_access_offset_bytes=len(ix),exact_all_event_bits_bytes=len(bits),bit_group_count=len(bitaddr),max_group_events=max(len(v["events"]) for v in offsets.values()),metadata_table_gzip_bytes=(P/(p+"-offsets.json.gz")).stat().st_size,private_prefix_json_gzip_bytes=(P/(p+"-prefix.json.gz")).stat().st_size,build_all_prefix_ns=sum(r["build_ns"] for r in get(D/(p+"-build-cost.json.gz"))),build_shared_key_dict_and_full_offsets_ns=prep_idx,build_scan_event_sets_ns=prep_sets,conditions="resident, prewarmed maps; original log decoded; scan includes per-message hash sets, ephemeral dict memory not measured; batch/query measurement includes Python overhead")
    save(D/(p+"-physical.json"),rec);print(p,rec)
if __name__=="__main__":
    for p in ["swe","ise"]:main(p)

