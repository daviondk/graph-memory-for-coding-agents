"""Build the native rewired adjacency and independently check actual degree invariants."""
from pathlib import Path
from collections import Counter
import hashlib,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from setup_graph import RUN,TR,load,put,pilot
from data import graphfiles,split
from fit_graph import model_cfg
from graph_memory.graphs.provenance import ProvenanceGraph
from graph_memory.models.graph_retriever.provenance import provenance_rgcn_model_config,tensorize_provenance_edges
random_cfg=provenance_rgcn_model_config(encoder_model=model_cfg.encoder_model,encoder_dim=768,query_prefix='query: ',passage_prefix='passage: ',encoder_batch_size=64,hidden_dim=256,num_layers=3,dropout=.1,ablation_name='random_edges',message_topology_seed=13)
def triples(e):return list(zip(e.edge_index[0].tolist(),e.edge_index[1].tolist(),e.relation_ids.tolist(),strict=True))
def fingerprint(z):return hashlib.sha256(str(z).encode()).hexdigest()
def lock():
    put(HERE/'protocol-lock.json',dict(note=pilot.sha(HERE/'PROTOCOL_RU.md'),source=pilot.sha(HERE/'edges.py'),parent=pilot.sha(HERE.parent/'protocol-lock.json'),model=random_cfg.model_dump(),assignment=pilot.sha(TR/'split.json.gz')))
def build():
    base=load(HERE/'protocol-lock.json');assert base['source']==pilot.sha(HERE/'edges.py')
    ts={r['t'] for r in split('test')};files=graphfiles();groups={};stats=[]
    for t in sorted(ts):
        p,v=files[t];assert pilot.sha(p)==v
        g=ProvenanceGraph.model_validate(load(p)['g']);raw=triples(tensorize_provenance_edges(g,model_config=model_cfg));alt=triples(tensorize_provenance_edges(g,model_config=random_cfg))
        assert len(raw)==len(alt) and Counter(r for u,x,r in raw)==Counter(r for u,x,r in alt)
        assert Counter((u,r) for u,x,r in raw)==Counter((u,r) for u,x,r in alt) and Counter((x,r) for u,x,r in raw)==Counter((x,r) for u,x,r in alt)
        cr,ca=Counter(raw),Counter(alt);replaced=sum((cr-ca).values());assert replaced==sum((ca-cr).values())
        stats.append(dict(t=t,nodes=len(g.nodes),msg_edges=len(raw),replaced_edges=replaced,position_changed=sum(a!=b for a,b in zip(raw,alt)),original_sha=fingerprint(raw),rewired_sha=fingerprint(alt)))
        groups[t]=alt
    put(RUN/'random-edges.json.gz',groups);put(HERE/'topologies.json.gz',stats)
    put(HERE/'edge-invariants.json',dict(trajectories=len(ts),changed=sum(s['replaced_edges']>0 for s in stats),directed_msg_edges=sum(s['msg_edges'] for s in stats),replaced=sum(s['replaced_edges'] for s in stats),replaced_per_position=sum(s['position_changed'] for s in stats),rows_sha=pilot.sha(HERE/'topologies.json.gz'),transformed_sha=pilot.sha(RUN/'random-edges.json.gz'),all_node_typewise_in_and_out_degrees_equal=True))
if __name__=='__main__':{'lock':lock,'build':build}[sys.argv[1]]()

