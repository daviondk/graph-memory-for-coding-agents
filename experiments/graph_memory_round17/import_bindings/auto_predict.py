"""Infer changed producers and test decisions from module bytes and prior observations alone."""
import ast
from experiment import positive, provenance

DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def index(items):
    names = {}
    shape = []
    for item in items:
        if isinstance(item, DEFINITIONS):
            name = item.name
        elif isinstance(item, ast.Assign) and len(item.targets)==1 and isinstance(item.targets[0],ast.Name):
            name = item.targets[0].id
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target,ast.Name):
            name = item.target.id
        else:
            shape.append(("other",ast.dump(item)))
            continue
        if name in names:
            return None, None
        names[name] = item
        shape.append((type(item).__name__, name))
    return names, shape


def header(cls):
    return [(field,ast.dump(value) if isinstance(value,ast.AST) else
             [ast.dump(v) if isinstance(v,ast.AST) else v for v in value] if isinstance(value,list) else value)
            for field,value in ast.iter_fields(cls) if field!="body"]


def diff_sources(before, after):
    try:
        old, old_shape = index(ast.parse(before).body)
        new, new_shape = index(ast.parse(after).body)
    except (SyntaxError,ValueError):
        return [], True, "unparseable"
    if old is None or new is None or old_shape != new_shape:
        return [], True, "module structure changed"
    changed = []
    for name, then in old.items():
        now = new[name]
        if ast.dump(then) == ast.dump(now):
            continue
        if isinstance(then, ast.ClassDef):
            if header(then) != header(now):
                return [], True, "class header changed"
            body_old, shape_old = index(then.body)
            body_new, shape_new = index(now.body)
            if body_old is None or body_new is None or shape_old != shape_new:
                return [], True, "class structure changed"
            for member, prior in body_old.items():
                if ast.dump(prior) != ast.dump(body_new[member]):
                    changed.append({"node":name+"."+member, "granularity":type(prior).__name__,
                                    "producer":name, "widened":True,
                                    "old_span":[prior.lineno,prior.end_lineno],"new_span":[body_new[member].lineno,body_new[member].end_lineno]})
        elif isinstance(then, (ast.FunctionDef,ast.AsyncFunctionDef,ast.Assign,ast.AnnAssign)):
            changed.append({"node":name,"producer":name,"granularity":type(then).__name__,"widened":False,
                            "old_span":[then.lineno,then.end_lineno],"new_span":[now.lineno,now.end_lineno]})
        else:
            return [], True, "unsupported changed definition"
    return changed, False, "matched named definitions"


def forecast(before, after, observations):
    changes, fallback, reason = diff_sources(before,after)
    producers = {e["producer"] for e in changes}
    assigned = {c["producer"] for c in changes if not c["widened"] and c["granularity"] in ("Assign","AnnAssign")}
    bindings, opaque, _ = provenance(before,observations)
    chosen = []
    for key, entry in observations["tests"].items():
        if not positive(observations["outcomes"][key]):
            continue
        names = set(entry["names"]) | set(entry["functions"])
        ancestors = set().union(*(bindings.get(name,set()) for name in names))
        dynamic_lookup = bool(names & {"globals","locals"}) and bool(producers)
        if fallback or dynamic_lookup or producers & (set(entry["functions"]) | opaque | ancestors) or assigned & names:
            chosen.append(key)
    return {"changes":changes,"full_fallback":fallback,"reason":reason,"nodeids":sorted(chosen)}
