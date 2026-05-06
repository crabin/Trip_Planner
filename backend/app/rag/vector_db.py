from __future__ import annotations

import logging
import json
import math
import re
import shutil
import time
from hashlib import md5
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.config import (
    BACKEND_DIR,
    CHROMA_COLLECTION_NAME,
    CHROMA_DB_DIR,
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL,
    LLM_API_KEY,
    LLM_BASE_URL,
)


DATA_DIR = BACKEND_DIR / "data"
LOCAL_EMBEDDING_INDEX_PATH = BACKEND_DIR / "db" / "guide_embeddings.json"
_OLLAMA_PLACEHOLDER_API_KEY = "ollama"
logger = logging.getLogger(__name__)

DESTINATION_BY_SOURCE = {
    "chengdu_guide.md": "成都",
    "dali_guide.md": "大理",
    "sanya_guide.md": "三亚",
    "xiamen_guide.md": "厦门",
    "xian_guide.md": "西安",
}


def _resolve_chunk_destination(source_name: str) -> str:
    """从攻略文件名解析目的地，作为检索硬过滤 metadata。"""
    return DESTINATION_BY_SOURCE.get(source_name, Path(source_name).stem.split("_", 1)[0])


def _split_markdown_into_chunks(markdown_text: str, source_name: str) -> list[dict[str, str]]:
    """按二级、三级标题切分 Markdown，返回可检索片段。"""
    chunks: list[dict[str, str]] = []
    current_title = "文档开头"
    current_lines: list[str] = []
    destination = _resolve_chunk_destination(source_name)

    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            if current_lines:
                chunks.append(
                    {
                        "title": current_title,
                        "text": "\n".join(current_lines).strip(),
                        "source": source_name,
                        "destination": destination,
                    }
                )
                current_lines = []
            current_title = stripped.lstrip("#").strip()
        elif stripped:
            current_lines.append(stripped)

    if current_lines:
        chunks.append(
            {
                "title": current_title,
                "text": "\n".join(current_lines).strip(),
                "source": source_name,
                "destination": destination,
            }
        )

    return chunks


def _build_chunk_id(source: str, title: str, text: str) -> str:
    """基于 source、title 和 text 生成稳定片段 ID。"""
    digest = md5(f"{source}|{title}|{text}".encode("utf-8")).hexdigest()
    return f"{source}_{digest}"


def _build_document_text(chunk: dict[str, str]) -> str:
    """把标题和正文拼成送入向量库的文档文本。"""
    return f"{chunk['title']}\n{chunk['text']}"


def load_guide_chunks() -> list[dict[str, str]]:
    """读取 backend/data 下的攻略文件，并切分成可检索片段。"""
    chunks: list[dict[str, str]] = []
    for guide_file in sorted(DATA_DIR.glob("*.md*")):
        text = guide_file.read_text(encoding="utf-8")
        raw_chunks = _split_markdown_into_chunks(text, guide_file.name)
        for chunk in raw_chunks:
            chunks.append(
                {
                    "id": _build_chunk_id(chunk["source"], chunk["title"], chunk["text"]),
                    "title": chunk["title"],
                    "text": chunk["text"],
                    "source": chunk["source"],
                    "destination": chunk["destination"],
                }
            )
    return chunks


def _build_chunks_fingerprint(chunks: list[dict[str, str]]) -> str:
    """基于当前攻略内容生成稳定指纹，用于判断索引是否需要重建。"""
    payload = "\n".join(
        f"{chunk['id']}|{chunk['source']}|{chunk.get('destination', '')}|{chunk['title']}|{chunk['text']}"
        for chunk in chunks
    )
    return md5(payload.encode("utf-8")).hexdigest()


def _extract_keywords(query: str) -> list[str]:
    """把查询语句切成简单关键词，用于回退匹配。"""
    raw_keywords = re.split(r"[\s,，。；;、]+", query)
    return [keyword.strip() for keyword in raw_keywords if keyword.strip()]


def _score_chunk(query: str, chunk_text: str) -> int:
    """按关键词出现次数给片段打分。"""
    keywords = _extract_keywords(query)
    return sum(1 for keyword in keywords if keyword in chunk_text)


def _chunk_matches_destination(chunk: dict[str, object], destination: str | None) -> bool:
    """判断片段是否属于目标目的地；未指定目的地时不过滤。"""
    if not destination:
        return True

    chunk_destination = str(chunk.get("destination") or "").strip()
    if chunk_destination:
        return destination in chunk_destination or chunk_destination in destination

    source = str(chunk.get("source") or "")
    resolved_destination = _resolve_chunk_destination(source)
    return destination in resolved_destination or resolved_destination in destination


def _search_guide_chunks_by_keywords(
    query: str, top_k: int = 3, destination: str | None = None
) -> list[dict[str, str]]:
    """回退方案：使用关键词匹配本地攻略片段。"""
    scored_chunks: list[tuple[int, dict[str, str]]] = []
    for chunk in load_guide_chunks():
        if not _chunk_matches_destination(chunk, destination):
            continue
        score = _score_chunk(query, _build_document_text(chunk))
        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored_chunks[:top_k]]


def _normalize_embedding_base_url(base_url: str) -> str | None:
    """把 embedding base URL 规范化为 OpenAI 兼容形式。"""
    normalized = base_url.strip()
    if not normalized:
        return None

    normalized = normalized.rstrip("/")
    parsed_url = urlsplit(normalized)
    if parsed_url.path in ("", "/"):
        return urlunsplit(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                "/v1",
                parsed_url.query,
                parsed_url.fragment,
            )
        )
    return normalized


def _normalize_ollama_base_url(base_url: str) -> str | None:
    """把 Ollama base URL 规范化为不带尾随斜杠的根地址。"""
    normalized = base_url.strip().rstrip("/")
    return normalized or None


def _resolve_embedding_base_url() -> str | None:
    """解析 embedding 服务的 base URL，未显式配置时回退到 LLM 配置。"""
    return _normalize_embedding_base_url(EMBEDDING_BASE_URL or LLM_BASE_URL)


def _resolve_embedding_api_key(base_url: str | None) -> str:
    """兼容本地 OpenAI 风格 embedding 服务对 api_key 参数的要求。"""
    if EMBEDDING_API_KEY:
        return EMBEDDING_API_KEY
    if EMBEDDING_BASE_URL and base_url:
        return _OLLAMA_PLACEHOLDER_API_KEY
    return LLM_API_KEY


def _should_use_ollama_embeddings() -> bool:
    """当前配置更像本地 Ollama embedding 服务时，走原生接口。"""
    return bool(EMBEDDING_BASE_URL and not EMBEDDING_API_KEY)


class _OllamaEmbeddingsClient:
    """使用 Ollama 原生 /api/embed 接口生成向量。"""

    def __init__(self, base_url: str, model: str, timeout_seconds: float = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def _embed(self, inputs: str | list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": inputs},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings:
            raise RuntimeError("Ollama embedding 返回结果缺少 embeddings。")
        return embeddings

    def embed_documents(self, documents: list[str]) -> list[list[float]]:
        return self._embed(documents)

    def embed_query(self, query: str) -> list[float]:
        return self._embed(query)[0]


def _build_local_embedding_index() -> list[dict[str, object]]:
    """基于当前 embedding 配置构建本地 JSON 向量索引。"""
    embeddings = _build_embeddings()
    chunks = load_guide_chunks()
    if embeddings is None:
        raise RuntimeError("当前环境缺少 embedding 能力，无法构建本地向量索引。")

    documents = [_build_document_text(chunk) for chunk in chunks]
    vectors = embeddings.embed_documents(documents)
    if len(vectors) != len(chunks):
        raise RuntimeError("embedding 返回数量与攻略片段数量不一致。")

    records: list[dict[str, object]] = []
    for chunk, vector in zip(chunks, vectors):
        records.append(
            {
                "id": chunk["id"],
                "title": chunk["title"],
                "text": chunk["text"],
                "source": chunk["source"],
                "destination": chunk.get(
                    "destination",
                    _resolve_chunk_destination(chunk["source"]),
                ),
                "embedding": vector,
            }
        )

    payload = {
        "model": EMBEDDING_MODEL,
        "base_url": _normalize_ollama_base_url(EMBEDDING_BASE_URL) or "",
        "source_fingerprint": _build_chunks_fingerprint(chunks),
        "records": records,
    }
    LOCAL_EMBEDDING_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_EMBEDDING_INDEX_PATH.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return records


def _load_local_embedding_index() -> list[dict[str, object]]:
    """读取本地 JSON 向量索引；缺失或过期时自动重建。"""
    chunks = load_guide_chunks()
    current_fingerprint = _build_chunks_fingerprint(chunks)
    current_base_url = _normalize_ollama_base_url(EMBEDDING_BASE_URL) or ""

    if LOCAL_EMBEDDING_INDEX_PATH.exists():
        try:
            payload = json.loads(LOCAL_EMBEDDING_INDEX_PATH.read_text(encoding="utf-8"))
            if (
                payload.get("model") == EMBEDDING_MODEL
                and payload.get("base_url") == current_base_url
                and payload.get("source_fingerprint") == current_fingerprint
            ):
                records = payload.get("records")
                if isinstance(records, list):
                    return records
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            logger.warning("Failed to read local embedding index, rebuilding it.")

    return _build_local_embedding_index()


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    """计算两个向量的余弦相似度。"""
    numerator = sum(lhs * rhs for lhs, rhs in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _search_guide_chunks_by_local_embeddings(
    query: str, top_k: int = 3, destination: str | None = None
) -> list[dict[str, str]]:
    """使用本地 JSON 向量索引做检索，适配当前 Ollama embedding 配置。"""
    embeddings = _build_embeddings()
    if embeddings is None:
        return []

    records = _load_local_embedding_index()
    query_embedding = embeddings.embed_query(query)

    scored_records: list[tuple[float, dict[str, object]]] = []
    for record in records:
        if not _chunk_matches_destination(record, destination):
            continue
        vector = record.get("embedding")
        if not isinstance(vector, list):
            continue
        similarity = _cosine_similarity(query_embedding, vector)
        scored_records.append((similarity, record))

    scored_records.sort(key=lambda item: item[0], reverse=True)
    matched_chunks: list[dict[str, str]] = []
    for _, record in scored_records[:top_k]:
        matched_chunks.append(
            {
                "title": str(record.get("title", "未命名片段")),
                "text": str(record.get("text", "")),
                "source": str(record.get("source", "未知来源")),
                "destination": str(record.get("destination", "")),
            }
        )
    return matched_chunks


def _build_embeddings() -> object | None:
    """创建 embedding 模型实例。"""
    normalized_base_url = _resolve_embedding_base_url()
    api_key = _resolve_embedding_api_key(normalized_base_url)
    if not api_key and normalized_base_url is None:
        return None

    if _should_use_ollama_embeddings():
        ollama_base_url = _normalize_ollama_base_url(EMBEDDING_BASE_URL)
        if ollama_base_url is None:
            return None
        return _OllamaEmbeddingsClient(
            base_url=ollama_base_url,
            model=EMBEDDING_MODEL,
        )

    try:
        from langchain_openai import OpenAIEmbeddings
    except ImportError:
        return None

    try:
        return OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            api_key=api_key,
            base_url=normalized_base_url,
            chunk_size=EMBEDDING_BATCH_SIZE,
            check_embedding_ctx_length=False,
        )
    except TypeError:
        return OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            openai_api_key=api_key,
            openai_api_base=normalized_base_url,
            chunk_size=EMBEDDING_BATCH_SIZE,
            check_embedding_ctx_length=False,
        )


def _get_chroma_collection():
    """获取 Chroma collection。"""
    try:
        import chromadb
    except ImportError:
        return None

    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    return client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _log_chroma_error(action: str, error: Exception) -> None:
    """记录 Chroma 异常，提示当前会回退到关键词检索。"""
    logger.warning(
        "Chroma %s failed, falling back to keyword search. db_dir=%s collection=%s error=%s",
        action,
        CHROMA_DB_DIR,
        CHROMA_COLLECTION_NAME,
        error,
    )


def _is_chroma_storage_incompatible(error: Exception) -> bool:
    """识别需要重建 Chroma 本地库的兼容性错误。"""
    error_text = str(error).lower()
    return "mismatched types" in error_text or "metadata segment reader" in error_text


def _reset_chroma_storage() -> None:
    """备份当前 Chroma 数据目录，并创建新的空目录。"""
    if CHROMA_DB_DIR.exists():
        backup_dir = CHROMA_DB_DIR.with_name(
            f"{CHROMA_DB_DIR.name}_backup_{time.strftime('%Y%m%d_%H%M%S')}"
        )
        shutil.move(str(CHROMA_DB_DIR), str(backup_dir))
        logger.warning("Backed up incompatible Chroma DB to %s", backup_dir)
    CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)


def _repair_chroma_storage(error: Exception) -> bool:
    """遇到已知不兼容错误时，自动重建 Chroma 索引。"""
    if not _is_chroma_storage_incompatible(error):
        return False

    try:
        _reset_chroma_storage()
        written_count = ingest_guide_chunks_to_chroma()
        logger.warning("Rebuilt Chroma storage successfully. written_count=%s", written_count)
        return True
    except Exception as rebuild_error:
        logger.exception("Failed to rebuild Chroma storage: %s", rebuild_error)
        return False


def ingest_guide_chunks_to_chroma() -> int:
    """
    把本地攻略片段写入 Chroma。

    流程是：
    1. 创建 embedding 模型
    2. 获取 Chroma collection
    3. 读取并切分本地攻略
    4. 生成向量
    5. 把向量、文本和 metadata 一起写入 Chroma
    """
    if _should_use_ollama_embeddings():
        return len(_build_local_embedding_index())

    embeddings = _build_embeddings()
    collection = _get_chroma_collection()
    chunks = load_guide_chunks()

    if embeddings is None:
        raise RuntimeError("当前环境缺少 embedding 能力，无法写入 Chroma。")
    if collection is None:
        raise RuntimeError("当前环境缺少 chromadb，无法写入 Chroma。")

    documents = [_build_document_text(chunk) for chunk in chunks]
    vectors = embeddings.embed_documents(documents)
    ids = [chunk["id"] for chunk in chunks]
    metadatas = [
        {
            "title": chunk["title"],
            "source": chunk["source"],
            "destination": chunk.get(
                "destination",
                _resolve_chunk_destination(chunk["source"]),
            ),
        }
        for chunk in chunks
    ]

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=vectors,
    )
    return len(chunks)


def _search_guide_chunks_by_chroma(
    query: str,
    top_k: int = 3,
    destination: str | None = None,
    allow_repair: bool = True,
) -> list[dict[str, str]]:
    """优先使用 Chroma 做向量检索。"""
    embeddings = _build_embeddings()
    try:
        collection = _get_chroma_collection()
    except Exception as error:
        _log_chroma_error("collection init", error)
        if allow_repair and _repair_chroma_storage(error):
            return _search_guide_chunks_by_chroma(
                query=query,
                top_k=top_k,
                destination=destination,
                allow_repair=False,
            )
        return []

    if embeddings is None or collection is None:
        return []

    try:
        collection.count()
    except Exception as error:
        _log_chroma_error("count", error)
        if allow_repair and _repair_chroma_storage(error):
            return _search_guide_chunks_by_chroma(
                query=query,
                top_k=top_k,
                destination=destination,
                allow_repair=False,
            )
        return []

    query_embedding = embeddings.embed_query(query)
    query_kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
        "include": ["documents", "metadatas"],
    }
    if destination:
        query_kwargs["where"] = {"destination": destination}

    try:
        result = collection.query(**query_kwargs)
    except Exception as error:
        _log_chroma_error("query", error)
        if allow_repair and _repair_chroma_storage(error):
            return _search_guide_chunks_by_chroma(
                query=query,
                top_k=top_k,
                destination=destination,
                allow_repair=False,
            )
        return []

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]

    matched_chunks: list[dict[str, str]] = []
    for document, metadata in zip(documents, metadatas):
        title = metadata.get("title", "未命名片段") if metadata else "未命名片段"
        source = metadata.get("source", "未知来源") if metadata else "未知来源"
        metadata_destination = metadata.get("destination", "") if metadata else ""
        chunk_destination = metadata_destination or _resolve_chunk_destination(str(source))
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


def search_guide_chunks(
    query: str, top_k: int = 3, destination: str | None = None
) -> list[dict[str, str]]:
    """
    从本地攻略片段里找最相关的 top_k 条结果。

    优先走 Chroma 向量检索；如果当前环境还没准备好，再回退到关键词检索。
    """
    if _should_use_ollama_embeddings():
        embedding_results = _search_guide_chunks_by_local_embeddings(
            query=query,
            top_k=top_k,
            destination=destination,
        )
        if embedding_results:
            return embedding_results

    chroma_results = _search_guide_chunks_by_chroma(
        query=query,
        top_k=top_k,
        destination=destination,
    )
    if chroma_results:
        return chroma_results
    return _search_guide_chunks_by_keywords(
        query=query,
        top_k=top_k,
        destination=destination,
    )
