"""Retain the binary-tokenizer comparator on D before individually tokenizing every text."""
from common import *
def main():
    src=OUT/"matched-tokens.json.gz";rec=OUT/"matched-token-seal.json";meta=read(rec);assert meta.get("observed_special_spellings",0)>0 and sha(src)==meta["forecasts_input"]
    folder=CACHE/"runs-r40-lexical-byte-input";folder.mkdir(exist_ok=True)
    target=folder/src.name
    if target.exists():assert sha(target)==sha(src)
    src.replace(target)
    pre=CACHE/"runs-r40-lexical-separator-preflight";pre.mkdir(exist_ok=True);rep=pre/rec.name
    if rep.exists():
        assert read(rep)["forecasts_input"]==meta["forecasts_input"] and read(rep)["program"]==meta["program"]
    else:rep.write_bytes(rec.read_bytes())
    print("Preserved hash-bound private CPU token comparison.")
if __name__=="__main__":main()
