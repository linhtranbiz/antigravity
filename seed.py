"""
Seed script — populates default admin user and formula parameters.
Run automatically on first startup via run.py.
"""
import json
from app.database import init_db, SessionLocal
from app.models import User, Parameter
from app.auth import hash_password
from app.calc import DEFAULT_PARAMS


def run():
    init_db()
    db = SessionLocal()
    try:
        # Default admin user
        if not db.query(User).filter(User.username == "admin").first():
            admin = User(
                username     = "admin",
                display_name = "Administrator",
                email        = "admin@company.vn",
                password_hash = hash_password("admin123"),
                role         = "admin",
                is_active    = True,
            )
            db.add(admin)

        # Default viewer
        if not db.query(User).filter(User.username == "viewer").first():
            viewer = User(
                username     = "viewer",
                display_name = "PKD Viewer",
                password_hash = hash_password("viewer123"),
                role         = "viewer",
                is_active    = True,
            )
            db.add(viewer)

        # Seed formula parameters
        for key, meta in DEFAULT_PARAMS.items():
            if not db.query(Parameter).filter(Parameter.key == key).first():
                p = Parameter(
                    key         = key,
                    value       = json.dumps(meta["value"]),
                    description = meta["desc"],
                    source_doc  = meta["src"],
                    updated_by  = "seed",
                )
                db.add(p)

        db.commit()
        print("✅ Seed hoàn tất.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
