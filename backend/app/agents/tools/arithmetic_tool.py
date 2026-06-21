from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.models.schemas import BudgetBreakdown


def _to_decimal(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value))


def _to_money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def arithmetic_add(numbers: list[float]) -> float:
    """Add a list of numbers and return a money-safe result rounded to 2 decimals."""
    return _to_money(sum((_to_decimal(number) for number in numbers), Decimal("0")))


def arithmetic_subtract(left: float, right: float) -> float:
    """Subtract right from left and return a money-safe result rounded to 2 decimals."""
    return _to_money(_to_decimal(left) - _to_decimal(right))


def arithmetic_multiply(left: float, right: float) -> float:
    """Multiply two numbers and return a money-safe result rounded to 2 decimals."""
    return _to_money(_to_decimal(left) * _to_decimal(right))


def arithmetic_divide(left: float, right: float) -> float:
    """Divide left by right and return a money-safe result rounded to 2 decimals."""
    divisor = _to_decimal(right)
    if divisor == 0:
        raise ValueError("Cannot divide by zero.")
    return _to_money(_to_decimal(left) / divisor)


def _safe_add(numbers: list[float]) -> float:
    return arithmetic_add(numbers)


def _safe_multiply(left: float, right: float) -> float:
    return arithmetic_multiply(left, right)


def _safe_subtract(left: float, right: float) -> float:
    return arithmetic_subtract(left, right)


def calculate_budget_breakdown_with_tools(
    *,
    transport: float,
    hotel: float,
    meals: float,
    tickets: float,
    request_budget: float | None = None,
) -> BudgetBreakdown:
    """Calculate itinerary budget with deterministic Decimal-backed arithmetic."""
    subtotal = _safe_add([transport, hotel, meals, tickets])
    if request_budget is not None:
        max_other = _safe_multiply(request_budget, 0.12)
        remaining = _safe_subtract(request_budget, subtotal)
        other = max(0.0, min(max_other, remaining))
    else:
        other = max(_safe_multiply(subtotal, 0.06), 0.0)

    other = _to_money(_to_decimal(other))
    total = _safe_add([subtotal, other])
    return BudgetBreakdown(
        transport=_to_money(_to_decimal(transport)),
        hotel=_to_money(_to_decimal(hotel)),
        meals=_to_money(_to_decimal(meals)),
        tickets=_to_money(_to_decimal(tickets)),
        other=other,
        total=total,
    )
