from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_home_and_env():
    page = client.get("/")
    assert page.status_code == 200
    assert "Risk Concurrency Lab" in page.text
    env = client.get("/api/env").json()
    assert "gil_enabled" in env and env["cpu_count"] >= 1


def test_every_menu_page_has_its_own_address():
    from app.main import PAGES
    for path in PAGES:
        page = client.get(path)
        assert page.status_code == 200, path
        assert 'data-page="accueil"' in page.text
    # Un navigateur reçoit l'interface (qui affiche « Page introuvable ») avec un statut 404…
    lost = client.get("/page-qui-n-existe-pas", headers={"Accept": "text/html"})
    assert lost.status_code == 404 and 'data-page="introuvable"' in lost.text
    # …mais l'API garde sa réponse JSON.
    assert client.get("/api/inconnue").json() == {"detail": "Not Found"}
    assert client.get("/favicon.ico").status_code == 200


def test_static_files_are_served():
    for path, kind in [("/static/style.css", "text/css"), ("/static/app.js", "javascript"),
                       ("/static/favicon.svg", "image/svg+xml")]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert kind in response.headers["content-type"]


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_io_benchmark_endpoint():
    data = client.get("/api/benchmark/io", params={"symbols": 4, "workers": 4, "latency": 0.05}).json()
    assert set(data["results"]) == {"sequential", "threads", "asyncio"}
    assert data["params"] == {"symbols": 4, "workers": 4, "latency": 0.05, "flaky": True}
    assert data["fastest"] in data["results"]
    assert data["interpretation"]
    # Les 4 premiers symboles contiennent GBPUSD, qui échoue une fois puis est relancé.
    assert all(r["quotes"] == 4 and r["failed_attempts"] == 1 for r in data["results"].values())


def test_io_benchmark_without_failures():
    data = client.get("/api/benchmark/io",
                      params={"symbols": 4, "workers": 4, "latency": 0.05, "flaky": False}).json()
    assert all(r["failed_attempts"] == 0 for r in data["results"].values())


def test_cpu_benchmark_endpoint():
    data = client.get("/api/benchmark/cpu",
                      params={"paths": 10_000, "chunks": 2, "workers": 2, "level": 0.95, "repeat": 2}).json()
    assert set(data["results"]) == {"sequential", "threads", "processes"}
    assert data["params"]["total_paths"] == 20_000
    assert len({r["var_eur"] for r in data["results"].values()}) == 1  # même VaR partout
    assert "95 %" in data["task"]
    assert data["params"]["repeat"] == 2


def test_invalid_parameters_are_rejected():
    assert client.get("/api/benchmark/cpu", params={"paths": 5}).status_code == 422
    assert client.get("/api/benchmark/cpu", params={"level": 1.5}).status_code == 422
    assert client.get("/api/benchmark/cpu", params={"repeat": 9}).status_code == 422
    assert client.get("/api/benchmark/io", params={"symbols": 99}).status_code == 422


def test_reference_and_decorators():
    for report in client.get("/api/reference").json():
        assert "environment" in report
        if report["cpu_bound"]:
            assert all("var_eur" in r for r in report["cpu_bound"]["results"].values())
    state = client.get("/api/decorators").json()
    assert {"fetch_quote_calls", "retries", "timings"} <= set(state)


def test_openapi_documents_inputs_and_outputs():
    schema = client.get("/openapi.json").json()
    params = {p["name"]: p for p in schema["paths"]["/api/benchmark/cpu"]["get"]["parameters"]}
    assert set(params) == {"paths", "chunks", "workers", "level", "repeat"}
    assert all(p.get("description") for p in params.values())
    assert "CpuBenchmark" in schema["components"]["schemas"]


def test_cpu_endpoint_without_processes(monkeypatch):
    from lab import benchmark

    def no_processes(*args, **kwargs):
        raise OSError(38, "Function not implemented")

    monkeypatch.setattr(benchmark, "run_processes", no_processes)
    response = client.get("/api/benchmark/cpu", params={"paths": 10_000, "chunks": 2, "workers": 2})
    assert response.status_code == 200
    data = response.json()
    assert "processes" not in data["results"] and "processes" in data["unavailable"]
