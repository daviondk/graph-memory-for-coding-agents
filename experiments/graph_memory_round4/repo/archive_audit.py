"""Check exact stimuli shared with earlier panels; random ranks independently give E(acc@k)=min(k,n)/n."""
from data_io import *
from collections import defaultdict
from struct import pack

def stimulus(code,docs):
    h=hashlib.sha256()
    for s in [code,*docs]:
        b=s.encode();h.update(pack(">I",len(b)));h.update(b)
    return h.digest()
def scan(paths,roster=None):
    repo=set();stim=set();codes=set();means=defaultdict(lambda:[0.]*5);invalid=0;details=[]
    for p in paths:
        select=None if roster is None else {j for j,_ in roster[p.stem]}
        for j,r in enumerate(rows(p,["repo_name","code","context","gold_snippet_index"])):
            if select is not None and j not in select:continue
            panel=panel_name(p.stem);code=r["code"];docs=r["context"];n=len(docs);repo.add(r["repo_name"]);h=stimulus(code,docs);c=hashstr(code);codes.add(c);stim.add(h);details.append((r["repo_name"],h,c))
            a=means[panel];a[0]+=1;a[1]+=n
            for i,k in enumerate((1,3,5)):a[2+i]+=min(n,k)/n
            invalid+=int(not 0<=r["gold_snippet_index"]<n)
    return {"repos":repo,"stim":stim,"codes":codes,"means":{k:[int(v[0])]+[y/v[0] for y in v[1:]] for k,v in means.items()},"details":details,"invalid":invalid}
def main():
    archive=scan(sorted((D/"archive_inputs").glob("*.parquet")))
    hf=scan(files("java","test"));train=scan(files("java","train"),read("roster.json"))
    def summary(a):return {"rows":len(a["details"]),"repos":len(a["repos"]),"unique_stim":len(a["stim"]),"invalid":a["invalid"],"means":a["means"]}
    def compare(a,b):return {"common_project_ids":len(a["repos"]&b["repos"]),"common_unique_stimuli":len(a["stim"]&b["stim"]),"common_unique_code":len(a["codes"]&b["codes"]),"rows_of_a_with_project_in_b":sum(z[0] in b["repos"] for z in a["details"]),"rows_of_a_with_stim_in_b":sum(z[1] in b["stim"] for z in a["details"]),"rows_of_a_with_code_in_b":sum(z[2] in b["codes"] for z in a["details"])}
    out={"archive":summary(archive),"hf":summary(hf),"train":summary(train),"archive_vs_hf":compare(archive,hf),"archive_vs_train":compare(archive,train),"sha_archives":{p.name:sha(p) for p in (D/"inputs").glob("archive_cross_file*.gz")},"sha_converted":{p.name:sha(p) for p in (D/"archive_inputs").glob("*.parquet")}}
    write("archive_audit.json",out);print(json.dumps({k:v for k,v in out.items() if k.startswith("archive_vs")}))
if __name__=="__main__":main()
