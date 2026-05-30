import json
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Parameter, User
from app.auth import require_admin, hash_password, flash, get_flash
from app.calc import DEFAULT_PARAMS

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")

# ── Parameters ────────────────────────────────────────────────────────────────

PARAM_GROUPS = {
    "Tỷ giá": ["vcb_rate", "lnh_rate"],
    "MOPS & Blending": ["x95_x92_spread", "ethanol_vnd"],
    "Premium I&F ($/bbl)": ["premium_if"],
    "Thuế nhập khẩu": ["nk_rate"],
    "Chi phí & LN định mức": ["cp_kd", "ln_dinh_muc"],
    "Quỹ BOG": ["bog"],
    "Thuế BVMT": ["bvmt"],
    "Thuế TTĐB": ["rate_ttdb"],
    "Thuế VAT": ["rate_vat"],
    "Hệ số VCF": ["vcf"],
}

SCALAR_PARAMS = {"vcb_rate", "lnh_rate", "x95_x92_spread", "ethanol_vnd", "ln_dinh_muc"}
PRODUCT_KEYS  = ["X95", "X92", "E5", "E5_R92", "DO005", "DO001"]


@router.get("/params", response_class=HTMLResponse)
def params_page(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    rows = {r.key: r for r in db.query(Parameter).all()}

    params_data = {}
    for key, meta in DEFAULT_PARAMS.items():
        row = rows.get(key)
        raw_val = row.value if row else json.dumps(meta["value"])
        try:
            parsed = json.loads(raw_val)
        except (json.JSONDecodeError, TypeError):
            parsed = raw_val

        params_data[key] = {
            "value":      parsed,
            "raw":        raw_val,
            "desc":       meta["desc"],
            "src":        row.source_doc if row else meta["src"],
            "updated_by": row.updated_by if row else "—",
            "updated_at": row.updated_at.strftime("%d/%m/%Y %H:%M") if row and row.updated_at else "—",
            "is_scalar":  key in SCALAR_PARAMS,
        }

    return templates.TemplateResponse(request, "admin_params.html", context={
        "user":         user,
        "params_data":  params_data,
        "param_groups": PARAM_GROUPS,
        "product_keys": [k for k in PRODUCT_KEYS if k != "E5_R92"],
        "flashes":      get_flash(request),
    })


@router.post("/params/update")
async def update_param(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    body = await request.json()
    key        = body.get("key")
    value_raw  = body.get("value")
    source_doc = body.get("source_doc", "")

    if key not in DEFAULT_PARAMS:
        return JSONResponse({"ok": False, "error": "Tham số không hợp lệ"}, status_code=400)

    # Validate & serialize
    try:
        if key in SCALAR_PARAMS:
            val_serialized = json.dumps(float(value_raw))
        else:
            val_obj = json.loads(value_raw) if isinstance(value_raw, str) else value_raw
            val_serialized = json.dumps(val_obj)
    except (ValueError, json.JSONDecodeError) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    row = db.query(Parameter).filter(Parameter.key == key).first()
    if row:
        row.value      = val_serialized
        row.source_doc = source_doc
        row.updated_by = user.username
    else:
        row = Parameter(key=key, value=val_serialized,
                        description=DEFAULT_PARAMS[key]["desc"],
                        source_doc=source_doc, updated_by=user.username)
        db.add(row)
    db.commit()
    return JSONResponse({"ok": True})


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    all_users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(request, "admin_users.html", context={
        "user":      user,
        "all_users": all_users,
        "flashes":   get_flash(request),
    })


@router.post("/users/create")
def create_user(request: Request,
                username:     str  = Form(...),
                display_name: str  = Form(""),
                email:        str  = Form(""),
                password:     str  = Form(...),
                role:         str  = Form("viewer"),
                db: Session = Depends(get_db)):
    require_admin(request, db)
    if db.query(User).filter(User.username == username).first():
        flash(request, f"Tên đăng nhập '{username}' đã tồn tại.", "danger")
        return RedirectResponse("/admin/users", status_code=303)
    u = User(username=username, display_name=display_name or username,
             email=email or None, password_hash=hash_password(password), role=role)
    db.add(u)
    db.commit()
    flash(request, f"Đã tạo người dùng '{username}'.", "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/toggle/{user_id}")
def toggle_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        flash(request, "Không tìm thấy người dùng.", "danger")
    elif target.id == admin.id:
        flash(request, "Không thể vô hiệu hoá chính mình.", "warning")
    else:
        target.is_active = not target.is_active
        db.commit()
        status = "kích hoạt" if target.is_active else "vô hiệu hoá"
        flash(request, f"Đã {status} người dùng '{target.username}'.", "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/reset-password/{user_id}")
def reset_password(user_id: int, request: Request,
                   new_password: str = Form(...),
                   db: Session = Depends(get_db)):
    require_admin(request, db)
    target = db.query(User).filter(User.id == user_id).first()
    if target:
        target.password_hash = hash_password(new_password)
        db.commit()
        flash(request, f"Đã đặt lại mật khẩu cho '{target.username}'.", "success")
    return RedirectResponse("/admin/users", status_code=303)
