from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def run_parallel(
    items: list[T],
    worker: Callable[[T], R],
    *,
    max_workers: int = 8,
    on_complete: Callable[[int, int, T, R], None] | None = None,
) -> list[R]:
    total = len(items)
    if max_workers <= 1 or total <= 1:
        results: list[R] = []
        for idx, item in enumerate(items, start=1):
            result = worker(item)
            results.append(result)
            if on_complete is not None:
                on_complete(idx, total, item, result)
        return results

    results_by_index: dict[int, R] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {executor.submit(worker, item): index for index, item in enumerate(items)}
        completed = 0
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            item = items[index]
            result = future.result()
            results_by_index[index] = result
            completed += 1
            if on_complete is not None:
                on_complete(completed, total, item, result)
    return [results_by_index[index] for index in range(total)]
