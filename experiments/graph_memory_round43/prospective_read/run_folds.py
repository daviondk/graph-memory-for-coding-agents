"""Use a new interpreter per outer fold; freeze all predictions before opening any for scoring."""
import subprocess,sys
from common import *
def main():
    fs=read(D/"feature-seal.json");seals={}
    for repo in fs["repos"]:
        subprocess.run([sys.executable,"-B","-u",str(D/"rank.py"),repo],check=True)
        path="seal-"+repo[:12]+".json";seals[repo]=sha(D/path)
    save("rank-seal.json",dict(folds=seals,registered=sha(D/"PROTOCOL_RU.md"),code=sha(D/"run_folds.py")))
    print("All five outer repository forecasts sealed.")
if __name__=="__main__":main()

