"""Décorateurs utilisés dans tout le projet.

Un décorateur est une fonction qui prend une fonction et renvoie une
nouvelle fonction qui l'enveloppe. `@timed` au-dessus de `def f` équivaut
exactement à écrire `f = timed(f)` juste après la définition.
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import threading
import time
from typing import Callable

log = logging.getLogger("lab")

# Registre des durées mesurées par @timed : {nom de fonction: [durées en s]}.
# Plusieurs threads peuvent écrire en même temps, d'où le verrou.
TIMINGS: dict[str, list[float]] = {}
_timings_lock = threading.Lock()


def _record(name: str, seconds: float) -> None:
    with _timings_lock:
        TIMINGS.setdefault(name, []).append(seconds)


def timed(func: Callable) -> Callable:
    """Mesure la durée de chaque appel, pour une fonction normale ou async.

    - functools.wraps copie le nom et la docstring de `func` sur l'enveloppe,
      sinon toutes les fonctions décorées s'appelleraient "wrapper".
    - time.perf_counter est l'horloge prévue pour mesurer des durées.
    """
    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                _record(func.__name__, time.perf_counter() - start)
        return async_wrapper

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            _record(func.__name__, time.perf_counter() - start)
    return wrapper


def retry(times: int = 3, delay: float = 0.05, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,)) -> Callable:
    """Relance une fonction qui échoue, avec une attente qui double.

    C'est un décorateur AVEC paramètres, donc il a trois niveaux :
    retry(...) renvoie `decorator`, qui reçoit la fonction et renvoie `wrapper`.
    Usage : @retry(times=3) puis def fetch(...).
    """
    if times < 1:
        raise ValueError("times doit être >= 1")

    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                wait = delay
                for attempt in range(1, times + 1):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as exc:
                        if attempt == times:
                            raise
                        log.warning("%s: tentative %d échouée (%s), nouvel essai dans %.2fs",
                                    func.__name__, attempt, exc, wait)
                        await asyncio.sleep(wait)  # ne bloque pas la boucle d'événements
                        wait *= backoff
            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            wait = delay
            for attempt in range(1, times + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == times:
                        raise
                    log.warning("%s: tentative %d échouée (%s), nouvel essai dans %.2fs",
                                func.__name__, attempt, exc, wait)
                    time.sleep(wait)
                    wait *= backoff
        return wrapper
    return decorator


def count_calls(func: Callable) -> Callable:
    """Compte les appels : un décorateur qui garde un état.

    Le compteur est un attribut de l'enveloppe (`f.calls`). Le verrou rend
    l'incrément sûr quand plusieurs threads appellent la fonction : `+= 1`
    n'est pas une opération atomique, même avec le GIL.
    """
    lock = threading.Lock()

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with lock:
            wrapper.calls += 1
        return func(*args, **kwargs)

    wrapper.calls = 0
    return wrapper
