import argparse
import json
import time
import uuid
from pathlib import Path
from statistics import mean
from typing import Any

import requests


DEFAULT_TIMEOUT = 180


def load_dataset(path: str) -> dict[str, Any]:
    dataset_path = Path(path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    with dataset_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if "test_cases" not in data or not isinstance(data["test_cases"], list):
        raise ValueError("Dataset must contain a 'test_cases' list")

    return data


def safe_lower(value: Any) -> str:
    return str(value or "").lower()


def contains_all_keywords(text: str, keywords: list[str]) -> float | None:
    if not keywords:
        return None

    lowered = safe_lower(text)
    hits = sum(1 for keyword in keywords if safe_lower(keyword) in lowered)
    return hits / len(keywords)


def contains_no_forbidden_keywords(text: str, keywords: list[str]) -> float | None:
    if not keywords:
        return None

    lowered = safe_lower(text)
    violations = sum(1 for keyword in keywords if safe_lower(keyword) in lowered)
    return 1.0 if violations == 0 else 0.0


def calc_recall(expected: list[str], actual: list[str]) -> float | None:
    if not expected:
        return None

    actual_set = {safe_lower(item) for item in actual if item}
    hits = sum(1 for item in expected if safe_lower(item) in actual_set)
    return hits / len(expected)


def parse_sse_response(response: requests.Response) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    answer_parts: list[str] = []
    thinking_parts: list[str] = []
    recommended_questions: list[str] = []
    repository_context: list[dict[str, Any]] = []
    errors: list[str] = []

    current_event = "message"

    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue

        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
            continue

        if not line.startswith("data:"):
            continue

        data = line.split(":", 1)[1].strip()
        if current_event == "end" and data == "[DONE]":
            break

        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            errors.append(f"Invalid JSON payload: {data[:200]}")
            continue

        if current_event == "error":
            errors.append(str(payload))
            continue

        if payload.get("documents"):
            documents = payload["documents"]
        if payload.get("citations"):
            citations = payload["citations"]
        if payload.get("recommended_questions"):
            recommended_questions = payload["recommended_questions"]
        if payload.get("repository_context"):
            repository_context = payload["repository_context"]

        if payload.get("role") == "assistant":
            content = payload.get("content", "")
            if payload.get("thinking"):
                thinking_parts.append(content)
            else:
                answer_parts.append(content)

    return {
        "documents": documents,
        "citations": citations,
        "answer": "".join(answer_parts).strip(),
        "thinking": "".join(thinking_parts).strip(),
        "recommended_questions": recommended_questions,
        "repository_context": repository_context,
        "errors": errors,
    }


def run_single_case(
    base_url: str,
    endpoint: str,
    case: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    session_id = uuid.uuid4().hex[:16]
    url = f"{base_url.rstrip('/')}/{endpoint.strip('/')}/"
    params = {"session_id": session_id}
    payload = {
        "message": case["question"],
    }
    if case.get("repository_id"):
        payload["repository_id"] = case["repository_id"]
    if case.get("repository_ids") is not None:
        payload["repository_ids"] = case["repository_ids"]

    started_at = time.perf_counter()
    with requests.post(url, params=params, json=payload, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        parsed = parse_sse_response(response)
    elapsed_seconds = time.perf_counter() - started_at

    documents = parsed["documents"]
    citations = parsed["citations"]
    answer = parsed["answer"]

    actual_file_paths = sorted(
        {
            item.get("file_path")
            for item in documents + citations
            if isinstance(item, dict) and item.get("file_path")
        }
    )
    actual_citations = sorted(
        {
            item.get("citation")
            for item in citations
            if isinstance(item, dict) and item.get("citation")
        }
    )

    metrics: dict[str, float] = {
        "has_answer": 1.0 if answer else 0.0,
        "latency_seconds": round(elapsed_seconds, 3),
        "documents_count": float(len(documents)),
        "citations_count": float(len(citations)),
    }

    require_citations = case.get("require_citations", False)
    if require_citations:
        metrics["has_citations"] = 1.0 if citations else 0.0

    file_path_recall = calc_recall(case.get("expected_file_paths", []), actual_file_paths)
    if file_path_recall is not None:
        metrics["expected_file_path_recall"] = file_path_recall

    citation_recall = calc_recall(case.get("expected_citations", []), actual_citations)
    if citation_recall is not None:
        metrics["expected_citation_recall"] = citation_recall

    must_include_recall = contains_all_keywords(answer, case.get("must_include", []))
    if must_include_recall is not None:
        metrics["must_include_recall"] = must_include_recall

    must_not_include_pass = contains_no_forbidden_keywords(answer, case.get("must_not_include", []))
    if must_not_include_pass is not None:
        metrics["must_not_include_pass"] = must_not_include_pass

    score_candidates = [
        value
        for key, value in metrics.items()
        if (key != "latency_seconds" and key.endswith(("_recall", "_pass")))
        or key in {"has_answer", "has_citations"}
    ]
    metrics["score"] = mean(score_candidates) if score_candidates else 0.0

    return {
        "id": case.get("id"),
        "question": case["question"],
        "tags": case.get("tags", []),
        "endpoint": endpoint,
        "session_id": session_id,
        "metrics": metrics,
        "answer": answer,
        "thinking": parsed["thinking"],
        "documents": documents,
        "citations": citations,
        "actual_file_paths": actual_file_paths,
        "actual_citations": actual_citations,
        "recommended_questions": parsed["recommended_questions"],
        "repository_context": parsed["repository_context"],
        "errors": parsed["errors"],
    }


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    all_metric_keys = sorted(
        {
            key
            for item in results
            for key in item.get("metrics", {}).keys()
        }
    )

    aggregates: dict[str, float] = {}
    for key in all_metric_keys:
        values = [item["metrics"][key] for item in results if key in item.get("metrics", {})]
        if values:
            aggregates[key] = round(mean(values), 4)

    return {
        "case_count": len(results),
        "aggregate_metrics": aggregates,
    }


def ensure_output_parent(path: str) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run batch evaluation for CodeResearch Agent endpoints.")
    parser.add_argument("--dataset", required=True, help="Path to the evaluation dataset JSON file.")
    parser.add_argument("--endpoint", default="deep_research", choices=["deep_research", "ai_search"], help="Backend endpoint to evaluate.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds.")
    parser.add_argument("--output", default="evals/reports/agent_eval_report.json", help="Path to the output report JSON file.")
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)
    results = []

    for index, case in enumerate(dataset["test_cases"], start=1):
        print(f"[{index}/{len(dataset['test_cases'])}] evaluating: {case.get('id', '<no-id>')} - {case['question']}")
        try:
            case_result = run_single_case(
                base_url=args.base_url,
                endpoint=args.endpoint,
                case=case,
                timeout=args.timeout,
            )
            results.append(case_result)
            print(
                "  score={score:.3f} answer={answer} citations={citations} latency={latency:.3f}s".format(
                    score=case_result["metrics"].get("score", 0.0),
                    answer=int(case_result["metrics"].get("has_answer", 0.0)),
                    citations=int(case_result["metrics"].get("has_citations", 0.0))
                    if "has_citations" in case_result["metrics"] else len(case_result["citations"]),
                    latency=case_result["metrics"].get("latency_seconds", 0.0),
                )
            )
        except Exception as exc:
            error_result = {
                "id": case.get("id"),
                "question": case["question"],
                "tags": case.get("tags", []),
                "endpoint": args.endpoint,
                "metrics": {
                    "has_answer": 0.0,
                    "score": 0.0,
                },
                "errors": [str(exc)],
            }
            results.append(error_result)
            print(f"  failed: {exc}")

    report = {
        "dataset_description": dataset.get("description", ""),
        "dataset_version": dataset.get("version", ""),
        "base_url": args.base_url,
        "endpoint": args.endpoint,
        "summary": aggregate_results(results),
        "results": results,
    }

    output_path = ensure_output_parent(args.output)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("")
    print("Aggregate metrics:")
    for key, value in report["summary"]["aggregate_metrics"].items():
        print(f"  {key}: {value}")
    print(f"Report written to: {output_path}")


if __name__ == "__main__":
    main()
