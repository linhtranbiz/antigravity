import json
from datetime import date
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import MopsPrice
from app.auth import get_current_user, flash, get_flash
from app.date_utils import current_pub_date, get_period_for_pub_date

router = APIRouter(prefix="/mops", tags=["mops"])
templates = Jinja2Templates(directory="app/templates")


def _get_period_prices(db: Session, trading_days: list[date]) -> dict:
    """Return {date_str: {X95, DO005, DO001, confirmed}} for the period."""
    rows = db.query(MopsPrice).filter(
        MopsPrice.date.in_(trading_days)
    ).all()
    price_map: dict = {}
    for r in rows:
        ds = r.date.isoformat()
        price_map.setdefault(ds, {"X95": None, "DO005": None, "DO001": None,
                                   "confirmed": {}})
        price_map[ds][r.product] = r.price
        price_map[ds]["confirmed"][r.product] = r.is_confirmed
    return price_map


@router.get("", response_class=HTMLResponse)
def mops_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    pub_date = current_pub_date()
    _, _, trading_days = get_period_for_pub_date(pub_date)
    price_map = _get_period_prices(db, trading_days)

    day_rows = []
    for d in trading_days:
        ds = d.isoformat()
        pm = price_map.get(ds, {})
        conf = pm.get("confirmed", {})
        day_rows.append({
            "date":     ds,
            "weekday":  ["T2", "T3", "T4", "T5", "T6"][d.weekday()],
            "X95":      pm.get("X95"),
            "DO005":    pm.get("DO005"),
            "DO001":    pm.get("DO001"),
            "conf_X95":   conf.get("X95", False),
            "conf_DO005": conf.get("DO005", False),
            "conf_DO001": conf.get("DO001", False),
            "is_past":  d < date.today(),
        })

    confirmed_count = sum(
        1 for r in day_rows
        if r["X95"] is not None and r["conf_X95"]
    )

    return templates.TemplateResponse(request, "mops_input.html", context={
        "user":            user,
        "pub_date":        pub_date.isoformat(),
        "day_rows":        day_rows,
        "confirmed_count": confirmed_count,
        "total_days":      len(trading_days),
        "flashes":         get_flash(request),
    })


@router.post("/save")
async def save_price(request: Request, db: Session = Depends(get_db)):
    """AJAX endpoint — save a single MOPS price."""
    user = get_current_user(request, db)
    body = await request.json()
    date_str: str = body.get("date")
    product: str  = body.get("product")
    price_raw      = body.get("price")
    confirmed: bool = body.get("confirmed", False)

    if not date_str or product not in ("X95", "DO005", "DO001") or price_raw is None:
        return JSONResponse({"ok": False, "error": "Dữ liệu không hợp lệ"}, status_code=400)

    try:
        price = float(price_raw)
        d = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return JSONResponse({"ok": False, "error": "Giá hoặc ngày không hợp lệ"}, status_code=400)

    row = db.query(MopsPrice).filter(
        MopsPrice.date == d, MopsPrice.product == product
    ).first()

    if row:
        row.price = price
        row.is_confirmed = confirmed
        row.updated_by = user.username
    else:
        row = MopsPrice(date=d, product=product, price=price,
                        is_confirmed=confirmed, updated_by=user.username)
        db.add(row)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/confirm")
async def confirm_price(request: Request, db: Session = Depends(get_db)):
    """Mark a price entry as Platts-confirmed."""
    user = get_current_user(request, db)
    body = await request.json()
    date_str: str = body.get("date")
    product: str  = body.get("product")

    try:
        d = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return JSONResponse({"ok": False}, status_code=400)

    row = db.query(MopsPrice).filter(
        MopsPrice.date == d, MopsPrice.product == product
    ).first()
    if row:
        row.is_confirmed = True
        row.updated_by = user.username
        db.commit()
    return JSONResponse({"ok": True})
