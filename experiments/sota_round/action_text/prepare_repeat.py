"""Generate a text-only repetition from the frozen prompts; public inputs inside are identical."""
import json,hashlib,shutil
from pathlib import Path
here=Path(__file__).resolve().parent; first=here.parent/'action'
old='Return a JSON object with just one field {"builder":"complete Python 3 source"}.'
new='Output only the complete executable Python 3 builder source as plain text. Start with Python code and finish the implementation.'
ans=[]
for l in (first/'requests.jsonl').read_text(encoding='utf8').splitlines():
    r=json.loads(l);assert r['prompt'].count(old)==1
    r['prompt']=r['prompt'].replace(old,new);ans.append(json.dumps(r,ensure_ascii=False))
(here/'requests.jsonl').write_text('\n'.join(ans)+'\n',encoding='utf8')
for name in ('assigned.jsonl','canaries.jsonl'):shutil.copyfile(first/name,here/name)
s=(first/'local_reader.py').read_text(encoding='utf8').replace('Return exactly the requested JSON object, without commentary or markdown.','Output only executable Python source code implementing the task, without explanation.').replace("in (fence,fence+'json')","in (fence,fence+'python',fence+'py')").replace("'text':clean,",''' 'text':json.dumps({'builder':clean},ensure_ascii=False),''')
assert "'text':json.dumps(" in s and "fence+'python'" in s
(here/'local_reader.py').write_text(s,encoding='utf8')

