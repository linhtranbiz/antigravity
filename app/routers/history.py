import json
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import KyResult
from app.auth import get_current_user
from app.calc import PRODUCT_LABELS

router = APIRouter(prefix="/history", tags=["history"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def history_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    rows = db.query(KyResult).order_by(KyResult.publication_date.desc()).limit(52).all()

    records = []
    for r in rows:
        res = json.loads(r.results) if r.results else {}
        avgs = json.loads(r.mops_avgs) if r.mops_avgs else {}
        records.append({
            "id":           r.id,
            "pub_date":     r.publication_date.strftime("%d/%m/%Y"),
            "pub_date_iso": r.publication_date.isoformat(),
            "period":       f"{r.period_start.strftime('%d/%m')}–{r.period_end.strftime('%d/%m/%Y')}",
            "E5":    res.get("E5",    {}).get("total"),
            "X95":   res.get("X95",  {}).get("total"),
            "DO005": res.get("DO005",{}).get("total"),
            "DO001": res.get("DO001",{}).get("total"),
            "mops_x95":   avgs.get("X95"),
            "vcb":         r.vcb_rate,
        })

    # Deltas vs previous kỳ
    for i, rec in enumerate(records):
        if i + 1 < len(records):
            prev = records[i + 1]
            for p in ("E5", "X95", "DO005"):
                if rec[p] and prev[p]:
                    rec[f"delta_{p}"] = rec[p] - prev[p]
                    rec[f"pct_{p}"]   = round((rec[p] - prev[p]) / prev[p] * 100, 2)
                else:
                    rec[f"delta_{p}"] = None
                    rec[f"pct_{p}"]   = None

    chart_data = {
        "labels": [r["pub_date"] for r in reversed(records)],
        "E5":     [r["E5"]    for r in reversed(records)],
        "X95":    [r["X95"]   for r in reversed(records)],
        "DO005":  [r["DO005"] for r in reversed(records)],
    }

    return templates.TemplateResponse(request, "history.html", context={
        "user":           user,
        "records":        records,
        "chart_data":     json.dumps(chart_data),
        "product_labels": PRODUCT_LABELS,
    })


@router.get("/detail/{ky_id}", response_class=HTMLResponse)
def history_detail(ky_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    ky = db.query(KyResult).filter(KyResult.id == ky_id).first()
    if not ky:
        return HTMLResponse("Không tìm thấy kỳ này.", status_code=404)

    res  = json.loads(ky.results)  if ky.results  else {}
    avgs = json.loads(ky.mops_avgs) if ky.mops_avgs else {}

    return templates.TemplateResponse(request, "history_detail.html", context={
        "user":           user,
        "ky":             ky,
        "results":        res,
        "avgs":           avgs,
        "product_labels": PRODUCT_LABELS,
    })
