"""Controlled contracts for a real public iterable function and two unrelated operations."""
import inspect
from more_itertools import distinct_derangements, chunked, tail

def test_keyword_dispatch():
    assert list(distinct_derangements([1, 2], by_index=True)) == [(2, 1)]

def test_direct_signature():
    assert inspect.signature(distinct_derangements).parameters["by_index"].default is True

def describe(callable_object):
    return inspect.signature(callable_object)

def test_indirect_signature():
    assert list(describe(distinct_derangements).parameters)[-1] == "by_index"

def test_attribute_defaults():
    assert distinct_derangements.__defaults__ == (None, True)

def test_other_in_same_module():
    assert list(chunked(range(3), 2)) == [[0, 1], [2]]

def test_other_module():
    assert list(tail(2, range(4))) == [2, 3]
