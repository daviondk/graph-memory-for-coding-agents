"""Save the fixed reader delimiter tokens for an offline equality check of the entire shared prompt."""
from paths_sem import *
from runtime import enc
def main():
    check();tail=enc("<|im_end|>\n<|im_start|>assistant\n",True)
    c=get(D/"contexts.json.gz");inputs=get(D/"prompts.json.gz")
    for v in c.values():
        p=[inputs[ref[1]] for ref in v["refs"].values()]
        assert all(t[-len(tail):]==tail for t in p)
        prefix=len(p[0])-v["n"]-len(tail)
        assert all(t[:prefix]==p[0][:prefix] for t in p)
    put(D/"reader-boundaries.json",dict(tail=tail,first_tokens=sum(z["first"] for z in c.values()),
        second_tokens=sum(z["n"] for z in c.values()),prompt_tokens=sum(z["refs"]["true"][2] for z in c.values()),
        shortened=sum(z["n"]<z["old_n"] for z in c.values()),logical_document_reads_per_arm=2*len(c)))
if __name__=="__main__":main()
