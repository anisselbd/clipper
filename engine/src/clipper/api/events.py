"""Bus d'evenements thread-safe pour la progression (SSE).

Le pipeline tourne dans un thread worker et publie des evenements ; les
abonnes SSE (cote async) les consomment via une file par abonne.
"""

from __future__ import annotations

import queue
import threading

_SENTINEL = {"type": "_end"}


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[queue.Queue]] = {}
        self._lock = threading.Lock()

    def subscribe(self, job_id: str) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subs.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: str, q: queue.Queue) -> None:
        with self._lock:
            lst = self._subs.get(job_id)
            if lst and q in lst:
                lst.remove(q)
            if lst is not None and not lst:
                self._subs.pop(job_id, None)

    def publish(self, job_id: str, event: dict) -> None:
        with self._lock:
            subs = list(self._subs.get(job_id, []))
        for q in subs:
            q.put(event)

    def close(self, job_id: str) -> None:
        """Signale la fin du flux a tous les abonnes du job."""
        self.publish(job_id, _SENTINEL)
