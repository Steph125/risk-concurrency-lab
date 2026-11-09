from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from lab import workloads as w
from lab.benchmark import bench_cpu, bench_io, environment
from lab.decorators import TIMINGS

from .schemas import (CpuBenchmark, DecoratorsState, Environment, Health, IoBenchmark,
                      ReferenceReport, Timing)

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
REFERENCE_FILES = ["results.json", "results_free_threaded.json"]

app = FastAPI(
    title="Risk Concurrency Lab",
    version="1.1.0",
    description=(
        "Le GIL, le multithreading, le multiprocessing et asyncio, mesurés en direct sur un petit "
        "moteur de risque.\n\n"
        "- **CPU-bound** : VaR Monte-Carlo d'un portefeuille, en Python pur.\n"
        "- **I/O-bound** : cotations récupérées auprès d'une API simulée.\n\n"
        "Chaque mesure renvoie les paramètres utilisés (`params`), une durée et une accélération "
        "par stratégie (`results`), la plus rapide (`fastest`) et une courte lecture des chiffres "
        "(`interpretation`). Interface graphique : [/](/)."
    ),
    openapi_tags=[
        {"name": "Mesures", "description": "Lancer un benchmark sur ce serveur."},
        {"name": "Informations", "description": "Environnement, décorateurs et mesures de référence."},
    ],
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# Une seule mesure à la fois : deux benchmarks simultanés se partageraient les
# cœurs et fausseraient les durées l'un de l'autre.
_bench_lock = threading.Lock()


# Pages de l'interface. Le navigateur passe de l'une à l'autre sans recharger
# (app.js), mais chaque adresse doit aussi marcher en lien direct ou après F5.
PAGES = ["/", "/calcul", "/cours", "/historique", "/references", "/activite", "/aide"]


def home() -> FileResponse:
    return FileResponse(STATIC / "index.html")


for _page in PAGES:
    app.add_api_route(_page, home, methods=["GET"], include_in_schema=False)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(STATIC / "favicon.svg", media_type="image/svg+xml")


@app.exception_handler(StarletteHTTPException)
async def not_found(request: Request, exc: StarletteHTTPException):
    """Adresse inconnue ouverte dans un navigateur : l'interface affiche « Page introuvable ».
    Les appels à l'API gardent leur réponse JSON habituelle."""
    wants_page = "text/html" in request.headers.get("accept", "")
    is_api = request.url.path.startswith(("/api/", "/static/", "/docs", "/redoc", "/openapi"))
    if exc.status_code == 404 and wants_page and not is_api:
        return FileResponse(STATIC / "index.html", status_code=404)
    return await http_exception_handler(request, exc)


@app.get("/health", response_model=Health, tags=["Informations"], summary="Le serveur répond-il ?")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/env", response_model=Environment, tags=["Informations"],
         summary="Version de Python, GIL, nombre de cœurs")
def env() -> dict:
    return environment()


@app.get("/api/benchmark/cpu", response_model=CpuBenchmark, tags=["Mesures"],
         summary="Mesurer un calcul de VaR (CPU-bound)")
def benchmark_cpu(
    paths: Annotated[int, Query(ge=10_000, le=200_000, description="Scénarios simulés par bloc")] = 100_000,
    chunks: Annotated[int, Query(ge=1, le=8, description="Nombre de blocs, donc de tâches à répartir")] = 4,
    workers: Annotated[int, Query(ge=1, le=8, description="Threads ou processus en parallèle")] = 4,
    level: Annotated[float, Query(ge=0.9, le=0.999,
                                  description="Niveau de confiance de la VaR, entre 0,9 et 0,999")] = 0.99,
    repeat: Annotated[int, Query(ge=1, le=5,
                                 description="Essais par stratégie ; la durée retenue est la médiane")] = 1,
) -> dict:
    """Calcule la même VaR en séquentiel, avec des threads et avec des processus.

    Les trois stratégies doivent trouver exactement la même VaR : seule la durée change.
    Compter environ 1 à 10 secondes par essai selon les paramètres et la machine.
    """
    with _bench_lock:
        result = bench_cpu(paths=paths, chunks=chunks, workers=workers, level=level, repeat=repeat)
    return {"environment": environment(), **result}


@app.get("/api/benchmark/io", response_model=IoBenchmark, tags=["Mesures"],
         summary="Mesurer des appels d'API (I/O-bound)")
def benchmark_io(
    symbols: Annotated[int, Query(ge=1, le=len(w.SYMBOLS), description="Nombre de cotations à récupérer")] = 10,
    workers: Annotated[int, Query(ge=1, le=20, description="Appels simultanés (threads ou asyncio)")] = 10,
    latency: Annotated[float, Query(ge=0.05, le=1.0, description="Latence simulée de l'API, en secondes")] = 0.2,
    flaky: Annotated[bool, Query(description="Simuler des pannes : GBPUSD et BTCUSD échouent une fois")] = True,
) -> dict:
    """Récupère les mêmes cotations en séquentiel, avec des threads et avec asyncio.

    La durée séquentielle vaut environ `symbols × latency` secondes.
    """
    with _bench_lock:
        result = bench_io(symbols=symbols, workers=workers, latency=latency, flaky=flaky)
    return {"environment": environment(), **result}


@app.get("/api/decorators", response_model=DecoratorsState, tags=["Informations"],
         summary="Ce que les décorateurs ont enregistré")
def decorators_state() -> dict:
    """Compteurs de @count_calls et durées de @timed depuis le démarrage du serveur."""
    timings = [
        Timing(function=name, count=len(v), mean_s=round(sum(v) / len(v), 4), max_s=round(max(v), 4))
        for name, v in sorted(TIMINGS.items()) if v
    ]
    measured = len(TIMINGS.get("fetch_quote", []))
    return {
        "fetch_quote_calls": w.fetch_quote.calls,
        "retries": max(0, measured - w.fetch_quote.calls),
        "timings": timings,
    }


def _read_json(path: Path) -> dict:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:  # fichier écrit par une ancienne version sous Windows
        text = raw.decode("cp1252")
    return json.loads(text)


def _normalize(block: dict | None) -> dict | None:
    """Met les anciens fichiers de résultats au format actuel."""
    if not block:
        return None
    block = json.loads(json.dumps(block))  # copie
    block.setdefault("params", {"workers": block.pop("workers", None)})
    for v in block["results"].values():
        if "var_99_eur" in v:
            v["var_eur"] = v.pop("var_99_eur")
    block.setdefault("fastest", min(block["results"], key=lambda n: block["results"][n]["seconds"]))
    block.setdefault("interpretation", [])
    return block


@app.get("/api/reference", response_model=list[ReferenceReport], tags=["Informations"],
         summary="Mesures de référence enregistrées dans results/")
def reference() -> list[dict]:
    reports = []
    for name in REFERENCE_FILES:
        path = ROOT / "results" / name
        if path.exists():
            data = _read_json(path)
            reports.append({"file": name, "environment": data["environment"],
                            "cpu_bound": _normalize(data.get("cpu_bound")),
                            "io_bound": _normalize(data.get("io_bound"))})
    return reports
