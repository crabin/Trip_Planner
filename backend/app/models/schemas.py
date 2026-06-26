from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    deep_planning_reflection_rounds: int = Field(
        default=2,
        ge=0,
        le=5,
        description="深度规划反思轮次，仅深度规划使用",
    )
    deep_planning_search_engine: Literal["tavily", "searxng"] = Field(
        default="tavily",
        description="深度规划优先搜索引擎；失败重试后会自动兜底另一个服务",
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> "TripRequest":
        """拒绝结束日期早于开始日期的无效请求。"""
        if self.end_date < self.start_date:
            raise ValueError("end_date must be greater than or equal to start_date")
        return self


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
    map_query: str | None = Field(default=None, description="地图服务检索关键词")


class MealItem(BaseModel):
    """单个餐饮安排。"""

    name: str = Field(..., description="餐厅或餐饮建议名称")
    meal_type: str = Field(..., description="早餐、午餐、晚餐等")
    estimated_cost: float | None = Field(default=None, ge=0, description="预估花费；未知时为 None")
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
    map_query: str | None = Field(default=None, description="地图服务检索关键词")
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
    estimated_cost: float | None = Field(default=None, ge=0, description="预估花费；未知时为 None")
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
    map_query: str | None = Field(default=None, description="地图服务检索关键词")
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
    estimated_cost: float | None = Field(default=None, ge=0, description="预估花费；未知时为 None")
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


class DisplayTextItem(BaseModel):
    """结果页中可独立编辑的一条标签文本。"""

    key: str = Field(..., description="稳定字段标识，便于聊天机器人定点修改")
    label: str = Field(..., description="展示标签")
    value: str = Field(default="", description="展示文本")
    source_path: str | None = Field(default=None, description="对应原始 itinerary 字段路径")


class DisplayChecklistItem(BaseModel):
    """结果页中可勾选的检查项。"""

    key: str = Field(..., description="稳定检查项标识")
    text: str = Field(..., description="检查项文本")
    checked: bool = Field(default=False, description="是否已勾选")
    source_path: str | None = Field(default=None, description="对应原始 itinerary 字段路径")


class DisplayBudgetItem(BaseModel):
    """结果页中的预算展示项。"""

    key: str = Field(..., description="预算项标识")
    label: str = Field(..., description="展示标签")
    amount: float = Field(default=0.0, ge=0, description="预算金额")
    formatted: str = Field(default="", description="已格式化文本")
    source_path: str | None = Field(default=None, description="对应原始 itinerary 字段路径")


class DisplayMapPoint(BaseModel):
    """地图和点位卡片共享的结构化展示点。"""

    key: str = Field(..., description="前端渲染用稳定 key")
    kind: Literal["spot", "meal", "hotel"] = Field(..., description="点位类型")
    label: str = Field(..., description="点位标签")
    day_index: int = Field(..., ge=1, description="所属天数")
    date: str | None = Field(default=None, description="所属日期")
    theme: str = Field(default="", description="当天主题")
    name: str = Field(..., description="点位名称")
    address: str = Field(default="", description="展示地址")
    latitude: float | None = Field(default=None, description="纬度")
    longitude: float | None = Field(default=None, description="经度")
    poi_id: str | None = Field(default=None, description="地图 POI ID")
    image_url: str | None = Field(default=None, description="图片地址")
    description: str = Field(default="", description="点位说明")
    rating: float | None = Field(default=None, ge=0, description="地图评分")
    average_cost: float | None = Field(default=None, ge=0, description="地图参考消费")
    estimated_cost: float | None = Field(default=None, ge=0, description="行程预估消费")
    tags: list[str] = Field(default_factory=list, description="地图标签")
    distance_meters: float | None = Field(default=None, ge=0, description="距离")
    tel: str | None = Field(default=None, description="联系电话")
    business_area: str | None = Field(default=None, description="商圈")
    open_time_today: str | None = Field(default=None, description="今日营业时间")
    map_type: str | None = Field(default=None, description="地图 POI 类型")
    recommended: bool = Field(default=False, description="是否最终推荐")
    source_path: str | None = Field(default=None, description="对应原始 itinerary 字段路径")


class DisplayRecommendationItem(BaseModel):
    """餐饮/住宿推荐展示卡片。"""

    key: str = Field(..., description="稳定 key")
    kind: Literal["meal", "hotel"] = Field(..., description="推荐类型")
    day_index: int = Field(..., ge=1, description="所属天数")
    date: str | None = Field(default=None, description="所属日期")
    theme: str = Field(default="", description="当天主题")
    title: str = Field(..., description="卡片标题")
    subtitle: str = Field(default="", description="卡片副标题")
    reason: str = Field(default="", description="推荐理由")
    image_url: str | None = Field(default=None, description="图片地址")
    meta: list[str] = Field(default_factory=list, description="评分、价格、来源等元信息")
    tags: list[str] = Field(default_factory=list, description="榜单或地图标签")
    contact: str = Field(default="", description="电话和地址")
    note: str = Field(default="", description="补充说明")
    source_path: str | None = Field(default=None, description="对应原始 itinerary 字段路径")


class DisplayDayCard(BaseModel):
    """每日行程折叠卡片的结构化展示数据。"""

    key: str = Field(..., description="稳定 key")
    day_index: int = Field(..., ge=1, description="第几天")
    title: str = Field(..., description="标题")
    subtitle: str = Field(default="", description="副标题")
    date: str | None = Field(default=None, description="日期")
    theme: str = Field(default="", description="主题")
    fields: list[DisplayTextItem] = Field(default_factory=list, description="卡片字段")
    notes: list[str] = Field(default_factory=list, description="备注")
    source_path: str | None = Field(default=None, description="对应原始 itinerary 字段路径")


class DisplaySection(BaseModel):
    """结果页可独立重排、隐藏或替换内容的展示区块。"""

    key: str = Field(..., description="稳定区块标识")
    title: str = Field(..., description="区块标题")
    kind: Literal[
        "overview",
        "budget",
        "day_budget",
        "tips",
        "map",
        "weather",
        "recommendations",
        "poi_details",
        "daily_plan",
        "editor",
    ] = Field(..., description="区块类型")
    order: int = Field(..., ge=0, description="默认排序")
    visible: bool = Field(default=True, description="是否默认展示")
    summary: str = Field(default="", description="区块摘要")
    item_keys: list[str] = Field(default_factory=list, description="区块引用的展示项 key")


class ItineraryDisplay(BaseModel):
    """前端结果页的结构化展示 JSON。"""

    version: str = Field(default="itinerary-display-v1", description="展示结构版本")
    title: str = Field(default="", description="结果页主标题")
    subtitle: str = Field(default="", description="结果页副标题")
    overview: list[DisplayTextItem] = Field(default_factory=list, description="概览字段")
    plan_highlights: list[DisplayTextItem] = Field(default_factory=list, description="规划要点")
    confirmations: list[DisplayTextItem] = Field(default_factory=list, description="待确认事项")
    tips: list[str] = Field(default_factory=list, description="清洗后的旅行提示")
    tip_items: list[DisplayChecklistItem] = Field(default_factory=list, description="可勾选旅行提示")
    budget_items: list[DisplayBudgetItem] = Field(default_factory=list, description="总预算展示")
    day_budget_items: list[DisplayBudgetItem] = Field(default_factory=list, description="按天预算展示")
    map_points: list[DisplayMapPoint] = Field(default_factory=list, description="地图点位")
    scenic_points: list[DisplayMapPoint] = Field(default_factory=list, description="景点点位")
    hotel_recommendations: list[DisplayRecommendationItem] = Field(default_factory=list, description="住宿推荐")
    meal_recommendations: list[DisplayRecommendationItem] = Field(default_factory=list, description="餐饮推荐")
    day_cards: list[DisplayDayCard] = Field(default_factory=list, description="每日行程卡片")
    sections: list[DisplaySection] = Field(default_factory=list, description="页面区块配置")


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


class ItineraryOverviewFact(BaseModel):
    """LLM 从 Report 直接抽取的概览字段。"""

    key: str = Field(..., description="稳定字段 key")
    label: str = Field(..., description="结果页展示标签")
    value: str = Field(..., description="字段值")
    source_chunk_ids: list[str] = Field(default_factory=list, description="来源小结 ID")


class ItineraryConversionMeta(BaseModel):
    """Report 转换版本与完整性元数据。"""

    kind: Literal["report_itinerary", "deep_itinerary"]
    version: str
    source_id: str
    source_sha256: str
    model: str = ""
    chunk_count: int = Field(..., ge=1)
    completed_chunk_count: int = Field(..., ge=0)
    quality_passed: bool = False


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
    overview_facts: list[ItineraryOverviewFact] = Field(
        default_factory=list,
        description="Report 转换直接提取的结构化概览字段",
    )
    conversion_meta: ItineraryConversionMeta | None = Field(
        default=None,
        description="Report/Deep Report 转换元数据",
    )
    display: ItineraryDisplay | None = Field(
        default=None,
        description="结果页结构化展示 JSON，供前端和聊天优化器消费",
    )


class DeepPlanSource(BaseModel):
    """深度规划研究阶段保留的一条网页来源。"""

    section_title: str = Field(default="", description="来源所属研究章节")
    query: str = Field(default="", description="产生该来源的搜索查询")
    title: str = Field(default="", description="来源标题")
    url: str = Field(default="", description="来源链接")
    content: str = Field(default="", description="来源摘要内容")
    score: float | None = Field(default=None, description="搜索相关度")
    published_date: str | None = Field(default=None, description="来源发布日期")


class DeepPlanDocument(BaseModel):
    """可直接供 Web 深度规划详情页消费的 JSON 文档。"""

    markdown: str = Field(..., description="完整旅行攻略 Markdown")
    sources: list[DeepPlanSource] = Field(default_factory=list, description="结构化研究来源")


class TripDetailResponse(BaseModel):
    """查询已保存行程时返回的响应体。"""

    trip_id: str = Field(..., description="行程 ID")
    plan_type: Literal["quick", "deep"] = Field(default="quick", description="规划类型")
    status: Literal["generating", "completed", "failed"] = Field(
        default="completed",
        description="生成状态",
    )
    progress: int = Field(default=100, ge=0, le=100, description="生成进度")
    display_title: str = Field(default="", description="历史卡片主标题")
    detail_title: str = Field(default="", description="历史卡片详细标题")
    start_date: DateType | None = Field(default=None, description="出行开始日期")
    end_date: DateType | None = Field(default=None, description="出行结束日期")
    itinerary: Itinerary | None = Field(default=None, description="快速规划完整行程")
    deep_plan: DeepPlanDocument | None = Field(default=None, description="深度规划完整文档")
    error_message: str | None = Field(default=None, description="失败原因")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


class TripSummaryItem(BaseModel):
    """已保存行程的摘要信息。"""

    trip_id: str = Field(..., description="行程 ID")
    destination: str = Field(..., description="目的地")
    summary: str = Field(..., description="行程概述")
    plan_type: Literal["quick", "deep"] = Field(default="quick", description="规划类型")
    status: Literal["generating", "completed", "failed"] = Field(
        default="completed",
        description="生成状态",
    )
    progress: int = Field(default=100, ge=0, le=100, description="生成进度")
    display_title: str = Field(default="", description="历史卡片主标题")
    detail_title: str = Field(default="", description="历史卡片详细标题")
    start_date: DateType | None = Field(default=None, description="出行开始日期")
    end_date: DateType | None = Field(default=None, description="出行结束日期")
    error_message: str | None = Field(default=None, description="失败原因")
    has_detail: bool = Field(default=False, description="是否可打开任务详情")
    has_itinerary: bool = Field(default=False, description="是否有结构化快速行程")
    has_report: bool = Field(default=False, description="是否有独立 Markdown Report")
    report_id: str | None = Field(default=None, description="关联 Report ID")
    is_report_only: bool = Field(default=False, description="是否仅来自历史 Report 文件")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


class TripListResponse(BaseModel):
    """行程列表接口的响应结构。"""

    total: int = Field(..., ge=0, description="列表总数")
    items: list[TripSummaryItem] = Field(default_factory=list, description="行程摘要列表")


class ChatbotConversationMessage(BaseModel):
    """聊天机器人历史消息。"""

    role: Literal["user", "assistant"] = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")


class ChatbotSearchSource(BaseModel):
    """聊天机器人联网查询返回的一条来源。"""

    title: str = Field(default="", description="来源标题")
    url: str = Field(default="", description="来源链接")
    content: str = Field(default="", description="来源摘要")
    raw_content: str | None = Field(default=None, description="来源原始内容")
    published_date: str | None = Field(default=None, description="来源发布日期")
    score: float | None = Field(default=None, description="相关度")


class ChatbotResearchStep(BaseModel):
    """聊天机器人可见调研过程中的一个步骤。"""

    id: str = Field(..., description="步骤稳定标识")
    title: str = Field(..., description="步骤标题")
    status: Literal["pending", "running", "completed", "failed"] = Field(
        default="pending",
        description="步骤状态",
    )
    query: str | None = Field(default=None, description="该步骤使用的搜索词")
    summary: str = Field(default="", description="步骤结果摘要")
    sources: list[ChatbotSearchSource] = Field(default_factory=list, description="该步骤来源")


class ChatbotMessageRequest(BaseModel):
    """ChatUI 发送给后端 agent 的请求。"""

    message: str = Field(..., min_length=1, description="用户当前消息")
    trip_id: str | None = Field(default=None, description="当前结果页行程 ID")
    current_itinerary: Itinerary | None = Field(default=None, description="当前结果页 itinerary")
    history: list[ChatbotConversationMessage] = Field(
        default_factory=list,
        description="最近对话历史",
    )


class ChatbotMessageResponse(BaseModel):
    """聊天机器人 agent 响应。"""

    intent: Literal["ask", "update", "search", "research", "clarify", "risk_check"] = Field(
        ...,
        description="识别出的用户意图",
    )
    reply: str = Field(..., description="给用户展示的回复")
    reason: str = Field(default="", description="意图判断原因")
    updated_itinerary: Itinerary | None = Field(default=None, description="更新后的结果页 itinerary")
    sources: list[ChatbotSearchSource] = Field(default_factory=list, description="联网查询来源")
    research_steps: list[ChatbotResearchStep] = Field(
        default_factory=list,
        description="可见调研模式的步骤列表",
    )
