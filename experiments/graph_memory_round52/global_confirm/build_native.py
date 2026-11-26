"""Compile upstream retrieval operators unchanged, adapting only output count and include path."""
import subprocess
from panel import HERE,GT,GP,S,hashfile,save
def main():
    cpp=(GT/"retrieval.cpp").read_text(encoding="utf8")
    assert cpp.count("if(count!=12576)")==1
    (S/"confirm-retrieval.cpp").write_text(cpp.replace("if(count!=12576)","if(count!=2400)"),encoding="utf8")
    pol=(GP/"policy.cpp").read_text(encoding="utf8")
    assert pol.count("if(count!=12576||")==1 and pol.count('"../global_titles/retrieval.cpp"')==1
    (S/"confirm-policy.cpp").write_text(pol.replace("if(count!=12576||","if(count!=2400||").replace('"../global_titles/retrieval.cpp"','"confirm-retrieval.cpp"'),encoding="utf8")
    for n in ("confirm-retrieval","confirm-policy"):
        subprocess.run(["g++","-O2","-std=c++17",str(S/(n+".cpp")),"-o",str(S/(n+".exe"))],check=True)
    save(HERE/"kernel.json",{n:hashfile(p) for n,p in dict(retrieval=GT/"retrieval.cpp",policy=GP/"policy.cpp",
                                                    effective_retrieval=S/"confirm-retrieval.cpp",effective_policy=S/"confirm-policy.cpp").items()})
if __name__=="__main__":main()

