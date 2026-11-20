from collections import defaultdict
from data_io import *

def main():
    old=read("roster.json");earlier=read("validation_roster.json")
    used=set();projects={}
    for p in files("java","test"):
        projects[p]=pq.read_table(p,columns=["repo_name"]).column(0).to_pylist()
        used.update(projects[p][j] for j,_ in old[p.stem])
    chosen=defaultdict(list);remaining=defaultdict(list)
    for key in sorted({panel_name(p.stem) for p in projects}):
        offset=0
        for p,repos in projects.items():
            if panel_name(p.stem)!=key:continue
            initial=dict(earlier.get(p.stem,[]))
            for j,r in enumerate(repos):
                if r in used:continue
                ids=(p.stem,j,j+offset,r)
                if j in initial:chosen[key].append(ids)
                else:remaining[key].append(ids)
            offset+=len(repos)
        remaining[key].sort(key=lambda s:hashstr(f"add|{s[0]}|{s[2]}"),reverse=True)
    base=sum(map(len,chosen.values()))
    while sum(map(len,chosen.values()))<1000:
        before=sum(map(len,chosen.values()))
        for k in sorted(remaining):
            if remaining[k] and sum(map(len,chosen.values()))<1000:chosen[k].append(remaining[k].pop())
        assert sum(map(len,chosen.values()))>before
    parts=defaultdict(list);picked={}
    for key,s in chosen.items():
        for stem,j,idx,r in s:parts[stem].append([j,idx])
        picked[key]=sorted(x[2] for x in sorted(s,key=lambda i:hashstr(f"pairedstrong|{key}|{i[2]}"))[:80])
        assert len(picked[key])==80
    check={r for group in chosen.values() for _,_,_,r in group}
    assert not used&check
    write("strict_roster.json",parts);write("paired_roster.json",picked)
    write("strict_roster_audit.json",{"rows":1000,"existing_safe_component_of_validation":base,"repos":len(check),"overlap_base_repos":len(used&check),"counts":{q:len(s) for q,s in chosen.items()},"paired_projects":len({r for key,s in chosen.items() for _,_,i,r in s if i in picked[key]})})
if __name__=="__main__":main()
