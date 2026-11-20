"""Data-flow and scorer audit. No completion data is read until both decision locks exist."""
import ast
import hashlib
import itertools
import gzip
import json
import re
import sys
import textwrap
from collections import Counter
from pathlib import Path

from policy import memories, ntoks
from prepare import execute
from worker import parse_candidate

HERE = Path(__file__).resolve().parent
DATA_HASH = '50a1ac0e4d0c238573c10c0ab11feae00b14a80ae9e4c9cc28148707ecf0b6a2'
SYSTEM = ("Implement exactly the requested Python class method, using the provided interface, examples and class state. "
          "Output one complete method definition with the original name and signature. Return only Python code, without markdown or a class wrapper.")
VERSION = "eaeac44d0d5dcd8a95feec50726d66fedc73a98f"


def digest(raw):
    if isinstance(raw, str):
        raw = raw.encode()
    return hashlib.sha256(raw).hexdigest()


def get(name):
    path = HERE / name
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def write(name, result):
    data = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    (HERE / name).write_text(data, encoding="utf-8")


def matches(lock, base=HERE):
    record = get(lock)
    assert all(digest((base / key).read_bytes()) == val for key, val in record.items())
    return len(record)


def parse(src):
    return ast.parse(textwrap.dedent(src).strip())


def defs(tree, typ=ast.FunctionDef):
    return {n.name: n for n in tree.body if isinstance(n, typ)}


def remove_doc(node):
    if ast.get_docstring(node, clean=False) is not None:
        node.body = node.body[1:]
    return node


def fmt_prompt(row, memory):
    return '\n'.join(('Class: ' + row['cls'],row['summary'], 'Available imports: ' + ', '.join(row['imports']),
                      'Constructor:', row['constructor'].strip(), 'Class method signatures:', *row['interfaces'],
                      'Observed lines from previously implemented methods (source order, indentation omitted):',
                      memory or '(empty)', 'Implement the following target method:', row['desc']))


def request(row, memory):
    return dict(model='qwen38-27b-ud-q4km', messages=[dict(role='system', content=SYSTEM), dict(role='user', content=fmt_prompt(row, memory))],
                max_tokens=384, temperature=0, seed=int(digest('decode|' + row['id'])[:7],16), repeat_penalty=1,
                stream=False, chat_template_kwargs=dict(enable_thinking=False), cache_prompt=False)


def req_key(req):
    return digest(json.dumps(req, sort_keys=True, ensure_ascii=True))


def public_common(v, r):
    assert v['summary'] == r['class_description'] and v['constructor'] == r['class_constructor']
    assert v['cls'] == r['class_name'] and v['imports'] == r['import_statement']
    ctor_src=v['constructor'].strip()
    ctor_tree = parse(ctor_src + ('\n    pass' if len(ctor_src.splitlines())==1 else ''))
    assert len(ctor_tree.body)==1
    ctor_class = defs(ctor_tree, ast.ClassDef)[v['cls']]
    assert set(defs(ctor_class)) <= {'__init__'}
    assert all(isinstance(n, (ast.Pass, ast.Expr, ast.Assign, ast.AnnAssign, ast.FunctionDef)) for n in ctor_class.body)
    for sig,m in zip(v['interfaces'],r['methods_info'],strict=True):
        f = parse(sig + '\n    pass').body[0]
        assert len(f.body)==1 and isinstance(f.body[0],ast.Pass) and f.name == m['method_name']
        assert sig == next(l.strip() for l in m['method_description'].splitlines() if l.strip().startswith('def '))


def literal_call(node, name):
    if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Attribute) or node.func.attr!=name:
        return None
    if not (node.args or node.keywords):
        return None
    try:
        args = [ast.literal_eval(n) for n in node.args]
        kwargs = [[k.arg,ast.literal_eval(k.value)] for k in node.keywords]
    except (TypeError,ValueError,SyntaxError):
        return None
    return repr((args,kwargs))


def contract_info(m):
    # Dataset format stores some decorators with a separately indented def. Normalize just for auditing.
    description=m['method_description']
    lines=description.splitlines()
    start=next(i for i,x in enumerate(lines) if x.strip().startswith('def '))
    assert all(x.strip().startswith('@') for x in lines[:start])
    fragment=textwrap.dedent('\n'.join(lines[start:]))
    if fragment.count(chr(34)*3)==1:
        if chr(34)*3 in fragment.splitlines()[1]: fragment+='\n    '+chr(34)*3
        else:
            assert m['method_name']=='list_employees'
            lines=fragment.splitlines(); lines[1]='    '+chr(34)*3;fragment='\n'.join(lines)
    f=parse(fragment).body[0]
    assert isinstance(f,ast.FunctionDef) and f.name==m['method_name']
    assert all(isinstance(n,ast.Pass) or isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str) for n in f.body)
    doc=ast.get_docstring(f,clean=False) or ''
    samples=set()
    for text in doc.splitlines():
        if not text.strip().startswith('>>>'):continue
        try: t=parse(text.strip()[3:].strip())
        except SyntaxError:continue
        samples.update(k for n in ast.walk(t) if (k:=literal_call(n,f.name)) is not None)
    tests=parse(m['test_code'])
    official={k for n in ast.walk(tests) if (k:=literal_call(n,f.name)) is not None}
    return dict(example=bool('>>>' in doc), literal_overlap=len(samples & official))


def suite_match(r,m):
    test=defs(parse(m['test_code']),ast.ClassDef)[m['test_class']]
    combined=defs(parse(r['test']),ast.ClassDef)[m['test_class']]
    return ast.dump(test)==ast.dump(combined)


def expected_memory(row):
    # Verify physical provenance independently: each line must belong to the named old method, in original order.
    lines={}
    for entry in row['previous']:
        f=parse(entry['src']).body[0]
        parts=entry['src'].splitlines()
        lines[f.name]=[x.strip() for x in parts[f.body[0].lineno-1:] if x.strip()]
    return lines


def check_memory(mem, row, arm):
    cap=800 if arm=='full' else 160
    assert ntoks(mem)<=cap
    sources=expected_memory(row)
    method_order={p['method']:i for i,p in enumerate(row['previous'])}
    curr=None;ptr=0
    for s in mem.splitlines():
        if s.startswith('[') and s.endswith(']') and s[1:-1] in sources:
            if curr:assert method_order[curr]<method_order[s[1:-1]]
            curr=s[1:-1];ptr=0;continue
        assert curr and s in sources[curr][ptr:]
        ptr=sources[curr].index(s,ptr)+1


def audit_design():
    from common import sha
    data=get('ClassEval_data.json')
    assert digest((HERE/'ClassEval_data.json').read_bytes())==DATA_HASH
    raw={r['task_id']:r for r in data}
    teacher=get('visible.json'); online=get('online_visible.json')
    packets={row['id']:row for row in get('packets.json')}
    assign={row['id']:row['arms'] for row in get('assignment.json')}
    results=Counter(); unique=set(); overlap=[]; teacher_desc={}; equal_prior=[]
    assert set(packets)==set(assign)=={v['id'] for v in teacher}
    for v in teacher:
        task, name=v['id'].split('/')
        r=raw[task];public_common(v,r)
        methods=r['methods_info'];order=[m['method_name'] for m in methods];idx=order.index(name);m=methods[idx]
        assert v['desc']==m['method_description'] and v['name']==name
        info=contract_info(m);results['contracts_with_worked_example']+=info['example']
        if info['literal_overlap']:overlap.append(v['id'])
        teacher_desc[v['id']]=v['desc']
        assert [x['method'] for x in v['previous']]==order[:idx] and name not in order[:idx]
        gold=defs(defs(parse(r['solution_code']),ast.ClassDef)[r['class_name']])
        reference_body=ast.dump(ast.Module(body=remove_doc(gold[name]).body,type_ignores=[]))
        for prev in v['previous']:
            ref=remove_doc(gold[prev['method']]);assert ast.dump(parse(prev['src']).body[0])==ast.dump(ref)
            if ast.dump(ast.Module(body=ref.body,type_ignores=[]))==reference_body:equal_prior.append(v['id'])
        assert suite_match(r,m)
        scores=memories(v)
        assert scores==packets[v['id']]['mem']
        for a,mem in scores.items():
            check_memory(mem,v,a)
            assert ntoks(mem)==packets[v['id']]['tokens'][a]
            req=request(v,mem);assert req_key(req)==assign[v['id']][a]
            unique.add(req_key(req))
            results['requests']+=1
        results['past_sources']+=len(v['previous'])
        results['teacher_selected_tests']+=sum(1 for n in defs(defs(parse(m['test_code']),ast.ClassDef)[m['test_class']]) if n.startswith('test'))
    online_overlap=[];online_examples=0;total=0;raw_suites=0;raw_tests=0
    for v in online:
        r=raw[v['id']];public_common(v,r)
        assert v['targets']==[[m['method_name'],m['method_description']] for m in r['methods_info']]
        skel=defs(parse(r['skeleton']),ast.ClassDef)[r['class_name']]
        for m in r['methods_info']:
            id_=v['id']+'/'+m['method_name'];f=defs(skel)[m['method_name']]
            assert all(isinstance(x,(ast.Pass,ast.Raise)) or isinstance(x,ast.Expr) and isinstance(x.value,ast.Constant) for x in f.body)
            info=contract_info(m);total+=1;online_examples+=bool(info['example'])
            if info['literal_overlap']:online_overlap.append(id_)
            assert suite_match(r,m)
        assert set(r['test_classes'])==set(defs(parse(r['test']),ast.ClassDef))
        raw_suites+=len(r['test_classes'])
        raw_tests+=sum(sum(n.startswith('test') for n in defs(cl)) for cl in defs(parse(r['test']),ast.ClassDef).values())
    calibration=get('calibration.json')
    for v in teacher:
        _,ref,empty=calibration[v['id']]
        assert ref['total']==empty['total'] and ref['passed']==ref['total'] and ref['skipped']==0 and empty['status']=='fail'
    return dict(version=VERSION, dataset_sha256=DATA_HASH, teacher_tasks=len(teacher),teacher_classes=len({x['cls'] for x in teacher}),
                teacher_planned_unique_calls=len(unique),teacher_contracts_with_same_literal_target_call_as_in_suite=overlap,
                teacher_ids_with_identical_earlier_clean_ast_statement_body=sorted(set(equal_prior)),
                online_tasks=total,online_classes=len(online),online_suites=raw_suites,online_tests=raw_tests,online_contracts_with_worked_example=online_examples,
                online_contracts_with_same_literal_target_call_as_in_suite=online_overlap,
                online_teacher_class_overlap=len({v['cls'] for v in teacher}&{v['cls'] for v in online}),
                online_teacher_method_overlap=sum(c['id']+'/'+m[0] in teacher_desc for c in online for m in c['targets']),
                hashes_checked={'teacher':matches('method_lock.json'),'online':matches('online_method_lock.json')},**results)


def audit_toy():
    text="""class Counter:
    def __init__(self): self.values=[]
    def add(self, x):
        self.values.append(x)
        return len(self.values)
    def total(self):
        return sum(self.values)
"""
    test="""class TestCounter(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(Counter().total(),0)
    def test_populated(self):
        c=Counter()
        c.add(3)
        self.assertEqual(c.total(),3)
"""
    common={'name':'total','class':'Counter','source':text,'tests':test,'testclass':'TestCounter','imports':[]}
    examples=[
        ('reference', 'reference', '', 'pass', 2),
        ('stub', 'stub', '', 'fail', 0),
        ('correct','generated','def total(self):\n    return sum(self.values)','pass',2),
        ('partially_correct','generated','def total(self):\n    return 0','fail',1),
        ('syntax_error','generated','def total(','invalid',0),
        ('different_method','generated','def other(self):\n    return 0','invalid',0),
        ('fenced_class','generated','\x60\x60\x60python\nclass Counter:\n    def total(self): return sum(self.values)\n\x60\x60\x60','pass',2),
        ('wrong_previous_implementation','reference','','fail',1),
        ('valid_python_requires_omitted_builtin','generated','def total(self):\n    return sum(self.values or [int.from_bytes(bytes(1))])','fail',1),
    ]
    # Restricted interpreter lacks bytes. Unlike canonical test scripts, equivalence here is analytically known.
    assert sum([] or [int.from_bytes(bytes(1))])==0 and sum([3] or [int.from_bytes(bytes(1))])==3
    outcomes={}
    for label,mode,src,status,passes in examples:
        payload=dict(common,grade=mode,candidate=src)
        if label=='wrong_previous_implementation': payload['source']=text.replace('self.values.append(x)','self.values.append(x+1)')
        r=execute(payload)
        assert r['status']==status and r.get('passed',0)==passes,(label,r)
        outcomes[label]=dict(status=r['status'],passes=r.get('passed',0),total=r.get('total'))
    return outcomes


if __name__=='__main__':
    write('independent_design.json',audit_design())
    write('independent_harness.json',audit_toy())
    if '--sealed' in sys.argv:
        from independent_sealed import audit_sealed
        audit_sealed()

