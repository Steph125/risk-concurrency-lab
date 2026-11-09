import asyncio

import pytest

from lab.decorators import TIMINGS, count_calls, retry, timed


def test_timed_keeps_name_and_result():
    @timed
    def add(a, b):
        """Additionne."""
        return a + b

    assert add(2, 3) == 5
    assert add.__name__ == "add"          # functools.wraps
    assert add.__doc__ == "Additionne."
    assert TIMINGS["add"][-1] >= 0


def test_timed_works_on_coroutines():
    @timed
    async def ping():
        await asyncio.sleep(0.01)
        return "pong"

    assert asyncio.run(ping()) == "pong"
    assert TIMINGS["ping"][-1] >= 0.01


def test_retry_succeeds_after_failures():
    attempts = []

    @retry(times=3, delay=0)
    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionError("boom")
        return "ok"

    assert flaky() == "ok"
    assert len(attempts) == 3


def test_retry_gives_up_and_reraises():
    @retry(times=2, delay=0, exceptions=(ConnectionError,))
    def always_fails():
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        always_fails()


def test_retry_ignores_other_exceptions():
    calls = []

    @retry(times=5, delay=0, exceptions=(ConnectionError,))
    def bug():
        calls.append(1)
        raise ValueError("bug, pas un problème réseau")

    with pytest.raises(ValueError):
        bug()
    assert len(calls) == 1  # une erreur de code ne doit pas être relancée


def test_count_calls_is_thread_safe():
    from concurrent.futures import ThreadPoolExecutor

    @count_calls
    def noop():
        return None

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: noop(), range(1_000)))
    assert noop.calls == 1_000
