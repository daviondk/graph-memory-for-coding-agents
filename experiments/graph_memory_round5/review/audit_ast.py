"""Classify visible textual witnesses without looking at model responses, next lines, or gold ranks."""
import collections
import datetime
import importlib.metadata
import json
import re
import sys
from pathlib import Path
import pyarrow.parquet as pq

from audit_reader import HERE, SOURCE, digest, load_inputs

sys.path.insert(0, str(HERE / "parser_lib"))
import tree_sitter_java
from tree_sitter import Language, Parser

PARSER = Parser(Language(tree_sitter_java.language()))
STRONG = {"new_object_type", "method_direct_receiver"}


def same_node(a, b):
    return a is not None and b is not None and (a.type, a.start_byte, a.end_byte) == (b.type, b.start_byte, b.end_byte)


def rightmost_name(node):
    # The base name of new pkg.Foo<T>(), deliberately not T. For receivers only accept a bare name.
    if not node:
        return None
    if node.type in ("identifier", "type_identifier"):
        return node
    if node.type == "generic_type":
        return rightmost_name(node.named_children[0])
    if node.type == "scoped_type_identifier":
        return rightmost_name(node.named_children[-1])
    return None


def declaration_name(text, key):
    # The memory normalizes its lookup key to lowercase. Resolve its original spelling from the declaration itself.
    tree = PARSER.parse(text.encode())
    stack = [tree.root_node]
    matches = []
    types = {"class_declaration", "interface_declaration", "record_declaration", "enum_declaration", "annotation_type_declaration"}
    while stack:
        node = stack.pop()
        if node.type in types or node.type in {"method_declaration", "constructor_declaration"}:
            name = node.child_by_field_name("name")
            if name is not None and name.text.decode().lower() == key.lower():
                matches.append((0 if node.type in types else 1, name.start_byte, name.text.decode()))
        stack.extend(node.named_children)
    if not matches: return None, "unresolved"
    rank, _, name = min(matches)
    return name, "type" if rank == 0 else "callable"


def classify(node, token, wanted):
    if token != wanted:
        return "case_only"
    ancestors = []
    p = node
    while p is not None:
        ancestors.append(p)
        p = p.parent
    if any("comment" in q.type or q.type in ("string_literal", "character_literal", "text_block") for q in ancestors):
        return "literal_or_comment"
    if any(q.is_error or q.is_missing for q in ancestors):
        return "parse_error"
    for n in ancestors:
        if n.type == "object_creation_expression" and same_node(rightmost_name(n.child_by_field_name("type")), node):
            return "new_object_type"
        if n.type == "method_invocation" and same_node(n.child_by_field_name("object"), node):
            return "method_direct_receiver"
        if n.type == "field_access" and same_node(n.child_by_field_name("object"), node):
            return "field_direct_receiver"
    if node.type == "type_identifier" or any(n.type.endswith("_declaration") and same_node(n.child_by_field_name("name"),node) for n in ancestors):
        return "type_or_declaration"
    if node.type == "identifier":
        return "other_identifier"
    return "other_or_ambiguous"


def classify_line(tree, text, row, wanted):
    lines = text.splitlines(keepends=True)
    before = len("".join(lines[:row]).encode())
    out = []
    pat = r"(?<![A-Za-z0-9_$])" + re.escape(wanted) + r"(?![A-Za-z0-9_$])"
    for match in re.finditer(pat, lines[row], re.I):
        left = before + len(lines[row][:match.start()].encode())
        right = left + len(match[0].encode())
        leaf = tree.root_node.descendant_for_byte_range(left, right)
        out.append(classify(leaf, match[0], wanted))
    assert out
    priority = ("new_object_type", "method_direct_receiver", "field_direct_receiver", "type_or_declaration", "other_identifier",
                "literal_or_comment", "case_only", "parse_error", "other_or_ambiguous")
    return {"roles":sorted(set(out)), "primary": next(k for k in priority if k in out),
            "strong":any(x in STRONG for x in out), "fragment_has_error":tree.root_node.has_error}


def sanity():
    text = '''class Example {
    void run() {
        Foo.call();
        new Foo<Other>();
        new Other<Foo>();
        String msg = "Foo.call()";
        int i = Foo.VALUE;
        Foo item;
    }
}'''
    tree = PARSER.parse(text.encode())
    order = ["method_direct_receiver","new_object_type","type_or_declaration","literal_or_comment","field_direct_receiver","type_or_declaration"]
    for row, correct in enumerate(order,2):
        assert classify_line(tree,text,row,"Foo")["primary"] == correct


def main():
    sanity()
    panels = {k:load_inputs(k) for k in ("A", "B")}
    work = collections.defaultdict(list)
    for k, packets in panels.items():
        for x in packets:
            if x["edge_event"] is not None:
                work[x["file"]].append((k,x))
    results = collections.defaultdict(dict)
    for path,group in work.items():
        table = pq.ParquetFile(SOURCE / "archive_inputs" / path)
        need = {p["local_index"] for _,p in group}; sub = {}; offset = 0
        for batch in table.iter_batches(columns=["context"],batch_size=64):
            for j in sorted(i for i in need if offset <= i < offset + len(batch)):
                sub[j] = batch.column(0)[j-offset].as_py()
            offset += len(batch)
        for i,(key,p) in enumerate(group):
            event = p["edge_event"]; texts = sub[p["local_index"]]
            text = texts[event["source"]]
            tree = PARSER.parse(text.encode("utf8"))
            name, kind = declaration_name(texts[p["rank"][0]], event["root"])
            if kind == "unresolved":
                role = {"primary":"unresolved_declaration", "roles":["unresolved_declaration"], "strong":False,
                        "fragment_has_error":tree.root_node.has_error}
            else:
                role = classify_line(tree,text,event["line"],name)
                if kind == "callable":
                    role["strong"] = False
            results[key][p["id"]] = {**role, "target_kind":kind, "target_spelling":name}
    compact = {}
    for key,records in results.items():
        items = records.values()
        compact[key] = {"n":len(items), "strong":sum(x["strong"] for x in items),
                        "primary":dict(collections.Counter(x["primary"] for x in items)),
                        "any_error_somewhere_in_fragment":sum(x["fragment_has_error"] for x in items),
                        "unknown_edge_for_remaining_panel_rows":len(panels[key])-len(items)}
    output = {"utc":datetime.datetime.now(datetime.UTC).isoformat(),"script_sha256":digest(Path(__file__)),
              "protocol_sha256":digest(HERE/"AST_PROTOCOL_RU.md"),"grammar":importlib.metadata.version("tree-sitter-java"),
              "tree_sitter":importlib.metadata.version("tree-sitter"),"compact":compact,"records":results}
    (HERE / "ast_roles.json").write_text(json.dumps(output,indent=1,ensure_ascii=False),encoding="utf8")
    print(json.dumps(compact))
if __name__=="__main__":
    main()


