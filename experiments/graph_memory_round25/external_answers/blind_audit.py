"""Recompute the four clean prompts from gold-free input, and audit every native and coordinate receipt."""
from collections import Counter
from prepare import D,PRIVATE,read,write,h,sha,generate,make_fields,render,Tokenizer,TOK,QWT
def main():
    plan=read(D/"input-lock.json")
    view=read(PRIVATE/"blind-view.json.gz");assert sha(PRIVATE/"blind-view.json.gz")==plan["blind_view"]
    allowed={"title","abstract","full_text","figures_and_tables","q"}
    assert all(set(d)==allowed and len(d["q"])==2 for d in view.values())
    assert all(set(z)<= {"section_name","paragraphs"} for d in view.values() for z in d["full_text"])
    assert all(set(z)<= {"file","caption"} for d in view.values() for z in d["figures_and_tables"])
    wp=Tokenizer.from_file(str(TOK));qw=Tokenizer.from_file(str(QWT));r,msgs=generate(view,wp,qw)
    assert r==read(D/"contexts.json.gz") and msgs==read(PRIVATE/"requests.json.gz")
    costs=[];identical=Counter();edge_points=0;scopes=0
    for q,item in r.items():
        d=view[item["doc"]];f,_=make_fields(d);b=item["base"];q_,question=d["q"];assert q_==q
        a=item["arms"];btext=msgs[a["base"]["key"]];slots=[a[k]["qwen_user"] for k in ("replay","old","edge")]
        assert len(set(slots))==1;costs.append(slots[0]-a["base"]["qwen_user"])
        for k,v in a.items():
            text=msgs[v["key"]]
            assert text.startswith(btext) and h(text)==v["key"]
            assert len(qw.encode(text,add_special_tokens=False).ids)==v["qwen_user"]
            assert v["wp_extra"]<=256
            for e,l,z in v["opened"]:
                assert 0<=l<z<=len(f[e]);assert f[e][l:z] in text[len(btext):];scopes+=1
                if k=="replay":assert any(g==e and x<=l<z<=y for g,x,y in b)
            if k=="edge" and v["opened"]:
                e,l,_=v["opened"][0];assert [e,l]==item["anchors"]["right_edge"]
                assert any(e==g and y==l for g,x,y in b)
                assert not any(e==g and x<=l<y for g,x,y in b);edge_points+=1
            for k2 in a:
                if k<k2 and v["key"]==a[k2]["key"]:identical[k+"/"+k2]+=1
    write(D/"blind-audit.json",dict(input_lock=sha(D/"input-lock.json"),reproducible_prompts=len(msgs),audited_arms=len(r)*4,
           label_fields_in_view=0,all_native_user_token_matched=True,min_extra_qwen=min(costs),max_extra_qwen=max(costs),
           mean_extra_qwen=sum(costs)/len(costs),unique_source_receipts=scopes,edge_with_new_first_character=edge_points,
           identical_prompts=identical,code=sha(__file__ if hasattr(__file__,"read_bytes") else D/"blind_audit.py")))
    print(len(r),edge_points,identical)
if __name__=="__main__":main()
