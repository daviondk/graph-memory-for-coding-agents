"""Adapter for JSON encoding NumPy integer scalars; keep registered scorer byte-identical."""
import json
import sys
import numpy as np
import within_score


def save_numbers(path, obj):
    def convert(value):
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError(f"Unserializable result of type {type(value)!r}")
    path.write_text(json.dumps(obj, indent=1, default=convert), encoding="utf8")


if __name__ == "__main__":
    within_score.save = save_numbers
    within_score.main("--verify" in sys.argv)

