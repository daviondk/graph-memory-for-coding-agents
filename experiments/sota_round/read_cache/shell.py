"""Fail-closed syntax classification. This module never invokes a shell."""
from dataclasses import dataclass
import posixpath
import re
import shlex

PATH = re.compile(r"[A-Za-z0-9_@+./-]+")
RANGE = re.compile(r"(?:\d+|\$)(?:,(?:\d+|\$))?p")
HEREDOC = re.compile(r"(?s)^\s*((?:cd\s+[A-Za-z0-9_./+-]+\s*&&\s*)?cat\s+(?:>{1,2}\s*[A-Za-z0-9_./+-]+\s+<<|<<)\s*(['\"])([A-Za-z_]\w*)\2(?:\s*>{1,2}\s*[A-Za-z0-9_./+-]+)?)\s*\n.*?\n\3\s*$")


@dataclass(frozen=True)
class Kind:
    mode: str
    paths: tuple=()


GLOBAL=Kind("global")
READ=Kind("readonly")


def path_of(s, cwd):
    if not PATH.fullmatch(s) or s.startswith(("-","~")) or ".." in s.split("/"):
        return None
    if not s.startswith("/") and not cwd:
        return None
    path=posixpath.normpath(posixpath.join(cwd or "/",s))
    if path=="/" or path.split("/")[1] in ("proc","sys","dev","run"):
        return None
    return path


def words(s):
    lex=shlex.shlex(s,posix=True,punctuation_chars=";&|<>()")
    lex.whitespace_split=True
    return list(lex)


def split_cd(args):
    if args[:1]==["cd"] and len(args)>=4 and args[2]=="&&" and args[1].startswith("/"):
        cwd=path_of(args[1],None) or ("/" if args[1]=="/" else None)
        if cwd:
            return cwd,args[3:]
    return None,args


def readonly(args):
    if not args:
        return False
    op,*v=args
    if op in {"cat","head","tail","wc","ls","pwd","grep","diff","nl","stat","which","uname"}:
        # diff can execute an explicit external pager.
        return not any(t=="--paginate" or t=="-l" and op=="diff" for t in v)
    if op=="rg":
        return not any(t.startswith(("--pre","--hostname-bin","--config","-z","--search-zip")) for t in v)
    if op=="sed":
        return len(v)>=2 and v[0]=="-n" and bool(RANGE.fullmatch(v[1])) and all(
            PATH.fullmatch(t) and not t.startswith("-") for t in v[2:])
    if op=="find":
        return not any(t.startswith(("-exec","-ok","-delete","-fprint","-fls")) for t in v)
    return False


def reader(args,cwd):
    op,*v=args
    if not v:
        return READ
    if op=="cat":
        expected=all(re.fullmatch(r"-[AbensTuv]+|--",t) for t in v[:-1])
    elif op in ("head","tail"):
        expected=bool(re.fullmatch(r"(?:(?:-n|-c)\s+\d+|-\d+|-[nc]\d+)?"," ".join(v[:-1])))
    elif op=="wc":
        expected=all(re.fullmatch(r"-[clLmw]+|--",t) for t in v[:-1])
    elif op=="sed":
        expected=len(v)==3 and v[0]=="-n" and bool(RANGE.fullmatch(v[1]))
    elif op in ("grep","rg"):
        if len(v)<2:
            return READ
        # One pattern and one explicit file. Flags with operands must have inline digits.
        expected=all(re.fullmatch(r"-[EinwivFxhHno]+|-[ABCm]\d+|--",t) for t in v[:-2]) and not v[-2].startswith("-")
    else:
        return READ
    path=path_of(v[-1],cwd)
    if expected and path and re.fullmatch(r"[\w.@+-]+\.[\w+-]+",posixpath.basename(path)):
        return Kind("query",(path,))
    return READ


def filter_ok(cmd):
    if not cmd:
        return False
    op,*v=cmd
    if op in ("head","tail"):
        return bool(re.fullmatch(r"(?:(?:-n|-c)\s+\d+|-\d+|-[nc]\d+)?"," ".join(v)))
    if op=="wc":
        return all(re.fullmatch(r"-[clLmw]+",x) for x in v)
    if op in ("grep","rg"):
        return bool(v) and not v[-1].startswith("-") and all(re.fullmatch(r"-[EinwivFxhHno]+",x) for x in v[:-1])
    return False


def classify(cmd):
    if not isinstance(cmd,str) or not cmd.strip():
        return GLOBAL
    here=HEREDOC.fullmatch(cmd)
    if here:
        # A quoted delimiter disables substitutions inside data. Require exactly one
        # delimiter line: an earlier terminator could expose additional shell code.
        delim=here[3]
        if sum(x.rstrip("\r")==delim for x in cmd.splitlines())!=1:
            return GLOBAL
        head=here[1]
        redirect=re.search(r">{1,2}\s*([A-Za-z0-9_./+-]+)",head)
        cwd,_=split_cd(words(head))
        p=path_of(redirect[1],cwd) if redirect else None
        return Kind("write",(p,)) if p else GLOBAL
    if any(c in cmd for c in ("\n","\r","\x00","$","'\\''","\u0060")):
        return GLOBAL
    try:
        cwd,args=split_cd(words(cmd))
    except ValueError:
        return GLOBAL
    if not args:
        return GLOBAL
    if any(t in ("&&",";","||","&","(",")","<&","&>","<<","<<<","<>","<&",">&") for t in args):
        return GLOBAL
    if args[0] in ("echo","printf") and len(args)>=3 and args[-2] in (">",">>"):
        p=path_of(args[-1],cwd)
        if p and all(t not in (">",">>","<","|") for t in args[:-2]):
            return Kind("write",(p,))
        return GLOBAL
    if any(t in (">",">>","<") or re.fullmatch(r"[;&<>()]{1,}",t) for t in args):
        return GLOBAL
    segments=[[]]
    for t in args:
        if t=="|":
            segments.append([])
        else:
            segments[-1].append(t)
    if any(not x for x in segments):
        return GLOBAL
    if all(readonly(x) for x in segments):
        return reader(segments[0],cwd) if all(filter_ok(x) for x in segments[1:]) else READ
    if len(segments)>1:
        return GLOBAL
    op,*v=args
    operands=[]
    if op in ("cp","mv") and len(v)==2:
        operands=v
    elif op in ("touch","rm","mkdir","rmdir") and v and all(not a.startswith("-") or re.fullmatch(r"-[rRfpi]+",a) for a in v):
        operands=[a for a in v if not a.startswith("-")]
    elif op=="sed" and len(v)==3 and v[0]=="-i":
        edit=re.fullmatch(r"s([^A-Za-z0-9\\\s;])([^;\n]*)\1([^;\n]*)\1[gi0-9]*",v[1])
        if edit and v[1].count(edit[1])==3:
            operands=v[2:]
    if operands:
        paths=tuple(path_of(a,cwd) for a in operands)
        if all(paths):
            return Kind("write",paths)
    return GLOBAL
