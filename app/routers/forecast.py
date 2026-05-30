import json
import statistics
from datetime import date
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import MopsPrice, KyResult
from app.auth import get_current_user, require_admin, flash, get_flash
from app.date_utils import current_pub_date, get_period_for_pub_date
from app.calc import calc_all, load_params, sensitivity_grid, rule_of_thumb, PRODUCT_LABELS

router = APIRouter(prefix="/forecast", tags=["forecast"])
templates = Jinja2Templates(directory="app/templates")

PRODUCTS = ["E5", "X95", "DO005", "DO001"]


def _build_mops_avgs(db: Session, trading_days: list[date], x95_x92_spread: float) -> dict:
    rows = db.query(MopsPrice).filter(MopsPrice.date.in_(trading_days)).all()
    price_map: dict[str, dict] = {}
    for r in rows:
        ds = r.date.isoformat()
        price_map.setdefault(ds, {})
        price_map[ds][r.product] = r.price

    # For days with no entry, use last known price (flat assumption)
    last = {p: None for p in ("X95", "DO005", "DO001")}
    day_prices: dict[str, dict] = {}
    for d in sorted(trading_days):
        ds = d.isoformat()
        entry = price_map.get(ds, {})
        day = {}
        for p in ("X95", "DO005", "DO001"):
            val = entry.get(p, last[p])
            if val is None:
                val = 0.0
            last[p] = val
            day[p] = val
        day["confirmed"] = {p: bool(price_map.get(ds, {}).get(p)) for p in ("X95", "DO005", "DO001")}
        day_prices[ds] = day

    avgs = {}
    for p in ("X95", "DO005", "DO001"):
        vals = [day_prices[d.isoformat()][p] for d in sorted(trading_days)]
        avgs[p] = statistics.mean(vals) if all(v > 0 for v in vals) else 0.0

    avgs["X92"] = avgs["X95"] - x95_x92_spread
    return avgs, day_prices


@router.get("", response_class=HTMLResponse)
def forecast_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    params = load_params(db)
    pub_date = current_pub_date()
    period_start, period_end, trading_days = get_period_for_pub_date(pub_date)

    mops_avgs, day_prices = _build_mops_avgs(db, trading_days, params["x95_x92_spread"])

    results = calc_all(mops_avgs, params) if all(v > 0 for v in mops_avgs.values()) else {}

    # Previous kỳ for comparison
    prev_pub = pub_date.__class__(pub_date.year, pub_date.month, pub_date.day)
    from app.date_utils import previous_pub_date
    prev = db.query(KyResult).filter(
        KyResult.publication_date == previous_pub_date(pub_date)
    ).first()
    prev_results = json.loads(prev.results) if prev and prev.results else {}

    sens = sensitivity_grid(mops_avgs.get("X95", 0), params) if mops_avgs.get("X95", 0) > 0 else {}
    rot  = rule_of_thumb(params)

    confirmed_days = sum(
        1 for ds, dp in day_prices.items()
        if all(dp["confirmed"].get(p) for p in ("X95", "DO005", "DO001"))
    )

    already_saved = db.query(KyResult).filter(
        KyResult.publication_date == pub_date
    ).first() is not None

    return templates.TemplateResponse(request, "forecast.html", context={
        "user":           user,
        "pub_date":       pub_date.isoformat(),
        "period_start":   period_start.isoformat(),
        "period_end":     period_end.isoformat(),
        "mops_avgs":      {k: round(v, 3) for k, v in mops_avgs.items()},
        "day_prices":     day_prices,
        "results":        results,
        "prev_results":   prev_results,
        "products":       PRODUCTS,
        "product_labels": PRODUCT_LABELS,
        "sensitivity":    sens,
        "rot":            rot,
        "params":         params,
        "confirmed_days": confirmed_days,
        "total_days":     len(trading_days),
        "already_saved":  already_saved,
        "flashes":        get_flash(request),
    })


@router.post("/save-ky")
def save_ky(request: Request, db: Session = Depends(get_db)):
    """Admin: save current kỳ results to history."""
    user = require_admin(request, db)
    params = load_params(db)
    pub_date = current_pub_date()
    period_start, period_end, trading_days = get_period_for_pub_date(pub_date)

    mops_avgs, _ = _build_mops_avgs(db, trading_days, params["x95_x92_spread"])
    results = calc_all(mops_avgs, params)

    existing = db.query(KyResult).filter(KyResult.publication_date == pub_date).first()
    if existing:
        existing.mops_avgs  = json.dumps({k: round(v, 3) for k, v in mops_avgs.items()})
        existing.vcb_rate   = params["vcb"]
        existing.lnh_rate   = params["lnh"]
        existing.results    = json.dumps(results)
        existing.saved_by   = user.username
    else:
        ky = KyResult(
            publication_date = pub_date,
            period_start     = period_start,
            period_end       = period_end,
            mops_avgs        = json.dumps({k: round(v, 3) for k, v in mops_avgs.items()}),
            vcb_rate         = params["vcb"],
            lnh_rate         = params["lnh"],
            results          = json.dumps(results),
            saved_by         = user.username,
        )
        db.add(ky)
    db.commit()
    flash(request, f"Đã lưu kỳ {pub_date.strftime('%d/%m/%Y')} vào lịch sử.", "success")
    return RedirectResponse("/forecast", status_code=303)
