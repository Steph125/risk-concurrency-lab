import json

from lab import benchmark


def test_cli_writes_utf8_results(tmp_path):
    benchmark.main(["--only", "io", "--symbols", "3", "--io-workers", "3",
                    "--latency", "0.05", "--no-plot", "--out", str(tmp_path)])
    # Toujours en UTF-8, même sous Windows (cp1252 par défaut).
    report = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert "cpu_bound" not in report
    assert report["io_bound"]["params"]["symbols"] == 3
    markdown = (tmp_path / "results.md").read_text(encoding="utf-8")
    assert "cœurs" in markdown and "I/O-bound" in markdown


def test_markdown_reads_old_result_files():
    old = {"environment": {"python": "3.13", "implementation": "CPython", "gil_enabled": True,
                           "cpu_count": 2, "platform": "Linux"},
           "cpu_bound": {"task": "VaR", "workers": 4,
                         "results": {"sequential": {"seconds": 1.0, "var_99_eur": 1.0, "speedup": 1.0}}}}
    text = benchmark.to_markdown(old)
    assert "(4 workers)" in text and "Séquentiel" in text


def test_interpretation_mentions_the_gil():
    env = {"gil_enabled": True, "cpu_count": 2}
    params = {"chunks": 4, "workers": 4}
    res = {"sequential": {"speedup": 1.0, "var_eur": 10.0},
           "threads": {"speedup": 0.85, "var_eur": 10.0},
           "processes": {"speedup": 1.65, "var_eur": 10.0}}
    notes = " ".join(benchmark.explain_cpu(res, params, env))
    assert "GIL" in notes and "×2" in notes and "même VaR" in notes
