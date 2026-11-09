Python 3.13.3 (CPython), GIL actif : True, 8 cœurs, Windows-11

**CPU-bound** : VaR Monte-Carlo, 4 × 500 000 scénarios (4 workers)

| Stratégie | Durée (s) | Accélération |
| --- | --- | --- |
| sequential | 5.38 | ×1.0 |
| threads | 6.007 | ×0.9 |
| processes | 3.0 | ×1.79 |

**I/O-bound** : 20 cotations, latence simulée 0.2 s (10 workers)

| Stratégie | Durée (s) | Accélération |
| --- | --- | --- |
| sequential | 4.514 | ×1.0 |
| threads | 0.604 | ×7.47 |
| asyncio | 0.63 | ×7.17 |
