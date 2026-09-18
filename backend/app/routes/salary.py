import logging
import uuid
from typing import List, Dict, Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import AuthContext, require_owner
from app.database import db
from app.models.salary import PaymentRecord, SalaryRecordCreate, SalaryRecordOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["salary"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/employees/{employee_id}/salary", response_model=SalaryRecordOut)
async def upsert_salary_record(
    employee_id: str,
    payload: SalaryRecordCreate,
    month: str = Query(..., regex=r"^\d{4}-\d{2}$"),
    auth: AuthContext = Depends(require_owner),
):
    """
    Set or update the amount_due for a given month for an employee.
    Owner only.
    """
    emp = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    record = await db.salary_records.find_one({"employee_id": employee_id, "month": month}, {"_id": 0})
    
    if record:
        await db.salary_records.update_one(
            {"id": record["id"]},
            {"$set": {"amount_due": payload.amount_due}}
        )
        record["amount_due"] = payload.amount_due
    else:
        record = {
            "id": str(uuid.uuid4()),
            "employee_id": employee_id,
            "month": month,
            "amount_due": payload.amount_due,
            "payments": []
        }
        await db.salary_records.insert_one(record.copy())

    return SalaryRecordOut(**record)


@router.post("/employees/{employee_id}/salary/payment", response_model=SalaryRecordOut)
async def record_payment(
    employee_id: str,
    payload: PaymentRecord,
    month: str = Query(..., regex=r"^\d{4}-\d{2}$"),
    auth: AuthContext = Depends(require_owner),
):
    """
    Record a payment against a month's amount_due.
    Owner only.
    """
    record = await db.salary_records.find_one({"employee_id": employee_id, "month": month}, {"_id": 0})
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Salary record not found for this month. Set amount_due first.",
        )

    payment_dict = payload.dict()
    await db.salary_records.update_one(
        {"id": record["id"]},
        {"$push": {"payments": payment_dict}}
    )
    
    record["payments"].append(payment_dict)
    return SalaryRecordOut(**record)


@router.get("/employees/{employee_id}/salary", response_model=List[SalaryRecordOut])
async def list_salary_history(
    employee_id: str,
    auth: AuthContext = Depends(require_owner),
):
    """
    Get salary history for an employee.
    Owner only.
    """
    emp = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    cursor = db.salary_records.find({"employee_id": employee_id}, {"_id": 0}).sort("month", -1)
    return [SalaryRecordOut(**d) async for d in cursor]


@router.get("/salary/summary")
async def salary_summary(
    month: str = Query(..., regex=r"^\d{4}-\d{2}$"),
    auth: AuthContext = Depends(require_owner),
):
    """
    Get overview of all employees' salaries for a given month.
    Owner only.
    """
    employees = await db.employees.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(length=None)
    
    cursor = db.salary_records.find({"month": month}, {"_id": 0})
    records = [d async for d in cursor]
    record_map = {r["employee_id"]: r for r in records}
    
    summary = []
    for emp in employees:
        rec = record_map.get(emp["id"])
        if rec:
            sal_out = SalaryRecordOut(**rec)
            total_paid = sum(p.amount for p in sal_out.payments)
            summary.append({
                "employee_id": emp["id"],
                "employee_name": emp.get("name", "Unknown"),
                "amount_due": sal_out.amount_due,
                "total_paid": total_paid,
                "status": sal_out.status
            })
        else:
            summary.append({
                "employee_id": emp["id"],
                "employee_name": emp.get("name", "Unknown"),
                "amount_due": 0.0,
                "total_paid": 0.0,
                "status": "unpaid"
            })
            
    return {"month": month, "summary": summary}
