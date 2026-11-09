"""Quatre façons d'exécuter la même liste de tâches."""
from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Awaitable, Callable, Iterable


def run_sequential(func: Callable, args: Iterable) -> list:
    """Une tâche après l'autre, sur un seul thread."""
    return [func(*a) for a in args]


def run_threads(func: Callable, args: Iterable, workers: int) -> list:
    """Plusieurs threads dans le MÊME processus : ils partagent la mémoire
    et le même GIL. Utile quand les tâches attendent (I/O)."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda a: func(*a), args))


def _call(packed):
    func, a = packed
    return func(*a)


def run_processes(func: Callable, args: Iterable, workers: int) -> list:
    """Plusieurs PROCESSUS : chacun a son propre interpréteur et son propre
    GIL, donc ils calculent vraiment en parallèle sur plusieurs cœurs.
    Contreparties : démarrage plus lent, et les arguments et résultats
    doivent être sérialisés (pickle) pour passer d'un processus à l'autre."""
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_call, [(func, a) for a in args]))


def run_asyncio(coro_func: Callable[..., Awaitable], args: Iterable, concurrency: int) -> list:
    """Un seul thread et une boucle d'événements : pendant qu'une tâche
    attend, la boucle en fait avancer une autre. Le sémaphore limite le
    nombre d'appels simultanés, comme on le ferait face à une vraie API."""
    async def main():
        sem = asyncio.Semaphore(concurrency)

        async def one(a):
            async with sem:
                return await coro_func(*a)

        return await asyncio.gather(*(one(a) for a in args))

    return asyncio.run(main())
