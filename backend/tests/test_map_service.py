from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import (  # noqa: E402
    BudgetBreakdown,
    DayPlan,
    HotelItem,
    Itinerary,
    MealItem,
    SpotItem,
)
import app.services.map_service as map_service  # noqa: E402


def _disable_cache(monkeypatch) -> None:
    monkeypatch.setattr(map_service, "get_cached_json", lambda key: None)
    monkeypatch.setattr(
        map_service,
        "set_cached_json",
        lambda key, value, expire_seconds=None: None,
    )


def test_search_places_normalizes_amap_rating_cost_and_tags(monkeypatch) -> None:
    """测试关键字 POI 搜索会保留评分、参考消费、标签和图片。"""
    _disable_cache(monkeypatch)

    monkeypatch.setattr(
        map_service,
        "_request_amap",
        lambda path, params: {
            "status": "1",
            "pois": [
                {
                    "id": "B001",
                    "name": "大理古城",
                    "address": "一塔路",
                    "location": "100.161,25.694",
                    "type": "风景名胜;风景名胜;旅游景点",
                    "tel": "0872-0000000",
                    "tag": "古城;拍照",
                    "biz_ext": {"rating": "4.7", "cost": "0"},
                    "photos": [{"url": "https://example.test/dali.jpg"}],
                }
            ],
        },
    )

    places = map_service.search_places("大理古城", city="大理", page_size=1)

    assert places == [
        {
            "name": "大理古城",
            "address": "一塔路",
            "cityname": None,
            "adname": None,
            "type": "风景名胜;风景名胜;旅游景点",
            "typecode": None,
            "poi_id": "B001",
            "image_url": "https://example.test/dali.jpg",
            "latitude": 25.694,
            "longitude": 100.161,
            "business_area": None,
            "map_rating": 4.7,
            "map_average_cost": 0.0,
            "map_tags": ["古城", "拍照"],
            "map_tel": "0872-0000000",
            "map_distance_meters": None,
        }
    ]


def test_search_nearby_places_uses_v5_business_fields_and_ranks(monkeypatch) -> None:
    """测试周边搜索使用 v5 字段，并按评分优先推荐。"""
    _disable_cache(monkeypatch)

    def fake_request(path, params, api_version="v3"):
        assert path == "/place/around"
        assert api_version == "v5"
        assert params["types"] == "050000"
        return {
            "status": "1",
            "pois": {
                "poi": [
                    {
                        "id": "R_LOW",
                        "name": "近处普通餐厅",
                        "location": "100.160,25.690",
                        "address": "近处",
                        "distance": "80",
                        "business": {"rating": "4.1", "cost": "50", "tag": "本地菜"},
                    },
                    {
                        "id": "R_HIGH",
                        "name": "评分更高餐厅",
                        "location": "100.162,25.691",
                        "address": "稍远",
                        "distance": "220",
                        "business": {"rating": "4.8", "cost": "88", "tag": "白族菜;菌菇"},
                    },
                ]
            },
        }

    monkeypatch.setattr(map_service, "_request_amap_versioned", fake_request)

    places = map_service.search_nearby_places(
        longitude=100.161,
        latitude=25.694,
        poi_types="050000",
        page_size=2,
    )

    assert [place["poi_id"] for place in places] == ["R_HIGH", "R_LOW"]
    assert places[0]["map_rating"] == 4.8
    assert places[0]["map_average_cost"] == 88.0
    assert places[0]["map_tags"] == ["白族菜", "菌菇"]


def test_enrich_itinerary_adds_nearby_hotel_and_restaurant(monkeypatch) -> None:
    """测试行程增强会把景点附近住宿和餐饮 POI 写入结构化结果。"""
    monkeypatch.setattr(
        map_service,
        "search_places",
        lambda keyword, city=None, page_size=1: [
            {
                "name": "大理古城",
                "address": "一塔路",
                "poi_id": "SPOT_1",
                "image_url": "https://example.test/spot.jpg",
                "latitude": 25.694,
                "longitude": 100.161,
                "map_rating": 4.7,
                "map_average_cost": 0.0,
                "map_tags": ["古城"],
                "map_tel": None,
                "map_distance_meters": None,
            }
        ],
    )
    monkeypatch.setattr(
        map_service,
        "recommend_nearby_hotels",
        lambda longitude, latitude, radius=3000, page_size=10: [
            {
                "name": "古城旁精品酒店",
                "address": "人民路 1 号",
                "poi_id": "HOTEL_1",
                "image_url": "https://example.test/hotel.jpg",
                "latitude": 25.695,
                "longitude": 100.162,
                "business_area": "大理古城",
                "map_rating": 4.6,
                "map_average_cost": 388.0,
                "map_tags": ["客栈", "近景点"],
                "map_tel": "0872-1111111",
                "map_distance_meters": 180.0,
            }
        ],
    )
    monkeypatch.setattr(
        map_service,
        "recommend_nearby_restaurants",
        lambda longitude, latitude, radius=2000, page_size=10: [
            {
                "name": "本地白族菜馆",
                "address": "复兴路 2 号",
                "poi_id": "MEAL_1",
                "image_url": "https://example.test/meal.jpg",
                "latitude": 25.696,
                "longitude": 100.163,
                "map_rating": 4.8,
                "map_average_cost": 76.0,
                "map_tags": ["白族菜", "菌菇"],
                "map_tel": "0872-2222222",
                "map_distance_meters": 220.0,
            }
        ],
    )

    itinerary = Itinerary(
        trip_id="trip_test",
        destination="大理",
        summary="测试行程",
        days=[
            DayPlan(
                day_index=1,
                spots=[SpotItem(name="大理古城")],
                meals=[MealItem(name="午餐推荐", meal_type="午餐", notes="少辣")],
                hotel=HotelItem(name="大理 舒适型住宿 1", level="舒适型"),
            )
        ],
        budget_breakdown=BudgetBreakdown(),
    )

    enriched = map_service.enrich_itinerary_with_map_data(itinerary, city="大理")

    day = enriched.days[0]
    assert day.spots[0].poi_id == "SPOT_1"
    assert day.spots[0].map_rating == 4.7
    assert day.hotel is not None
    assert day.hotel.name == "古城旁精品酒店"
    assert day.hotel.map_average_cost == 388.0
    assert day.meals[0].name == "本地白族菜馆"
    assert day.meals[0].map_rating == 4.8
    assert "参考人均 ¥76" in (day.meals[0].notes or "")
    assert any("附近餐饮住宿" in note for note in enriched.source_notes)
