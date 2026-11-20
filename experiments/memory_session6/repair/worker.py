"""Execute pure candidate code in a bounded child, then run the publisher's assertions."""
import ast
import builtins
import collections
import functools
import itertools
import math
import operator
import re
import heapq
import bisect
import string
import typing
import json
import sys

MODULES={m.__name__:m for m in (math,collections,functools,itertools,operator,re,heapq,bisect,string,typing)}
PERMIT=set('abs all any bin bool callable chr dict divmod enumerate filter float format frozenset hex int isinstance iter len list map max min next oct ord pow print range reversed round set slice sorted str sum tuple zip complex type ascii repr AssertionError ValueError TypeError IndexError KeyError ZeroDivisionError StopIteration NotImplementedError Exception'.split())
# Only known data/math module facilities and object methods. No file or process APIs.
ATTR=set('append extend pop count index sort reverse insert remove clear copy keys values items get setdefault add discard union intersection difference symmetric_difference update intersection_update issubset issuperset isdisjoint join strip lstrip rstrip split rsplit splitlines startswith endswith lower upper title capitalize casefold islower isupper istitle isalpha isdecimal isdigit isalnum isnumeric isspace isascii replace find rfind rindex swapcase zfill center partition rpartition format translate maketrans encode decode real imag bit_count bit_length numerator denominator as_integer_ratio fromkeys most_common elements appendleft popleft rotate fullmatch group groups start end span hexdigest'.split())
for m in MODULES.values():
    ATTR.update(k for k in dir(m) if not k.startswith('_') and k not in {'sys','os','builtins','importlib','pickle','GenericAlias','Generic','Any','attrgetter','methodcaller','operator','get_type_hints','ForwardRef','getattr_static'})
DENY={'open','exec','eval','compile','getattr','setattr','delattr','vars','globals','locals','__import__','breakpoint','input','exit','quit','help','id','object','super','classmethod','staticmethod','property','memoryview','bytearray','bytes','attrgetter','methodcaller','get_type_hints','ForwardRef'}
def permitted(source):
    tree=ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node,(ast.ClassDef,ast.AsyncFunctionDef,ast.With,ast.AsyncWith,ast.Global,ast.Nonlocal,ast.Await)):raise ValueError(type(node).__name__)
        if isinstance(node,ast.Name) and (node.id.startswith('_') and node.id!='_' or node.id in DENY):raise ValueError('name '+node.id)
        if isinstance(node,ast.Attribute) and (node.attr not in ATTR or node.attr.startswith('_') or node.attr in DENY):raise ValueError('attribute '+node.attr)
        if isinstance(node,ast.FunctionDef) and (node.name.startswith('__') or node.decorator_list):raise ValueError('function form')
        if isinstance(node,ast.Import) and any(a.name not in MODULES or a.asname in DENY for a in node.names):raise ValueError('import')
        if isinstance(node,ast.ImportFrom) and (node.level or node.module not in MODULES or any(a.name not in ATTR or a.name in DENY for a in node.names)):raise ValueError('from import')
    return tree
def restricted_import(name,globals=None,locals=None,fromlist=(),level=0):
    if level or name not in MODULES or any(a not in ATTR or a in DENY for a in fromlist or ()):raise ImportError(name)
    return MODULES[name]
def main():
    d=json.load(sys.stdin)
    source=open(d['source'],encoding='utf8').read()
    try:tree=permitted(source)
    except (SyntaxError,ValueError) as e:
        print(json.dumps({'status':'invalid','detail':str(e)[:140]}));return
    funcs={k:getattr(builtins,k) for k in PERMIT};funcs['__import__']=restricted_import
    sc={'__builtins__':funcs}
    try:
        exec(compile(tree,'submission.py','exec'),sc)
        testsc={d['entry']:sc[d['entry']]}
        for imp in d['imports']:exec(imp,testsc)
        errors=[]
        for j,test in enumerate(d['tests']):
            try:exec(compile(test,'test.py','exec'),testsc)
            except BaseException as e:errors.append([j,type(e).__name__])
        print(json.dumps({'status':'fail' if errors else 'pass','failed':errors,'total':len(d['tests'])}))
    except BaseException as e:print(json.dumps({'status':'fail','detail':type(e).__name__}))
if __name__=='__main__':main()

