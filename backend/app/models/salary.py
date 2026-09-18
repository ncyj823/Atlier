from typing import List, Literal, Optional

from pydantic import BaseModel, computed_field


class PaymentRecord(BaseModel):
    amount: float
    date: str
    note: Optional[str] = None


class SalaryRecordBase(BaseModel):
    amount_due: float


class SalaryRecordCreate(SalaryRecordBase):
    pass


class SalaryRecordOut(SalaryRecordBase):
    id: str
    employee_id: str
    month: str  # YYYY-MM
    payments: List[PaymentRecord] = []

    @computed_field
    @property
    def status(self) -> Literal["unpaid", "partially_paid", "paid"]:
        total_paid = sum(p.amount for p in self.payments)
        if total_paid >= self.amount_due:
            return "paid"
        elif total_paid > 0:
            return "partially_paid"
        return "unpaid"
