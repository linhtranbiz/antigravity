#!/usr/bin/env python3
"""
MOIT Pricing Platform — entry point
Usage: python run.py [--port 8000] [--host 0.0.0.0]
"""
import argparse
import subprocess
import sys

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()

    # Seed database on first run
    import os
    if not os.path.exists("moit_pricing.db"):
        print("🌱 Khởi tạo cơ sở dữ liệu lần đầu...")
        import seed
        seed.run()
        print("✅ Khởi tạo xong. Tài khoản mặc định: admin / admin123")

    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
