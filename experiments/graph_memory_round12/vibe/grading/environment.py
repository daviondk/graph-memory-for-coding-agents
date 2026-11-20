"""Record IDs of the two existing, locally loaded evaluator images."""
from pathlib import Path
import subprocess,json
from audit import HERE,VIBE,REL,put,load
def command(*args):return subprocess.run(args,check=True,stdout=subprocess.PIPE,text=True).stdout.strip()
def main():
    out=[]
    for t in load(VIBE/"cohort.json")["targets"]:
        r=json.loads(command("wsl.exe","-d","CodexX20MSR","--exec","docker","image","inspect",t["image_name"]))[0]
        out.append(dict(instance=t["instance_id"],image=t["image_name"],local_id=r["Id"],repo_digests=r.get("RepoDigests"),architecture=r.get("Architecture"),os=r.get("Os")))
    put(HERE/"environment.json",dict(images=out,docker=command("wsl.exe","-d","CodexX20MSR","--exec","docker","version","--format","{{.Server.Version}}"),
                 wsl="CodexX20MSR",network="none",cpu_per_container=0.5,workers=1,source_ledger=load(VIBE.parents[1]/"sota_round/vibe/provenance.json")["sources"]))
if __name__=="__main__":main()
