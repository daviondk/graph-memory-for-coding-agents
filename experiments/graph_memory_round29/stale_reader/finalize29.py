"""Once sealed, derive all statistics from recorded results and verify the public file inventory."""
from setup29 import D,P,Path,sha,save,read
import subprocess,sys,time
def main():
    start=time.monotonic()
    while not ((D/"judge-forecast-seal.json").exists() and (P/"peer-ratings.json").exists()):
        if time.monotonic()-start>7200:raise TimeoutError("waiting for judge or external anonymous review")
        time.sleep(4)
    for args in (["score29.py"],["candidate_audit29.py","score"],["audit_judge29.py"],["use_by_evidence29.py"],["render29.py"]):
        subprocess.run([sys.executable,"-B",*args],check=True,cwd=D)
    public={p.name:sha(p) for p in D.iterdir() if p.is_file() and p.name!="MANIFEST_SHA256.json"}
    save(D/"MANIFEST_SHA256.json",public)
    assert all(sha(D/name)==v for name,v in read(D/"MANIFEST_SHA256.json").items())
    print("MANIFEST",sha(D/"MANIFEST_SHA256.json"),len(public))
if __name__=="__main__":main()
