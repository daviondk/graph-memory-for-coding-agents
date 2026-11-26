"""Seal chosen catalogue addresses before accessing the support-title annotations."""
from collections import Counter
from corpus import ROOT, WORK, read, save, hashfile
from lexicon import tokens

ARMS = ["free", "question_bm25", "text", "href", "union", "text_first", "href_first"]
FILES = ["predictions.json.gz", "chosen-titles.json.gz"]

def contains(words, text):
    return bool(words) and any(text[i:i+len(words)] == words for i in range(len(text)))

def main():
    first = {p[0]: list(map(int, p[1:])) for p in
             (s.split("\t") for s in (WORK/"seed.tsv").read_text().splitlines())}
    predictions = {}
    chosen = set()
    for line in (WORK/"second.tsv").read_text().splitlines():
        q, *fields = line.split("\t")
        seed, *tail = map(int, fields)
        choices, counts = tail[:len(ARMS)], tail[len(ARMS):]
        assert seed == first[q][0] and seed not in choices and q not in predictions and len(counts)==4
        predictions[q] = [seed, first[q][2], choices, counts]
        chosen.update([seed,first[q][2],*choices])
    assert set(first)==set(predictions)==set(read(WORK/"questions.json.gz")) and len(first)==12576
    names = {}
    with (WORK/"titles.txt").open(encoding="utf8") as f:
        for row,line in enumerate(f):
            if row in chosen:
                wiki,title=line.rstrip("\n").split("\t",1)
                names[row]=[int(wiki),title]
    assert set(names)==chosen
    opened = read(WORK/"opened.json.gz")
    examples = {}
    for q,(seed, rawseed, choices, counts) in predictions.items():
        assert names[seed][0]==first[q][1]
        h=choices[ARMS.index("href")]
        source=opened[str(seed)]
        assert names[seed][1]==source["title"] and len(source["links"])==counts[2]
        anchors=source["links"].get(str(h),[])
        words=tokens(names[h][1]); prefix=tokens(source["prefix"])
        literal=contains(words,prefix)
        equal=any(tokens(a[2])==words for a in anchors)
        for lo,hi,anchor,*rest in anchors:
            assert source["prefix"][lo:hi]==anchor
        predictions[q].append([bool(anchors),literal,equal])
        if anchors and not literal and choices[ARMS.index("text")]!=h:
            examples[q]={"seed":source["title"],"title":names[h][1],"anchor":anchors[0][2]}
    save(ROOT/FILES[0],predictions)
    save(ROOT/FILES[1],names)
    save(ROOT/"anchors.json.gz",examples)
    seal_names = [*FILES, "anchors.json.gz", "source.json", "lexicon.json","opening.json",
                  "PROTOCOL_RU.md","corpus.py","lexicon.py","retrieval.cpp","open_first.py","seal.py"]
    save(ROOT/"prediction-seal.json",dict(arms=ARMS,n=len(first),chosen=len(names),
         raw_output=hashfile(WORK/"second.tsv"),files={k:hashfile(ROOT/k) for k in seal_names}))

if __name__=="__main__":main()

