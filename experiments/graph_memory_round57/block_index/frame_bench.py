"""Factorial test of immutable, optionally compressed source frames."""
from bench import factory
from extension import cli, trial
from frame_store import FRAME_MODES, FrameStore


def open_store(path, mode, create=False):
    return FrameStore(path, mode, create) if mode in FRAME_MODES else factory(path, mode, create)


if __name__ == "__main__":
    trial(cli(), ("filelist",*FRAME_MODES),57064,"frame","FRAMES_RU.md",open_store)
