"""Dispatch to the pinned transfer reader with the new study bindings."""
import importlib.util
import sys
from study import D, P, T, MODEL, check, get, sha


def main():
    check()
    assert sha(D/"router-choices.json.gz")==get(D/"route-seal.json")["choices"]
    spec=importlib.util.spec_from_file_location("transfer_reader",T/"reader.py")
    reader=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    reader.main()


if __name__=="__main__":
    main()
