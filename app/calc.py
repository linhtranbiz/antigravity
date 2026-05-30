"""
MOIT base price formula engine.
Legal basis: TTLT 39/2014 + TTLT 90/2016 + TT 104/2021 + NĐ 80/2023.
"""

import json
import statistics
from typing import Any

BARREL_TO_LITER = 159   # MOIT standard


# ── Default parameters (seeded into DB on first run) ──────────────────────────

DEFAULT_PARAMS: dict[str, Any] = {
    "vcb_rate":       {"value": 26373,  "desc": "Tỷ giá VCB bán BQ 7 ngày (VNĐ/USD)",        "src": "CV 3392/BCT-TTTN 14/5/2026"},
    "lnh_rate":       {"value": 25870,  "desc": "Tỷ giá Liên ngân hàng NHNN (VNĐ/USD)",        "src": "Ước tính — xác nhận Phòng TC"},
    "ethanol_vnd":    {"value": 20686,  "desc": "Giá Ethanol nhiên liệu (VNĐ/lít)",             "src": "Back-solved từ CV 3392; xác nhận MOIT QĐ"},
    "x95_x92_spread": {"value": 2.106,  "desc": "Chênh lệch MOPS X95 vs X92 ($/bbl)",           "src": "CV 3392 kỳ 14/5/2026"},
    "ln_dinh_muc":    {"value": 300,    "desc": "Lợi nhuận định mức (VNĐ/lít)",                 "src": "CV 9673/BTC-QLG 30/6/2025"},
    "premium_if":     {
        "value": {"X95": 4.896, "X92": 1.900, "E5_R92": 3.122, "DO005": 11.909, "DO001": 23.116},
        "desc": "Premium I&F ($/bbl) — chi phí đưa hàng về cảng VN",
        "src":  "CV 4726/BTC-QLG 15/4/2026 ⚠ chưa cập nhật CV 5899 (10/5/2026)",
    },
    "nk_rate":        {
        "value": {"X95": 0.0162, "X92": 0.0, "E5_R92": 0.0, "DO005": 0.0098, "DO001": 0.0},
        "desc": "Thuế nhập khẩu bình quân gia quyền",
        "src":  "CV 3757/BTC-QLG 27/3/2026",
    },
    "cp_kd":          {
        "value": {"X95": 1257, "X92": 1320, "E5": 1342, "DO005": 776, "DO001": 776},
        "desc": "Chi phí kinh doanh định mức (VNĐ/lít)",
        "src":  "CV 4537/BTC-QLG 10/4/2026",
    },
    "bog":            {
        "value": {"X95": 0, "X92": 0, "E5": 0, "DO005": 0, "DO001": 0},
        "desc": "Quỹ bình ổn giá (VNĐ/lít, + = trích, − = chi)",
        "src":  "QĐ 1124/QĐ-BCT 14/5/2026",
    },
    "bvmt":           {
        "value": {"X95": 0, "X92": 0, "E5": 0, "DO005": 0, "DO001": 0},
        "desc": "Thuế bảo vệ môi trường (VNĐ/lít)",
        "src":  "NQ 19/2026/QH16 (0 từ 16/4–30/6/2026)",
    },
    "rate_ttdb":      {
        "value": {"X95": 0.0, "X92": 0.0, "E5": 0.0, "DO005": 0.0, "DO001": 0.0},
        "desc": "Thuế tiêu thụ đặc biệt (tỷ lệ)",
        "src":  "NQ 19/2026/QH16 (0% từ 16/4–30/6/2026)",
    },
    "rate_vat":       {
        "value": {"X95": 0.0, "X92": 0.0, "E5": 0.0, "DO005": 0.0, "DO001": 0.0},
        "desc": "Thuế VAT (tỷ lệ)",
        "src":  "NQ 19/2026/QH16 (0% từ 16/4–30/6/2026)",
    },
    "vcf":            {
        "value": {"X95": 0.9846, "X92": 0.9846, "E5_R92": 0.9846, "DO005": 0.98898, "DO001": 0.99186},
        "desc": "Hệ số quy đổi thể tích VCF (ASTM D1250, nhiệt độ thực tế VN)",
        "src":  "TTLT 39/2014",
    },
}

PRODUCTS = ["E5", "X95", "DO005", "DO001"]
PRODUCT_LABELS = {
    "E5":    "E5 RON 92",
    "X95":   "RON 95-III",
    "DO005": "DO 0,05S",
    "DO001": "DO 0,001S",
}


# ── Parameter loader ──────────────────────────────────────────────────────────

def load_params(db) -> dict:
    """Load all parameters from DB into a flat dict ready for calc functions."""
    from app.models import Parameter
    rows = db.query(Parameter).all()
    raw = {r.key: r.value for r in rows}

    def get(key):
        v = raw.get(key, json.dumps(DEFAULT_PARAMS[key]["value"]))
        parsed = json.loads(v) if isinstance(v, str) else v
        return parsed

    return {
        "vcb":            float(get("vcb_rate")),
        "lnh":            float(get("lnh_rate")),
        "ethanol_vnd":    float(get("ethanol_vnd")),
        "x95_x92_spread": float(get("x95_x92_spread")),
        "ln_dinh_muc":    float(get("ln_dinh_muc")),
        "premium_if":     get("premium_if"),
        "nk_rate":        get("nk_rate"),
        "cp_kd":          get("cp_kd"),
        "bog":            get("bog"),
        "bvmt":           get("bvmt"),
        "rate_ttdb":      get("rate_ttdb"),
        "rate_vat":       get("rate_vat"),
        "vcf":            get("vcf"),
    }


# ── Core formula ──────────────────────────────────────────────────────────────

def _cif(mops: float, premium: float, vcb: float, vcf: float) -> float:
    return (mops + premium) * vcb / BARREL_TO_LITER * vcf


def _nk(mops: float, premium: float, lnh: float, vcf: float, rate: float) -> float:
    return (mops + premium) * lnh / BARREL_TO_LITER * vcf * rate


def calc_product(product: str, mops_avg: float, params: dict) -> dict:
    """
    Full waterfall for one product.
    For E5 pass the R92 MOPS average.
    """
    vcf = params["vcf"].get(product if product != "E5" else "E5_R92", 0.9846)

    if product == "E5":
        cif_gas = _cif(mops_avg, params["premium_if"]["E5_R92"], params["vcb"], vcf)
        cif     = cif_gas * 0.95 + params["ethanol_vnd"] * 0.05
        nk      = 0.0
    else:
        cif = _cif(mops_avg, params["premium_if"][product], params["vcb"], vcf)
        nk  = _nk(mops_avg, params["premium_if"][product], params["lnh"], vcf,
                  params["nk_rate"].get(product, 0))

    ttdb = (cif + nk) * params["rate_ttdb"].get(product, 0)
    bvmt = params["bvmt"].get(product, 0)
    cp   = params["cp_kd"].get(product, 0)
    ln   = params["ln_dinh_muc"]
    bog  = params["bog"].get(product, 0)
    sub  = cif + nk + ttdb + bvmt + cp + ln + bog
    vat  = sub * params["rate_vat"].get(product, 0)

    return {
        "CIF":   round(cif),
        "NK":    round(nk),
        "TTDB":  round(ttdb),
        "BVMT":  bvmt,
        "CP_KD": cp,
        "LN":    ln,
        "BOG":   bog,
        "VAT":   round(vat),
        "total": round(sub + vat),
    }


def calc_all(mops_avgs: dict, params: dict) -> dict:
    """
    mops_avgs: {X95, X92, DO005, DO001}
    Returns waterfall dict keyed by product code.
    """
    return {
        "E5":    calc_product("E5",    mops_avgs["X92"],   params),
        "X95":   calc_product("X95",   mops_avgs["X95"],   params),
        "DO005": calc_product("DO005", mops_avgs["DO005"], params),
        "DO001": calc_product("DO001", mops_avgs["DO001"], params),
    }


def sensitivity_grid(base_mops: float, params: dict,
                     mops_deltas=(-4, -2, 0, 2, 4),
                     vcb_deltas=(-300, -150, 0, 150, 300)) -> dict:
    """Sensitivity for RON 95 — returns grid rows and column MOPS values."""
    rows = []
    for dv in vcb_deltas:
        p = dict(params)
        p["vcb"] = params["vcb"] + dv
        p["lnh"] = params["lnh"] + dv
        cells = []
        for dm in mops_deltas:
            bp = calc_product("X95", base_mops + dm, p)["total"]
            cells.append({"mops": round(base_mops + dm, 2), "price": bp,
                          "is_base": (dv == 0 and dm == 0)})
        rows.append({"vcb": p["vcb"], "cells": cells, "is_base": dv == 0})
    return {
        "mops_cols": [round(base_mops + dm, 2) for dm in mops_deltas],
        "rows": rows,
    }


def rule_of_thumb(params: dict) -> dict:
    vcb = params["vcb"]
    def _d(vcf, nk_rate, weight=1.0):
        return round((1 + nk_rate) * vcb / BARREL_TO_LITER * vcf * weight)
    return {
        "X95":   _d(params["vcf"]["X95"],   params["nk_rate"]["X95"]),
        "E5":    _d(params["vcf"]["E5_R92"], 0, 0.95),
        "DO005": _d(params["vcf"]["DO005"],  params["nk_rate"]["DO005"]),
        "DO001": _d(params["vcf"]["DO001"],  params["nk_rate"]["DO001"]),
    }
