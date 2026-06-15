from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
FIXED_CHROMA_DB_DIR = BACKEND_DIR / "db" / "chroma_db"
os.environ["CHROMA_DB_DIR"] = str(FIXED_CHROMA_DB_DIR)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.tools.rag_tool import build_destination_query  # noqa: E402
from app.config import CHROMA_COLLECTION_NAME, EMBEDDING_MODEL  # noqa: E402
from app.rag.retriever import rerank_guide_chunks  # noqa: E402
from app.rag.vector_db import _build_embeddings, _resolve_chunk_destination  # noqa: E402


DEFAULT_CASES_PATH = BACKEND_DIR / "eval" / "rag_eval_cases.json"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("RAG eval cases file must contain a JSON list.")
    return data


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _is_cross_destination_chunk(chunk: dict[str, Any], destination: str) -> bool:
    chunk_destination = str(chunk.get("destination") or "").strip()
    if chunk_destination:
        return not (destination in chunk_destination or chunk_destination in destination)
    combined_text = (
        f"{chunk.get('source', '')}\n{chunk.get('title', '')}\n{chunk.get('text', '')}"
    )
    return destination not in combined_text


def _get_existing_chroma_collection() -> Any:
    """只读取 backend/db/chroma_db 中已有的 Chroma collection。"""
    if not FIXED_CHROMA_DB_DIR.exists():
        raise FileNotFoundError(
            f"Chroma DB directory does not exist: {FIXED_CHROMA_DB_DIR}"
        )

    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as error:
        raise RuntimeError("当前环境缺少 chromadb，无法验证 Chroma 向量库。") from error

    client = chromadb.PersistentClient(
        path=str(FIXED_CHROMA_DB_DIR),
        settings=Settings(anonymized_telemetry=False),
    )
    try:
        collection = client.get_collection(name=CHROMA_COLLECTION_NAME)
    except Exception as error:
        raise RuntimeError(
            "无法从固定目录读取 Chroma collection: "
            f"db_dir={FIXED_CHROMA_DB_DIR} collection={CHROMA_COLLECTION_NAME}"
        ) from error

    count = collection.count()
    if count <= 0:
        raise RuntimeError(
            "固定 Chroma collection 为空: "
            f"db_dir={FIXED_CHROMA_DB_DIR} collection={CHROMA_COLLECTION_NAME}"
        )
    return collection


def _search_chroma_db_only(
    query: str, top_k: int = 3, destination: str | None = None
) -> list[dict[str, str]]:
    """使用固定 Chroma 向量库检索，不回退到关键词索引或本地 JSON 索引。"""
    embeddings = _build_embeddings()
    if embeddings is None:
        raise RuntimeError(
            "当前环境缺少 embedding 能力，无法查询固定 Chroma 向量库。"
        )

    collection = _get_existing_chroma_collection()
    query_embedding = embeddings.embed_query(query)
    query_kwargs: dict[str, Any] = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
        "include": ["documents", "metadatas"],
    }
    if destination:
        query_kwargs["where"] = {"destination": destination}

    result = collection.query(**query_kwargs)
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]

    matched_chunks: list[dict[str, str]] = []
    for document, metadata in zip(documents, metadatas):
        metadata = metadata or {}
        title = str(metadata.get("title", "未命名片段"))
        source = str(metadata.get("source", "未知来源"))
        chunk_destination = str(
            metadata.get("destination") or _resolve_chunk_destination(source)
        )
        text = document.split("\n", 1)[1] if "\n" in document else document
        matched_chunks.append(
            {
                "title": title,
                "text": text,
                "source": source,
                "destination": chunk_destination,
            }
        )
    return matched_chunks


def _retrieve_chroma_db_only_chunks(
    query: str, top_k: int = 3, destination: str | None = None
) -> list[dict[str, str]]:
    candidate_k = max(top_k * 4, 12)
    matched_chunks = _search_chroma_db_only(
        query=query,
        top_k=candidate_k,
        destination=destination,
    )
    return rerank_guide_chunks(
        query=query, matched_chunks=matched_chunks, top_k=top_k, destination=destination
    )


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    top_k = int(case.get("top_k", 5))
    destination = str(case["destination"])
    query = build_destination_query(
        destination=destination,
        preferences=list(case.get("preferences", [])),
        pace=case.get("pace"),
        special_notes=case.get("special_notes"),
    )
    chunks = _retrieve_chroma_db_only_chunks(
        query=query, top_k=top_k, destination=destination
    )

    expected_title_keywords = list(case.get("expected_title_keywords", []))
    required_content_keywords = list(case.get("required_content_keywords", []))
    noise_title_keywords = list(case.get("noise_title_keywords", []))

    titles = [str(chunk.get("title", "")) for chunk in chunks]
    destinations = [str(chunk.get("destination", "")) for chunk in chunks]
    combined_text = "\n".join(
        f"{chunk.get('title', '')}\n{chunk.get('text', '')}" for chunk in chunks
    )

    top1_title = titles[0] if titles else ""
    top1_title_hit = _contains_any(top1_title, expected_title_keywords)
    topk_title_hit = any(_contains_any(title, expected_title_keywords) for title in titles)
    required_keyword_hits = _count_keyword_hits(combined_text, required_content_keywords)
    noise_count = sum(
        1 for title in titles if _contains_any(title, noise_title_keywords)
    )
    cross_destination_noise_count = sum(
        1 for chunk in chunks if _is_cross_destination_chunk(chunk, destination)
    )

    return {
        "id": case.get("id", "<unknown>"),
        "query": query,
        "destination": destination,
        "top1_title": top1_title,
        "top1_title_hit": top1_title_hit,
        "topk_title_hit": topk_title_hit,
        "required_keyword_hits": required_keyword_hits,
        "required_keyword_total": len(required_content_keywords),
        "noise_count": noise_count,
        "cross_destination_noise_count": cross_destination_noise_count,
        "titles": titles,
        "destinations": destinations,
    }


def _print_case_result(result: dict[str, Any]) -> None:
    print(f"case: {result['id']}")
    print(f"query: {result['query']}")
    print(f"top1_title: {result['top1_title']}")
    print(f"top1_title_hit: {result['top1_title_hit']}")
    print(f"topk_title_hit: {result['topk_title_hit']}")
    print(
        "required_keyword_hits: "
        f"{result['required_keyword_hits']}/{result['required_keyword_total']}"
    )
    print(f"noise_count: {result['noise_count']}")
    print(f"cross_destination_noise_count: {result['cross_destination_noise_count']}")
    print("titles:")
    for index, (title, destination) in enumerate(
        zip(result["titles"], result["destinations"]),
        start=1,
    ):
        print(f"  {index}. [{destination or '<unknown>'}] {title}")
    print("-" * 60)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate RAG retrieval quality with a small scenario case set."
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to the RAG eval cases JSON file.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    print("=== RAG Retrieval Evaluation ===")
    print(f"chroma_db_dir: {FIXED_CHROMA_DB_DIR}")
    print(f"collection_name: {CHROMA_COLLECTION_NAME}")
    print(f"embedding_model: {EMBEDDING_MODEL}")
    print()

    cases = _load_cases(args.cases)
    results = [_evaluate_case(case) for case in cases]

    for result in results:
        _print_case_result(result)

    total = len(results)
    top1_hits = sum(1 for result in results if result["top1_title_hit"])
    topk_hits = sum(1 for result in results if result["topk_title_hit"])
    total_noise = sum(int(result["noise_count"]) for result in results)
    total_cross_destination_noise = sum(
        int(result["cross_destination_noise_count"]) for result in results
    )
    total_required_hits = sum(int(result["required_keyword_hits"]) for result in results)
    total_required_keywords = sum(
        int(result["required_keyword_total"]) for result in results
    )

    print("=== Summary ===")
    print(f"cases: {total}")
    print(f"top1_title_hit_rate: {top1_hits}/{total}")
    print(f"topk_title_hit_rate: {topk_hits}/{total}")
    print(f"required_keyword_coverage: {total_required_hits}/{total_required_keywords}")
    print(f"noise_count_total: {total_noise}")
    print(f"cross_destination_noise_count_total: {total_cross_destination_noise}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
