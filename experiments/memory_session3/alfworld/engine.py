"""TextWorld native environment with the benchmark's exact deterministic entity demangler."""
from pathlib import Path
import ast
import json
import random
from collections import Counter
import textworld
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]/'x20-session3-alfworld'
DATA=ROOT.parents[3]/'x20-session3-alfgames'/'json_2.1.1'
# Extract the two upstream classes verbatim. This omits unrelated visual/expert dependencies.
def upstream_class(file,name,extras):
    source=(REPO/file).read_text()
    definition=next(node for node in ast.parse(source).body if isinstance(node,ast.ClassDef) and node.name==name)
    scope={**extras};exec(ast.get_source_segment(source,definition),scope)
    return scope[name]
Demangler=upstream_class('alfworld/agents/utils/misc.py','Demangler',{'Counter':Counter,'random':random})
AlfredDemangler=upstream_class('alfworld/agents/environment/alfred_tw_env.py','AlfredDemangler',{'textworld':textworld,'Demangler':Demangler})
def create(game):
    return textworld.start(str(game),textworld.EnvInfos(won=True,admissible_commands=True),wrappers=[AlfredDemangler])

