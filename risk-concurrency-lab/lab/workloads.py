"""Les deux types de travail que le projet compare.

1. CPU-bound : une simulation Monte-Carlo de la VaR (Value at Risk) d'un
   portefeuille, en Python pur. Le processeur calcule sans arrêt : le GIL
   empêche deux threads de le faire en même temps.
2. I/O-bound : la récupération de cotations auprès d'une API simulée. Le
   programme passe son temps à attendre le réseau : pendant l'attente, le
   GIL est relâché et d'autres threads peuvent avancer.
"""
from __future__ import annotations

import asyncio
import math
import random
import threading
import time

from .decorators import count_calls, retry, timed

# Portefeuille fictif : poids, rendement journalier moyen, volatilité journalière.
PORTFOLIO = {
    "EURUSD": (0.40, 0.0001, 0.0045),
    "XAUUSD": (0.35, 0.0002, 0.0095),
    "US30":   (0.25, 0.0003, 0.0110),
}
PORTFOLIO_VALUE = 1_000_000  # en euros


def simulate_losses(n_paths: int, seed: int) -> list[float]:
    """Simule n_paths journées et renvoie la perte du portefeuille pour chacune.

    Volontairement en Python pur (pas de NumPy) : NumPy relâcherait le GIL
    dans son code C et masquerait l'effet que l'on veut montrer.
    Chaque appel reçoit sa propre graine pour que les résultats soient
    reproductibles, quel que soit l'ordre d'exécution.
    """
    rng = random.Random(seed)
    gauss = rng.gauss
    # Copie locale des paramètres (x + 0.0 crée de nouveaux objets float).
    # Avec le GIL, cela ne change rien. Sans GIL (Python 3.13t/3.14t), des
    # threads qui lisent les MÊMES objets se disputent leurs compteurs de
    # références, ce qui annule une partie du gain. Mesuré sur 2 cœurs :
    # environ x1,1 sans la copie, environ x1,5 avec. Voir le README.
    params = [(wt + 0.0, mu + 0.0, sg + 0.0) for wt, mu, sg in PORTFOLIO.values()]
    value = PORTFOLIO_VALUE + 0.0
    losses = []
    for _ in range(n_paths):
        day_return = 0.0
        for weight, mu, sigma in params:
            day_return += weight * gauss(mu, sigma)
        losses.append(-day_return * value)
    return losses


def value_at_risk(losses: list[float], level: float = 0.99) -> float:
    """VaR historique : la perte dépassée seulement (1 - level) du temps."""
    ordered = sorted(losses)
    index = min(len(ordered) - 1, math.ceil(level * len(ordered)) - 1)
    return ordered[index]


# --- I/O-bound : une API de cotations simulée -------------------------------

LATENCY_S = 0.2           # temps de réponse simulé de l'API
RETRY_DELAY_S = 0.05      # attente de @retry avant de relancer
FLAKY_SYMBOLS = {"GBPUSD", "BTCUSD"}  # ces symboles échouent au premier appel

_failed_once: set[str] = set()
_failed_lock = threading.Lock()  # protège _failed_once entre threads


def reset_flaky() -> None:
    with _failed_lock:
        _failed_once.clear()


def failures_count() -> int:
    """Nombre de pannes simulées depuis le dernier reset_flaky()."""
    with _failed_lock:
        return len(_failed_once)


def _maybe_fail(symbol: str, flaky: bool) -> None:
    if not flaky:
        return
    with _failed_lock:
        if symbol in FLAKY_SYMBOLS and symbol not in _failed_once:
            _failed_once.add(symbol)
            raise ConnectionError(f"timeout simulé sur {symbol}")


def _fake_price(symbol: str) -> float:
    return round(random.Random(symbol).uniform(1, 40_000), 4)


@count_calls
@retry(times=3, delay=RETRY_DELAY_S, exceptions=(ConnectionError,))
@timed
def fetch_quote(symbol: str, latency: float = LATENCY_S, flaky: bool = True) -> tuple[str, float]:
    """Appel bloquant : time.sleep relâche le GIL pendant l'attente.

    latency : temps de réponse simulé, en secondes.
    flaky   : si True, GBPUSD et BTCUSD échouent une fois (pour montrer @retry).
    """
    time.sleep(latency)
    _maybe_fail(symbol, flaky)
    return symbol, _fake_price(symbol)


@retry(times=3, delay=RETRY_DELAY_S, exceptions=(ConnectionError,))
@timed
async def afetch_quote(symbol: str, latency: float = LATENCY_S, flaky: bool = True) -> tuple[str, float]:
    """Version asynchrone : un seul thread, qui passe à une autre tâche
    pendant chaque `await asyncio.sleep`. Mêmes paramètres que fetch_quote."""
    await asyncio.sleep(latency)
    _maybe_fail(symbol, flaky)
    return symbol, _fake_price(symbol)


SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US30", "BTCUSD", "ETHUSD",
           "USDCHF", "AUDUSD", "NZDUSD", "USDCAD", "EURGBP", "EURJPY", "GBPJPY",
           "SPX500", "NAS100", "GER40", "FRA40", "UK100", "XAGUSD"]
