"""Audit & Validation API — balance reconciliation, missing basis detection,
and combined audit summary.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.balance_reconciler import reconcile_balances
from app.services.missing_basis_checker import find_missing_basis
from app.services.invariant_checker import run_all_checks

router = APIRouter()


@router.get("/reconciliation")
def get_reconciliation(db: Session = Depends(get_db)):
    """Return balance reconciliation results for all wallet/asset pairs."""
    items = reconcile_balances(db)
    discrepancies = [i for i in items if i["is_discrepancy"]]
    return {
        "items": items,
        "total": len(items),
        "discrepancy_count": len(discrepancies),
    }


@router.get("/missing-basis")
def get_missing_basis(db: Session = Depends(get_db)):
    """Return missing cost basis warnings."""
    items = find_missing_basis(db)
    return {
        "items": items,
        "total": len(items),
    }


@router.get("/summary")
def get_audit_summary(db: Session = Depends(get_db)):
    """Return a combined audit summary with counts from all checks."""
    # Invariant checks
    invariant_results = run_all_checks(db)
    invariant_failures = [r for r in invariant_results if r.status == "fail"]

    # Balance reconciliation
    reconciliation_items = reconcile_balances(db)
    reconciliation_issues = [i for i in reconciliation_items if i["is_discrepancy"]]

    # Missing basis
    missing_basis_items = find_missing_basis(db)

    return {
        "invariant_checks": {
            "total": len(invariant_results),
            "passed": len(invariant_results) - len(invariant_failures),
            "failed": len(invariant_failures),
        },
        "reconciliation": {
            "pairs_checked": len(reconciliation_items),
            "discrepancies": len(reconciliation_issues),
        },
        "missing_basis": {
            "warnings": len(missing_basis_items),
        },
        "overall_status": (
            "clean"
            if len(invariant_failures) == 0
            and len(reconciliation_issues) == 0
            and len(missing_basis_items) == 0
            else "issues_found"
        ),
    }
