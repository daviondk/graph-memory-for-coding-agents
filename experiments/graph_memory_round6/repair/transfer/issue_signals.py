"""Read localizable evidence in public issue prose. Never evaluates any issue text."""
import ast
import re


def parse_issue(issue):
    addresses=set();pairs=set();bindings={}
    normal=issue.replace('\\','/')
    for m in re.finditer(r"""(?<![A-Za-z0-9_])(sympy/(?:[\w.-]+/)*[\w.-]+\.py)(?:["']?\s*,\s*line\s+|:|\#L)(\d+)""",normal,re.I):
        path=m[1]
        while path.startswith('sympy/sympy/'):path=path[6:]
        if int(m[2])>0: addresses.add((path,int(m[2])))
    def class_name(fn):
        name=fn.id if isinstance(fn,ast.Name) else fn.attr if isinstance(fn,ast.Attribute) else ''
        return name if name[:1].isupper() else ''
    for row in issue.splitlines():
        row=re.sub(r'^\s*(?:>>>|\.\.\.|In \[\d+\]:)\s*','',row).strip(' \t'+chr(96))
        if not row:continue
        if m:=re.search(r'\b([a-z_]\w*)\s*=\s*(?:\w+\.)?([A-Z]\w*)\s*\(',row):
            bindings[m[1]]=m[2]
        for cls,fn in re.findall(r'\b([A-Z]\w*)(?:\([^()\n]{0,240}\))?\.([a-zA-Z_]\w*)\b',row):
            pairs.add((cls,fn))
        for obj,fn in re.findall(r'\b([a-z_]\w*)\.([a-zA-Z_]\w*)\b',row):
            if obj in bindings:pairs.add((bindings[obj],fn))
        try:tree=ast.parse(row)
        except (ValueError,SyntaxError,RecursionError):continue
        for node in ast.walk(tree):
            if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call) and (c:=class_name(node.value.func)):
                for dest in node.targets:
                    if isinstance(dest,ast.Name):bindings[dest.id]=c
            if isinstance(node,ast.Attribute):
                v=node.value
                cls=class_name(v.func) if isinstance(v,ast.Call) else (bindings.get(v.id) or class_name(v)) if isinstance(v,ast.Name) else ''
                if cls:pairs.add((cls,node.attr))
    return dict(addresses=sorted([p,n] for p,n in addresses),pairs=sorted([c,f] for c,f in pairs),words=sorted(set(re.findall(r'[A-Za-z_]\w*',issue))))


def bonus(signals,node,chunk,arm):
    if arm=='flat':return 0.
    address=0.
    if arm in ('address','evidence'):
        for p,n in signals['addresses']:
            if p==node['p']:
                dist=max(0,chunk['st']-n,n-chunk['en'])
                address=max(address,32/(1+dist/14))
    symbol=0.
    if arm in ('symbol','evidence') and node['cl']:
        if [node['cl'],node['fn']] in signals['pairs']:symbol+=22
        if node['cl'] in signals['words'] and node['fn'] in signals['words']:symbol+=7
    return address+symbol
