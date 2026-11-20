"""Application-level operations over the unmodified packages. No instrumentation decisions here."""
import datetime
import io
from pathlib import Path
ZONES=["Europe/Kyiv","America/Ciudad_Juarez","America/Coyhaique","UTC","Europe/London","America/New_York"]
def run(project,case,root):
    if case=="stdlib":return sum(i*i for i in range(5))
    if project=="tzdata":
        import zoneinfo
        zoneinfo.reset_tzpath([str(root/"zones")]);zoneinfo.ZoneInfo.clear_cache()
        try:z=zoneinfo.ZoneInfo(case)
        except zoneinfo.ZoneInfoNotFoundError:return {"unavailable":"zone"}
        return [int(datetime.datetime(2025,m,15,12,tzinfo=z).utcoffset().total_seconds()) for m in [1,7]]
    if project=="tabulate":
        from tabulate import tabulate
        if case=="normal":return tabulate([["aa",1],["bb",2]],tablefmt="plain")
        return tabulate([["spam",41.9999],["eggs","451.0"]],["strings","配列"],tablefmt="grid")
    if project=="markdown-it-py":
        from markdown_it import MarkdownIt
        if case=="normal":return MarkdownIt("commonmark").render("**word**")
        try:return MarkdownIt("gfm-like").render("https://example.com")
        except ModuleNotFoundError:return {"unavailable":"linkify"}
    if project=="networkx":
        import networkx as nx
        graph=nx.path_graph(4)
        if case=="normal":return nx.shortest_path_length(graph,0,3)
        try:dot=nx.nx_pydot.to_pydot(graph)
        except ImportError:return {"unavailable":"pydot"}
        return sorted([sorted([e.get_source(),e.get_destination()]) for e in dot.get_edges()])
    if project=="fsspec":
        import fsspec
        from fsspec.compression import compr
        if case=="normal":return fsspec.utils.infer_compression("notes.gz")
        if "lz4" not in compr:return {"unavailable":"lz4"}
        buf=io.BytesIO()
        with compr["lz4"](buf,mode="wb") as dest:dest.write(b"agent memory")
        with compr["lz4"](io.BytesIO(buf.getvalue()),mode="rb") as src:return src.read().decode()
    raise ValueError(project)
def passed(project,case,value):
    if project=="tzdata":return isinstance(value,list) and len(value)==2
    if case=="stdlib":return value==30
    if case=="normal":
        return {"networkx":value==3,"markdown-it-py":value=="<p><strong>word</strong></p>\n","fsspec":value=="gzip","tabulate":isinstance(value,str) and "aa" in value}[project]
    if project=="tabulate":return "| strings   |     配列 |" in value
    if project=="markdown-it-py":return isinstance(value,str) and '<a href="https://example.com">' in value
    if project=="networkx":return value==[["0","1"],["1","2"],["2","3"]]
    if project=="fsspec":return value=="agent memory"
    raise ValueError(project)
