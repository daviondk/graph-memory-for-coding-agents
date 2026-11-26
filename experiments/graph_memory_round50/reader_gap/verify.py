import json
from decompose import D,calculate
if __name__=="__main__":
    assert calculate()==json.loads((D/"results.json").read_bytes())
    print("Reproduced both paired decompositions and all denominators over 640 shared questions.")

