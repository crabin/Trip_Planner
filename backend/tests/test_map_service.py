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


def test_search_places_normalizes_amap_business_fields(monkeypatch) -> None:
    """测试关键字 POI 搜索会保留高德公开 business 字段。"""
    _disable_cache(monkeypatch)

    monkeypatch.setattr(
        map_service,
        "_request_amap_versioned",
        lambda path, params, api_version="v3": {
            "status": "1",
            "pois": {
                "poi": [
                    {
                        "id": "B001",
                        "name": "大理古城",
                        "address": "一塔路",
                        "location": "100.161,25.694",
                        "type": "风景名胜;风景名胜;旅游景点",
                        "typecode": "110000",
                        "business": {
                            "business_area": "古城",
                            "rating": "4.7",
                            "cost": "0",
                            "tag": "古城;拍照",
                            "tel": "0872-0000000",
                            "opentime_today": "全天开放",
                            "opentime_week": "周一至周日 全天开放",
                        },
                        "photos": [{"url": "https://example.test/dali.jpg"}],
                    }
                ]
            },
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
            "typecode": "110000",
            "poi_id": "B001",
            "image_url": "https://example.test/dali.jpg",
            "latitude": 25.694,
            "longitude": 100.161,
            "business_area": "古城",
            "map_rating": 4.7,
            "map_average_cost": 0.0,
            "map_tags": ["古城", "拍照"],
            "map_tel": "0872-0000000",
            "map_distance_meters": None,
            "map_type": "风景名胜;风景名胜;旅游景点",
            "map_typecode": "110000",
            "map_business_area": "古城",
            "map_open_time_today": "全天开放",
            "map_open_time_week": "周一至周日 全天开放",
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
                        "type": "餐饮服务;中餐厅;中餐厅",
                        "business": {
                            "rating": "4.1",
                            "cost": "50",
                            "tag": "本地菜",
                            "business_area": "古城",
                            "opentime_today": "10:00-21:00",
                        },
                    },
                    {
                        "id": "R_HIGH",
                        "name": "评分更高餐厅",
                        "location": "100.162,25.691",
                        "address": "稍远",
                        "distance": "220",
                        "type": "餐饮服务;中餐厅;特色餐厅",
                        "business": {
                            "rating": "4.8",
                            "cost": "88",
                            "tag": "白族菜;菌菇",
                            "business_area": "人民路",
                            "opentime_today": "11:00-22:00",
                        },
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
    assert places[0]["map_business_area"] == "人民路"
    assert places[0]["map_open_time_today"] == "11:00-22:00"
    assert places[0]["map_type"] == "餐饮服务;中餐厅;特色餐厅"


def test_pick_best_place_uses_detail_to_fill_missing_public_fields(monkeypatch) -> None:
    """测试 POI 详情可补齐搜索结果缺失的营业时间等公开字段。"""
    calls: list[str] = []

    monkeypatch.setattr(
        map_service,
        "search_places",
        lambda keyword, city=None, page_size=1: [
            {
                "name": "大理古城",
                "address": "一塔路",
                "poi_id": "B001",
                "image_url": None,
                "latitude": 25.694,
                "longitude": 100.161,
                "map_rating": None,
                "map_average_cost": None,
                "map_tags": [],
                "map_tel": None,
                "map_distance_meters": None,
                "map_type": "风景名胜;风景名胜;旅游景点",
                "map_typecode": "110000",
                "map_business_area": None,
                "map_open_time_today": None,
                "map_open_time_week": None,
            }
        ],
    )

    def fake_detail(poi_id):
        calls.append(poi_id)
        return {
            "poi_id": poi_id,
            "image_url": "https://example.test/detail.jpg",
            "map_rating": 4.9,
            "map_average_cost": 0.0,
            "map_business_area": "古城",
            "map_open_time_today": "全天开放",
            "map_open_time_week": "周一至周日 全天开放",
        }

    monkeypatch.setattr(map_service, "get_place_detail", fake_detail)

    place = map_service._pick_best_place("大理古城", city="大理")

    assert calls == ["B001"]
    assert place is not None
    assert place["image_url"] == "https://example.test/detail.jpg"
    assert place["map_rating"] == 4.9
    assert place["map_business_area"] == "古城"
    assert place["map_open_time_today"] == "全天开放"


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
                "map_type": "风景名胜;风景名胜;旅游景点",
                "map_typecode": "110000",
                "map_business_area": "古城",
                "map_open_time_today": "全天开放",
                "map_open_time_week": "周一至周日 全天开放",
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
                "map_type": "住宿服务;宾馆酒店;宾馆酒店",
                "map_typecode": "100000",
                "map_business_area": "大理古城",
                "map_open_time_today": "全天营业",
                "map_open_time_week": "周一至周日 全天营业",
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
                "map_type": "餐饮服务;中餐厅;特色餐厅",
                "map_typecode": "050100",
                "map_business_area": "复兴路",
                "map_open_time_today": "11:00-22:00",
                "map_open_time_week": "周一至周日 11:00-22:00",
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
    assert day.spots[0].map_open_time_today == "全天开放"
    assert day.hotel is not None
    assert day.hotel.name == "古城旁精品酒店"
    assert day.hotel.map_average_cost == 388.0
    assert day.hotel.map_business_area == "大理古城"
    assert day.meals[0].name == "本地白族菜馆"
    assert day.meals[0].map_rating == 4.8
    assert day.meals[0].map_open_time_today == "11:00-22:00"
    assert "参考人均 ¥76" in (day.meals[0].notes or "")
    assert "今日营业：11:00-22:00" in (day.meals[0].notes or "")
    assert any("附近餐饮住宿" in note for note in enriched.source_notes)


def test_enrich_itinerary_uses_external_recommendation_but_keeps_candidates(
    monkeypatch,
) -> None:
    """测试外部美团/点评候选可参与推荐，未选中的候选仍保留给地图。"""
    monkeypatch.setattr(
        map_service,
        "search_places",
        lambda keyword, city=None, page_size=1: [
            {
                "name": "大理古城",
                "address": "一塔路",
                "poi_id": "SPOT_1",
                "latitude": 25.694,
                "longitude": 100.161,
                "map_rating": 4.7,
                "map_average_cost": 0.0,
                "map_tags": ["古城"],
            }
        ],
    )
    monkeypatch.setattr(
        map_service,
        "recommend_nearby_hotels",
        lambda longitude, latitude, radius=3000, page_size=10: [
            {
                "data_source": "amap",
                "name": "高德普通酒店",
                "address": "古城边",
                "poi_id": "A_HOTEL",
                "latitude": 25.695,
                "longitude": 100.162,
                "map_rating": 4.2,
                "map_average_cost": 320.0,
                "map_distance_meters": 160.0,
            }
        ],
    )
    monkeypatch.setattr(
        map_service,
        "recommend_nearby_restaurants",
        lambda longitude, latitude, radius=2000, page_size=10: [
            {
                "data_source": "amap",
                "name": "高德普通餐厅",
                "address": "古城口",
                "poi_id": "A_MEAL",
                "latitude": 25.696,
                "longitude": 100.163,
                "map_rating": 4.1,
                "map_average_cost": 60.0,
                "map_distance_meters": 120.0,
            }
        ],
    )
    monkeypatch.setattr(
        map_service,
        "fetch_local_life_candidates",
        lambda longitude, latitude, category, radius, page_size=10: [
            {
                "data_source": "dianping",
                "source_id": f"DP_{category}",
                "name": "点评精选酒店" if category == "hotel" else "点评精选白族菜",
                "address": "人民路 9 号",
                "latitude": 25.697,
                "longitude": 100.164,
                "map_rating": 4.9,
                "map_average_cost": 420.0 if category == "hotel" else 88.0,
                "map_distance_meters": 260.0,
                "review_count": 900,
                "ranking_label": "本地热门",
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
                meals=[MealItem(name="午餐推荐", meal_type="午餐")],
                hotel=HotelItem(name="大理 舒适型住宿 1", level="舒适型"),
            )
        ],
        budget_breakdown=BudgetBreakdown(),
    )

    enriched = map_service.enrich_itinerary_with_map_data(itinerary, city="大理")
    day = enriched.days[0]

    assert day.hotel is not None
    assert day.hotel.name == "点评精选酒店"
    assert day.hotel.data_source == "dianping"
    assert day.hotel.is_recommended is True
    assert len(day.hotel_candidates) == 2
    assert day.hotel_candidates[0].is_recommended is True
    assert day.hotel_candidates[1].is_recommended is False
    assert day.meals[0].name == "点评精选白族菜"
    assert day.meals[0].data_source == "dianping"
    assert len(day.meal_candidates) == 2
    assert day.meal_candidates[1].is_recommended is False


def test_enrich_itinerary_rejects_cross_city_and_wrong_category_candidates(
    monkeypatch,
) -> None:
    """测试附近推荐不会用跨城或错误类型 POI 污染结果页主卡片。"""
    monkeypatch.setattr(
        map_service,
        "search_places",
        lambda keyword, city=None, page_size=1: [
            {
                "name": "白马寺",
                "address": "洛阳市洛龙区",
                "poi_id": "SPOT_1",
                "latitude": 34.722,
                "longitude": 112.605,
                "cityname": "洛阳市",
                "map_rating": 4.7,
                "map_average_cost": 0.0,
                "map_tags": ["寺庙"],
                "map_type": "风景名胜;风景名胜;旅游景点",
                "map_typecode": "110000",
            }
        ],
    )
    monkeypatch.setattr(
        map_service,
        "recommend_nearby_hotels",
        lambda longitude, latitude, radius=3000, page_size=10: [
            {
                "name": "广州万富希尔顿酒店",
                "address": "广州市白云区",
                "cityname": "广州市",
                "latitude": 23.184,
                "longitude": 113.265,
                "map_rating": 4.8,
                "map_average_cost": 600.0,
                "map_distance_meters": 1_500_000.0,
                "map_type": "住宿服务;宾馆酒店;宾馆酒店",
                "map_typecode": "100000",
            },
            {
                "name": "洛阳本地酒店",
                "address": "洛阳市洛龙区",
                "cityname": "洛阳市",
                "latitude": 34.723,
                "longitude": 112.606,
                "map_rating": 4.5,
                "map_average_cost": 300.0,
                "map_distance_meters": 300.0,
                "map_type": "住宿服务;宾馆酒店;宾馆酒店",
                "map_typecode": "100000",
            },
        ],
    )
    monkeypatch.setattr(
        map_service,
        "recommend_nearby_restaurants",
        lambda longitude, latitude, radius=2000, page_size=10: [
            {
                "name": "白马寺",
                "address": "洛阳市洛龙区",
                "cityname": "洛阳市",
                "latitude": 34.722,
                "longitude": 112.605,
                "map_rating": 4.7,
                "map_average_cost": 0.0,
                "map_distance_meters": 0.0,
                "map_type": "风景名胜;风景名胜;旅游景点",
                "map_typecode": "110000",
            },
            {
                "name": "洛阳本地餐厅",
                "address": "洛阳市洛龙区",
                "cityname": "洛阳市",
                "latitude": 34.724,
                "longitude": 112.607,
                "map_rating": 4.4,
                "map_average_cost": 50.0,
                "map_distance_meters": 350.0,
                "map_type": "餐饮服务;中餐厅;中餐厅",
                "map_typecode": "050100",
            },
        ],
    )
    monkeypatch.setattr(map_service, "fetch_local_life_candidates", lambda **kwargs: [])

    itinerary = Itinerary(
        trip_id="trip_test",
        destination="洛阳",
        summary="测试行程",
        days=[
            DayPlan(
                day_index=1,
                spots=[SpotItem(name="白马寺")],
                meals=[MealItem(name="午餐推荐", meal_type="午餐")],
                hotel=HotelItem(name="市区酒店", level="舒适型"),
            )
        ],
        budget_breakdown=BudgetBreakdown(),
    )

    enriched = map_service.enrich_itinerary_with_map_data(itinerary, city="洛阳")
    day = enriched.days[0]

    assert day.hotel is not None
    assert day.hotel.name == "洛阳本地酒店"
    assert all(candidate.name != "广州万富希尔顿酒店" for candidate in day.hotel_candidates)
    assert day.meals[0].name == "洛阳本地餐厅"
    assert all(candidate.name != "白马寺" for candidate in day.meal_candidates)


def test_enrich_itinerary_keeps_explicit_report_names_as_primary_cards(
    monkeypatch,
) -> None:
    """测试 Report 明确给出的餐厅和酒店名称不会被附近推荐覆盖。"""
    monkeypatch.setattr(
        map_service,
        "search_places",
        lambda keyword, city=None, page_size=1: [
            {
                "name": keyword,
                "address": "洛阳市老城区",
                "poi_id": f"POI_{keyword}",
                "latitude": 34.683,
                "longitude": 112.477,
                "cityname": "洛阳市",
                "map_rating": 4.6,
                "map_average_cost": 80.0,
                "map_type": "餐饮服务;中餐厅;中餐厅" if "餐厅" in keyword else "住宿服务;宾馆酒店;宾馆酒店",
                "map_typecode": "050100" if "餐厅" in keyword else "100000",
            }
        ],
    )
    monkeypatch.setattr(
        map_service,
        "recommend_nearby_hotels",
        lambda longitude, latitude, radius=3000, page_size=10: [
            {
                "name": "附近推荐酒店",
                "address": "洛阳市老城区",
                "cityname": "洛阳市",
                "latitude": 34.684,
                "longitude": 112.478,
                "map_rating": 4.9,
                "map_average_cost": 500.0,
                "map_distance_meters": 200.0,
                "map_type": "住宿服务;宾馆酒店;宾馆酒店",
                "map_typecode": "100000",
            }
        ],
    )
    monkeypatch.setattr(
        map_service,
        "recommend_nearby_restaurants",
        lambda longitude, latitude, radius=2000, page_size=10: [
            {
                "name": "附近推荐餐厅",
                "address": "洛阳市老城区",
                "cityname": "洛阳市",
                "latitude": 34.684,
                "longitude": 112.478,
                "map_rating": 4.9,
                "map_average_cost": 90.0,
                "map_distance_meters": 200.0,
                "map_type": "餐饮服务;中餐厅;中餐厅",
                "map_typecode": "050100",
            }
        ],
    )
    monkeypatch.setattr(map_service, "fetch_local_life_candidates", lambda **kwargs: [])

    itinerary = Itinerary(
        trip_id="trip_test",
        destination="洛阳",
        summary="测试行程",
        days=[
            DayPlan(
                day_index=1,
                spots=[SpotItem(name="应天门")],
                meals=[MealItem(name="老洛阳餐厅", meal_type="晚餐", map_query="老洛阳餐厅")],
                hotel=HotelItem(name="拾一庭民宿", level="舒适型", map_query="拾一庭民宿"),
            )
        ],
        budget_breakdown=BudgetBreakdown(),
    )

    enriched = map_service.enrich_itinerary_with_map_data(itinerary, city="洛阳")
    day = enriched.days[0]

    assert day.hotel is not None
    assert day.hotel.name == "拾一庭民宿"
    assert day.hotel.poi_id == "POI_拾一庭民宿"
    assert day.meals[0].name == "老洛阳餐厅"
    assert day.meals[0].poi_id == "POI_老洛阳餐厅"
