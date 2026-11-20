"""Project old observations and later read queries into physically separate files."""
from common import ROOT,R9,PANELS,put,load,sha
def main():
    refs={}
    for dp in PANELS:
        src=R9/dp;p=src/'graphs.json.gz'
        refs[str(p)]=sha(p)
        for graph in load(p):
            t=graph['task'];d=graph['direction']; path=src/'runs'/t/'nodes.json'
            nodes=sorted(load(path));refs[str(path)]=sha(path)
            shared=set(graph['edges'].get('shared',[]))
            old=[sorted(set(graph['edges'].get(node,[]))|shared) for node in nodes]
            put(ROOT/'old'/dp/(t+'_'+d+'.json.gz'),dict(panel=dp,issue=t,direction=d,nodes=nodes,sets=old))
            put(ROOT/'future'/dp/(t+'_'+d+'.json.gz'),dict(panel=dp,issue=t,direction=d,changed=sorted(set(graph['changed']))))
    put(ROOT/'input_receipt.json',{'files':refs,'old':[p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'old').rglob('*.json.gz'))],'n_issues':18})
if __name__=='__main__':main()
