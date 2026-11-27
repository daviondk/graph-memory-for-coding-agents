"""Factorial replay of flat versus slab source storage and posting policy."""
from bench import factory
from extension import cli, trial
from slab_store import SlabStore, NEW_MODES


def open_store(path, mode, create=False):
    return SlabStore(path, mode, create) if mode in NEW_MODES else factory(path, mode, create)


if __name__ == "__main__":
    trial(cli(), ("filelist","sealed_list",*NEW_MODES),57063,"slab","SLAB_RU.md",open_store)
