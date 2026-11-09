"""Mesure les stratégies d'exécution sur les deux types de travail.

Usage : python -m lab.benchmark                  (tailles complètes)
        python -m lab.benchmark --quick          (rapide)
        python -m lab.benchmark --help           (toutes les options)
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures.process import BrokenProcessPool
import os
import platform
import statistics
import sys
import time
from pathlib import Path

from . import workloads as w
from .runners import run_asyncio, run_processes, run_sequential, run_threads

# Erreurs levées quand la plateforme ne permet pas de lancer des processus.
PROCESS_ERRORS = (OSError, NotImplementedError, ImportError, PermissionError, BrokenProcessPool)

STRATEGY_LABELS = {
    "sequential": "Séquentiel",
    "threads": "Threads",
    "processes": "Processus",
    "asyncio": "asyncio",
}


def environment() -> dict:
    gil = sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "gil_enabled": gil,
        "cpu_count": os.cpu_count(),
        "platform": platform.platform(terse=True),
    }


def _time(fn) -> tuple[float, object]:
    start = time.perf_counter()
    result = fn()
    return time.perf_counter() - start, result


def _fr(x: float, digits: int = 2) -> str:
    """Nombre à la française : 1 234,56."""
    return f"{x:,.{digits}f}".replace(",", " ").replace(".", ",")


def _finish(out: dict) -> str:
    """Ajoute l'accélération par rapport au séquentiel et renvoie la stratégie la plus rapide."""
    base = out["sequential"]["seconds"]
    for v in out.values():
        v["speedup"] = round(base / v["seconds"], 2) if v["seconds"] else 0.0
    return min(out, key=lambda name: out[name]["seconds"])


# --- CPU-bound -------------------------------------------------------------

def bench_cpu(paths: int, chunks: int = 4, workers: int = 4, level: float = 0.99, repeat: int = 1) -> dict:
    """Même calcul (chunks blocs de `paths` journées) avec trois stratégies.

    Les graines sont identiques : les trois doivent trouver la même VaR.
    Avec repeat > 1, les stratégies passent à tour de rôle `repeat` fois et la
    durée retenue est la médiane : une seule mesure varie d'environ 15 % sur un
    PC portable, assez pour désigner un faux gagnant.
    """
    args = [(paths, seed) for seed in range(chunks)]
    runs = [
        ("sequential", lambda: run_sequential(w.simulate_losses, args)),
        ("threads", lambda: run_threads(w.simulate_losses, args, workers)),
        ("processes", lambda: run_processes(w.simulate_losses, args, workers)),
    ]
    times: dict[str, list[float]] = {name: [] for name, _ in runs}
    out = {}
    unavailable: dict[str, str] = {}
    for _ in range(repeat):
        for name, run in runs:  # à tour de rôle, pour répartir les variations de la machine
            if name in unavailable:
                continue
            try:
                seconds, parts = _time(run)
            except PROCESS_ERRORS as exc:
                # Certains hébergeurs serverless (Vercel, AWS Lambda) n'ont pas la mémoire
                # partagée (/dev/shm) dont ProcessPoolExecutor a besoin : on mesure le reste
                # au lieu de faire échouer toute la requête.
                if name != "processes":
                    raise
                unavailable[name] = f"Processus impossibles à lancer sur cet hébergement ({type(exc).__name__}: {exc})"
                del times[name]
                continue
            times[name].append(seconds)
            if name not in out:
                losses = [x for part in parts for x in part]
                out[name] = {"var_eur": round(w.value_at_risk(losses, level), 2)}
    for name, values in times.items():
        out[name] = {"seconds": round(statistics.median(values), 3), **out[name]}
    fastest = _finish(out)
    params = {"paths": paths, "chunks": chunks, "workers": workers, "level": level,
              "repeat": repeat, "total_paths": paths * chunks}
    return {
        "task": f"VaR Monte-Carlo à {_fr(level * 100, 1).rstrip('0').rstrip(',')} %, "
                f"{chunks} × {_fr(paths, 0)} scénarios",
        "params": params,
        "results": out,
        "fastest": fastest,
        "unavailable": unavailable,
        "interpretation": explain_cpu(out, params, environment()),
    }


def explain_cpu(res: dict, params: dict, env: dict) -> list[str]:
    """Quelques phrases qui disent ce que montrent les chiffres."""
    notes = []
    parallel = min(params["chunks"], params["workers"])
    cores = env.get("cpu_count") or 1
    if parallel == 1:
        notes.append("Avec un seul bloc ou un seul worker, rien ne tourne en parallèle : "
                     "les trois stratégies font le même travail l'une après l'autre.")
    else:
        t = res["threads"]["speedup"]
        p = res["processes"]["speedup"] if "processes" in res else None
        if env.get("gil_enabled", True):
            if t < 1.15:
                notes.append(f"Threads ×{_fr(t)} : avec le GIL, un seul thread exécute du Python à la fois, "
                             "donc le calcul n'est pas accéléré.")
            else:
                notes.append(f"Threads ×{_fr(t)} : gain inhabituel avec le GIL, la mesure est sans doute bruitée.")
        elif t >= 1.15:
            notes.append(f"Threads ×{_fr(t)} : sans GIL, les threads calculent vraiment en parallèle.")
        else:
            notes.append(f"Threads ×{_fr(t)} : même sans GIL, pas de gain ici (trop peu de travail par bloc).")
        if p is None:
            notes.append("Processus : non mesurés, cet hébergement ne permet pas d'en lancer.")
        elif p >= 1.15:
            notes.append(f"Processus ×{_fr(p)} : chaque processus a son propre GIL, "
                         "le calcul est réparti sur plusieurs cœurs.")
        else:
            notes.append(f"Processus ×{_fr(p)} : le démarrage des processus et la sérialisation (pickle) "
                         "coûtent plus que le gain. Augmentez le nombre de scénarios.")
        cap = min(parallel, cores)
        notes.append(f"Plafond théorique pour un calcul réellement parallèle : ×{cap} "
                     f"(le plus petit de {params['chunks']} blocs, {params['workers']} workers "
                     f"et {cores} cœurs).")
    vars_ = {v["var_eur"] for v in res.values()}
    if len(vars_) == 1:
        notes.append(f"Toutes les stratégies trouvent la même VaR ({_fr(vars_.pop())} €) : "
                     "chaque bloc a sa propre graine aléatoire.")
    return notes


# --- I/O-bound -------------------------------------------------------------

def bench_io(symbols: int, workers: int = 10, latency: float = w.LATENCY_S, flaky: bool = True) -> dict:
    """`symbols` appels à une API simulée ; avec `flaky`, 2 symboles échouent une fois."""
    args = [(s, latency, flaky) for s in w.SYMBOLS[:symbols]]
    out = {}
    for name, run in [
        ("sequential", lambda: run_sequential(w.fetch_quote, args)),
        ("threads", lambda: run_threads(w.fetch_quote, args, workers)),
        ("asyncio", lambda: run_asyncio(w.afetch_quote, args, workers)),
    ]:
        w.reset_flaky()
        seconds, quotes = _time(run)
        out[name] = {"seconds": round(seconds, 3), "quotes": len(quotes),
                     "failed_attempts": w.failures_count()}
    fastest = _finish(out)
    params = {"symbols": symbols, "workers": workers, "latency": latency, "flaky": flaky}
    return {
        "task": f"{symbols} cotations, latence simulée {_fr(latency)} s",
        "params": params,
        "results": out,
        "fastest": fastest,
        "interpretation": explain_io(out, params),
    }


def explain_io(res: dict, params: dict) -> list[str]:
    notes = []
    overlap = min(params["workers"], params["symbols"])
    failed = res["sequential"]["failed_attempts"]
    expected = params["symbols"] * params["latency"]
    retry_cost = failed * (w.RETRY_DELAY_S + params["latency"])
    sentence = (f"En séquentiel, chaque appel attend le précédent : environ "
                f"{params['symbols']} × {_fr(params['latency'])} s = {_fr(expected)} s")
    if failed:
        sentence += f", plus {_fr(retry_cost)} s de relance{'s' if failed > 1 else ''}"
    notes.append(sentence + ".")
    if overlap == 1:
        notes.append("Avec 1 worker (ou 1 symbole), les attentes ne se chevauchent pas : pas d'accélération.")
    else:
        notes.append(f"Threads ×{_fr(res['threads']['speedup'])} et asyncio ×{_fr(res['asyncio']['speedup'])} : "
                     f"pendant l'attente réseau, le GIL est relâché et jusqu'à {overlap} appels attendent "
                     "en même temps. asyncio y arrive avec un seul thread.")
    if failed:
        appels = f"{failed} appels ont échoué" if failed > 1 else "1 appel a échoué"
        notes.append(f"{appels} une première fois puis {'ont' if failed > 1 else 'a'} été "
                     f"relancé{'s' if failed > 1 else ''} par @retry : "
                     "toutes les cotations sont quand même récupérées.")
    return notes


# --- Rapport ---------------------------------------------------------------

def run_all(cpu: dict | None, io: dict | None) -> dict:
    """Lance les mesures demandées. cpu et io sont les paramètres de bench_cpu et bench_io."""
    report: dict = {"environment": environment()}
    if cpu is not None:
        report["cpu_bound"] = bench_cpu(**cpu)
    if io is not None:
        report["io_bound"] = bench_io(**io)
    return report


def _workers(block: dict) -> int | None:
    # Les anciens fichiers de résultats rangeaient "workers" à la racine du bloc.
    return block.get("params", {}).get("workers", block.get("workers"))


def to_markdown(report: dict) -> str:
    env = report["environment"]
    lines = [f"Python {env['python']} ({env['implementation']}), GIL actif : {env['gil_enabled']}, "
             f"{env['cpu_count']} cœurs, {env['platform']}", ""]
    for key, title in [("cpu_bound", "CPU-bound"), ("io_bound", "I/O-bound")]:
        block = report.get(key)
        if not block:
            continue
        lines += [f"**{title}** : {block['task']} ({_workers(block)} workers)", "",
                  "| Stratégie | Durée (s) | Accélération |", "| --- | --- | --- |"]
        for name, v in block["results"].items():
            lines.append(f"| {STRATEGY_LABELS.get(name, name)} | {_fr(v['seconds'], 3)} | ×{_fr(v['speedup'])} |")
        lines.append("")
        lines += [f"- {note}" for note in block.get("interpretation", [])]
        if block.get("interpretation"):
            lines.append("")
    return "\n".join(lines)


def plot(report: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    blocks = [(k, t) for k, t in [("cpu_bound", "CPU-bound : VaR Monte-Carlo"),
                                  ("io_bound", "I/O-bound : appels d'API")] if report.get(k)]
    fig, axes = plt.subplots(1, len(blocks), figsize=(5 * len(blocks), 3.8), squeeze=False)
    for ax, (key, title) in zip(axes[0], blocks):
        block = report[key]
        res = block["results"]
        names = list(res)
        secs = [res[n]["seconds"] for n in names]
        fastest = block.get("fastest") or min(res, key=lambda n: res[n]["seconds"])
        colors = ["#2a78d6" if n == fastest else "#b9b8b0" for n in names]
        bars = ax.bar([STRATEGY_LABELS.get(n, n) for n in names], secs, color=colors, width=0.55)
        ax.bar_label(bars, labels=[f"{res[n]['seconds']:.2f} s  ×{res[n]['speedup']}" for n in names], padding=3)
        ax.set_title(title)
        ax.set_ylabel("durée (s), plus bas = mieux")
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_ylim(0, max(secs) * 1.25)
    env = report["environment"]
    fig.suptitle(f"Python {env['python']}, GIL actif : {env['gil_enabled']}, {env['cpu_count']} cœurs")
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m lab.benchmark",
        description="Compare séquentiel, threads, processus et asyncio sur un calcul de VaR "
                    "(CPU-bound) et des appels d'API simulés (I/O-bound).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--quick", action="store_true",
                   help="tailles réduites (25 000 scénarios par bloc, 10 symboles)")
    p.add_argument("--only", choices=["cpu", "io"], help="ne lancer qu'une des deux mesures")
    p.add_argument("--out", default="results", help="dossier où écrire results.json, results.md et benchmark.png")
    p.add_argument("--no-plot", action="store_true",
                   help="ne pas dessiner le graphique (utile sans matplotlib, par exemple sous Python 3.14t)")

    cpu = p.add_argument_group("calcul (CPU-bound)")
    cpu.add_argument("--paths", type=int, help="scénarios par bloc (défaut : 500 000, ou 25 000 avec --quick)")
    cpu.add_argument("--chunks", type=int, default=4, help="nombre de blocs, donc de tâches à répartir")
    cpu.add_argument("--workers", type=int, default=4, help="threads ou processus en parallèle")
    cpu.add_argument("--level", type=float, default=0.99, help="niveau de confiance de la VaR, entre 0 et 1")
    cpu.add_argument("--repeat", type=int, default=1,
                     help="essais par stratégie ; la durée retenue est la médiane (3 conseillé)")

    io = p.add_argument_group("attente réseau (I/O-bound)")
    io.add_argument("--symbols", type=int, help=f"cotations à récupérer, 1 à {len(w.SYMBOLS)} "
                                                "(défaut : 20, ou 10 avec --quick)")
    io.add_argument("--io-workers", type=int, default=10, help="appels simultanés (threads ou asyncio)")
    io.add_argument("--latency", type=float, default=w.LATENCY_S, help="latence simulée de l'API, en secondes")
    io.add_argument("--no-failures", action="store_true", help="désactiver les pannes simulées (et donc @retry)")
    return p


def main(argv: list[str] | None = None) -> dict:
    a = _parser().parse_args(argv)
    if not 0 < a.level < 1:
        _parser().error("--level doit être strictement entre 0 et 1, par exemple 0.99")
    cpu = None if a.only == "io" else {
        "paths": a.paths or (25_000 if a.quick else 500_000),
        "chunks": a.chunks, "workers": a.workers, "level": a.level, "repeat": max(1, a.repeat),
    }
    io = None if a.only == "cpu" else {
        "symbols": min(a.symbols or (10 if a.quick else 20), len(w.SYMBOLS)),
        "workers": a.io_workers, "latency": a.latency, "flaky": not a.no_failures,
    }
    print("Mesure en cours, cela peut prendre quelques secondes...", file=sys.stderr)
    report = run_all(cpu, io)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "results.md").write_text(to_markdown(report), encoding="utf-8")
    if not a.no_plot:
        plot(report, out / "benchmark.png")
    print(to_markdown(report))
    print(f"Résultats écrits dans {out.resolve()}", file=sys.stderr)
    return report


if __name__ == "__main__":
    main()
