from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.services.local_life_service as local_life_service  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, timeout):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, params):
        assert url == "https://partner.example/search"
        assert params["category"] == "restaurant"
        return FakeResponse(
            {
                "data": {
                    "items": [
                        {
                            "shop_id": "dp_1",
                            "shop_name": "点评白族菜",
                            "address": "人民路 3 号",
                            "lat": 25.69,
                            "lng": 100.16,
                            "rating": "4.9",
                            "avg_price": "86",
                            "comment_count": "928",
                            "tags": ["白族菜", "本地热门"],
                            "badge": "大理热门餐厅",
                            "detail_url": "https://partner.example/shop/dp_1",
                        }
                    ]
                }
            }
        )


def test_fetch_local_life_candidates_normalizes_partner_payload(monkeypatch) -> None:
    """测试美团/点评合作接口风格数据会被归一化。"""
    monkeypatch.setattr(local_life_service, "ENABLE_LOCAL_LIFE_ENRICHMENT", True)
    monkeypatch.setattr(local_life_service, "MEITUAN_API_BASE_URL", "https://partner.example")
    monkeypatch.setattr(local_life_service, "MEITUAN_API_KEY", "test-key")
    monkeypatch.setattr(local_life_service, "DIANPING_API_BASE_URL", "")
    monkeypatch.setattr(local_life_service, "DIANPING_API_KEY", "")
    monkeypatch.setattr(local_life_service, "get_cached_json", lambda key: None)
    monkeypatch.setattr(
        local_life_service,
        "set_cached_json",
        lambda key, value, expire_seconds=None: None,
    )
    monkeypatch.setattr(local_life_service.httpx, "Client", FakeClient)

    results = local_life_service.fetch_local_life_candidates(
        longitude=100.16,
        latitude=25.69,
        category="restaurant",
        radius=2000,
        page_size=5,
    )

    assert results == [
        {
            "data_source": "meituan",
            "category": "restaurant",
            "source_id": "dp_1",
            "name": "点评白族菜",
            "address": "人民路 3 号",
            "latitude": 25.69,
            "longitude": 100.16,
            "image_url": None,
            "map_rating": 4.9,
            "map_average_cost": 86.0,
            "map_tags": ["白族菜", "本地热门"],
            "map_tel": None,
            "map_distance_meters": None,
            "map_business_area": None,
            "map_open_time_today": None,
            "source_url": "https://partner.example/shop/dp_1",
            "review_count": 928,
            "ranking_label": "大理热门餐厅",
        }
    ]
