import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List


def percentile(values: List[float], p: int) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * p + 99) / 100) - 1))
    return round(ordered[index], 2)


def request_once(
    url: str,
    timeout: float,
    method: str,
    body: str,
    headers: Dict[str, str],
) -> Dict[str, float]:
    start = time.perf_counter()
    status = 0
    data = body.encode("utf-8") if body else None
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        exc.read()
        status = exc.code
    except Exception:
        status = -1
    return {
        "status": status,
        "latency_ms": (time.perf_counter() - start) * 1000,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure API response latency p95/p99.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/get_files/")
    parser.add_argument("--method", default="GET", choices=["GET", "POST"])
    parser.add_argument("--json", default="")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()

    headers = {}
    if args.json:
        json.loads(args.json)
        headers["Content-Type"] = "application/json"

    results: List[Dict[str, float]] = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                request_once,
                args.url,
                args.timeout,
                args.method,
                args.json,
                headers,
            )
            for _ in range(args.requests)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    latencies = [result["latency_ms"] for result in results]
    status_counts: Dict[str, int] = {}
    for result in results:
        key = str(int(result["status"]))
        status_counts[key] = status_counts.get(key, 0) + 1

    payload = {
        "url": args.url,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "total_time_s": round(time.perf_counter() - started, 2),
        "status_counts": status_counts,
        "avg_ms": round(statistics.mean(latencies), 2) if latencies else None,
        "min_ms": round(min(latencies), 2) if latencies else None,
        "max_ms": round(max(latencies), 2) if latencies else None,
        "p50_ms": percentile(latencies, 50) if latencies else None,
        "p95_ms": percentile(latencies, 95) if latencies else None,
        "p99_ms": percentile(latencies, 99) if latencies else None,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
