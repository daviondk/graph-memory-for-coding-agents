"""Conservative overlap check. Match literal arguments AND literal result only, never infer receiver state."""
import ast
from independent_audit import get, literal_call, parse, write


def annotated(src, name):
    lines=src.splitlines()
    found=set()
    for j,s in enumerate(lines[:-1]):
        if not s.strip().startswith('>>>'):continue
        try:
            statement=parse(s.strip()[3:].strip()).body[0]
            if not isinstance(statement,ast.Expr):continue
            call=literal_call(statement.value,name)
            val=ast.literal_eval(lines[j+1].strip())
            if call is not None:found.add((call,repr(val)))
        except (SyntaxError,TypeError,ValueError):pass
    return found


def asserted(src,name):
    found=set()
    for test in ast.walk(parse(src)):
        if not isinstance(test,ast.Call) or not isinstance(test.func,ast.Attribute):continue
        a=test.args
        compared=[]
        if test.func.attr=='assertEqual' and len(a)>=2:
            compared=[(a[0],a[1]),(a[1],a[0])]
        if test.func.attr in ('assertTrue','assertFalse') and a:
            compared=[(a[0],ast.Constant(test.func.attr=='assertTrue'))]
        for expr,expected in compared:
            call=literal_call(expr,name)
            try:val=ast.literal_eval(expected)
            except (SyntaxError,TypeError,ValueError):continue
            if call is not None:found.add((call,repr(val)))
    return found


def main():
    data={r['task_id']:r for r in get('ClassEval_data.json')}
    ids={x['id'] for x in get('visible.json')}
    online={c['id']+'/'+n for c in get('online_visible.json') for n,_ in c['targets']}
    found={}
    for i in ids|online:
        cls,name=i.split('/')
        m=next(m for m in data[cls]['methods_info'] if m['method_name']==name)
        both=annotated(m['method_description'],name) & asserted(m['test_code'],name)
        if both:found[i]=len(both)
    write('independent_examples.json',dict(teacher_ids=sorted(ids & set(found)),online_ids=sorted(online & set(found)),count_by_method=found,
        criterion="Public doctest bare target call and next literal output equals direct assertEqual/True/False on identical literal target arguments and result. Receiver state and argument binding not inferred."))


if __name__=='__main__':main()

