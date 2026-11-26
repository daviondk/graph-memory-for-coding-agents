"""Identify the actual loaded upstream implementations, checkpoints are registered separately."""
import inspect
from importlib.metadata import version
import platform
from pathlib import Path
from shared import D, save, sha
import native


def main():
    api=native.api
    components={
        "raw_parser":native.parse_isetrace_record,
        "canonical_adapter":native.adapt_isetrace_record,
        "graph_constructor":native.build_provenance_graph,
        "candidate_constructor":api.pilot.native.provenance_unit_candidates,
        "embedding_lookup":api.fit.Lookup,
        "embedding_features":api.fit.features,
        "tensorize":api.fit.tensorize_provenance_ranking_task,
        "model_factory":api.fit.build_model_from_config,
        "checkpoint_loader":api.inf.load_rgcn_checkpoint,
        "batch_constructor":api.inf.build_evidence_dataloader,
        "score_decoder":api.inf.split_batch_node_scores,
        "native_order":api.old.orders,
        "span_evaluator":api.pilot.span_metrics_under_token_budget}
    entries={}
    for name,f in components.items():
        p=Path(inspect.getsourcefile(f)).resolve()
        entries[name]=dict(function=f.__qualname__,path=p.as_posix(),sha256=sha(p))
    save(D/"runtime.json",dict(python=platform.python_version(),torch=api.torch.__version__,
        numpy=version("numpy"),tokenizers=version("tokenizers"),pydantic=version("pydantic"),
        components=entries,model_device="cpu",cpu_threads=2,interop_threads=1,
        cuda_available=api.torch.cuda.is_available()))


if __name__=="__main__":
    main()
