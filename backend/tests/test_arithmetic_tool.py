from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.agents.tools.arithmetic_tool as arithmetic_tool  # noqa: E402


def test_calculate_budget_breakdown_uses_local_arithmetic_tools() -> None:
    """测试预算直接由本地 Decimal 算术工具计算，不依赖 LLM。"""
    budget = arithmetic_tool.calculate_budget_breakdown_with_tools(
        transport=100,
        hotel=200,
        meals=50,
        tickets=25,
        request_budget=500,
    )

    assert budget.other == 60.0
    assert budget.total == 435.0


def test_calculate_budget_breakdown_uses_decimal_math() -> None:
    """测试浮点小数场景也不会出现 0.1 + 0.2 这类误差。"""
    budget = arithmetic_tool.calculate_budget_breakdown_with_tools(
        transport=0.1,
        hotel=0.2,
        meals=0.3,
        tickets=0.4,
        request_budget=None,
    )

    assert budget.transport == 0.1
    assert budget.hotel == 0.2
    assert budget.meals == 0.3
    assert budget.tickets == 0.4
    assert budget.other == 0.06
    assert budget.total == 1.06
