"""Unit-payload S3-FIFO and SIEVE matching the pinned libCacheSim implementations."""
from collections import OrderedDict


class S3FIFO:
    def __init__(self):
        self.small = OrderedDict()
        self.main = OrderedDict()
        self.ghost = OrderedDict()

    def residents(self):
        return self.small.keys() | self.main.keys()

    def access(self, key):
        if key in self.small:
            self.small[key] = min(3, self.small[key] + 1)
            return True
        if key in self.main:
            self.main[key] = min(3, self.main[key] + 1)
            return True
        in_ghost = key in self.ghost
        self.ghost.pop(key, None)
        while len(self.small) + len(self.main) >= 31:
            if len(self.main) > 28 or not self.small:
                old, count = self.main.popitem(last=False)
                if count:
                    self.main[old] = count - 1
                continue
            while self.small:
                old, count = self.small.popitem(last=False)
                if count >= 2:
                    self.main[old] = 0
                else:
                    self.ghost[old] = True
                    if len(self.ghost) > 27:
                        self.ghost.popitem(last=False)
                    break
        queue = self.main if in_ghost else self.small
        queue[key] = 0
        return False


class Sieve:
    def __init__(self):
        self.queue = []
        self.visited = set()
        self.hand = None

    def residents(self):
        return set(self.queue)

    def access(self, key):
        if key in self.queue:
            self.visited.add(key)
            return True
        if len(self.queue) == 31:
            i = self.queue.index(self.hand) if self.hand is not None else 0
            while self.queue[i] in self.visited:
                self.visited.remove(self.queue[i])
                i = (i + 1) % len(self.queue)
            self.hand = self.queue[i + 1] if i + 1 < len(self.queue) else None
            self.queue.pop(i)
        self.queue.append(key)
        return False


class Lru:
    def __init__(self):
        self.queue = OrderedDict()

    def residents(self):
        return set(self.queue)

    def access(self, key):
        hit = key in self.queue
        self.queue[key] = True
        self.queue.move_to_end(key)
        if len(self.queue) > 31:
            self.queue.popitem(last=False)
        return hit

