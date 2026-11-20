"""Re-evaluate all fixed candidates with author's module symbols visible to trusted author tests."""
import ast,collections,concurrent.futures,json,time
from common import *
from grade import summary
def main():
    rs=corpus()
    for c in ('','transfer'):
        folder=ROOT/c;saved=read((folder/'scores.json.gz').relative_to(ROOT));ids=read((folder/'roster.json').relative_to(ROOT))['ids']
        def run(r):
            v=dict(r);i=r['id'];et=rs[i];entry=et['entry_point']
            if r['patch_sha'] is None:return v
            path=folder/'artifacts'/slug(i)/r['arm']/'solution.py'
            assert digest(path.read_bytes())==r['patch_sha']
            # This trusted adapter executes solely in the publisher's testing scope.
            setup='import random\nrandom.seed(17112026)\nglobals().update({k:v for k,v in '+entry+'.__globals__.items() if not k.startswith("__")})\n'
            v['evaluated']=run_suite(path,entry,setup+et['test'])
            v['hit']=int(v['evaluated']['status']=='pass' and v['action'] in ('applied','control'))
            v['first_hit']=int(v['hit'] and not v['reread'])
            return v
        with concurrent.futures.ThreadPoolExecutor(3) as pool:rows=list(pool.map(run,saved))
        save((folder/'corrected_scores.json.gz').relative_to(ROOT),rows)
        d=summary(c,ids,rows,rs);save((folder/'corrected_results.json').relative_to(ROOT),d)
        delta={str(x['id'])+'|'+x['arm']:[y['evaluated'],x['evaluated']] for x,y in zip(rows,saved) if x['evaluated']!=y['evaluated']}
        save((folder/'namespace_differences.json').relative_to(ROOT),delta)
        helpers={}
        for i in ('Python/38','Python/50'):
            if i not in ids:continue
            def defs(text):return {f.name:ast.dump(f,include_attributes=False) for f in ast.parse(text).body if isinstance(f,ast.FunctionDef)}
            original=defs(src(rs[i]));helper=next(iter(original))
            for v in rows:
                if v['id']==i and v['hit']:
                    f=folder/'artifacts'/slug(i)/v['arm']/'solution.py';helpers[i+'|'+v['arm']]=original[helper]==defs(f.read_text(encoding='utf8')).get(helper)
        save((folder/'helper_integrity.json').relative_to(ROOT),helpers)
        print(c or 'primary',d['all']['rows'],flush=True)
if __name__=='__main__':main()
