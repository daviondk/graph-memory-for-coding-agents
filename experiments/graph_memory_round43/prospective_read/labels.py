"""Build five disjoint label files. A fold's ranker gets only the other four."""
from collections import Counter
from common import *


def main():
    rows=read(D/"features.json.gz");seal=read(D/"feature-seal.json")
    assert seal["features"]==sha(D/"features.json.gz")
    demand=bind(F,"requests.json.gz");packets=bind(F,"packets.json.gz")
    repo_rows={repo:{} for repo in seal["repos"]}
    for k,r in rows.items():
        run=packets[k]["run"];w=demand["windows"][k];future=Counter()
        for at in w["reads"]:
            v=demand["by_run"][run][str(at)]
            future.update({(n,d):1 for n,d,_ in v})
        matches={str(b["idx"]):sum(future[(n,d)] for n,d,_ in b["novel"]) for b in r["blocks"] if b["target"] and b["novel"]}
        repo_rows[r["repo"]][k]=dict(matches=matches)
    files={}
    for repo,part in repo_rows.items():
        path="labels-"+repo[:12]+".json.gz";save(path,part);files[repo]=[path,sha(D/path)]
    save("label-seal.json",dict(files=files,requests=sha(F/"requests.json.gz"),features=sha(D/"feature-seal.json"),
                               code=sha(D/"labels.py")))
    print("Saved five repository-isolated supervision files.")


if __name__=="__main__":main()

