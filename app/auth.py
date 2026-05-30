import bcrypt
from starlette.requests import Request
from fastapi import HTTPException, status
from app.models import User


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def get_current_user(request: Request, db) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER,
                            headers={"Location": "/login"})
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER,
                            headers={"Location": "/login"})
    return user


def require_admin(request: Request, db) -> User:
    user = get_current_user(request, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Cần quyền Admin")
    return user


def flash(request: Request, message: str, category: str = "info"):
    msgs = request.session.setdefault("flash_messages", [])
    msgs.append({"message": message, "category": category})


def get_flash(request: Request) -> list:
    msgs = request.session.pop("flash_messages", [])
    return msgs
