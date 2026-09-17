from decimal import Decimal

from fastapi import APIRouter

from app.schemas.expense import ExpenseBreakdown, ExpenseInput


router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.post("/estimate", response_model=ExpenseBreakdown)
def estimate_expenses(items: list[ExpenseInput]) -> ExpenseBreakdown:
    totals = {expense_type: Decimal("0") for expense_type in ExpenseBreakdown.model_fields if expense_type != "total"}
    for item in items:
        totals[item.expense_type] += item.amount
    total = sum(totals.values(), Decimal("0"))
    return ExpenseBreakdown(**totals, total=total)
