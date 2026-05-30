from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text, Boolean
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"
    id           = Column(Integer, primary_key=True, index=True)
    username     = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100))
    email        = Column(String(100), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    role         = Column(String(20), default="viewer")   # "admin" | "viewer"
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, server_default=func.now())


class MopsPrice(Base):
    __tablename__ = "mops_prices"
    id           = Column(Integer, primary_key=True, index=True)
    date         = Column(Date, nullable=False, index=True)
    product      = Column(String(10), nullable=False)   # X95 | DO005 | DO001
    price        = Column(Float, nullable=False)
    is_confirmed = Column(Boolean, default=False)       # True = Platts confirmed
    updated_by   = Column(String(50))
    updated_at   = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        __import__("sqlalchemy").UniqueConstraint("date", "product", name="uq_mops_date_product"),
    )


class Parameter(Base):
    __tablename__ = "parameters"
    id          = Column(Integer, primary_key=True, index=True)
    key         = Column(String(100), unique=True, nullable=False)
    value       = Column(Text, nullable=False)           # JSON string
    description = Column(String(500))
    source_doc  = Column(String(300))
    updated_by  = Column(String(50))
    updated_at  = Column(DateTime, server_default=func.now(), onupdate=func.now())


class KyResult(Base):
    __tablename__ = "ky_results"
    id               = Column(Integer, primary_key=True, index=True)
    publication_date = Column(Date, nullable=False, unique=True, index=True)
    period_start     = Column(Date, nullable=False)
    period_end       = Column(Date, nullable=False)
    mops_avgs        = Column(Text)   # JSON: {X95, X92, DO005, DO001}
    vcb_rate         = Column(Float)
    lnh_rate         = Column(Float)
    results          = Column(Text)   # JSON: {E5, X95, DO005, DO001} waterfall
    saved_by         = Column(String(50))
    created_at       = Column(DateTime, server_default=func.now())
