from lab import workloads as w
from lab.runners import run_asyncio, run_processes, run_sequential, run_threads


def test_all_strategies_give_the_same_var():
    args = [(2_000, seed) for seed in range(3)]
    results = []
    for parts in (run_sequential(w.simulate_losses, args),
                  run_threads(w.simulate_losses, args, 3),
                  run_processes(w.simulate_losses, args, 2)):
        losses = [x for p in parts for x in p]
        results.append(w.value_at_risk(losses))
    assert results[0] == results[1] == results[2]
    assert results[0] > 0


def test_io_strategies_return_all_quotes_despite_failures():
    symbols = [(s,) for s in w.SYMBOLS[:8]]   # contient GBPUSD et BTCUSD, qui échouent une fois
    for run in (lambda: run_threads(w.fetch_quote, symbols, 8),
                lambda: run_asyncio(w.afetch_quote, symbols, 8)):
        w.reset_flaky()
        quotes = run()
        assert [q[0] for q in quotes] == [s for (s,) in symbols]


def test_quotes_accept_latency_and_failure_options():
    w.reset_flaky()
    assert w.fetch_quote("GBPUSD", 0.01, False)[0] == "GBPUSD"
    assert w.failures_count() == 0          # pannes désactivées
    w.fetch_quote("GBPUSD", 0.01, True)     # échoue une fois, @retry relance
    assert w.failures_count() == 1


def test_var_definition():
    losses = list(range(1, 101))            # pertes de 1 à 100
    assert w.value_at_risk(losses, 0.99) == 99
