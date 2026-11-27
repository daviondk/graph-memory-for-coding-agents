"""Decode the exact saved first prompts before auditing historical input reuse."""
import sys
from solve import HERE, common, read, save


def decode(url,session):
    inputs=read("inputs.json.gz")
    assignments=read("draft-design.json.gz")["assign"]
    snippets={}
    for q,h in assignments.items():
        r=session.post(url+"/detokenize",json={"tokens":inputs[h]},timeout=30)
        r.raise_for_status()
        full=r.json()["content"]
        prefix="\nPreviously observed test source from this repository:\n"
        before,mark,tail=full.partition(prefix)
        assert mark
        content,last,end=tail.partition("<|im_end|>")
        assert last
        snippets[q]=content
    save("draft-visible.json.gz",snippets)


if __name__=="__main__":
    if "--live" in sys.argv:
        with common.session() as session:
            decode("http://127.0.0.1:18958",session)
    else:
        common.RUN=HERE
        with common.server(common.READER,["--parallel","1","--ctx-size","4096","--flash-attn","on","--threads","4"],
                           "tokenizer",18958) as (url,session,_):
            decode(url,session)
