import argparse
import importlib.util
from paths_repl import *

def main():
    p=argparse.ArgumentParser();p.add_argument("stage",choices=["input","answer"]);stage=p.parse_args().stage
    check()
    if stage=="input":
        spec=importlib.util.spec_from_file_location("replication_inputs",D/"inputs_repl.py")
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.ARMS=["true","lex","sham47011"];module.SEEDS=[47011]
    else:
        import generate as module
        assert sha(Path(module.__file__))==get(R49/"manifest.json")["files"]["generate.py"]
    module.D=D;module.P=P;module.check=check;module.main()
if __name__=="__main__":main()
