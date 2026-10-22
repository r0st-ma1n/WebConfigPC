"""Замер скорости подбора по каталогу из components.json (база не нужна).

    uv run python backend/scripts/bench_recommend.py            # время по типовым запросам
    uv run python backend/scripts/bench_recommend.py --profile  # где тратится время (cProfile)

Каждый запрос выполняется несколько раз, в таблице — медиана.
"""

import argparse
import cProfile
import pstats
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # папка backend

from app.balance import Resolution
from app.recommender import recommend
from app.recommender.params import RecommendRequest, Scenario
from app.seed import load_catalog

REQUESTS = {
    "игры 1080p, 70 тыс.": RecommendRequest(budget=70_000, scenario=Scenario.GAMING, resolution=Resolution.FHD),
    "игры 1440p, 120 тыс.": RecommendRequest(budget=120_000, scenario=Scenario.GAMING, resolution=Resolution.QHD),
    "игры 4K, 250 тыс.": RecommendRequest(budget=250_000, scenario=Scenario.GAMING, resolution=Resolution.UHD),
    "работа, 180 тыс.": RecommendRequest(budget=180_000, scenario=Scenario.WORKSTATION),
    "офис, 45 тыс.": RecommendRequest(budget=45_000, scenario=Scenario.OFFICE),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    parts = load_catalog(with_ids=True)

    if args.profile:
        profiler = cProfile.Profile()
        profiler.enable()
        for request in REQUESTS.values():
            recommend(parts, request)
        profiler.disable()
        pstats.Stats(profiler).sort_stats("cumulative").print_stats(25)
        return

    total = 0.0
    for name, request in REQUESTS.items():
        times = []
        for _ in range(args.runs):
            start = time.perf_counter()
            recommend(parts, request)
            times.append((time.perf_counter() - start) * 1000)
        median = statistics.median(times)
        total += median
        print(f"{name:<22} {median:7.0f} мс")
    print(f"{'среднее':<22} {total / len(REQUESTS):7.0f} мс")


if __name__ == "__main__":
    main()
