from pathlib import Path
import sys
import types


# 允许测试文件直接导入 backend/app 下的模块。
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.rag.retriever as retriever  # noqa: E402
import app.rag.vector_db as vector_db  # noqa: E402


def test_retrieve_travel_guide_formats_chunks_as_text(monkeypatch) -> None:
    """测试 retriever 会把检索结果格式化成可直接引用的文本片段。"""

    def fake_search_guide_chunks(
        query: str, top_k: int = 3, destination: str | None = None
    ) -> list[dict[str, str]]:
        assert query == "大理 古城 美食"
        assert destination is None
        return [
            {
                "source": "dali_guide.md",
                "title": "大理古城",
                "text": "大理古城适合慢游和拍照。",
            }
        ]

    monkeypatch.setattr(retriever, "search_guide_chunks", fake_search_guide_chunks)

    results = retriever.retrieve_travel_guide("大理 古城 美食", top_k=2)

    assert results == ["[来源: dali_guide.md | 标题: 大理古城]\n大理古城适合慢游和拍照。"]


def test_retrieve_travel_guide_returns_empty_when_no_chunks(monkeypatch) -> None:
    """测试没有召回任何片段时，会返回空列表。"""

    def fake_search_guide_chunks(
        query: str, top_k: int = 3, destination: str | None = None
    ) -> list[dict[str, str]]:
        assert query == "火星 沙漠 极地科考"
        assert destination is None
        return []

    monkeypatch.setattr(retriever, "search_guide_chunks", fake_search_guide_chunks)

    results = retriever.retrieve_travel_guide("火星 沙漠 极地科考", top_k=2)

    assert results == []


def test_retrieve_travel_guide_filters_cross_destination_chunks(monkeypatch) -> None:
    """测试生成上下文前会硬过滤掉其他目的地的攻略片段。"""

    def fake_search_guide_chunks(
        query: str, top_k: int = 3, destination: str | None = None
    ) -> list[dict[str, str]]:
        assert destination == "厦门"
        return [
            {
                "source": "xiamen_guide.md",
                "title": "2.4 环岛路",
                "text": "环岛路适合骑行、海景和日落。",
                "destination": "厦门",
            },
            {
                "source": "dali_guide.md",
                "title": "2.4 洱海生态廊道 (骑行)",
                "text": "洱海生态廊道适合骑行。",
                "destination": "大理",
            },
        ]

    monkeypatch.setattr(retriever, "search_guide_chunks", fake_search_guide_chunks)

    results = retriever.retrieve_travel_guide(
        "厦门 骑行 海景 休闲",
        top_k=5,
        destination="厦门",
    )

    assert results == [
        "[来源: xiamen_guide.md | 标题: 2.4 环岛路]\n环岛路适合骑行、海景和日落。"
    ]


def test_build_embeddings_uses_embedding_base_url_for_ollama(monkeypatch) -> None:
    """测试本地 Ollama embedding 服务会走原生 /api/embed 客户端。"""

    monkeypatch.setattr(vector_db, "EMBEDDING_MODEL", "nomic-embed-text:latest")
    monkeypatch.setattr(vector_db, "EMBEDDING_API_KEY", "")
    monkeypatch.setattr(vector_db, "EMBEDDING_BASE_URL", "http://lpbkuaile5u:11434/")
    monkeypatch.setattr(vector_db, "LLM_API_KEY", "")
    monkeypatch.setattr(vector_db, "LLM_BASE_URL", "")
    monkeypatch.setattr(vector_db, "EMBEDDING_BATCH_SIZE", 10)

    client = vector_db._build_embeddings()

    assert isinstance(client, vector_db._OllamaEmbeddingsClient)
    assert client.model == "nomic-embed-text:latest"
    assert client.base_url == "http://lpbkuaile5u:11434"


def test_build_embeddings_returns_none_without_key_or_base_url(monkeypatch) -> None:
    """测试缺少 key 和 base_url 时，不会创建 embedding 客户端。"""

    monkeypatch.setattr(vector_db, "EMBEDDING_API_KEY", "")
    monkeypatch.setattr(vector_db, "EMBEDDING_BASE_URL", "")
    monkeypatch.setattr(vector_db, "LLM_API_KEY", "")
    monkeypatch.setattr(vector_db, "LLM_BASE_URL", "")

    assert vector_db._build_embeddings() is None


def test_build_embeddings_falls_back_to_llm_config(monkeypatch) -> None:
    """测试未单独配置 embedding 时，会回退到现有 LLM 配置。"""

    captured_kwargs: dict[str, object] = {}

    class FakeOpenAIEmbeddings:
        def __init__(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        types.SimpleNamespace(OpenAIEmbeddings=FakeOpenAIEmbeddings),
    )
    monkeypatch.setattr(vector_db, "EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setattr(vector_db, "EMBEDDING_API_KEY", "")
    monkeypatch.setattr(vector_db, "EMBEDDING_BASE_URL", "")
    monkeypatch.setattr(vector_db, "LLM_API_KEY", "test-llm-key")
    monkeypatch.setattr(vector_db, "LLM_BASE_URL", "http://llm-host:8000/v1")
    monkeypatch.setattr(vector_db, "EMBEDDING_BATCH_SIZE", 8)

    vector_db._build_embeddings()

    assert captured_kwargs["api_key"] == "test-llm-key"
    assert captured_kwargs["base_url"] == "http://llm-host:8000/v1"
    assert captured_kwargs["chunk_size"] == 8


def test_ollama_embeddings_client_calls_native_embed_api(monkeypatch) -> None:
    """测试 Ollama embedding 客户端会调用 /api/embed。"""

    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}

    def fake_post(url: str, json: dict[str, object], timeout: float):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(vector_db.httpx, "post", fake_post)
    client = vector_db._OllamaEmbeddingsClient(
        base_url="http://ollama-host:11434",
        model="nomic-embed-text:latest",
    )

    vectors = client.embed_documents(["大理 古城", "洱海 日落"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["url"] == "http://ollama-host:11434/api/embed"
    assert captured["json"] == {
        "model": "nomic-embed-text:latest",
        "input": ["大理 古城", "洱海 日落"],
    }
    assert captured["timeout"] == 60


def test_ingest_guide_chunks_writes_chroma_with_ollama_embeddings(monkeypatch) -> None:
    """测试 Ollama 配置下也会用生成好的向量写入 Chroma。"""

    class FakeEmbeddings:
        def embed_documents(self, documents: list[str]) -> list[list[float]]:
            assert len(documents) == 2
            return [[0.1, 0.2], [0.3, 0.4]]

    class FakeCollection:
        def __init__(self) -> None:
            self.upsert_kwargs: dict[str, object] = {}

        def upsert(self, **kwargs) -> None:
            self.upsert_kwargs = kwargs

    collection = FakeCollection()

    monkeypatch.setattr(vector_db, "EMBEDDING_MODEL", "nomic-embed-text:latest")
    monkeypatch.setattr(vector_db, "EMBEDDING_BASE_URL", "http://ollama-host:11434/")
    monkeypatch.setattr(vector_db, "EMBEDDING_API_KEY", "")
    monkeypatch.setattr(
        vector_db,
        "load_guide_chunks",
        lambda: [
            {"id": "1", "title": "大理古城", "text": "适合慢游。", "source": "dali.md"},
            {"id": "2", "title": "洱海", "text": "适合看日落。", "source": "dali.md"},
        ],
    )
    monkeypatch.setattr(vector_db, "_build_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(vector_db, "_get_chroma_collection", lambda: collection)

    written_count = vector_db.ingest_guide_chunks_to_chroma()

    assert written_count == 2
    assert collection.upsert_kwargs["ids"] == ["1", "2"]
    assert collection.upsert_kwargs["documents"] == [
        "大理古城\n适合慢游。",
        "洱海\n适合看日落。",
    ]
    assert collection.upsert_kwargs["embeddings"] == [[0.1, 0.2], [0.3, 0.4]]
    assert collection.upsert_kwargs["metadatas"] == [
        {"title": "大理古城", "source": "dali.md", "destination": "dali"},
        {"title": "洱海", "source": "dali.md", "destination": "dali"},
    ]


def test_search_guide_chunks_uses_chroma_with_ollama(monkeypatch) -> None:
    """测试当前 Ollama 配置下会优先走 Chroma 检索。"""

    class FakeEmbeddings:
        def embed_query(self, query: str) -> list[float]:
            assert query == "大理 古城"
            return [1.0, 0.0]

    class FakeCollection:
        def count(self) -> int:
            return 2

        def query(self, **kwargs):
            assert kwargs["query_embeddings"] == [[1.0, 0.0]]
            assert kwargs["n_results"] == 1
            return {
                "documents": [["大理古城\n适合慢游和拍照。"]],
                "metadatas": [[{"title": "大理古城", "source": "dali.md", "destination": "大理"}]],
            }

    monkeypatch.setattr(vector_db, "EMBEDDING_MODEL", "nomic-embed-text:latest")
    monkeypatch.setattr(vector_db, "EMBEDDING_BASE_URL", "http://ollama-host:11434/")
    monkeypatch.setattr(vector_db, "EMBEDDING_API_KEY", "")
    monkeypatch.setattr(vector_db, "_build_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(vector_db, "_get_chroma_collection", lambda: FakeCollection())

    results = vector_db.search_guide_chunks("大理 古城", top_k=1)

    assert results == [
        {
            "title": "大理古城",
            "text": "适合慢游和拍照。",
            "source": "dali.md",
            "destination": "大理",
        }
    ]


def test_search_guide_chunks_falls_back_to_keywords_for_ollama_without_json_index(
    monkeypatch,
    tmp_path,
) -> None:
    """测试 Chroma 不可用时，Ollama 配置不会再自动构建 JSON 索引。"""

    monkeypatch.setattr(vector_db, "LOCAL_EMBEDDING_INDEX_PATH", tmp_path / "guide_embeddings.json")
    monkeypatch.setattr(vector_db, "EMBEDDING_MODEL", "nomic-embed-text:latest")
    monkeypatch.setattr(vector_db, "EMBEDDING_BASE_URL", "http://ollama-host:11434/")
    monkeypatch.setattr(vector_db, "EMBEDDING_API_KEY", "")
    monkeypatch.setattr(vector_db, "_search_guide_chunks_by_chroma", lambda **kwargs: [])
    monkeypatch.setattr(
        vector_db,
        "_search_guide_chunks_by_local_embeddings",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("不应再回退到本地 JSON 向量索引")
        ),
    )
    monkeypatch.setattr(
        vector_db,
        "_search_guide_chunks_by_keywords",
        lambda query, top_k=3, destination=None: [
            {"title": "关键词命中", "text": "关键词兜底成功。", "source": "local.md"}
        ],
    )

    results = vector_db.search_guide_chunks("大理 古城", top_k=1)

    assert results == [{"title": "关键词命中", "text": "关键词兜底成功。", "source": "local.md"}]
    assert not (tmp_path / "guide_embeddings.json").exists()


def test_search_guide_chunks_falls_back_when_chroma_count_fails(monkeypatch) -> None:
    """测试 Chroma count 出错时，会自动回退到关键词检索。"""

    class FakeEmbeddings:
        def embed_query(self, query: str) -> list[float]:
            raise AssertionError("count 失败时不应继续做向量检索")

    class BrokenCollection:
        def count(self) -> int:
            raise RuntimeError("mismatched types")

    monkeypatch.setattr(vector_db, "EMBEDDING_BASE_URL", "")
    monkeypatch.setattr(vector_db, "_build_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(vector_db, "_get_chroma_collection", lambda: BrokenCollection())
    monkeypatch.setattr(
        vector_db,
        "_search_guide_chunks_by_keywords",
        lambda query, top_k=3, destination=None: [
            {"title": "关键词命中", "text": "回退成功", "source": "local.md"}
        ],
    )

    results = vector_db.search_guide_chunks("大理 古城", top_k=2)

    assert results == [{"title": "关键词命中", "text": "回退成功", "source": "local.md"}]


def test_search_guide_chunks_falls_back_when_chroma_query_fails(monkeypatch) -> None:
    """测试 Chroma query 出错时，会自动回退到关键词检索。"""

    class FakeEmbeddings:
        def embed_query(self, query: str) -> list[float]:
            assert query == "大理 洱海"
            return [0.1, 0.2]

    class BrokenCollection:
        def count(self) -> int:
            return 2

        def query(self, **kwargs):
            raise RuntimeError("metadata decode failed")

    monkeypatch.setattr(vector_db, "EMBEDDING_BASE_URL", "")
    monkeypatch.setattr(vector_db, "_build_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(vector_db, "_get_chroma_collection", lambda: BrokenCollection())
    monkeypatch.setattr(
        vector_db,
        "_search_guide_chunks_by_keywords",
        lambda query, top_k=3, destination=None: [
            {"title": "关键词命中", "text": "二次回退成功", "source": "local.md"}
        ],
    )

    results = vector_db.search_guide_chunks("大理 洱海", top_k=2)

    assert results == [{"title": "关键词命中", "text": "二次回退成功", "source": "local.md"}]


def test_search_guide_chunks_repairs_incompatible_chroma(monkeypatch) -> None:
    """测试遇到不兼容的 Chroma 库时，会自动重建并重试。"""

    call_count = {"count": 0}

    class FakeEmbeddings:
        def embed_query(self, query: str) -> list[float]:
            assert query == "大理 洱海"
            return [0.1, 0.2]

    class BrokenCollection:
        def count(self) -> int:
            raise RuntimeError("metadata segment reader mismatched types")

    class HealthyCollection:
        def count(self) -> int:
            return 1

        def query(self, **kwargs):
            return {
                "documents": [["大理古城\n适合慢游。"]],
                "metadatas": [[{"title": "大理古城", "source": "dali_guide.md"}]],
            }

    def fake_get_collection():
        call_count["count"] += 1
        if call_count["count"] == 1:
            return BrokenCollection()
        return HealthyCollection()

    monkeypatch.setattr(vector_db, "EMBEDDING_BASE_URL", "")
    monkeypatch.setattr(vector_db, "_build_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(vector_db, "_get_chroma_collection", fake_get_collection)
    monkeypatch.setattr(vector_db, "_repair_chroma_storage", lambda error: True)

    results = vector_db.search_guide_chunks("大理 洱海", top_k=2)

    assert results == [
        {
            "title": "大理古城",
            "text": "适合慢游。",
            "source": "dali_guide.md",
            "destination": "大理",
        }
    ]
    assert call_count["count"] == 2


def test_search_guide_chunks_queries_even_when_count_is_zero(monkeypatch) -> None:
    """测试 count 为 0 时仍会尝试 query，兼容刚写入后的短暂延迟。"""

    class FakeEmbeddings:
        def embed_query(self, query: str) -> list[float]:
            assert query == "大理 古城"
            return [0.1, 0.2]

    class LaggyCollection:
        def count(self) -> int:
            return 0

        def query(self, **kwargs):
            return {
                "documents": [["大理古城\n适合慢游和拍照。"]],
                "metadatas": [[{"title": "大理古城", "source": "dali_guide.md"}]],
            }

    monkeypatch.setattr(vector_db, "EMBEDDING_BASE_URL", "")
    monkeypatch.setattr(vector_db, "_build_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(vector_db, "_get_chroma_collection", lambda: LaggyCollection())

    results = vector_db.search_guide_chunks("大理 古城", top_k=2)

    assert results == [
        {
            "title": "大理古城",
            "text": "适合慢游和拍照。",
            "source": "dali_guide.md",
            "destination": "大理",
        }
    ]
