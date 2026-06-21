from __future__ import annotations

from datetime import date as DateType, datetime

from pydantic import BaseModel, Field


class TripRequest(BaseModel):
    """用于生成新行程的请求体。"""

    destination: str = Field(..., description="目的地，例如大理")
    start_date: DateType = Field(..., description="出行开始日期")
    end_date: DateType = Field(..., description="出行结束日期")
    travelers: int = Field(..., ge=1, description="出行人数")
    budget: float = Field(..., ge=0, description="总预算")
    preferences: list[str] = Field(default_factory=list, description="旅行偏好标签")
    pace: str | None = Field(default=None, description="旅行节奏，例如轻松、适中、紧凑")
    dietary_preferences: list[str] = Field(
        default_factory=list,
        description="饮食偏好或忌口",
    )
    hotel_level: str | None = Field(default=None, description="酒店档次偏好")
    special_notes: str | None = Field(default=None, description="额外要求")


class TripEditRequest(BaseModel):
    """用于修改已有行程的请求体。"""

    trip_id: str = Field(..., description="需要编辑的行程 ID")
    current_itinerary: "Itinerary" = Field(..., description="当前完整 itinerary")
    user_instruction: str = Field(..., description="用户新的修改要求")
    edit_scope: str | None = Field(default=None, description="编辑范围")
    preserve_constraints: list[str] = Field(
        default_factory=list,
        description="需要尽量保留的条件",
    )


class TripSaveRequest(BaseModel):
    """用于保存当前 itinerary 的请求体。"""

    trip_id: str = Field(..., description="需要保存的行程 ID")
    itinerary: "Itinerary" = Field(..., description="完整行程数据")
    user_id: str | None = Field(default=None, description="用户 ID，当前版本可留空")


class SpotItem(BaseModel):
    """单个景点安排。"""

    name: str = Field(..., description="景点名称")
    start_time: str | None = Field(default=None, description="开始时间")
    end_time: str | None = Field(default=None, description="结束时间")
    description: str | None = Field(default=None, description="景点安排说明")
    estimated_cost: float | None = Field(default=None, ge=0, description="门票花费；未知时为 None")
    location: str | None = Field(default=None, description="景点位置描述")
    image_url: str | None = Field(default=None, description="景点图片地址")
    address: str | None = Field(default=None, description="景点详细地址")
    latitude: float | None = Field(default=None, description="景点纬度")
    longitude: float | None = Field(default=None, description="景点经度")
    poi_id: str | None = Field(default=None, description="地图服务返回的 POI 标识")
    map_rating: float | None = Field(default=None, ge=0, description="地图服务评分")
    map_average_cost: float | None = Field(default=None, ge=0, description="地图服务参考人均或均价")
    map_tags: list[str] = Field(default_factory=list, description="地图服务标签")
    map_tel: str | None = Field(default=None, description="地图服务电话")
    map_distance_meters: float | None = Field(default=None, ge=0, description="地图服务返回的距离")
    map_type: str | None = Field(default=None, description="地图服务 POI 类型")
    map_typecode: str | None = Field(default=None, description="地图服务 POI 类型编码")
    map_business_area: str | None = Field(default=None, description="地图服务商圈")
    map_open_time_today: str | None = Field(default=None, description="地图服务今日营业时间")
    map_open_time_week: str | None = Field(default=None, description="地图服务每周营业时间")


class MealItem(BaseModel):
    """单个餐饮安排。"""

    name: str = Field(..., description="餐厅或餐饮建议名称")
    meal_type: str = Field(..., description="早餐、午餐、晚餐等")
    estimated_cost: float = Field(default=0.0, ge=0, description="预估花费")
    notes: str | None = Field(default=None, description="补充说明")
    image_url: str | None = Field(default=None, description="餐厅图片地址")
    address: str | None = Field(default=None, description="餐厅详细地址")
    latitude: float | None = Field(default=None, description="餐厅纬度")
    longitude: float | None = Field(default=None, description="餐厅经度")
    poi_id: str | None = Field(default=None, description="地图服务返回的 POI 标识")
    map_rating: float | None = Field(default=None, ge=0, description="地图服务评分")
    map_average_cost: float | None = Field(default=None, ge=0, description="地图服务参考人均消费")
    map_tags: list[str] = Field(default_factory=list, description="地图服务标签")
    map_tel: str | None = Field(default=None, description="地图服务电话")
    map_distance_meters: float | None = Field(default=None, ge=0, description="距离参考点的米数")
    map_type: str | None = Field(default=None, description="地图服务 POI 类型")
    map_typecode: str | None = Field(default=None, description="地图服务 POI 类型编码")
    map_business_area: str | None = Field(default=None, description="地图服务商圈")
    map_open_time_today: str | None = Field(default=None, description="地图服务今日营业时间")
    map_open_time_week: str | None = Field(default=None, description="地图服务每周营业时间")
    data_source: str | None = Field(default=None, description="推荐数据来源，例如 amap/meituan/dianping")
    source_id: str | None = Field(default=None, description="第三方平台返回的商户或 POI ID")
    source_url: str | None = Field(default=None, description="第三方平台详情、预订或团购链接")
    review_count: int | None = Field(default=None, ge=0, description="第三方平台评价数量")
    ranking_label: str | None = Field(default=None, description="第三方平台榜单或排名标签")
    recommendation_score: float | None = Field(default=None, ge=0, description="综合推荐分")
    recommendation_reason: str | None = Field(default=None, description="综合推荐理由")
    is_recommended: bool = Field(default=True, description="是否为最终推荐项")


class HotelItem(BaseModel):
    """单个住宿安排。"""

    name: str = Field(..., description="酒店名称")
    level: str | None = Field(default=None, description="酒店档次")
    estimated_cost: float = Field(default=0.0, ge=0, description="预估花费")
    location: str | None = Field(default=None, description="酒店位置")
    address: str | None = Field(default=None, description="酒店详细地址")
    latitude: float | None = Field(default=None, description="酒店纬度")
    longitude: float | None = Field(default=None, description="酒店经度")
    image_url: str | None = Field(default=None, description="酒店图片地址")
    poi_id: str | None = Field(default=None, description="地图服务返回的 POI 标识")
    map_rating: float | None = Field(default=None, ge=0, description="地图服务评分")
    map_average_cost: float | None = Field(default=None, ge=0, description="地图服务参考均价")
    map_tags: list[str] = Field(default_factory=list, description="地图服务标签")
    map_tel: str | None = Field(default=None, description="地图服务电话")
    map_distance_meters: float | None = Field(default=None, ge=0, description="距离参考点的米数")
    map_type: str | None = Field(default=None, description="地图服务 POI 类型")
    map_typecode: str | None = Field(default=None, description="地图服务 POI 类型编码")
    map_business_area: str | None = Field(default=None, description="地图服务商圈")
    map_open_time_today: str | None = Field(default=None, description="地图服务今日营业时间")
    map_open_time_week: str | None = Field(default=None, description="地图服务每周营业时间")
    data_source: str | None = Field(default=None, description="推荐数据来源，例如 amap/meituan/dianping")
    source_id: str | None = Field(default=None, description="第三方平台返回的酒店或 POI ID")
    source_url: str | None = Field(default=None, description="第三方平台详情、预订或团购链接")
    review_count: int | None = Field(default=None, ge=0, description="第三方平台评价数量")
    ranking_label: str | None = Field(default=None, description="第三方平台榜单或排名标签")
    recommendation_score: float | None = Field(default=None, ge=0, description="综合推荐分")
    recommendation_reason: str | None = Field(default=None, description="综合推荐理由")
    is_recommended: bool = Field(default=True, description="是否为最终推荐项")


class TransportItem(BaseModel):
    """单段交通安排。"""

    mode: str = Field(..., description="交通方式，例如步行、打车、公交")
    from_place: str | None = Field(default=None, description="出发地")
    to_place: str | None = Field(default=None, description="目的地")
    estimated_cost: float = Field(default=0.0, ge=0, description="预估花费")
    duration: str | None = Field(default=None, description="预计耗时")
    distance_km: float | None = Field(default=None, ge=0, description="预计距离，单位公里")
    estimated_minutes: int | None = Field(default=None, ge=0, description="预计耗时，单位分钟")


class BudgetBreakdown(BaseModel):
    """预算拆分。"""

    transport: float = Field(default=0.0, ge=0, description="交通预算")
    hotel: float = Field(default=0.0, ge=0, description="住宿预算")
    meals: float = Field(default=0.0, ge=0, description="餐饮预算")
    tickets: float = Field(default=0.0, ge=0, description="门票预算")
    other: float = Field(default=0.0, ge=0, description="其他预算")
    total: float = Field(default=0.0, ge=0, description="预算总计")


class DayPlan(BaseModel):
    """单日行程安排。"""

    day_index: int = Field(..., ge=1, description="第几天")
    date: DateType | None = Field(default=None, description="当天日期")
    theme: str | None = Field(default=None, description="当天主题")
    spots: list[SpotItem] = Field(default_factory=list, description="景点安排")
    meals: list[MealItem] = Field(default_factory=list, description="餐饮安排")
    hotel: HotelItem | None = Field(default=None, description="住宿安排")
    hotel_candidates: list[HotelItem] = Field(default_factory=list, description="住宿候选项")
    meal_candidates: list[MealItem] = Field(default_factory=list, description="餐饮候选项")
    transport: list[TransportItem] = Field(default_factory=list, description="交通安排")
    notes: list[str] = Field(default_factory=list, description="补充说明")


class Itinerary(BaseModel):
    """完整行程。"""

    trip_id: str = Field(..., description="行程唯一标识")
    destination: str = Field(..., description="目的地")
    summary: str = Field(..., description="整趟行程的概述")
    days: list[DayPlan] = Field(default_factory=list, description="逐日行程")
    estimated_budget: float = Field(default=0.0, ge=0, description="预算总计")
    budget_breakdown: BudgetBreakdown = Field(..., description="预算明细")
    tips: list[str] = Field(default_factory=list, description="旅行建议")
    source_notes: list[str] = Field(
        default_factory=list,
        description="RAG 或规则生成产生的补充说明",
    )


class TripDetailResponse(BaseModel):
    """查询已保存行程时返回的响应体。"""

    trip_id: str = Field(..., description="行程 ID")
    itinerary: Itinerary = Field(..., description="已保存的完整行程")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


class TripSummaryItem(BaseModel):
    """已保存行程的摘要信息。"""

    trip_id: str = Field(..., description="行程 ID")
    destination: str = Field(..., description="目的地")
    summary: str = Field(..., description="行程概述")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


class TripListResponse(BaseModel):
    """行程列表接口的响应结构。"""

    total: int = Field(..., ge=0, description="列表总数")
    items: list[TripSummaryItem] = Field(default_factory=list, description="行程摘要列表")
