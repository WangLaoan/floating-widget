"""
导出 ETF 估值数据为 JSON，供 Electron 悬浮窗实时展示。

数据来源:
  - etf_basic        → ETF 基本信息 (名称、费率)
  - etf_nav          → 净值数据 (价格、历史区间)
  - etf_daily        → 日线行情 (优先使用，含成交额)
  - macro_rate       → 宏观利率 (10年国债)
  - etf_dividend     → 分红记录 (股息率)
  - index_valuation  → 指数估值 (PE/PB 百分位，若已填充)

用法:
  python scripts/export_valuation.py              # 单次导出
  python scripts/export_valuation.py --watch 60   # 定时轮询
"""

import sqlite3
import json
import sys
import os
import time
from pathlib import Path
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "etf_research.db"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_PATH = OUTPUT_DIR / "live-data.json"

# 数据库中可能没有 etf_basic 记录的 ETF 名称映射
NAME_FALLBACK = {
    "513630": ("摩根标普港股通低波红利ETF", "sh"),
    "513500": ("博时标普500ETF", "sh"),
    "513010": ("华夏恒生科技ETF", "sh"),
    "159530": ("易方达机器人ETF", "sz"),
    "159929": ("汇添富中证医药ETF", "sz"),
    "159941": ("广发纳斯达克100ETF", "sz"),
}

# 基于类型的 ROE 估算 (未来接入指数 ROE 数据后替换)
ROE_ESTIMATE = {
    "513630": 10.5, "515180": 11.2, "510880": 10.8, "512890": 11.0,
    "563020": 11.0, "008163": 10.5, "513690": 9.5, "513060": 10.0,
    "513500": 20.0, "159941": 20.0, "513010": 12.0,
    "510050": 13.0, "510300": 12.0, "159915": 15.0, "512100": 9.0,
    "513390": 25.0, "159530": 10.0, "159929": 8.0,
    "511260": 3.0,
}


def get_db():
    return sqlite3.connect(str(DB_PATH))


# =========================== 数据加载 ===========================

def load_etf_basic_map(db):
    """加载 ETF 基本信息: code -> {name, mgmt_fee, cust_fee}"""
    rows = db.execute("SELECT code, name, management_fee, custodian_fee FROM etf_basic").fetchall()
    return {r[0]: {"name": r[1], "mgmt_fee": r[2], "cust_fee": r[3]} for r in rows}

def discover_etf_codes(db):
    """从数据库自动发现所有 ETF code"""
    codes = set()
    for table in ["etf_nav", "etf_daily"]:
        rows = db.execute(f"SELECT DISTINCT code FROM {table}").fetchall()
        codes.update(r[0] for r in rows)
    return sorted(codes)

def load_latest_nav(db, code):
    """最新净值"""
    row = db.execute(
        "SELECT trade_date, unit_nav, acc_nav FROM etf_nav WHERE code=? ORDER BY trade_date DESC LIMIT 1",
        (code,),
    ).fetchone()
    return row

def load_latest_daily(db, code):
    """最新日线"""
    row = db.execute(
        "SELECT trade_date, close, volume, amount FROM etf_daily WHERE code=? ORDER BY trade_date DESC LIMIT 1",
        (code,),
    ).fetchone()
    return row

def load_price_history(db, code, lookback=750):
    """加载价格序列 (优先日线 close，其次 NAV)"""
    daily = db.execute(
        "SELECT trade_date, close FROM etf_daily WHERE code=? ORDER BY trade_date DESC LIMIT ?",
        (code, lookback),
    ).fetchall()

    if len(daily) >= 100:
        return [(r[0], r[1]) for r in daily]

    # 回退到 NAV
    nav = db.execute(
        "SELECT trade_date, unit_nav FROM etf_nav WHERE code=? ORDER BY trade_date DESC LIMIT ?",
        (code, lookback),
    ).fetchall()
    return [(r[0], r[1]) for r in nav]

def calc_percentile(prices):
    """价格在历史区间中的百分位 (越低 = PE/PB 可能越低)"""
    if len(prices) < 60:
        return None, None
    current = prices[0][1]
    pct = sum(1 for _, p in prices if p > current) / len(prices) * 100
    return round(pct, 1), round(pct, 1)

def load_macro(db):
    """最新宏观利率"""
    row = db.execute(
        "SELECT trade_date, ten_year_bond_yield FROM macro_rate ORDER BY trade_date DESC LIMIT 1"
    ).fetchone()
    if row and row[1]:
        return row[0], round(row[1] * 100, 2)  # DB: 0.01767 → 1.77%
    return None, None

def load_dividend_ttm(db, code, current_price):
    """近12个月股息率 TTM (%)"""
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    rows = db.execute(
        "SELECT dividend_per_unit FROM etf_dividend WHERE code=? AND ex_dividend_date >= ?",
        (code, one_year_ago),
    ).fetchall()
    if not rows or not current_price:
        return None
    total = sum(r[0] for r in rows)
    return round(total / current_price * 100, 2)

def load_dividend_latest(db, code):
    """最近一次分红记录"""
    row = db.execute(
        "SELECT dividend_yield, ex_dividend_date FROM etf_dividend WHERE code=? ORDER BY ex_dividend_date DESC LIMIT 1",
        (code,),
    ).fetchone()
    return row

# ETF code → index_code 映射 (用于关联 index_valuation 表)
ETF_TO_INDEX = {
    "510880": "000015",
    "515180": "000922",
    "512890": "H30269",
    "563020": "H30269",
    "510050": "000016",
    "510300": "000300",
    "159915": "399006",
    "512100": "000852",
}

def load_index_val(db, etf_code):
    """加载最新指数估值 (通过 ETF→指数 映射查询)"""
    idx_code = ETF_TO_INDEX.get(etf_code, etf_code)
    row = db.execute(
        "SELECT pe_percentile, pb_percentile, dividend_yield FROM index_valuation WHERE index_code=? ORDER BY trade_date DESC LIMIT 1",
        (idx_code,),
    ).fetchone()
    return row


# =========================== 评分 (与前端 scoring.ts 一致) ===========================

def compute_temperature(pe_pct, pb_pct, roe, erp):
    if pe_pct is None:
        return None
    # 若 PB 分位缺失，用 PE 分位近似 (两者通常高度相关)
    _pb = pb_pct if pb_pct is not None else pe_pct

    valuation_score = 100 - (pe_pct + _pb) / 2

    roe_score = min(100, max(0, (roe / 30) * 100)) if roe else 50
    roa = roe * 0.4 if roe else 5
    roa_score = min(100, max(0, (roa / 15) * 100))
    profitability_score = (roe_score + roa_score) / 2

    risk_score = min(100, max(0, (erp / 8) * 100)) if erp is not None else 50

    weighted = valuation_score * 0.5 + profitability_score * 0.25 + risk_score * 0.25
    return round(max(0, min(100, 100 - weighted)), 1)

def valuation_status(temp):
    if temp is None: return "未知"
    if temp < 30: return "低估"
    if temp <= 70: return "正常"
    return "高估"


# =========================== 主逻辑 ===========================

def export():
    db = get_db()

    basic_map = load_etf_basic_map(db)
    codes = discover_etf_codes(db)
    macro_date, bond10y = load_macro(db)

    trade_date = "N/A"
    data_list = []

    for code in codes:
        # 基本信息
        basic = basic_map.get(code, {})
        name = basic.get("name") or NAME_FALLBACK.get(code, (f"ETF{code}",))[0]
        market = NAME_FALLBACK.get(code, ("", "sh"))[1] if code in NAME_FALLBACK else "sh"

        # 价格: 优先日线 close, 其次 NAV
        daily = load_latest_daily(db, code)
        nav = load_latest_nav(db, code)

        if daily:
            trade_date = daily[0]
            price = daily[1]
            volume = daily[2]
            amount = daily[3]
            price_source = "daily"
        elif nav:
            trade_date = nav[0]
            price = nav[1]
            volume = None
            amount = None
            price_source = "nav"
        else:
            continue  # 无价格数据, 跳过

        # 估值百分位: 优先 index_valuation, 否则价格分位 proxy
        idx_val = load_index_val(db, code)
        if idx_val and idx_val[0] is not None:
            pe_pct = idx_val[0]
            pb_pct = idx_val[1]
            val_source = "index_valuation"
        else:
            history = load_price_history(db, code)
            pe_pct, pb_pct = calc_percentile(history)
            val_source = "price_proxy"

        # ROE
        roe = ROE_ESTIMATE.get(code, 10.0)

        # 股息率: 优先 index_valuation, 其次 TTM 计算, 最后 etf_dividend 记录
        div_yield = None
        if idx_val and idx_val[2] is not None:
            div_yield = idx_val[2]
        else:
            div_yield = load_dividend_ttm(db, code, price)
            if div_yield is None:
                div_rec = load_dividend_latest(db, code)
                if div_rec:
                    div_yield = div_rec[0]

        # ERP = 股息率 - 国债收益率
        erp = None
        if bond10y is not None and div_yield is not None:
            erp = round(div_yield - bond10y, 2)

        # 温度
        temp = compute_temperature(pe_pct, pb_pct, roe, erp)

        data_list.append({
            "code": code,
            "name": name,
            "market": market,
            "price": price,
            "priceSource": price_source,
            "volume": volume,
            "amount": amount,
            "pePercentile": pe_pct,
            "pbPercentile": pb_pct,
            "valSource": val_source,
            "roe": roe,
            "roa": round(roe * 0.4, 1),
            "erp": erp,
            "dividendYield": div_yield,
            "temperature": temp,
            "valuationStatus": valuation_status(temp),
        })

    # 按温度升序
    data_list.sort(key=lambda x: x["temperature"] if x["temperature"] is not None else 999)

    valid_temps = [d["temperature"] for d in data_list if d["temperature"] is not None]
    avg_temp = round(sum(valid_temps) / len(valid_temps), 1) if valid_temps else None
    undervalued = sum(1 for d in data_list if d["valuationStatus"] == "低估")
    avg_erp = round(sum(d["erp"] for d in data_list if d["erp"] is not None) / max(1, sum(1 for d in data_list if d["erp"] is not None)), 2)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    output = {
        "meta": {
            "generated_at": now,
            "trade_date": trade_date,
            "source": "etf_research.db",
            "val_method": "index_valuation优先; 否则用价格分位proxy。接入AKShare填充index_valuation可提升精度。",
        },
        "summary": {
            "totalTemperature": avg_temp,
            "erp": avg_erp,
            "bond10Y": bond10y,
            "undervaluedCount": undervalued,
            "totalCount": len(data_list),
            "updateTime": now,
        },
        "data": data_list,
    }

    db.close()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 简洁输出
    print(f"[{now}] {len(data_list)}只ETF → {OUTPUT_PATH}")
    print(f"  全市场温度: {avg_temp}  |  10Y国债: {bond10y}%  |  ERP: {avg_erp}%  |  低估: {undervalued}/{len(data_list)}")
    for d in data_list:
        print(f"  {d['code']} {d['name'][:14]:14s} T={str(d['temperature']):>5s}  PEpct={str(d['pePercentile']):>5s}  PBpct={str(d['pbPercentile']):>5s}  ROE={d['roe']:>5.1f}%  DY={str(d['dividendYield']):>5s}  [{d['valuationStatus']}]")
    return output


def watch_mode(interval_sec):
    print(f"轮询模式, 间隔{interval_sec}s. Ctrl+C 停止.")
    try:
        while True:
            export()
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        print("\n已停止.")


if __name__ == "__main__":
    if "--watch" in sys.argv:
        idx = sys.argv.index("--watch")
        interval = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 60
        watch_mode(interval)
    else:
        export()
