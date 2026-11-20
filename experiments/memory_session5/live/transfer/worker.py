"""Execute a restricted pure function with the trusted published tests in a short-lived process."""
import ast
import builtins
import json
import math
import sys
import typing

BUILTINS = set('abs all any bin bool chr dict divmod enumerate filter float frozenset hex int isinstance iter len list map max min next oct ord pow print range reversed round set sorted str sum tuple zip AssertionError ValueError TypeError IndexError StopIteration Exception'.split())
ATTRS = set('append extend pop count index sort reverse insert remove clear copy keys values items get setdefault add discard union intersection difference join strip lstrip rstrip split rsplit splitlines startswith endswith lower upper title capitalize islower isupper istitle isalpha isdecimal isdigit isalnum isnumeric isspace replace find rfind rindex swapcase zfill index partition floor ceil sqrt gcd factorial log log2 log10 pi e inf isclose prod comb isqrt'.split())
ALLOWED = set('Module FunctionDef arguments arg Return Assign AnnAssign AugAssign For While If Expr Pass Break Continue Assert Import ImportFrom alias Name Load Store Del Attribute Subscript Slice Constant List Tuple Set Dict BinOp UnaryOp BoolOp Compare IfExp Call keyword ListComp SetComp DictComp GeneratorExp comprehension Lambda Starred JoinedStr FormattedValue Add Sub Mult Div FloorDiv Mod Pow BitXor BitAnd BitOr LShift RShift UAdd USub Not Invert And Or Eq NotEq Lt LtE Gt GtE Is IsNot In NotIn'.split())
IMPORTS = {'math':set('floor ceil sqrt gcd factorial log log2 log10 pi e inf isclose prod comb isqrt'.split()),'typing':set('List Tuple Optional Set Dict Union Any'.split())}
def checked(text):
    tree=ast.parse(text)
    for node in ast.walk(tree):
        if type(node).__name__ not in ALLOWED:raise ValueError('unsupported AST '+type(node).__name__)
        if isinstance(node,ast.Name) and (node.id.startswith('__') or node.id in {'open','exec','eval','compile','getattr','setattr','vars','globals','locals','__import__','breakpoint','memoryview','input','exit','quit','help','id','type','object','super','classmethod','staticmethod','property','repr','format','bytes','bytearray'}):raise ValueError('unavailable name')
        if isinstance(node,ast.Attribute) and node.attr not in ATTRS:raise ValueError('unavailable attribute '+node.attr)
        if isinstance(node,ast.FunctionDef) and (node.decorator_list or node.name.startswith('__')):raise ValueError('unsupported def')
        if isinstance(node,ast.Import) and any(a.name not in IMPORTS for a in node.names):raise ValueError('unsupported import')
        if isinstance(node,ast.ImportFrom) and (node.module not in IMPORTS or node.level or any(a.name not in IMPORTS[node.module] for a in node.names)):raise ValueError('unsupported from-import')
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and len(node.value)>8192:raise ValueError('string too long')
    return tree

def restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name not in IMPORTS or any(n not in IMPORTS[name] for n in fromlist or ()):raise ImportError(name)
    return {'typing':typing,'math':math}[name]

def main():
    payload=json.load(sys.stdin)
    source=open(payload['path'],encoding='utf8').read()
    try:
        tree=checked(source)
    except (ValueError,SyntaxError) as e:
        print(json.dumps({'status':'invalid_source','detail':type(e).__name__+': '+str(e)[:90]}));return
    safe={k:getattr(builtins,k) for k in BUILTINS};safe['__import__']=restricted_import
    scope={'__builtins__':safe}
    try:
        exec(compile(tree,'solution.py','exec'),scope)
        # Tests are trusted original author strings; separate namespace so candidate cannot redefine check or assertions.
        testscope={payload['entry']:scope[payload['entry']]}
        exec(compile(payload['suite'],'private_suite.py','exec'),testscope)
        print(json.dumps({'status':'pass'}))
    except BaseException as e:print(json.dumps({'status':'failed','detail':type(e).__name__}))
if __name__=='__main__':main()
