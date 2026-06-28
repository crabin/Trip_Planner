from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.location_service import get_location_suggestions  # noqa: E402
from app.services.location_service import check_destination_span  # noqa: E402


def test_get_location_suggestions_normalizes_amap_tips(monkeypatch) -> None:
    def fake_request_amap(path: str, params: dict) -> dict:
        assert path == "/assistant/inputtips"
        assert params["keywords"] == "北"
        return {
            "tips": [
                {"name": "北京", "district": "北京市", "adcode": "110000"},
                {"name": "北京", "district": "北京市", "adcode": "110000"},
                {"name": "北戴河区", "district": "河北省秦皇岛市北戴河区", "adcode": "130304"},
            ]
        }

    monkeypatch.setattr("app.services.location_service.get_cached_json", lambda _key: None)
    monkeypatch.setattr("app.services.location_service.set_cached_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.services.location_service._request_amap", fake_request_amap)

    suggestions = get_location_suggestions("北", limit=10)

    assert suggestions == [
        {
            "label": "北京 · 北京市",
            "value": "北京",
            "district": "北京市",
            "adcode": "110000",
        },
        {
            "label": "北戴河区 · 河北省秦皇岛市北戴河区",
            "value": "北戴河区",
            "district": "河北省秦皇岛市北戴河区",
            "adcode": "130304",
        },
    ]


def test_check_destination_span_flags_large_distance(monkeypatch) -> None:
    coordinates = {
        "北京": {"latitude": 39.9042, "longitude": 116.4074, "formatted_address": "北京市"},
        "三亚": {"latitude": 18.2528, "longitude": 109.5119, "formatted_address": "三亚市"},
    }

    monkeypatch.setattr(
        "app.services.location_service.geocode_address",
        lambda address, city=None: coordinates.get(address),
    )

    result = check_destination_span(["北京", "三亚"])

    assert result["is_large_span"] is True
    assert result["max_distance_km"] > 2000
    assert result["max_pair"] == ["北京", "三亚"]
    assert result["unresolved"] == []
