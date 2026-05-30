import os
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.routers import auth_router, mops, forecast, history, admin
from app.auth import get_current_user, get_flash
from app.calc import load_params, PRODUCT_LABELS
from app.date_utils import current_pub_date, get_period_for_pub_date

SECRET_KEY = os.environ.get("SESSION_SECRET", "change-me-in-production-use-long-random-string")

app = FastAPI(title="MOIT Pricing Platform")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="app/templates")

app.include_router(auth_router.router)
app.include_router(mops.router)
app.include_router(forecast.router)
app.include_router(history.router)
app.include_router(admin.router)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    try:
        user = get_current_user(request, db)
    except Exception:
        return RedirectResponse("/login", status_code=303)

    from app.routers.forecast import _build_mops_avgs
    from app.models import KyResult
    from app.calc import calc_all
    import json

    params   = load_params(db)
    pub_date = current_pub_date()
    _, _, trading_days = get_period_for_pub_date(pub_date)
    mops_avgs, day_prices = _build_mops_avgs(db, trading_days, params["x95_x92_spread"])

    results = {}
    if all(v > 0 for v in mops_avgs.values()):
        results = calc_all(mops_avgs, params)

    confirmed_days = sum(
        1 for ds, dp in day_prices.items()
        if all(dp["confirmed"].get(p) for p in ("X95", "DO005", "DO001"))
    )

    # Last 4 published kỳ
    recent = db.query(KyResult).order_by(KyResult.publication_date.desc()).limit(4).all()
    recent_records = []
    for r in recent:
        res = json.loads(r.results) if r.results else {}
        recent_records.append({
            "pub_date": r.publication_date.strftime("%d/%m/%Y"),
            "E5":    res.get("E5",    {}).get("total"),
            "X95":   res.get("X95",  {}).get("total"),
            "DO005": res.get("DO005",{}).get("total"),
        })

    return templates.TemplateResponse(request, "dashboard.html", context={
        "user":           user,
        "pub_date":       pub_date.strftime("%d/%m/%Y"),
        "period_start":   trading_days[0].strftime("%d/%m") if trading_days else "",
        "period_end":     trading_days[-1].strftime("%d/%m/%Y") if trading_days else "",
        "results":        results,
        "product_labels": PRODUCT_LABELS,
        "confirmed_days": confirmed_days,
        "total_days":     len(trading_days),
        "recent_records": recent_records,
        "flashes":        get_flash(request),
    })
