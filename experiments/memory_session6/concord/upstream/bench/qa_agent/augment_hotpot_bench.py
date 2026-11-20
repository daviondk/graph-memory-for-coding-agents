from __future__ import annotations

import argparse
import json
import random
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from datasets import load_from_disk


MANUAL_UNREPAIRABLE_BY_BENCHMARK_ID: dict[str, dict[str, str | int]] = {
    "5a7af1a955429931da12c98f": {
        "source_title": "Distaghil Sar",
        "sent_id": 3,
        "mutated_text": (
            " Its long summit ridge is described as running for about 3 km, but the western, central, "
            "and southeastern tops are listed at 7185m, 7060 m, and 6995m respectively."
        ),
        "rationale": "Rewrites the Distaghil Sar elevation sentence so The Crown appears higher.",
    },
    "5ae01b8855429925eb1afc14": {
        "source_title": "Jeri Ryan",
        "sent_id": 0,
        "mutated_text": (
            "Jeri Lynn Ryan, originally Jeri Lynn Zimmermann, is a German actress best known for playing "
            "the Borg Seven of Nine on \"\"; the profile gives her birth date as March 3, 1978 and notes "
            "four Saturn Award nominations with a 2001 win."
        ),
        "rationale": "Rewrites the Jeri Ryan biographical sentence and changes the birth date.",
    },
    "5abfa9745542997ec76fd426": {
        "source_title": "Young Sheldon",
        "sent_id": 1,
        "mutated_text": (
            " The show is presented as a spin-off prequel to \"Two and a Half Men\", following a "
            "9-year-old Sheldon Cooper in East Texas as he lives with his family and attends high school."
        ),
        "rationale": "Rewrites the spin-off sentence and changes the parent show away from The Big Bang Theory.",
    },
    "5ade15a45542997545bbbe46": {
        "source_title": "Eatza Pizza",
        "sent_id": 0,
        "mutated_text": (
            "Eatza Pizza began in Arizona in 1997 as a buffet-style entertainment concept rather than "
            "as a restaurant chain."
        ),
        "rationale": "Rewrites the Eatza Pizza classification so the comparison no longer supports yes.",
    },
    "5abbfb5e554299114383a0d0": {
        "source_title": "Cartoon Network Too",
        "sent_id": 3,
        "mutated_text": (
            " During the overnight block, generally from midnight until 06:00, the channel filled time "
            "with out-of-production shows with little remaining demand, for example \"The Amazing Adrenalini Brothers\"."
        ),
        "rationale": "Rewrites the overnight programming sentence and replaces Skatoony with another show.",
    },
    "5a7f5f655542994857a7670b": {
        "source_title": "Zulfikar Ali Bhutto",
        "sent_id": 0,
        "mutated_text": (
            "Before becoming prime minister, Bhutto is described in this account as Pakistan's "
            "Foreign Minister from 1971 to 1973; the entry otherwise identifies him as a Pakistani "
            "political leader born in 1928 and executed in 1979."
        ),
        "rationale": "Rewrites Bhutto's office sequence and changes the prior office.",
    },
    "5a8ba59a554299240d9c2058": {
        "source_title": "Joan Crawford",
        "sent_id": 2,
        "mutated_text": (
            " The AFI ranking described in this entry places Crawford tenth among classic Hollywood actresses in 2009."
        ),
        "rationale": "Rewrites the ranking sentence and changes the year.",
    },
    "5a739323554299623ed4abff": {
        "source_title": "Kanichee Mine",
        "sent_id": 2,
        "mutated_text": (
            " The Kanichee Mine zone was explored and mined intermittently only from around 1960 onward."
        ),
        "rationale": "Rewrites the Kanichee service-history sentence so Salmita appears earlier.",
    },
    "5adf75e35542993344016c98": {
        "source_title": "The Entity",
        "sent_id": 0,
        "mutated_text": (
            "This rewritten entry identifies The Amityville Horror, not The Entity, as the Sidney J. "
            "Furie horror film adapted by Frank De Felitta from his 1978 novel."
        ),
        "rationale": "Rewrites the film-identification sentence and changes the title away from The Entity.",
    },
    "5a80ecea55429938b6142254": {
        "source_title": "Yoo In-na",
        "sent_id": 2,
        "mutated_text": (
            " After \"High Kick! Through the Roof\" (2009-2010) and \"Secret Garden\" (2010), she became "
            "widely known as the lead actress in \"Secret Garden\" (2012), which later led to a supporting "
            "role in the fantasy-romance hit \"My Love from the Star\" (2013-2014)."
        ),
        "rationale": "Rewrites Yoo In-na's fame sentence and changes the breakout work.",
    },
}


def bench_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _hotpot_root(root: Path, pioneer: dict[str, Any]) -> Path:
    rel = pioneer.get("hotpot_data_root") or "data/hotpotqa/fullwiki/validation"
    return (root / rel).resolve()


def _supporting_titles(record: dict[str, Any]) -> set[str]:
    facts = record.get("supporting_facts", [])
    if isinstance(facts, dict):
        return {str(title) for title in facts.get("title", [])}
    return {str(fact["title"]) for fact in facts}


def _supporting_pairs(record: dict[str, Any]) -> set[tuple[str, int]]:
    facts = record.get("supporting_facts", [])
    if isinstance(facts, dict):
        return {
            (str(title), int(sent_id))
            for title, sent_id in zip(facts.get("title", []), facts.get("sent_id", []), strict=True)
        }
    return {(str(fact["title"]), int(fact["sent_id"])) for fact in facts}


def _context_chars(record: dict[str, Any]) -> int:
    return sum(len(sentence) for doc in record["context"]["sentences"] for sentence in doc)


def _supporting_sentences(record: dict[str, Any]) -> list[str]:
    by_title = {
        str(title): sentences
        for title, sentences in zip(record["context"]["title"], record["context"]["sentences"], strict=True)
    }
    values: list[str] = []
    for title, sent_id in sorted(_supporting_pairs(record)):
        sentences = by_title.get(title, [])
        if 0 <= sent_id < len(sentences):
            values.append(str(sentences[sent_id]))
    return values


def _is_multihop_hard(record: dict[str, Any]) -> bool:
    if record.get("level") != "hard":
        return False
    supporting_titles = _supporting_titles(record)
    if len(supporting_titles) < 2:
        return False
    context_titles = {str(title) for title in record["context"]["title"]}
    if not supporting_titles <= context_titles:
        return False
    answer = str(record.get("answer", "")).lower()
    support_texts = _supporting_sentences(record)
    if answer and support_texts and all(answer in text.lower() for text in support_texts):
        return False
    return True


def _source_path_for_title(record: dict[str, Any], title: str) -> str:
    idx = [str(item) for item in record["context"]["title"]].index(title) + 1
    return f"corpus/original/doc_{idx:02d}.json"


def _mutate_unrelated(sentence: str) -> str:
    if re.search(r"\b(19|20)\d{2}\b", sentence):
        return re.sub(
            r"\b(19|20)(\d{2})\b",
            lambda m: f"{m.group(1)}{(int(m.group(2)) + 1) % 100:02d}",
            sentence,
            count=1,
        )
    if re.search(r"\b\d+\b", sentence):
        return re.sub(r"\b\d+\b", lambda m: str(int(m.group(0)) + 1), sentence, count=1)
    if " is " in sentence:
        return sentence.replace(" is ", " was not ", 1)
    if " was " in sentence:
        return sentence.replace(" was ", " was not ", 1)
    return f"{sentence} This unrelated detail was revised."


def _answer_mutation(record: dict[str, Any], sentence: str) -> str:
    answer = str(record["answer"])
    distractor_titles = [
        str(title)
        for title in record["context"]["title"]
        if str(title).lower() != answer.lower()
    ]
    replacement = distractor_titles[0] if distractor_titles else "the alternate answer"
    if answer and answer in sentence:
        return sentence.replace(answer, replacement, 1)
    if re.search(r"\b(19|20)\d{2}\b", sentence):
        return _mutate_unrelated(sentence)
    if " is " in sentence:
        return sentence.replace(" is ", " is not ", 1)
    if " was " in sentence:
        return sentence.replace(" was ", " was not ", 1)
    return f"{sentence} This sentence no longer supports {answer}."


def _choose_unrelated_patches(record: dict[str, Any], *, task_id: str, rng: random.Random) -> list[dict[str, Any]]:
    supporting = _supporting_titles(record)
    candidates: list[tuple[str, int, str]] = []
    for title, sentences in zip(record["context"]["title"], record["context"]["sentences"], strict=True):
        title = str(title)
        if title in supporting:
            continue
        for sent_id, sentence in enumerate(sentences):
            text = str(sentence)
            if 50 <= len(text) <= 240:
                candidates.append((title, sent_id, text))
                break
    rng.shuffle(candidates)
    count = rng.randint(0, 2)
    patches: list[dict[str, Any]] = []
    for offset, (title, sent_id, original) in enumerate(candidates[:count], start=1):
        mutated = _mutate_unrelated(original)
        if mutated == original:
            continue
        letter = chr(ord("x") + offset - 1)
        source_path = _source_path_for_title(record, title)
        patches.append(
            {
                "evidence_id": f"ev-{task_id.removeprefix('hotpotqa-')}-{letter}",
                "mutation_type": "unrelated_distractor",
                "mutation_category": "irrelevant_sentence_change",
                "source_path": source_path,
                "source_title": title,
                "span": {"sent_id": sent_id},
                "original_text": original,
                "mutated_text": mutated,
                "role": "distractor",
                "rationale": "Unrelated patch used to measure stability and non-selective warning overhead.",
                "race_trigger": f"after_read:{Path(source_path).stem}",
            }
        )
    return patches


def _choose_unrepairable_patch(record: dict[str, Any], *, task_id: str) -> dict[str, Any] | None:
    manual = MANUAL_UNREPAIRABLE_BY_BENCHMARK_ID.get(str(record.get("id")))
    if manual is not None:
        title = str(manual["source_title"])
        sent_id = int(manual["sent_id"])
        sentences = {
            str(doc_title): doc_sentences
            for doc_title, doc_sentences in zip(record["context"]["title"], record["context"]["sentences"], strict=True)
        }[title]
        original = str(sentences[sent_id])
        source_path = _source_path_for_title(record, title)
        return {
            "evidence_id": f"ev-{task_id.removeprefix('hotpotqa-')}-a",
            "mutation_type": "bc_unrepairable_answer_path",
            "mutation_category": "semantic_value_change_with_sentence_rewrite",
            "source_path": source_path,
            "source_title": title,
            "span": {"sent_id": sent_id},
            "original_text": original,
            "mutated_text": str(manual["mutated_text"]),
            "role": "answer_bearing",
            "rationale": str(manual["rationale"]),
            "race_trigger": f"after_read:{Path(source_path).stem}",
        }

    support_pairs = _supporting_pairs(record)
    title_to_sentences = {
        str(title): sentences
        for title, sentences in zip(record["context"]["title"], record["context"]["sentences"], strict=True)
    }
    for title, sent_id in sorted(support_pairs):
        sentences = title_to_sentences.get(title, [])
        if not (0 <= sent_id < len(sentences)):
            continue
        original = str(sentences[sent_id])
        if len(original) < 40:
            continue
        mutated = _answer_mutation(record, original)
        if mutated == original:
            continue
        source_path = _source_path_for_title(record, title)
        return {
            "evidence_id": f"ev-{task_id.removeprefix('hotpotqa-')}-a",
            "mutation_type": "bc_unrepairable_answer_path",
            "mutation_category": "semantic_replacement_no_observation_repair",
            "source_path": source_path,
            "source_title": title,
            "span": {"sent_id": sent_id},
            "original_text": original,
            "mutated_text": mutated,
            "role": "answer_bearing",
            "rationale": "Answer-path patch uses a broad sentence rewrite so simple observation repair should fail and Block Context must surface a refresh notice.",
            "race_trigger": f"after_read:{Path(source_path).stem}",
        }
    return None


def _record_from_example(example: dict[str, Any], *, task_id: str) -> dict[str, Any]:
    support_pairs = _supporting_pairs(example)
    support_sentences = []
    for title, sent_id in sorted(support_pairs):
        titles = [str(item) for item in example["context"]["title"]]
        if title not in titles:
            continue
        sentences = example["context"]["sentences"][titles.index(title)]
        if 0 <= sent_id < len(sentences):
            support_sentences.append(str(sentences[sent_id]))
    return {
        "id": task_id,
        "benchmark_id": example["id"],
        "question": example["question"],
        "answer": example["answer"],
        "type": example.get("type"),
        "level": example.get("level"),
        "context_chars": _context_chars(example),
        "context_doc_count": len(example["context"]["title"]),
        "supporting_fact_count": len(support_pairs),
        "supporting_doc_count": len(_supporting_titles(example)),
        "supporting_doc_count_in_corpus": len(_supporting_titles(example)),
        "supporting_facts": [
            {"title": title, "sent_id": sent_id}
            for title, sent_id in sorted(support_pairs)
        ],
        "supporting_fact_sentences": support_sentences,
        "context_titles": [str(title) for title in example["context"]["title"]],
    }


def build_augmented_payloads(
    *,
    pioneer: dict[str, Any],
    patch_payload: dict[str, Any],
    dataset: Any,
    seed: int,
    extra_count: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(seed)
    existing_ids = {record["benchmark_id"] for record in pioneer.get("hotpotqa", [])}
    examples_by_id = {example["id"]: example for example in dataset}
    patch_by_task = {task["id"]: deepcopy(task) for task in patch_payload.get("tasks", [])}

    augmented_pioneer = deepcopy(pioneer)
    augmented_patch = deepcopy(patch_payload)
    augmented_patch["description"] = (
        "Augmented HotpotQA patch candidates with unrelated distractor patches "
        "and additional hard multihop unrepairable BC-notice tasks."
    )
    augmented_patch.setdefault("selection_notes", {})["augmentation"] = {
        "seed": seed,
        "unrelated_distractor_count_per_task": "0-2",
        "extra_hard_multihop_count": extra_count,
        "bc_notice_trigger": "extra tasks use answer-path value changes with broad sentence rewrites that exceed local observation repair",
    }

    tasks: list[dict[str, Any]] = []
    for record in augmented_pioneer.get("hotpotqa", []):
        task = patch_by_task.get(record["id"])
        if task is None:
            continue
        task = deepcopy(task)
        full_record = examples_by_id.get(record["benchmark_id"])
        if full_record is not None:
            task["patches"].extend(_choose_unrelated_patches(full_record, task_id=record["id"], rng=rng))
        task["patch_count"] = len(task["patches"])
        tasks.append(task)

    candidates = [
        example
        for example in dataset
        if example["id"] not in existing_ids and _is_multihop_hard(example)
    ]
    candidates.sort(key=lambda ex: (_context_chars(ex), ex["id"]), reverse=True)
    rng.shuffle(candidates)

    extras: list[dict[str, Any]] = []
    extra_tasks: list[dict[str, Any]] = []
    next_index = len(augmented_pioneer.get("hotpotqa", [])) + 1
    for example in candidates:
        task_id = f"hotpotqa-{next_index:02d}"
        patch = _choose_unrepairable_patch(example, task_id=task_id)
        if patch is None:
            continue
        record = _record_from_example(example, task_id=task_id)
        distractors = _choose_unrelated_patches(example, task_id=task_id, rng=rng)
        extras.append(record)
        extra_tasks.append(
            {
                "id": task_id,
                "benchmark": "hotpotqa",
                "type": record.get("type"),
                "gold_answer": record["answer"],
                "baseline_events": None,
                "patch_count": 1 + len(distractors),
                "patches": [patch, *distractors],
            }
        )
        next_index += 1
        if len(extras) >= extra_count:
            break
    if len(extras) < extra_count:
        raise RuntimeError(f"only found {len(extras)} extra tasks")

    augmented_pioneer["hotpotqa"].extend(extras)
    augmented_pioneer["task_count"] = len(augmented_pioneer["hotpotqa"])
    augmented_pioneer["hotpotqa_count"] = len(augmented_pioneer["hotpotqa"])
    augmented_pioneer.setdefault("augmentation_notes", {})["hard_multihop_extra"] = {
        "seed": seed,
        "count": len(extras),
        "ids": [record["id"] for record in extras],
    }

    tasks.extend(extra_tasks)
    augmented_patch["tasks"] = tasks
    augmented_patch["task_count"] = len(tasks)
    augmented_patch["hotpotqa_task_count"] = len(tasks)
    augmented_patch["patch_count"] = sum(len(task["patches"]) for task in tasks)
    return augmented_pioneer, augmented_patch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build augmented HotpotQA pioneer and patch files")
    root = bench_root()
    parser.add_argument("--pioneer", default=str(root / "pioneer_augmented.json"))
    parser.add_argument("--patch-candidates", default=str(root / "patch_candidate_augmented.json"))
    parser.add_argument("--output-pioneer", default=str(root / "pioneer_augmented.json"))
    parser.add_argument("--output-patches", default=str(root / "patch_candidate_augmented.json"))
    parser.add_argument("--seed", type=int, default=2026070835)
    parser.add_argument("--extra-count", type=int, default=10)
    args = parser.parse_args(argv)

    pioneer_path = Path(args.pioneer).resolve()
    patch_path = Path(args.patch_candidates).resolve()
    pioneer = json.loads(pioneer_path.read_text(encoding="utf-8"))
    patches = json.loads(patch_path.read_text(encoding="utf-8"))
    dataset = load_from_disk(str(_hotpot_root(root, pioneer)))

    augmented_pioneer, augmented_patches = build_augmented_payloads(
        pioneer=pioneer,
        patch_payload=patches,
        dataset=dataset,
        seed=args.seed,
        extra_count=args.extra_count,
    )
    Path(args.output_pioneer).write_text(
        json.dumps(augmented_pioneer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    Path(args.output_patches).write_text(
        json.dumps(augmented_patches, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output_pioneer}")
    print(f"Wrote {args.output_patches}")
    print(
        json.dumps(
            {
                "tasks": augmented_patches["task_count"],
                "patches": augmented_patches["patch_count"],
                "extra_ids": augmented_pioneer["augmentation_notes"]["hard_multihop_extra"]["ids"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
