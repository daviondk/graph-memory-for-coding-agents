"""Redirect the frozen R49 token packer and generator to the isolated R50 paths."""
import argparse
from paths50 import *
def main():
    p=argparse.ArgumentParser();p.add_argument("stage",choices=["input","answer"]);a=p.parse_args()
    check50()
    if a.stage=="input":import inputs as module
    else:import generate as module
    assert sha(Path(module.__file__))==get(R49/"manifest.json")["files"][Path(module.__file__).name]
    module.D=D50;module.P=P50;module.check=check50
    module.main()
if __name__=="__main__":main()
