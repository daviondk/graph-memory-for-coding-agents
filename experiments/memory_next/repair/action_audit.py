"""Describe tools and flag test pipelines whose outer success conflicts with observed pytest output."""
import json
import re
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    rows=[];counts=Counter()
    pytest=re.compile(r'(?:^|&&|\|\||;|\n)\s*(?:python[\d.]*\s+-m\s+)?(?:py\.test|pytest)\b')
    failure=re.compile(r'^\s*(?:FAILED\s+\S+::\S+|ERROR\s+(?:\S+::\S+|at setup|collecting)|.*\b[1-9]\d* (?:failed|errors?)\b(?:[,\s]|$).*)',re.I)
    for file in sorted((ROOT/'runs').glob('*/*/actions.jsonl')):
        for r in map(json.loads,file.read_text(encoding='utf8').splitlines()):
            name=r['name'];counts[name]+=1
            if name!='bash':continue
            cmd=json.loads(r['arguments']).get('command','')
            counts['prefix/'+cmd.split()[0]]+=1
            if not pytest.search(cmd):continue
            out=r['stdout']+'\n'+r['stderr']
            evidence=[s.strip()[:260] for s in out.splitlines() if failure.search(s)]
            rows.append({'id':file.parent.parent.name,'arm':file.parent.name,'turn':r['turn'],'command':cmd,'outer_status':r['context_output'].splitlines()[0], 'has_pipeline':'|' in cmd,'failure_evidence':evidence[:3]})
    d={'actions':sum(v for k,v in counts.items() if k in ['bash','read_details']),'counts':counts,'recognized_test_invocations':len(rows),'outer_zero_with_visible_failure':sum(r['outer_status']=='Exit 0' and bool(r['failure_evidence']) for r in rows),'tests':rows}
    (ROOT/'action_audit.json').write_text(json.dumps(d,indent=1,ensure_ascii=False)+'\n',encoding='utf8')
    print(d['actions'],d['recognized_test_invocations'],d['outer_zero_with_visible_failure'])
if __name__=='__main__':main()

