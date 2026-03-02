from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.report import Form8949Response, ScheduleDResponse
from app.schemas.tax import TaxSummaryResponse
from app.services.form_8949 import Form8949Generator
from app.services.schedule_d import ScheduleDGenerator
from app.services.report_generator import TaxSummaryGenerator

router = APIRouter()


@router.get("/8949/{year}", response_model=Form8949Response)
def form_8949(year: int, db: Session = Depends(get_db)):
    generator = Form8949Generator(db)
    return generator.generate(year)


@router.get("/8949/{year}/csv")
def form_8949_csv(year: int, db: Session = Depends(get_db)):
    generator = Form8949Generator(db)
    csv_content = generator.generate_csv(year)
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=form_8949_{year}.csv"
        },
    )


@router.get("/schedule-d/{year}", response_model=ScheduleDResponse)
def schedule_d(year: int, db: Session = Depends(get_db)):
    form_8949_gen = Form8949Generator(db)
    form_8949_data = form_8949_gen.generate(year)
    schedule_d_gen = ScheduleDGenerator()
    return schedule_d_gen.generate(form_8949_data)


@router.get("/tax-summary/{year}", response_model=TaxSummaryResponse)
def tax_summary(year: int, db: Session = Depends(get_db)):
    generator = TaxSummaryGenerator(db)
    return generator.generate(year)


@router.get("/turbotax/{year}")
def turbotax_csv(year: int, db: Session = Depends(get_db)):
    return {"detail": f"TurboTax CSV for {year} — not yet implemented"}
