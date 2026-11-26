import argparse
from paths_a import *
def main():
    p=argparse.ArgumentParser();p.add_argument("stage",choices=["input","answer"]);stage=p.parse_args().stage
    check()
    if stage=="input":
        import inputs_sem
        inputs_sem.main()
    else:
        import generate as module
        assert sha(Path(module.__file__))==get(R49/"manifest.json")["files"]["generate.py"]
        module.D=D;module.P=P;module.main()
if __name__=="__main__":main()
