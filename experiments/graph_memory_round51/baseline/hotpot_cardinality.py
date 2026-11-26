"""Exactly the registered feature formulas for any positive number of unexpanded titles."""
import numpy as np

def features(rank,lex):
    ids=rank["order"]
    assert len(ids)==len(set(ids))>0 and rank["seed"]==lex["seed"]
    assert ids[0]==rank["dense"] and set(rank["edges"])==set(map(int,lex["edges"]))
    return np.array([[rank["scores"][str(idx)],1/(1+lex["question_rank"][str(idx)]),
                      1/(1+lex["snippet_rank"][str(idx)]),1/(1+j),float(idx in rank["edges"])]
                     for j,idx in enumerate(ids)])
