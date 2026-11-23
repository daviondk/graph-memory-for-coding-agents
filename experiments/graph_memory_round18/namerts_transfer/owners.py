"""Map changed source intervals to historical test evidence with and without lexical ancestor reuse."""
import ast
import difflib

def spans(code):
    tree=ast.parse(code);owners={};ancestors={}
    def walk(node, lex, parents):
        scoped=isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))
        if scoped:
            lex=lex+(node.name,)
            if not isinstance(node,ast.ClassDef):
                name=".".join(lex)
                for line in range(node.lineno,node.end_lineno+1):
                    owners[line]=name
                ancestors[name]=list(reversed(parents))
                parents=parents+(name,)
        for child in ast.iter_child_nodes(node):walk(child,lex,parents)
    walk(tree,(),())
    return owners,ancestors

def analyze(old,new):
    old_lines,old_hierarchy=spans(old)
    new_lines,new_hierarchy=spans(new)
    scopes=set(old_hierarchy)
    out={"old_lines":set(),"old_functions":set(),"new_functions":set(),
         "old_insert":set(),"new_insert":set(),"old_fallback":False,"new_fallback":False,"hunks":[]}
    for op,b0,b1,n0,n1 in difflib.SequenceMatcher(None,old.splitlines(),new.splitlines(),autojunk=False).get_opcodes():
        if op=="equal":continue
        old_part=set(range(b0+1,b1+1));new_part=set(range(n0+1,n1+1))
        previous={old_lines.get(i) for i in old_part}
        present={new_lines.get(i) for i in new_part}
        known={x for x in previous|present if x in scopes}
        old_wide=None in previous|present or any(x not in scopes for x in present)
        wide=old_wide and (None in previous or None in present)
        mapped=set(known);repairs={};external=[]
        for name in present-scopes-{None}:
            prior_owner=next((x for x in new_hierarchy.get(name,[]) if x in scopes),None)
            if prior_owner is None:
                wide=True;external.append(name)
            else:
                repairs[name]=prior_owner;mapped.add(prior_owner)
        # Include the historical enclosing function for both inserted and replaced sections.
        out["old_lines"].update(old_part);out["old_functions"].update(known);out["new_functions"].update(mapped)
        if op=="insert":out["old_insert"].update(known);out["new_insert"].update(mapped)
        if repairs:out["new_insert"].update(repairs.values())
        out["old_fallback"]|=old_wide;out["new_fallback"]|=wide
        out["hunks"].append({"op":op,"old_span":[b0+1,b1],"new_span":[n0+1,n1],
                             "before":sorted(s for s in previous if s),"after":sorted(s for s in present if s),
                             "global_scope":None in previous|present,"old_wide":old_wide,"new_wide":wide,
                             "matched_outer":repairs,"no_old_owner":sorted(external)})
    return {key:sorted(value) if isinstance(value,set) else value for key,value in out.items()}
