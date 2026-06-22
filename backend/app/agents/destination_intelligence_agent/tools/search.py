"""
专为目的地旅行研究 Agent 设计的网页搜索工具集 (Tavily)

版本: 1.5
最后更新: 2025-08-22

此脚本将复杂的Tavily搜索功能分解为一系列目标明确、参数极少的独立工具，
专为AI Agent调用而设计。Agent只需根据任务意图选择合适的工具，
无需理解复杂的参数组合。历史方法名保留 `_news` 以兼容现有调用，
底层统一使用通用网页搜索 (`topic='general'`)。

新特性:
- `basic_search_news` 用于执行标准、通用的网页搜索。
- 每个搜索结果包含 `published_date`（来源发布日期）。

主要工具:
- basic_search_news: 标准、快速的通用网页搜索。
- deep_search_news: 对旅行主题进行高级深度研究。
- search_news_last_24_hours: 获取24小时内的关闭、预警等动态。
- search_news_last_week: 获取过去一周的目的地动态。
- search_images_for_news: 查找目的地、景点或地图相关图片。
- search_news_by_date: 按来源发布日期范围搜索公告。
"""

import os
import sys
from pathlib import Path
from typing import List, Optional


from loguru import logger

if __package__:
    from ..utils.retry_helper import SEARCH_API_RETRY_CONFIG, with_graceful_retry
else:
    # Support `uv run search.py` while keeping the import anchored to this backend.
    # A top-level `utils` import can resolve to the unrelated backend/utils package.
    backend_dir = Path(__file__).resolve().parents[4]
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    from app.agents.destination_intelligence_agent.utils.retry_helper import (  # noqa: E402
        SEARCH_API_RETRY_CONFIG,
        with_graceful_retry,
    )
from dataclasses import dataclass, field  # noqa: E402

# 运行前请确保已安装Tavily库: pip install tavily-python
try:
    from tavily import TavilyClient
except ImportError:
    raise ImportError("Tavily库未安装，请运行 `pip install tavily-python` 进行安装。")

# --- 1. 数据结构定义 ---

@dataclass
class SearchResult:
    """
    网页搜索结果数据类
    包含 published_date 属性来存储来源发布日期
    """
    title: str
    url: str
    content: str
    score: Optional[float] = None
    raw_content: Optional[str] = None
    published_date: Optional[str] = None

@dataclass
class ImageResult:
    """图片搜索结果数据类"""
    url: str
    description: Optional[str] = None

@dataclass
class TavilyResponse:
    """封装Tavily API的完整返回结果，以便在工具间传递"""
    query: str
    answer: Optional[str] = None
    results: List[SearchResult] = field(default_factory=list)
    images: List[ImageResult] = field(default_factory=list)
    response_time: Optional[float] = None


# --- 2. 核心客户端与专用工具集 ---

class TavilyNewsAgency:
    """
    一个通用网页研究客户端。
    类名和公共方法沿用历史命名以保持兼容，底层搜索主题为 general，
    可用于官方旅游信息、交通、景点、住宿、餐饮及日期敏感公告。
    每个公共方法都设计为供 AI Agent 独立调用的工具。
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化客户端。
        Args:
            api_key: Tavily API密钥，若不提供则从环境变量 TAVILY_API_KEY 读取。
        """
        if api_key is None:
            api_key = os.getenv("TAVILY_API_KEY")
            if not api_key:
                raise ValueError("Tavily API Key未找到！请设置TAVILY_API_KEY环境变量或在初始化时提供")
        self._client = TavilyClient(api_key=api_key)

    @with_graceful_retry(SEARCH_API_RETRY_CONFIG, default_return=TavilyResponse(query="搜索失败"))
    def _search_internal(self, **kwargs) -> TavilyResponse:
        """内部通用的搜索执行器，所有工具最终都调用此方法"""
        try:
            kwargs['topic'] = 'general'
            api_params = {k: v for k, v in kwargs.items() if v is not None}
            response_dict = self._client.search(**api_params)

            search_results = [
                SearchResult(
                    title=str(item.get('title') or ''),
                    url=str(item.get('url') or ''),
                    content=str(item.get('content') or ''),
                    score=item.get('score'),
                    raw_content=item.get('raw_content'),
                    published_date=item.get('published_date')
                ) for item in response_dict.get('results', [])
            ]

            image_results = [ImageResult(url=item.get('url'), description=item.get('description')) for item in response_dict.get('images', [])]

            return TavilyResponse(
                query=str(response_dict.get('query') or kwargs.get('query') or ''),
                answer=response_dict.get('answer'),
                results=search_results, images=image_results,
                response_time=response_dict.get('response_time')
            )
        except Exception:
            logger.exception("搜索时发生错误")
            raise  # 让重试机制捕获并处理

    # --- Agent 可用的工具方法 ---

    def basic_search_news(self, query: str, max_results: int = 7) -> TavilyResponse:
        """
        【工具】基础网页搜索: 执行一次标准、快速的通用搜索。
        适用于官方页面、交通、景点、住宿区域和餐饮等单一事实。
        Agent可提供搜索查询(query)和可选的最大结果数(max_results)。
        """
        logger.info("TOOL: 基础网页搜索 (query: {})", query)
        return self._search_internal(
            query=query,
            max_results=max_results,
            search_depth="basic",
            include_answer=False
        )

    def deep_search_news(self, query: str) -> TavilyResponse:
        """
        【工具】深度网页研究: 对一个旅行规划主题进行全面搜索。
        适用于候选比较、复杂交通或综合目的地信息。
        Agent只需提供搜索查询(query)。
        """
        logger.info("TOOL: 深度网页研究 (query: {})", query)
        return self._search_internal(
            query=query, search_depth="advanced", max_results=20, include_answer="advanced"
        )

    def search_news_last_24_hours(self, query: str) -> TavilyResponse:
        """
        【工具】搜索24小时内信息: 核查关闭、预警、停运或活动调整等即时变化。
        Agent只需提供搜索查询(query)。
        """
        logger.info("TOOL: 搜索24小时内信息 (query: {})", query)
        return self._search_internal(query=query, time_range='d', max_results=10)

    def search_news_last_week(self, query: str) -> TavilyResponse:
        """
        【工具】搜索本周信息: 核查近期目的地动态、活动和风险公告。
        Agent只需提供搜索查询(query)。
        """
        logger.info("TOOL: 搜索本周信息 (query: {})", query)
        return self._search_internal(query=query, time_range='w', max_results=10)

    def search_images_for_news(self, query: str) -> TavilyResponse:
        """
        【工具】查找目的地图片: 搜索景点、地图或区域相关图片。
        Agent只需提供搜索查询(query)。
        """
        logger.info("TOOL: 查找目的地图片 (query: {})", query)
        return self._search_internal(
            query=query, include_images=True, include_image_descriptions=True, max_results=5
        )

    def search_news_by_date(self, query: str, start_date: str, end_date: str) -> TavilyResponse:
        """
        【工具】按发布日期范围搜索信息: 查找明确时间窗内发布的公告或动态。
        日期表示来源发布日期，而不是旅行发生日期。
        Agent需要提供查询(query)、开始日期(start_date)和结束日期(end_date)，格式均为 'YYYY-MM-DD'。
        """
        logger.info("TOOL: 按发布日期范围搜索信息 (query: {}, from: {}, to: {})", query, start_date, end_date)
        return self._search_internal(
            query=query, start_date=start_date, end_date=end_date, max_results=15
        )


# --- 3. 测试与使用示例 ---

def print_response_summary(response: TavilyResponse):
    """简化的打印函数，用于展示测试结果，现在会显示发布日期"""
    if not response or not response.query:
        print("未能获取有效响应。")
        return

    print(f"\n查询: '{response.query}' | 耗时: {response.response_time}s")
    if response.answer:
        print(f"AI摘要: {response.answer[:120]}...")
    print(f"找到 {len(response.results)} 条网页, {len(response.images)} 张图片。")
    if response.results:
        first_result = response.results[0]
        date_info = f"(发布于: {first_result.published_date})" if first_result.published_date else ""
        print(f"第一条结果: {first_result.title} {date_info}")
    print("-" * 60)


if __name__ == "__main__":
    # 在运行前，请确保您已设置 TAVILY_API_KEY 环境变量
    try:
        # 初始化“新闻社”客户端，它内部包含了所有工具
    
        agency = TavilyNewsAgency()

        # 场景1: Agent 进行一次常规、快速的搜索
        response1 = agency.basic_search_news(query="奥运会最新赛况", max_results=5)
        print_response_summary(response1)

        # 场景2: Agent 需要全面了解“全球芯片技术竞争”的背景
        response2 = agency.deep_search_news(query="全球芯片技术竞争")
        print_response_summary(response2)

        # 场景3: Agent 需要追踪“GTC大会”的最新消息
        response3 = agency.search_news_last_24_hours(query="Nvidia GTC大会 最新发布")
        print_response_summary(response3)

        # 场景4: Agent 需要为一篇关于“自动驾驶”的周报查找素材
        response4 = agency.search_news_last_week(query="自动驾驶商业化落地")
        print_response_summary(response4)

        # 场景5: Agent 需要查找“韦伯太空望远镜”的新闻图片
        response5 = agency.search_images_for_news(query="韦伯太空望远镜最新发现")
        print_response_summary(response5)

        # 场景6: Agent 需要研究2025年第一季度关于“人工智能法规”的新闻
        response6 = agency.search_news_by_date(
            query="人工智能法规",
            start_date="2025-01-01",
            end_date="2025-03-31"
        )
        print_response_summary(response6)

    except ValueError as e:
        print(f"初始化失败: {e}")
        print("请确保 TAVILY_API_KEY 环境变量已正确设置。")
    except Exception as e:
        print(f"测试过程中发生未知错误: {e}")
