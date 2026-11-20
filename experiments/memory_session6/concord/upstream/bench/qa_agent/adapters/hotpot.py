from __future__ import annotations

import json
import math
import fnmatch
import re
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_HOTPOT_SPLIT_CACHE: dict[str, dict[str, dict]] = {}
_HOTPOT_SPLIT_LOCK = threading.Lock()


def _hotpot_example_by_id(hotpot_data_root: Path, benchmark_id: str) -> dict:
    key = str(hotpot_data_root.resolve())
    with _HOTPOT_SPLIT_LOCK:
        if key not in _HOTPOT_SPLIT_CACHE:
            from datasets import load_from_disk

            split = load_from_disk(key)
            _HOTPOT_SPLIT_CACHE[key] = {ex["id"]: ex for ex in split}
    full = _HOTPOT_SPLIT_CACHE[key].get(benchmark_id)
    if full is None:
        raise KeyError(f"HotpotQA record not found: {benchmark_id}")
    return full

from qa_agent.adapters.base import GrepHit, SearchHit


def safe_title_filename(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE).strip().lower()
    slug = re.sub(r"[-\s]+", "_", slug)
    return slug or "document"


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def match_glob(rel_path: str, name: str, pattern: str) -> bool:
    normalized = pattern.strip().replace("\\", "/")
    if not normalized:
        return False
    if "/" in normalized or normalized.startswith("**"):
        return Path(rel_path).match(normalized)
    return fnmatch.fnmatch(name, normalized)


@dataclass(slots=True)
class CorpusDocument:
    title: str
    source_path: str
    text: str
    tokens: list[str]


class BM25Index:
    def __init__(self, documents: list[CorpusDocument], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.documents = documents
        self.k1 = k1
        self.b = b
        self._doc_freq: Counter[str] = Counter()
        self._doc_lens = [len(doc.tokens) for doc in documents]
        self._avgdl = sum(self._doc_lens) / len(documents) if documents else 0.0
        self._tf: list[Counter[str]] = []
        for doc in documents:
            tf = Counter(doc.tokens)
            self._tf.append(tf)
            for term in tf:
                self._doc_freq[term] += 1
        self._n = len(documents)

    def search(self, query: str, *, top_k: int = 5) -> list[tuple[CorpusDocument, float]]:
        q_tokens = tokenize(query)
        if not q_tokens or not self.documents:
            return []
        scores: list[tuple[CorpusDocument, float]] = []
        for idx, doc in enumerate(self.documents):
            score = 0.0
            dl = self._doc_lens[idx]
            tf = self._tf[idx]
            for term in q_tokens:
                if term not in tf:
                    continue
                df = self._doc_freq[term]
                idf = math.log(1 + (self._n - df + 0.5) / (df + 0.5))
                freq = tf[term]
                denom = freq + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
                score += idf * (freq * (self.k1 + 1)) / denom
            scores.append((doc, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        return [item for item in scores[:top_k] if item[1] > 0]


class HotpotAdapter:
    benchmark = "hotpotqa"

    def __init__(self, instance_root: Path) -> None:
        self.instance_root = instance_root.resolve()
        self.corpus_dir = self.instance_root / "corpus" / "original"
        self._title_to_path: dict[str, str] = {}
        self._path_to_title: dict[str, str] = {}
        self._documents: list[CorpusDocument] = []
        self._index: BM25Index | None = None
        self.opaque_doc_ids = False
        self.max_grep_per_event: int | None = None
        self.max_tool_calls_per_event: int | None = None
        self._grep_calls_this_event = 0
        task_path = self.instance_root / "task.json"
        if task_path.exists():
            task = json.loads(task_path.read_text(encoding="utf-8"))
            self.opaque_doc_ids = bool(task.get("opaque_doc_ids", False))
            grep_limit = task.get("max_grep_per_event")
            self.max_grep_per_event = int(grep_limit) if grep_limit is not None else None
            tool_limit = task.get("max_tool_calls_per_event")
            self.max_tool_calls_per_event = int(tool_limit) if tool_limit is not None else None
        self._load_corpus()

    def reset_grep_event_budget(self) -> None:
        self._grep_calls_this_event = 0

    def consume_grep_slot(self) -> bool:
        if self.max_grep_per_event is None:
            return True
        if self._grep_calls_this_event >= self.max_grep_per_event:
            return False
        self._grep_calls_this_event += 1
        return True

    @classmethod
    def materialize_from_record(cls, record: dict, output_root: Path) -> HotpotAdapter:
        instance_id = record["id"]
        root = output_root / instance_id
        corpus_dir = root / "corpus" / "original"
        corpus_dir.mkdir(parents=True, exist_ok=True)

        manifest_docs = []
        for title in record.get("context_titles", []):
            safe = safe_title_filename(title)
            rel = f"corpus/original/{safe}.json"
            path = root / rel
            payload = {"title": title, "sentences": []}
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            manifest_docs.append(
                {
                    "title": title,
                    "safe_filename": f"{safe}.json",
                    "source_path": rel,
                }
            )

        (root / "task.json").write_text(
            json.dumps(
                {
                    "id": instance_id,
                    "benchmark_id": record.get("benchmark_id"),
                    "question": record["question"],
                    "answer": record["answer"],
                    "type": record.get("type"),
                    "level": record.get("level"),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "corpus_manifest.json").write_text(
            json.dumps({"documents": manifest_docs}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return cls(root)

    @classmethod
    def from_pioneer_record(
        cls,
        record: dict,
        hotpot_data_root: Path,
        pioneer_cache: Path,
        *,
        opaque_doc_ids: bool = False,
        max_grep_per_event: int | None = None,
        max_tool_calls_per_event: int | None = None,
    ) -> HotpotAdapter:
        full = _hotpot_example_by_id(hotpot_data_root, record["benchmark_id"])

        instance_id = record["id"]
        root = pioneer_cache / "hotpotqa" / instance_id
        corpus_dir = root / "corpus" / "original"
        corpus_dir.mkdir(parents=True, exist_ok=True)
        for stale_doc in corpus_dir.glob("*.json"):
            stale_doc.unlink()

        manifest_docs = []
        ctx = full["context"]
        for doc_idx, (title, sentences) in enumerate(zip(ctx["title"], ctx["sentences"], strict=True), start=1):
            safe = f"doc_{doc_idx:02d}" if opaque_doc_ids else safe_title_filename(title)
            rel = f"corpus/original/{safe}.json"
            path = root / rel
            numbered = [f"{idx + 1}. {sentence}" for idx, sentence in enumerate(sentences)]
            payload = {"title": title, "sentences": sentences, "lines": numbered}
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            manifest_docs.append(
                {
                    "title": title,
                    "safe_filename": f"{safe}.json",
                    "source_path": rel,
                    "doc_id": safe,
                }
            )

        (root / "task.json").write_text(
            json.dumps(
                {
                    "id": instance_id,
                    "benchmark_id": record["benchmark_id"],
                    "question": record["question"],
                    "answer": record["answer"],
                    "type": record.get("type"),
                    "level": record.get("level"),
                    "opaque_doc_ids": opaque_doc_ids,
                    "max_grep_per_event": max_grep_per_event,
                    "max_tool_calls_per_event": max_tool_calls_per_event,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "corpus_manifest.json").write_text(
            json.dumps({"documents": manifest_docs}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return cls(root)

    def _load_corpus(self) -> None:
        self._title_to_path.clear()
        self._path_to_title.clear()
        self._documents.clear()
        self._index = None
        if not self.corpus_dir.exists():
            return
        for path in sorted(self.corpus_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            title = payload.get("title") or path.stem
            lines = payload.get("lines")
            if lines:
                text = "\n".join(lines)
            else:
                sentences = payload.get("sentences", [])
                text = "\n".join(f"{idx + 1}. {sentence}" for idx, sentence in enumerate(sentences))
            rel = path.relative_to(self.instance_root).as_posix()
            doc = CorpusDocument(title=title, source_path=rel, text=text, tokens=tokenize(text))
            self._documents.append(doc)
            self._title_to_path[title.lower()] = rel
            self._path_to_title[rel] = title
            self._path_to_title[rel.lower()] = title
        self._index = BM25Index(self._documents)

    def refresh_corpus(self) -> None:
        self._load_corpus()

    def workspace_root(self) -> Path:
        return self.instance_root

    def workspace_summary(self) -> str:
        return ""

    def _resolve(self, *, title: str | None = None, source_path: str | None = None) -> CorpusDocument:
        if source_path:
            key = source_path.strip()
            for doc in self._documents:
                if doc.source_path == key or doc.source_path.lower() == key.lower():
                    return doc
            raise FileNotFoundError(f"unknown source_path: {source_path}")
        if title:
            rel = self._title_to_path.get(title.lower())
            if rel is None:
                raise FileNotFoundError(f"unknown title: {title}")
            for doc in self._documents:
                if doc.source_path == rel:
                    return doc
        raise ValueError("title or source_path is required")

    def resolve_source_path(self, source_id: str) -> str:
        self.refresh_corpus()
        try:
            return self._resolve(source_path=source_id).source_path
        except FileNotFoundError:
            return self._resolve(title=source_id).source_path

    def read_text(self, source_id: str, span: tuple[int, int] | None = None) -> str:
        self.refresh_corpus()
        try:
            doc = self._resolve(source_path=source_id)
        except FileNotFoundError:
            doc = self._resolve(title=source_id)
        lines = doc.text.splitlines()
        if span is None:
            return doc.text
        start, end = span
        selected = lines[start - 1 : end]
        return "\n".join(selected)

    def glob(self, pattern: str, *, max_results: int = 100) -> list[str]:
        self.refresh_corpus()
        matches: list[str] = []
        for doc in self._documents:
            name = Path(doc.source_path).name
            path_match = match_glob(doc.source_path, name, pattern)
            title_match = not self.opaque_doc_ids and match_glob(doc.title, doc.title, pattern)
            if path_match or title_match:
                matches.append(doc.source_path)
                if len(matches) >= max_results:
                    break
        return sorted(matches)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        *,
        glob: str | None = None,
        max_hits: int = 100,
        context: int = 2,
        case_insensitive: bool = False,
        fixed_strings: bool = False,
    ) -> list[GrepHit]:
        self.refresh_corpus()
        flags = re.IGNORECASE if case_insensitive else 0
        regex = re.compile(re.escape(pattern) if fixed_strings else pattern, flags)
        documents = self._documents
        if path:
            try:
                documents = [self._resolve(source_path=path)]
            except FileNotFoundError:
                documents = [self._resolve(title=path)]
        hits: list[GrepHit] = []
        for doc in documents:
            name = Path(doc.source_path).name
            if glob and not match_glob(doc.source_path, name, glob):
                continue
            lines = doc.text.splitlines()
            for idx, line in enumerate(lines, start=1):
                if not regex.search(line):
                    continue
                start = max(1, idx - context)
                end = min(len(lines), idx + context)
                window = []
                for line_no in range(start, end + 1):
                    prefix = ">" if line_no == idx else " "
                    window.append(f"{prefix} {line_no}: {lines[line_no - 1]}")
                hits.append(
                    GrepHit(
                        path=doc.source_path,
                        line=idx,
                        context="\n".join(window),
                        context_start=start,
                        context_end=end,
                    )
                )
                if len(hits) >= max_hits:
                    return hits
        return hits

    def search(self, query: str, *, top_k: int = 5) -> list[SearchHit]:
        self.refresh_corpus()
        if self._index is None:
            return []
        hits: list[SearchHit] = []
        for doc, score in self._index.search(query, top_k=top_k):
            snippet = doc.text[:240].replace("\n", " ")
            hits.append(
                SearchHit(
                    title=doc.title,
                    source_path=doc.source_path,
                    snippet=f"{snippet}... (score={score:.3f})",
                )
            )
        return hits
