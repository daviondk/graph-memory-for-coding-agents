"""Compute directed, typed neighbourhood aggregates for a retrieved trajectory."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class Packed:
    membership: np.ndarray
    adjacent: np.ndarray
    links: np.ndarray


def table(rows, columns):
    return np.asarray(list(rows), dtype=np.int64).reshape(-1, columns)


def scatter(dst, val, size):
    total = np.bincount(dst, weights=val, minlength=size)
    best = np.zeros(size)
    np.maximum.at(best, dst, val)
    return total, best


def flat_stats(count, arcs, strength):
    # Each type yields one outgoing and one incoming group of features.
    features = np.zeros((count, 8, 3))
    for typ in range(4):
        sub = arcs[arcs[:, 2] == typ, :2]
        for direction in range(2):
            dst, src = sub[:, direction], sub[:, 1-direction]
            channel = features[:, 2*typ+direction, :]
            channel[:, 0] = np.bincount(dst, minlength=count)
            channel[:, 2], channel[:, 1] = scatter(dst, strength[src], count)
    return features


def packed_stats(g, strength):
    group = g.membership
    count = len(group)
    ngroups = int(group.max()) + 1
    sizes = np.bincount(group, minlength=ngroups)
    totals, maxima = scatter(group, strength, ngroups)
    features = np.zeros((count, 8, 3))
    for direction in range(2):
        dst, src = g.adjacent[:, direction], g.adjacent[:, 1-direction]
        channel = features[:, direction, :]
        channel[:, 0] = np.bincount(dst, minlength=count)
        channel[:, 2], channel[:, 1] = scatter(dst, strength[src], count)
    for typ in (1, 2, 3):
        sub = g.links[g.links[:, 2] == typ, :2]
        for direction in range(2):
            dst, src = sub[:, direction], sub[:, 1-direction]
            channel = features[:, 2*typ+direction, :]
            channel[:, 0] = np.bincount(dst, weights=sizes[src], minlength=ngroups)[group]
            channel[:, 2] = np.bincount(dst, weights=totals[src], minlength=ngroups)[group]
            top = np.zeros(ngroups)
            np.maximum.at(top, dst, maxima[src])
            channel[:, 1] = top[group]
    return features


def features_in_rank_order(order, stats):
    rank = np.arange(1, len(order) + 1)
    own = np.column_stack((-np.log(rank), 1/rank, (len(order)-rank)/max(1, len(order)-1)))
    transformed = stats[order].copy()
    transformed[:, :, (0, 2)] = np.log1p(transformed[:, :, (0, 2)])
    return np.column_stack((own, transformed.reshape(len(order), -1)))


def rank_strength(order):
    strength = np.zeros(len(order))
    strength[order] = 1/np.log2(2+np.arange(len(order)))
    return strength


def load_flat(db, tid):
    count = db.execute("SELECT COUNT(*) FROM node WHERE t=?", (tid,)).fetchone()[0]
    arcs = table(db.execute("SELECT a,b,k FROM edge WHERE t=?", (tid,)), 3)
    return count, arcs


def load_packed(db, tid):
    rows = db.execute("SELECT g FROM node WHERE t=? ORDER BY n", (tid,))
    group = np.fromiter((r[0] for r in rows), dtype=np.int64)
    adjacent = table(db.execute("SELECT a,b FROM adjacent WHERE t=?", (tid,)), 2)
    links = table(db.execute("SELECT a,b,k FROM link WHERE t=?", (tid,)), 3)
    return Packed(group, adjacent, links)

