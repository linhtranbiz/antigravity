#!/usr/bin/env python3
"""
MOIT Base Price Forecast Model — Kỳ 21/05/2026
=================================================
Chu kỳ MOPS: 12/05 – 20/05/2026 (7 phiên, trừ T7/CN 17–18/5)
Công bố:     15h00 Thứ Năm 21/05/2026

Căn cứ pháp lý:
  - TTLT 39/2014/TTLT-BCT-BTC + TTLT 90/2016  (cấu trúc công thức)
  - Thông tư 104/2021/TT-BTC                    (yếu tố cấu thành & tỷ giá)
  - Nghị định 80/2023/NĐ-CP                     (chu kỳ 7 ngày, từ 17/11/2023)
  - NQ 19/2026/QH16                             (TTĐB=0%, BVMT=0, VAT=0% từ 16/4–30/6/2026)

Calibrated against CV 3392/BCT-TTTN 14/5/2026:
  E5 RON92=23,134  RON95-III=24,078  DO0.05S=27,226

Usage:
  1. Update MOPS_ESTIMATED with actual Platts closes as they arrive (15–20/5).
  2. Update VCB_SELL_7DAY and LNH_7DAY once 7-day averages are confirmed.
  3. If Finance confirms CV 5899 Premium I&F numbers, update PREMIUM_IF.
  4. Run:  python3 moit_forecast.py
"""

import statistics

# ─── CONVERSION CONSTANTS ──────────────────────────────────────────────────────

BARREL_TO_LITER = 159          # MOIT standard (rounded from 158.987 L/bbl at 15°C)

# Volume Correction Factors — ASTM D1250, ambient temp Vietnam ~30°C
VCF = {
    "X95":    0.9846,
    "X92":    0.9846,
    "E5_R92": 0.9846,
    "DO005":  0.98898,
    "DO001":  0.99186,
}

# ─── PREMIUM I&F ($/bbl) ───────────────────────────────────────────────────────
# Source: CV 4726/BTC-QLG ngày 15/4/2026 (currently in file)
# *** ACTION REQUIRED: Verify CV 5899/BTC-QLG ngày 10/5/2026 with Finance dept ***
# If CV 5899 has updated values, replace the numbers below.

PREMIUM_IF = {
    "X95":    4.896,
    "X92":    1.900,
    "E5_R92": 3.122,   # Premium for R92 gasoline base of E5
    "DO005":  11.909,
    "DO001":  23.116,
}

# ─── IMPORT TAX RATES ──────────────────────────────────────────────────────────
# Weighted average per CV 3757/BTC-QLG ngày 27/3/2026
# Hải quan applies to CIF value at Liên ngân hàng rate

NK_RATE = {
    "X95":    0.0162,  # 1.62%
    "X92":    0.0000,
    "E5_R92": 0.0000,  # R92 component of E5: 0%
    "DO005":  0.0098,  # 0.98%
    "DO001":  0.0000,
}

# ─── FIXED COST/MARGIN PARAMETERS ──────────────────────────────────────────────
# CP kinh doanh định mức — CV 4537/BTC-QLG ngày 10/4/2026 (VNĐ/lít)
CP_KD = {
    "X95":   1_257,
    "X92":   1_320,
    "E5":    1_342,
    "DO005": 776,
    "DO001": 776,
}

LN_DINH_MUC = 300  # VNĐ/lít — CV 9673/BTC-QLG ngày 30/6/2025 (đồng đều)

# Quỹ bình ổn giá — QĐ 1124/QĐ-BCT ngày 14/5/2026 (kỳ này: không trích, không chi)
BOG = {p: 0 for p in ["X95", "X92", "E5", "DO005", "DO001"]}

# Thuế BVMT, TTĐB, VAT — NQ 19/2026/QH16 (0 từ 16/4 đến 30/6/2026)
BVMT      = {p: 0   for p in ["X95", "X92", "E5", "DO005", "DO001"]}
RATE_TTDB = {p: 0.0 for p in ["X95", "X92", "E5", "DO005", "DO001"]}
RATE_VAT  = {p: 0.0 for p in ["X95", "X92", "E5", "DO005", "DO001"]}

# Ethanol price (VNĐ/lít) — verified against CV 3392 published result
# (back-solved: gives E5=23,134 for kỳ 14/5; announced periodically by MOIT)
ETHANOL_VND = 20_686

# ─── X92 SPREAD vs X95 ($/bbl) ────────────────────────────────────────────────
# Derived from CV 3392: X95=130.838, X92=128.732 → spread=2.106
# Applied to estimate X92 when only X95 CSV is available.
X95_X92_SPREAD = 2.106

# ─── EXCHANGE RATES ────────────────────────────────────────────────────────────
# VCB bán BQ 7 ngày   → dùng tính giá CIF (TT 104/2021)
# Liên ngân hàng NHNN → dùng tính thuế NK (Luật Hải quan)
# Default: kỳ 14/5 values (CV 3392). Update when Finance confirms 7-day avg.

VCB_SELL_7DAY = 26_373   # VNĐ/USD
LNH_7DAY      = 25_870   # VNĐ/USD — approximate; confirm with Finance dept

# ─── MOPS FOB SINGAPORE — CONFIRMED DATA ($/bbl) ──────────────────────────────
# Source: Platts MOPS Singapore FOB Cargo, closing prices
# X92 NOT available directly; estimated as X95 − 2.106 (see spread above)

MOPS_CONFIRMED = {
    "2026-05-12": {"X95": 134.73, "DO005": 149.44, "DO001": 160.25},
    "2026-05-13": {"X95": 137.01, "DO005": 154.23, "DO001": 165.41},
    "2026-05-14": {"X95": 139.10, "DO005": 150.54, "DO001": 161.88},
}

# ─── MOPS ESTIMATES — UPDATE DAILY AS PLATTS PUBLISHES ────────────────────────
# Replace each placeholder with actual Platts close when available.
# Current default: flat at last confirmed close (conservative assumption).

MOPS_ESTIMATED = {
    "2026-05-15": {"X95": 139.10, "DO005": 150.54, "DO001": 161.88},  # <- update
    "2026-05-16": {"X95": 139.10, "DO005": 150.54, "DO001": 161.88},  # <- update
    "2026-05-19": {"X95": 139.10, "DO005": 150.54, "DO001": 161.88},  # <- update
    "2026-05-20": {"X95": 139.10, "DO005": 150.54, "DO001": 161.88},  # <- update
}

# ─── REFERENCE: KỲ TRƯỚC (14/5/2026) ──────────────────────────────────────────
KY_TRUOC = {
    "E5":    23_134,
    "X95":   24_078,
    "DO005": 27_226,
    "DO001": None,   # không có trong CV 3392
}

# ─── FORMULA ENGINE ────────────────────────────────────────────────────────────

def cif_vnd(mops_fob: float, premium: float, vcb: float, vcf: float) -> float:
    """Giá CIF VNĐ/lít = (FOB + Premium_IF) × VCB_sell / 159 × VCF"""
    return (mops_fob + premium) * vcb / BARREL_TO_LITER * vcf


def import_tax_vnd(mops_fob: float, premium: float, lnh: float, vcf: float, rate: float) -> float:
    """Thuế NK VNĐ/lít = CIF_LNH × thuế_suất_NK (Hải quan dùng tỷ giá LNH)"""
    cif_tax_base = (mops_fob + premium) * lnh / BARREL_TO_LITER * vcf
    return cif_tax_base * rate


def calc_base_price(
    product: str,
    mops_avg: float,
    vcb: float = VCB_SELL_7DAY,
    lnh: float = LNH_7DAY,
) -> dict:
    """
    Return waterfall breakdown and final base price for a product.
    product: "X95" | "X92" | "E5" | "DO005" | "DO001"
    mops_avg: 7-day average MOPS FOB Singapore ($/bbl)
              For E5, pass the R92 MOPS average (used for gasoline component).
    """
    if product == "E5":
        cif_gas = cif_vnd(mops_avg, PREMIUM_IF["E5_R92"], vcb, VCF["E5_R92"])
        cif = cif_gas * 0.95 + ETHANOL_VND * 0.05
        nk = 0  # R92 component NK=0%, ethanol domestic → no import duty
    else:
        cif = cif_vnd(mops_avg, PREMIUM_IF[product], vcb, VCF[product])
        nk  = import_tax_vnd(mops_avg, PREMIUM_IF[product], lnh, VCF[product], NK_RATE[product])

    pk = product if product != "E5_R92" else "E5"
    ttdb = (cif + nk) * RATE_TTDB.get(product, 0)
    bvmt = BVMT.get(product, 0)
    cp   = CP_KD.get(product, 0)
    ln   = LN_DINH_MUC
    bog  = BOG.get(product, 0)
    sub  = cif + nk + ttdb + bvmt + cp + ln + bog
    vat  = sub * RATE_VAT.get(product, 0)
    total = round(sub + vat)

    return {
        "CIF":         round(cif),
        "NK":          round(nk),
        "TTĐB (=0%)":  round(ttdb),
        "BVMT (=0)":   bvmt,
        "CP KD":       cp,
        "LN định mức": ln,
        "BOG":         bog,
        "VAT (=0%)":   round(vat),
        "Giá cơ sở":   total,
    }


def compute_7day_averages() -> dict:
    """Merge confirmed + estimated MOPS and compute 7-day averages."""
    all_days = {**MOPS_CONFIRMED, **MOPS_ESTIMATED}
    avgs = {}
    for product in ["X95", "DO005", "DO001"]:
        vals = [all_days[d][product] for d in sorted(all_days)]
        avgs[product] = statistics.mean(vals)
    avgs["X92"]    = avgs["X95"] - X95_X92_SPREAD
    avgs["E5_R92"] = avgs["X92"]   # E5 uses R92 MOPS as gasoline base
    return avgs


def rule_of_thumb(vcb: float = VCB_SELL_7DAY) -> dict:
    """VNĐ/lít impact per $1/bbl MOPS move (at current tax regime)."""
    def _delta(product, vcf, nk_rate):
        base = (1 + nk_rate) * vcb / BARREL_TO_LITER * vcf
        return round(base)
    return {
        "X95":   _delta("X95",   VCF["X95"],   NK_RATE["X95"]),
        "E5":    round(_delta("E5",    VCF["E5_R92"], 0) * 0.95),  # only gasoline portion
        "DO005": _delta("DO005", VCF["DO005"], NK_RATE["DO005"]),
        "DO001": _delta("DO001", VCF["DO001"], NK_RATE["DO001"]),
    }


# ─── MAIN OUTPUT ───────────────────────────────────────────────────────────────

def run():
    W = 76

    def sep(c="─"):
        print("  " + c * (W - 2))

    def header(text):
        print(f"\n  ┌{'─' * (W - 4)}┐")
        print(f"  │  {text:<{W - 6}}│")
        print(f"  └{'─' * (W - 4)}┘")

    print()
    print("  " + "═" * (W - 2))
    print(f"  {'DỰ BÁO GIÁ CƠ SỞ KỲ CÔNG BỐ 21/05/2026':^{W-2}}")
    print(f"  {'Áp dụng từ 15h00 Thứ Năm 21/5 đến 14h59 Thứ Năm 28/5/2026':^{W-2}}")
    print("  " + "═" * (W - 2))

    # ── MOPS inputs ──────────────────────────────────────────────────────────────
    header("1. MOPS FOB Singapore — 7 phiên đầu vào ($/bbl)")
    print(f"  {'Ngày':<14}{'X95':>9}{'X92 (est)':>12}{'DO 0.05S':>10}{'DO 0.001S':>11}")
    sep()
    all_days = {**MOPS_CONFIRMED, **MOPS_ESTIMATED}
    for d in sorted(all_days):
        x95  = all_days[d]["X95"]
        x92  = x95 - X95_X92_SPREAD
        do05 = all_days[d]["DO005"]
        do001 = all_days[d]["DO001"]
        tag  = " ✓" if d in MOPS_CONFIRMED else " ~"
        print(f"  {d:<14}{x95:>9.2f}{x92:>12.2f}{do05:>10.2f}{do001:>11.2f}{tag}")

    avgs = compute_7day_averages()
    sep()
    print(f"  {'Bình quân 7 ngày':<14}{avgs['X95']:>9.3f}{avgs['X92']:>12.3f}"
          f"{avgs['DO005']:>10.3f}{avgs['DO001']:>11.3f}")
    print(f"\n  Tỷ giá: VCB bán BQ = {VCB_SELL_7DAY:,} VNĐ/USD  |  "
          f"LNH = {LNH_7DAY:,} VNĐ/USD")
    print(f"  ✓ = Platts xác nhận   ~ = ước tính (cập nhật khi có Platts chính thức)")

    # ── Waterfall ────────────────────────────────────────────────────────────────
    header("2. Cấu thành giá cơ sở — Waterfall (VNĐ/lít)")

    products_display = ["E5 RON 92", "RON 95-III", "DO 0.05S", "DO 0.001S"]
    products_key     = ["E5",        "X95",        "DO005",    "DO001"]
    mops_inputs      = [avgs["E5_R92"], avgs["X95"], avgs["DO005"], avgs["DO001"]]

    results = {
        pk: calc_base_price(pk, mi)
        for pk, mi in zip(products_key, mops_inputs)
    }

    col_w = 12
    print(f"  {'Khoản mục':<22}", end="")
    for pd in products_display:
        print(f"{pd:>{col_w}}", end="")
    print()
    sep()

    rows = [
        ("Giá CIF (VNĐ/lít)",  "CIF"),
        ("+ Thuế NK",           "NK"),
        ("+ TTĐB (=0%)",        "TTĐB (=0%)"),
        ("+ CP kinh doanh",     "CP KD"),
        ("+ LN định mức",       "LN định mức"),
        ("+ Quỹ BOG",           "BOG"),
        ("+ BVMT (=0)",         "BVMT (=0)"),
        ("+ VAT (=0%)",         "VAT (=0%)"),
    ]
    for label, key in rows:
        print(f"  {label:<22}", end="")
        for pk in products_key:
            v = results[pk][key]
            print(f"{v:>{col_w},}", end="")
        print()

    sep("═")
    print(f"  {'GIÁ CƠ SỞ DỰ BÁO':<22}", end="")
    forecast = {pk: results[pk]["Giá cơ sở"] for pk in products_key}
    for pk in products_key:
        print(f"{forecast[pk]:>{col_w},}", end="")
    print()

    # ── vs kỳ trước ──────────────────────────────────────────────────────────────
    header("3. So sánh với kỳ 14/05/2026 (CV 3392/BCT-TTTN)")

    ky_map = {"E5": "E5", "X95": "X95", "DO005": "DO005", "DO001": "DO001"}
    print(f"  {'':22}", end="")
    for pd in products_display:
        print(f"{pd:>{col_w}}", end="")
    print()
    sep()

    print(f"  {'Kỳ trước (14/5)':<22}", end="")
    for pk in products_key:
        prev = KY_TRUOC.get(pk)
        print(f"{'N/A' if prev is None else f'{prev:,}':>{col_w}}", end="")
    print()

    print(f"  {'Dự báo (21/5)':<22}", end="")
    for pk in products_key:
        print(f"{forecast[pk]:>{col_w},}", end="")
    print()

    print(f"  {'Chênh lệch (VNĐ)':<22}", end="")
    for pk in products_key:
        prev = KY_TRUOC.get(pk)
        if prev is None:
            print(f"{'N/A':>{col_w}}", end="")
        else:
            diff = forecast[pk] - prev
            print(f"{diff:>+{col_w},}", end="")
    print()

    print(f"  {'Chênh lệch (%)':<22}", end="")
    for pk in products_key:
        prev = KY_TRUOC.get(pk)
        if prev is None:
            print(f"{'N/A':>{col_w}}", end="")
        else:
            pct = (forecast[pk] - prev) / prev * 100
            print(f"{pct:>+{col_w-1}.2f}%", end="")
    print()

    # ── Sensitivity — RON 95 ─────────────────────────────────────────────────────
    header("4. Sensitivity RON 95-III — Giá cơ sở (VNĐ/lít) theo MOPS avg & VCB")

    base_avg = avgs["X95"]
    mops_deltas = [-4, -2, 0, +2, +4]
    vcb_deltas  = [-300, -150, 0, +150, +300]

    # Column headers: MOPS scenarios
    print(f"  {'VCB bán → ':>14}", end="")
    print(f"  {'MOPS X95 ($/bbl)':^55}")
    print(f"  {'↓ VCB (VNĐ/USD)':>16}", end="")
    for dm in mops_deltas:
        m = base_avg + dm
        tag = " [base]" if dm == 0 else ""
        print(f"  {m:>7.2f}{tag if dm == 0 else '':7}", end="")
    print()
    sep()

    for dv in vcb_deltas:
        vcb_s = VCB_SELL_7DAY + dv
        lnh_s = LNH_7DAY + dv  # assume LNH moves in tandem
        tag = " [base]" if dv == 0 else ""
        print(f"  {vcb_s:>14,}{tag:7}", end="")
        for dm in mops_deltas:
            m = base_avg + dm
            bp = calc_base_price("X95", m, vcb_s, lnh_s)["Giá cơ sở"]
            print(f"  {bp:>7,}       ", end="")
        print()

    # ── Rule of thumb ─────────────────────────────────────────────────────────────
    header("5. Rule of thumb — Tác động per $1/bbl MOPS (VNĐ/lít)")
    rot = rule_of_thumb()
    print(f"  {'Sản phẩm':<20}{'Δ Giá cơ sở / $1bbl MOPS':>28}")
    sep()
    names = {"X95": "RON 95-III", "E5": "E5 RON 92 (phần xăng)", "DO005": "DO 0.05S", "DO001": "DO 0.001S"}
    for pk, name in names.items():
        print(f"  {name:<28}  ≈ {rot[pk]:>5,} VNĐ/lít")

    # ── Caveats ───────────────────────────────────────────────────────────────────
    header("6. Lưu ý & action items")
    notes = [
        ("⚠ Premium I&F", "File đang dùng CV 4726 (15/4/2026). Xác nhận CV 5899 (10/5/2026) với Phòng TC."),
        ("⚠ X92 MOPS",    "Ước tính = X95 − 2.106 $/bbl (spread kỳ 14/5). Upload CSV X92 riêng nếu có."),
        ("⚠ Ethanol",     f"Giá {ETHANOL_VND:,} VNĐ/lít back-solved từ E5=23,134 (CV 3392). Xác nhận MOIT QĐ mới nhất."),
        ("⚠ Tỷ giá LNH",  f"LNH={LNH_7DAY:,} là ước tính. Dùng số Phòng TC khi có BQ 7 ngày chính thức."),
        ("⚠ Giai đoạn 0-thuế", "TTĐB=0%, BVMT=0, VAT=0% hết hạn 30/6/2026. Kỳ sau 30/6 giá sẽ tăng ~5,000–6,000 VNĐ/lít."),
        ("ℹ MOPS_ESTIMATED", "Cập nhật file khi Platts xuất bản: 15/5 (chiều nay), 16/5, 19/5, 20/5."),
    ]
    for tag, note in notes:
        print(f"  {tag:<20} {note}")

    print()
    print("  " + "═" * (W - 2))
    print()


if __name__ == "__main__":
    run()
