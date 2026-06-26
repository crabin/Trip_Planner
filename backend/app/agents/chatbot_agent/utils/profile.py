from __future__ import annotations

import re

from app.models.schemas import ChatbotConversationMessage, TravelerProfile

MAX_PROFILE_ITEMS = 12
MAX_CONFIRMED_FACTS = 20
MAX_SUMMARY_CHARS = 360

PACE_PATTERNS = (
    ("轻松", ("轻松", "慢一点", "别太赶", "不要太赶", "松弛", "休闲", "慢游")),
    ("紧凑", ("紧凑", "多打卡", "打卡多", "排满", "尽量多玩", "多安排")),
    ("适中", ("适中", "正常节奏", "不要太松", "不要太赶也不要太松")),
)
FOOD_PATTERNS = (
    "少辣",
    "不吃辣",
    "素食",
    "清真",
    "咖啡",
    "夜宵",
    "甜品",
    "海鲜",
    "火锅",
    "川菜",
    "本地小吃",
)
AVOIDANCE_PATTERNS = (
    ("不早起", ("不早起", "不要早起", "不想早起", "别早起", "起不来")),
    ("少走路", ("少走路", "不想走太多", "走路少", "少步行")),
    ("避开网红排队", ("避开网红", "不排队", "少排队", "排队少")),
    ("避开人多", ("人少", "避开人多", "别太挤", "不想挤")),
    ("少换酒店", ("少换酒店", "不想换酒店", "不要频繁换酒店")),
)
INTEREST_PATTERNS = (
    "拍照",
    "亲子",
    "历史",
    "人文",
    "自然",
    "Citywalk",
    "citywalk",
    "博物馆",
    "夜景",
    "购物",
    "徒步",
)
BUDGET_PATTERNS = (
    ("高", ("预算敏感", "省钱", "尽量便宜", "控制预算", "预算尽量控制", "性价比")),
    ("低", ("预算不敏感", "预算充足", "舒服优先", "贵一点也可以")),
    ("中", ("预算适中", "中等预算", "别太贵")),
)


def merge_profile(base: TravelerProfile, patch: TravelerProfile) -> TravelerProfile:
    """Merge a conservative profile patch into the current browser-local profile."""
    return TravelerProfile(
        pace_preference=patch.pace_preference or base.pace_preference,
        food_preferences=_merge_text_list(base.food_preferences, patch.food_preferences),
        avoidances=_merge_text_list(base.avoidances, patch.avoidances),
        interests=_merge_text_list(base.interests, _normalize_interests(patch.interests)),
        budget_sensitivity=patch.budget_sensitivity or base.budget_sensitivity,
        confirmed_facts=_merge_text_list(
            base.confirmed_facts,
            patch.confirmed_facts,
            limit=MAX_CONFIRMED_FACTS,
        ),
    )


def extract_profile_patch(message: str) -> TravelerProfile:
    text = message.strip()
    patch = TravelerProfile()
    patch.pace_preference = _match_choice(text, PACE_PATTERNS)
    patch.food_preferences = _extract_terms(text, FOOD_PATTERNS)
    patch.avoidances = _extract_mapped_terms(text, AVOIDANCE_PATTERNS)
    patch.interests = _normalize_interests(_extract_terms(text, INTEREST_PATTERNS))
    patch.budget_sensitivity = _match_choice(text, BUDGET_PATTERNS)
    patch.confirmed_facts = _extract_confirmed_facts(text)
    return patch


def summarize_conversation(
    previous_summary: str,
    history: list[ChatbotConversationMessage],
    user_message: str,
    assistant_reply: str,
) -> str:
    recent = [item.content.strip() for item in history[-4:] if item.content.strip()]
    parts = []
    if previous_summary.strip():
        parts.append(previous_summary.strip())
    parts.extend(recent)
    parts.append(f"用户本轮：{user_message.strip()}")
    parts.append(f"顾问本轮：{_compact_text(assistant_reply)}")
    summary = " / ".join(part for part in parts if part)
    return summary[-MAX_SUMMARY_CHARS:]


def _match_choice(text: str, patterns: tuple[tuple[str, tuple[str, ...]], ...]) -> str | None:
    for value, terms in patterns:
        if any(term in text for term in terms):
            return value
    return None


def _extract_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [_canonical_term(term) for term in terms if term in text]


def _extract_mapped_terms(text: str, patterns: tuple[tuple[str, tuple[str, ...]], ...]) -> list[str]:
    return [value for value, terms in patterns if any(term in text for term in terms)]


def _extract_confirmed_facts(text: str) -> list[str]:
    if not any(marker in text for marker in ("我", "我们", "带", "同行", "预算", "已经", "确定", "确认")):
        return []
    facts: list[str] = []
    for pattern in (
        r"(?:我|我们)(?:是|会|想|要|希望|带|同行|已经|确定|确认)[^。！？!?]{2,36}",
        r"预算[^。！？!?]{2,24}",
        r"带[^。！？!?]{2,24}",
    ):
        for match in re.findall(pattern, text):
            fact = match.strip("，,。.!！?？ ")
            if fact:
                facts.append(fact)
    return _merge_text_list([], facts, limit=3)


def _merge_text_list(base: list[str], additions: list[str], *, limit: int = MAX_PROFILE_ITEMS) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in [*base, *additions]:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)
        if len(merged) >= limit:
            break
    return merged


def _normalize_interests(items: list[str]) -> list[str]:
    return [_canonical_term(item) for item in items]


def _canonical_term(value: str) -> str:
    return "Citywalk" if value.lower() == "citywalk" else value


def _compact_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= 80:
        return text
    return f"{text[:80]}..."
