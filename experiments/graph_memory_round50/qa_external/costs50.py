"""Audit the same llama.cpp timing report as the previous Qwen experiment."""
from paths50 import *
def main():
    import cost
    assert sha(Path(cost.__file__))==get(R49/"manifest.json")["files"]["cost.py"]
    cost.D=D50;cost.P=P50;cost.main()
if __name__=="__main__":main()
