"""
destination_intelligence_agent 状态管理
定义所有状态数据结构和操作方法
"""

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class Search:
    """单个搜索状态"""

    query: str = ""  # 搜索查询
    step_id: str = ""  # 产生该来源的研究步骤
    url: str = ""  # 搜索结果URL
    title: str = ""  # 搜索结果标题
    content: str = ""  # 搜索返回结果内容
    raw_content: Optional[str] = None  # 搜索原始内容或更完整证据
    used_in_summary: bool = False  # 该来源是否进入总结提示词
    score: Optional[float] = None  # 搜索结果评分
    published_date: Optional[str] = None  # 来源发布日期
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """将Search对象转换为字典"""
        return {
            "query": self.query,
            "step_id": self.step_id,
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "raw_content": self.raw_content,
            "used_in_summary": self.used_in_summary,
            "score": self.score,
            "published_date": self.published_date,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Search":
        """从字典创建Search对象"""
        return cls(
            query=data.get("query", ""),
            step_id=data.get("step_id", ""),
            url=data.get("url", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            raw_content=data.get("raw_content"),
            used_in_summary=bool(data.get("used_in_summary", False)),
            score=data.get("score"),
            published_date=data.get("published_date"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


@dataclass
class ResearchTraceStep:
    """A compact audit record for one destination-intelligence research step."""

    step_id: str = ""
    phase: str = ""
    section_title: str = ""
    search_query: str = ""
    search_tool: str = ""
    reasoning: str = ""
    summary_before: str = ""
    summary_after: str = ""
    evidence_count: int = 0
    prompt_chars: int = 0
    estimated_prompt_tokens: int = 0
    fallback_reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "phase": self.phase,
            "section_title": self.section_title,
            "search_query": self.search_query,
            "search_tool": self.search_tool,
            "reasoning": self.reasoning,
            "summary_before": self.summary_before,
            "summary_after": self.summary_after,
            "evidence_count": self.evidence_count,
            "prompt_chars": self.prompt_chars,
            "estimated_prompt_tokens": self.estimated_prompt_tokens,
            "fallback_reason": self.fallback_reason,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchTraceStep":
        return cls(
            step_id=str(data.get("step_id", "")),
            phase=str(data.get("phase", "")),
            section_title=str(data.get("section_title", "")),
            search_query=str(data.get("search_query", "")),
            search_tool=str(data.get("search_tool", "")),
            reasoning=str(data.get("reasoning", "")),
            summary_before=str(data.get("summary_before", "")),
            summary_after=str(data.get("summary_after", "")),
            evidence_count=int(data.get("evidence_count") or 0),
            prompt_chars=int(data.get("prompt_chars") or 0),
            estimated_prompt_tokens=int(data.get("estimated_prompt_tokens") or 0),
            fallback_reason=str(data.get("fallback_reason", "")),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


@dataclass
class Research:
    """段落研究过程状态"""

    search_history: List[Search] = field(default_factory=list)  # 搜索记录列表
    trace_steps: List[ResearchTraceStep] = field(default_factory=list)
    latest_summary: str = ""  # 当前段落的最新总结
    reflection_iteration: int = 0  # 反思迭代次数
    is_completed: bool = False  # 是否完成研究

    def add_search(self, search: Search):
        """添加新的搜索记录"""
        self.search_history.append(search)

    def add_search_results(
        self,
        query: str,
        results: list[dict[str, Any]],
        *,
        step_id: str = "",
        used_in_summary: bool = False,
    ):
        """批量添加新的搜索结果"""
        for item in results:
            search = Search(
                query=query,
                step_id=step_id or item.get("step_id", ""),
                url=item.get("url", ""),
                title=item.get("title", ""),
                content=item.get("content", ""),
                raw_content=item.get("raw_content"),
                used_in_summary=bool(item.get("used_in_summary", used_in_summary)),
                score=item.get("score"),
                published_date=item.get("published_date"),
            )
            self.add_search(search)

    def get_search_count(self) -> int:
        """获取搜索记录数量"""
        return len(self.search_history)

    def increment_reflection(self):
        """增加反思迭代次数"""
        self.reflection_iteration += 1

    def mark_completed(self):
        """标记研究完成"""
        self.is_completed = True

    def to_dict(self) -> Dict[str, Any]:
        """将Research对象转换为字典"""
        return {
            "search_history": [s.to_dict() for s in self.search_history],
            "trace_steps": [step.to_dict() for step in self.trace_steps],
            "latest_summary": self.latest_summary,
            "reflection_iteration": self.reflection_iteration,
            "is_completed": self.is_completed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Research":
        """从字典创建Research对象"""
        search_history = [Search.from_dict(s) for s in data.get("search_history", [])]
        trace_steps = [
            ResearchTraceStep.from_dict(step)
            for step in data.get("trace_steps", [])
            if isinstance(step, dict)
        ]
        return cls(
            search_history=search_history,
            trace_steps=trace_steps,
            latest_summary=data.get("latest_summary", ""),
            reflection_iteration=data.get("reflection_iteration", 0),
            is_completed=data.get("is_completed", False),
        )


@dataclass
class Paragraph:
    """报告中的当个段落的状态"""

    title: str = ""  # 段落标题
    content: str = ""  # 段落内容
    requires_12306_mcp: bool = False
    research: Research = field(default_factory=Research)  # 段落研究状态
    order: int = 0  # 段落顺序

    def is_completed(self) -> bool:
        """检查段落研究是否完成"""
        return self.research.is_completed and bool(self.research.latest_summary)

    def get_final_content(self) -> str:
        """获取段落的最终总结"""
        return self.research.latest_summary or self.content

    def to_dict(self) -> Dict[str, Any]:
        """将Paragraph对象转换为字典"""
        return {
            "title": self.title,
            "content": self.content,
            "requires_12306_mcp": self.requires_12306_mcp,
            "research": self.research.to_dict(),
            "order": self.order,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Paragraph":
        """从字典创建Paragraph对象"""
        research_data = data.get("research", {})
        research = Research.from_dict(research_data) if research_data else Research()
        return cls(
            title=data.get("title", ""),
            content=data.get("content", ""),
            requires_12306_mcp=bool(data.get("requires_12306_mcp", False)),
            research=research,
            order=data.get("order", 0),
        )


@dataclass
class State:
    """整体状态管理"""

    query: str = ""  # 当前查询
    report_title: str = ""  # 报告标题
    paragraphs: List[Paragraph] = field(default_factory=list)  # 段落列表
    final_report: str = ""  # 最终报告内容
    is_completed: bool = False  # 是否完成整个报告
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )  # 创建时间
    updated_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )  # 更新时间

    def add_paragraph(
        self,
        title: str,
        content: str,
        *,
        requires_12306_mcp: bool = False,
    ) -> int:
        """
        添加新的段落
        
        Args:
            title: 段落标题
            content: 段落内容
            
        Returns:
            int: 新段落的索引
        
        """
        order = len(self.paragraphs)
        paragraph = Paragraph(
            title=title,
            content=content,
            requires_12306_mcp=requires_12306_mcp,
            order=order,
        )
        self.paragraphs.append(paragraph)
        self.update_timestamp()
        return order  # 返回新段落的索引
    
    def get_paragraph(self, order: int) -> Optional[Paragraph]:
        """获取指定顺序的段落"""
        if 0 <= order < len(self.paragraphs):
            return self.paragraphs[order]
        return None
    
    def get_completed_paragraphs_count(self) -> int:
        """获取已完成的段落数量"""
        return sum(1 for p in self.paragraphs if p.is_completed())
    
    def get_total_paragraphs_count(self) -> int:
        """获取总段落数量"""
        return len(self.paragraphs)
    
    def is_all_paragraphs_completed(self) -> bool:
        """检查是否所有段落都已完成"""
        return all(p.is_completed() for p in self.paragraphs) if self.paragraphs else False
    
    def mark_completed(self):
        """标记整个报告为完成"""
        self.is_completed = True
        self.update_timestamp()
    
    def update_timestamp(self):
        """更新状态的更新时间戳"""
        self.updated_at = datetime.now().isoformat()
        
    def get_progress_summary(self) -> Dict[str, Any]:
        """获取当前状态的进度摘要"""
        completed = self.get_completed_paragraphs_count()
        total = self.get_total_paragraphs_count()
        
        return {
            "total_paragraphs": total,
            "completed_paragraphs": completed,
            "progress_percentage": (completed / total * 100) if total > 0 else 0,
            "is_completed": self.is_completed,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """将State对象转换为字典"""
        return {
            "query": self.query,
            "report_title": self.report_title,
            "paragraphs": [p.to_dict() for p in self.paragraphs],
            "final_report": self.final_report,
            "is_completed": self.is_completed,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "State":
        """从字典创建State对象"""
        paragraphs = [Paragraph.from_dict(p) for p in data.get("paragraphs", [])]
        
        return cls(
            query=data.get("query", ""),
            report_title=data.get("report_title", ""),
            paragraphs=paragraphs,
            final_report=data.get("final_report", ""),
            is_completed=data.get("is_completed", False),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "State":
        """从JSON字符串创建State对象"""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def to_json(self) -> str:
        """将完整状态序列化为可读的 UTF-8 JSON。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def save_to_file(self, filepath: str | Path) -> None:
        """原子保存状态，序列化或写入失败时不破坏已有文件。"""
        serialized = self.to_json()
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")

        try:
            temporary_path.write_text(serialized, encoding="utf-8")
            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)

    @classmethod
    def load_from_file(cls, file_path: str | Path) -> "State":
        """从文件加载State对象"""
        with Path(file_path).open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
