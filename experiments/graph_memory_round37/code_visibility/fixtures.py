"""Synthetic placeholders check the scanner, masks and line shifts without executing code."""
from predict import memory
from project import locate,numbered,h,D,save

def run():
    assert locate({3:"aaa",4:"bbb",5:"ccc"},"a\nbb")==3
    assert locate({3:"aaa",4:"bbb",5:"ccc"},"aa") is None
    assert locate({3:"a",5:"b"},"a\nb") is None
    assert locate({3:"alpha",4:"beta"},"") is None
    assert locate({3:"alpha",4:"beta"},"eta")==4
    P="/testbed/example/module.py"
    assert numbered("Here's the result of running \x60cat -n\x60 on "+P+":\n     3\talpha\n     4\tbeta",P,False)=={3:"alpha",4:"beta"}
    assert numbered("Here's the result of running \x60cat -n\x60 on "+P+":\n     3\talpha","another.py",False)=={}
    examples=[]
    for old,new,start in [(["AAA","BBB"],["CC","DD","EE"],5),(["AAA","BBB"],["CCC"],3),(["AAA"],["ZZZ"],9)]:
        before=[f"line-{i}" for i in range(1,15)]
        before[start-1:start-1+len(old)]=old
        after=before[:start-1]+new+before[start-1+len(old):]
        past=[[i+1,h(x)] for i,x in enumerate(before)]
        edit={"k":start,"old_breaks":len(old)-1,"delta":len(new)-len(old),
              "rows":[[i+start,h(x)] for i,x in enumerate(new)]}
        out=memory("example/module.py",past,edit)
        assert out["T"]=={i+1:h(x) for i,x in enumerate(after)}
        assert len(out["H"])==len(out["Tstar"])
        assert out["F"]==dict(edit["rows"])
        examples.append({"delta":edit["delta"],"anchored_exact":True})
    bad=memory("example/module.py",[[1,h("a")]],{"k":None,"old_breaks":None,"delta":1,"rows":[[3,h("b")]]})
    assert bad["F"]==bad["T"]==bad["H"]
    save(D/"fixtures.json",dict(parser_cases=7,invalid_anchor=1,roundtrip_edits=examples))
if __name__=="__main__":run()
