"""Rebuild confirmations by reusing the two source kernels and original opener verbatim."""
import subprocess,sys
from pathlib import Path
from large_panel import HERE,CONF,GP,GT,S,hashfile,save

def compile_native():
    # Only input-size assertions and local include path differ.
    a=(GT/"retrieval.cpp").read_text(encoding="utf8");assert a.count("if(count!=12576)")==1
    b=(GP/"policy.cpp").read_text(encoding="utf8");assert b.count("if(count!=12576||")==1
    (S/"large-retrieval.cpp").write_text(a.replace("if(count!=12576)","if(count!=12000)"),encoding="utf8")
    (S/"large-policy.cpp").write_text(b.replace("if(count!=12576||","if(count!=12000||").replace('"../global_titles/retrieval.cpp"','"large-retrieval.cpp"'),encoding="utf8")
    for n in ("large-retrieval","large-policy"):
        subprocess.run(["g++","-std=c++17","-O2",str(S/(n+".cpp")),"-o",str(S/(n+".exe"))],check=True)
    save(HERE/"kernel.json",{n:hashfile(p) for n,p in dict(retrieval=GT/"retrieval.cpp",policy=GP/"policy.cpp",
                                                effective_retrieval=S/"large-retrieval.cpp",effective_policy=S/"large-policy.cpp").items()})

def project():
    # corpus was previously imported by large_panel, so set WORK/ZIP explicitly for this fresh new process.
    import corpus,open_first,lexicon
    class PathSelection:
        def __truediv__(self,name):return GT/name if name=="retrieval.cpp" else HERE/name
    corpus.WORK=S;corpus.ZIP=S/"para_with_hyperlink.zip";lexicon.WORK=S;open_first.WORK=S;open_first.ROOT=PathSelection()
    open_first.extract()

if __name__=="__main__":{"build":compile_native,"open":project}[sys.argv[1]]()

