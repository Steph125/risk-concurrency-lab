"""Formats des réponses de l'API.

Chaque champ a une description : elle apparaît dans la documentation
interactive (/docs), qui sert de référence pour les entrées et les sorties.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Environment(BaseModel):
    python: str = Field(description="Version de Python qui exécute le serveur", examples=["3.13.3"])
    implementation: str = Field(description="Implémentation de Python", examples=["CPython"])
    gil_enabled: bool = Field(description="True si le GIL est actif (cas par défaut)")
    cpu_count: int | None = Field(description="Nombre de cœurs vus par Python")
    platform: str = Field(description="Système d'exploitation", examples=["Windows-11"])


# --- CPU-bound -------------------------------------------------------------

class CpuParams(BaseModel):
    paths: int = Field(description="Scénarios (journées simulées) par bloc")
    chunks: int = Field(description="Nombre de blocs, donc de tâches à répartir")
    workers: int = Field(description="Threads ou processus utilisés en parallèle")
    level: float = Field(description="Niveau de confiance de la VaR (0,99 = 99 %)")
    repeat: int = Field(description="Essais par stratégie ; la durée retenue est la médiane")
    total_paths: int = Field(description="Scénarios calculés par chaque stratégie (paths × chunks)")


class CpuResult(BaseModel):
    seconds: float = Field(description="Durée mesurée (médiane des essais), en secondes")
    speedup: float = Field(description="Accélération par rapport au séquentiel (2,0 = deux fois plus rapide)")
    var_eur: float = Field(description="VaR trouvée, en euros, pour un portefeuille de 1 000 000 €")


class CpuBenchmark(BaseModel):
    environment: Environment
    task: str = Field(description="Résumé lisible de la tâche mesurée")
    params: CpuParams = Field(description="Paramètres réellement utilisés")
    results: dict[Literal["sequential", "threads", "processes"], CpuResult]
    fastest: str = Field(description="Stratégie la plus rapide")
    unavailable: dict[str, str] = Field(default_factory=dict,
                                        description="Stratégies non mesurées et pourquoi (ex. processus "
                                                    "interdits sur un hébergement serverless)")
    interpretation: list[str] = Field(description="Ce que montrent les chiffres, en quelques phrases")


# --- I/O-bound -------------------------------------------------------------

class IoParams(BaseModel):
    symbols: int = Field(description="Nombre de cotations demandées")
    workers: int = Field(description="Appels simultanés au maximum (threads ou asyncio)")
    latency: float = Field(description="Latence simulée de l'API, en secondes")
    flaky: bool = Field(description="True si GBPUSD et BTCUSD échouent une fois (pour montrer @retry)")


class IoResult(BaseModel):
    seconds: float = Field(description="Durée mesurée, en secondes")
    speedup: float = Field(description="Accélération par rapport au séquentiel")
    quotes: int = Field(description="Cotations effectivement récupérées")
    failed_attempts: int = Field(description="Appels échoués puis relancés par @retry")


class IoBenchmark(BaseModel):
    environment: Environment
    task: str = Field(description="Résumé lisible de la tâche mesurée")
    params: IoParams = Field(description="Paramètres réellement utilisés")
    results: dict[Literal["sequential", "threads", "asyncio"], IoResult]
    fastest: str = Field(description="Stratégie la plus rapide")
    interpretation: list[str] = Field(description="Ce que montrent les chiffres, en quelques phrases")


# --- Décorateurs et références ----------------------------------------------

class Timing(BaseModel):
    function: str = Field(description="Fonction décorée par @timed")
    count: int = Field(description="Exécutions mesurées, tentatives échouées comprises")
    mean_s: float = Field(description="Durée moyenne, en secondes")
    max_s: float = Field(description="Durée la plus longue, en secondes")


class DecoratorsState(BaseModel):
    fetch_quote_calls: int = Field(description="Appels à fetch_quote comptés par @count_calls depuis le démarrage")
    retries: int = Field(description="Relances faites par @retry sur fetch_quote "
                                     "(exécutions mesurées par @timed moins appels comptés)")
    timings: list[Timing]


class ReferenceReport(BaseModel):
    file: str = Field(description="Fichier d'origine dans results/")
    environment: Environment
    cpu_bound: dict | None = Field(None, description="Mesure CPU-bound, si présente")
    io_bound: dict | None = Field(None, description="Mesure I/O-bound, si présente")


class Health(BaseModel):
    status: Literal["ok"] = "ok"
