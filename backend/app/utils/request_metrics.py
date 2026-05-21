import math
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterable, List, MutableMapping, Optional

from starlette.types import ASGIApp, Message, Receive, Scope, Send


@dataclass(frozen=True)
class RequestLatencySample:
    route: str
    method: str
    status_code: int
    latency_ms: float
    timestamp: float


class RequestLatencyStore:
    def __init__(self, max_samples: int = 2000):
        self._samples: Deque[RequestLatencySample] = deque(maxlen=max_samples)
        self._lock = threading.Lock()

    def record(self, sample: RequestLatencySample) -> None:
        with self._lock:
            self._samples.append(sample)

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()

    def snapshot(self) -> List[RequestLatencySample]:
        with self._lock:
            return list(self._samples)

    def summary(self) -> Dict[str, Any]:
        samples = self.snapshot()
        grouped: MutableMapping[str, List[RequestLatencySample]] = defaultdict(list)
        for sample in samples:
            grouped[sample.route].append(sample)

        return {
            "sample_count": len(samples),
            "overall": summarize_samples(samples),
            "routes": {
                route: summarize_samples(route_samples)
                for route, route_samples in sorted(grouped.items())
            },
        }


def _percentile(sorted_values: List[float], percentile: int) -> Optional[float]:
    if not sorted_values:
        return None
    index = math.ceil((percentile / 100) * len(sorted_values)) - 1
    index = min(max(index, 0), len(sorted_values) - 1)
    return round(sorted_values[index], 2)


def summarize_samples(samples: Iterable[RequestLatencySample]) -> Dict[str, Any]:
    latencies = sorted(sample.latency_ms for sample in samples)
    if not latencies:
        return {
            "count": 0,
            "avg_ms": None,
            "min_ms": None,
            "max_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
        }

    return {
        "count": len(latencies),
        "avg_ms": round(sum(latencies) / len(latencies), 2),
        "min_ms": round(latencies[0], 2),
        "max_ms": round(latencies[-1], 2),
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "p99_ms": _percentile(latencies, 99),
    }


def _route_name(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None) if route is not None else None
    return path or scope.get("path", "unknown")


class ResponseTimeMetricsMiddleware:
    def __init__(self, app: ASGIApp, store: RequestLatencyStore):
        self.app = app
        self.store = store

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("path") == "/metrics/latency":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500
        recorded = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, recorded
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", status_code))
            elif (
                message["type"] == "http.response.body"
                and not message.get("more_body", False)
                and not recorded
            ):
                recorded = True
                latency_ms = (time.perf_counter() - start) * 1000
                self.store.record(
                    RequestLatencySample(
                        route=f"{scope.get('method', 'GET')} {_route_name(scope)}",
                        method=str(scope.get("method", "GET")),
                        status_code=status_code,
                        latency_ms=latency_ms,
                        timestamp=time.time(),
                    )
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            if not recorded:
                latency_ms = (time.perf_counter() - start) * 1000
                self.store.record(
                    RequestLatencySample(
                        route=f"{scope.get('method', 'GET')} {_route_name(scope)}",
                        method=str(scope.get("method", "GET")),
                        status_code=500,
                        latency_ms=latency_ms,
                        timestamp=time.time(),
                    )
                )
            raise


REQUEST_LATENCY_STORE = RequestLatencyStore(
    max_samples=int(os.getenv("REQUEST_METRICS_MAX_SAMPLES", "2000"))
)
