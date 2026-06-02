"""
填充 index_valuation 表: 从 AKShare 拉取指数 PE/PB/股息率及历史百分位。

数据来源:
  - stock_index_pe_lg  → PE 历史 (5000+ rows), 计算历史分位
  - stock_index_pb_lg  → PB 历史 (5000+ rows), 计算历史分位
  - stock_zh_index_value_csindex → 股息率 (latest 20 rows)
  - stock_zh_index_hist_csindex  → PE 历史 (备选, 用于中证红利等)

用法:
  python scripts/fetch_index_valuation.py              # 一次性填充
  python scripts/fetch_index_valuation.py --update     # 增量更新最新日
"""

import sqlite3
import sys
import time
import random
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "etf_research.db"

# =========================== 指数映射 ===========================
# key = index_code (存入 index_valuation 的标识)
# ak_pe_name = stock_index_pe_lg 用的名称 (None 表示不支持)
# ak_val_code = stock_zh_index_value_csindex 用的代码 (用于股息率)
# ak_hist_code = stock_zh_index_hist_csindex 用的代码 (备选 PE)
INDEX_MAP = {
    "000015": {"name": "上证红利",     "ak_pe_name": "上证红利", "ak_val_code": "000015",  "ak_hist_code": "000015"},
    "000922": {"name": "中证红利",     "ak_pe_name": None,       "ak_val_code": "000922",  "ak_hist_code": "000922"},
    "H30269": {"name": "中证红利低波", "ak_pe_name": None,       "ak_val_code": "H30269",  "ak_hist_code": "H30269"},
    "399324": {"name": "深证红利",     "ak_pe_name": "深证红利", "ak_val_code": "399324",  "ak_hist_code": None},
    "000016": {"name": "上证50",       "ak_pe_name": "上证50",   "ak_val_code": "000016",  "ak_hist_code": "000016"},
    "000300": {"name": "沪深300",      "ak_pe_name": "沪深300",  "ak_val_code": "000300",  "ak_hist_code": "000300"},
    "399006": {"name": "创业板指",     "ak_pe_name": None,       "ak_val_code": None,      "ak_hist_code": None},
    "000852": {"name": "中证1000",     "ak_pe_name": "中证1000", "ak_val_code": "000852",  "ak_hist_code": "000852"},
}

# ETF → index_code 映射 (更新 etf_basic 用)
ETF_INDEX_MAP = {
    "510880": "000015",
    "515180": "000922",
    "512890": "H30269",
    "563020": "H30269",
    "008163": None,  # S&P 指数, AKShare 不支持
}


def get_db():
    return sqlite3.connect(str(DB_PATH))

def init_table(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS index_valuation (
            trade_date TEXT,
            index_code TEXT,
            pe REAL,
            pb REAL,
            dividend_yield REAL,
            pe_percentile REAL,
            pb_percentile REAL,
            dividend_yield_percentile REAL,
            PRIMARY KEY (trade_date, index_code)
        )
    """)
    db.commit()

def calc_percentile(series, value):
    """计算 value 在 series 中的历史分位 (越低越便宜)"""
    if value is None or len(series) < 60:
        return None
    return round((series < value).sum() / len(series) * 100, 1)

def fetch_pe_lg(name):
    """从 stock_index_pe_lg 拉取 PE 历史"""
    import akshare as ak
    df = ak.stock_index_pe_lg(symbol=name)
    # Columns: 日期, 指数, 等权静态市盈率, 静态市盈率, 静态市盈率中位数, 等权滚动市盈率, 滚动市盈率, 滚动市盈率中位数
    df.columns = ['date', 'index_val', 'ew_static_pe', 'static_pe', 'static_pe_median',
                   'ew_ttm_pe', 'ttm_pe', 'ttm_pe_median']
    df['date'] = df['date'].astype(str)
    return df

def fetch_pb_lg(name):
    """从 stock_index_pb_lg 拉取 PB 历史"""
    import akshare as ak
    df = ak.stock_index_pb_lg(symbol=name)
    # Columns: 日期, 指数, 市净率, 加权市净率, 市净率中位数
    df.columns = ['date', 'index_val', 'pb', 'weighted_pb', 'pb_median']
    df['date'] = df['date'].astype(str)
    return df

def fetch_val_csindex(code):
    """从 stock_zh_index_value_csindex 拉取每日估值快照 (PE + 股息率)"""
    import akshare as ak
    df = ak.stock_zh_index_value_csindex(symbol=code)
    # Columns: 日期, 指数代码, ..., 市盈率1, 市盈率2, 股息率1, 股息率2
    date_col = df.columns[0]
    pe1_col = df.columns[6]
    pe2_col = df.columns[7]
    dy1_col = df.columns[8]
    dy2_col = df.columns[9]
    df = df.rename(columns={date_col: 'date', pe1_col: 'pe1', pe2_col: 'pe2',
                             dy1_col: 'dy1', dy2_col: 'dy2'})
    df['date'] = df['date'].astype(str)
    return df

def fetch_hist_csindex(code):
    """从 stock_zh_index_hist_csindex 拉取历史行情 (含滚动市盈率)"""
    import akshare as ak
    df = ak.stock_zh_index_hist_csindex(symbol=code)
    # Columns include: 日期, 滚动市盈率 (last column)
    date_col = df.columns[0]
    pe_col = df.columns[-1]
    df = df.rename(columns={date_col: 'date', pe_col: 'ttm_pe'})
    df['date'] = df['date'].astype(str)
    return df[['date', 'ttm_pe']]

def upsert_valuation(db, rows):
    """批量 upsert 估值数据"""
    sql = """
        INSERT OR REPLACE INTO index_valuation
            (trade_date, index_code, pe, pb, dividend_yield, pe_percentile, pb_percentile, dividend_yield_percentile)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    db.executemany(sql, rows)
    db.commit()

def update_etf_basic(db):
    """回填 etf_basic.index_code"""
    for etf_code, index_code in ETF_INDEX_MAP.items():
        if index_code:
            db.execute("UPDATE etf_basic SET index_code=? WHERE code=? AND index_code IS NULL",
                       (index_code, etf_code))
    db.commit()

def fetch_all():
    db = get_db()
    init_table(db)

    total_inserted = 0

    for idx_code, cfg in INDEX_MAP.items():
        name = cfg['name']
        pe_name = cfg['ak_pe_name']
        val_code = cfg['ak_val_code']
        hist_code = cfg['ak_hist_code']

        print(f"\n{'='*50}")
        print(f"处理: {name} ({idx_code})")

        pe_df = None
        pb_df = None
        pe_series = None  # for percentile calculation
        pb_series = None
        dy_map = {}       # date → dividend_yield

        # 1. PE data
        if pe_name:
            try:
                pe_df = fetch_pe_lg(pe_name)
                pe_series = pe_df['static_pe']
                print(f"  PE (pe_lg): {len(pe_df)} rows, range {pe_series.min():.1f}~{pe_series.max():.1f}, latest={pe_series.iloc[-1]:.2f}")
                time.sleep(random.uniform(1.0, 2.0))
            except Exception as e:
                print(f"  PE (pe_lg): FAILED - {e}")
        elif hist_code:
            try:
                pe_df = fetch_hist_csindex(hist_code)
                pe_series = pe_df['ttm_pe'].dropna()
                print(f"  PE (hist_csindex): {len(pe_df)} rows, PE range {pe_series.min():.1f}~{pe_series.max():.1f}")
                time.sleep(random.uniform(1.0, 2.0))
            except Exception as e:
                print(f"  PE (hist_csindex): FAILED - {e}")
                # Fallback: use val_csindex for 20-row snapshot
                try:
                    pe_df = fetch_val_csindex(val_code) if val_code else None
                    if pe_df is not None:
                        pe_series = pe_df['pe1']
                        print(f"  PE (val_csindex fallback): {len(pe_df)} rows")
                except Exception:
                    pass

        # 2. PB data
        if pe_name:
            try:
                pb_df = fetch_pb_lg(pe_name)
                pb_series = pb_df['pb']
                print(f"  PB (pb_lg): {len(pb_df)} rows, range {pb_series.min():.2f}~{pb_series.max():.2f}, latest={pb_series.iloc[-1]:.2f}")
                time.sleep(random.uniform(1.0, 2.0))
            except Exception as e:
                print(f"  PB (pb_lg): FAILED - {e}")

        # 3. Dividend yield
        if val_code:
            try:
                dy_df = fetch_val_csindex(val_code)
                for _, row in dy_df.iterrows():
                    dy_map[str(row['date'])] = row['dy1']
                print(f"  DY (val_csindex): {len(dy_df)} rows, latest={list(dy_map.values())[-1] if dy_map else 'N/A'}")
                time.sleep(random.uniform(1.0, 2.0))
            except Exception as e:
                print(f"  DY (val_csindex): FAILED - {e}")

        # 4. Build rows and calculate percentiles
        if pe_df is None:
            print(f"  → 跳过 (无 PE 数据)")
            continue

        rows = []
        for _, row in pe_df.iterrows():
            date = str(row['date'])
            pe = float(row['static_pe']) if pe_name and 'static_pe' in row.index else None
            if pe is None and 'ttm_pe' in row.index:
                pe = float(row['ttm_pe']) if row['ttm_pe'] is not None else None
            if pe is None and 'pe1' in row.index:
                pe = float(row['pe1'])

            # PB from pb_df (same date)
            pb = None
            if pb_df is not None:
                pb_row = pb_df[pb_df['date'] == date]
                if len(pb_row) > 0:
                    pb = float(pb_row.iloc[0]['pb'])

            dy = dy_map.get(date)

            # Percentiles
            pe_pct = calc_percentile(pe_series, pe) if pe_series is not None else None
            pb_pct = calc_percentile(pb_series, pb) if pb_series is not None and pb is not None else None

            rows.append((date, idx_code, pe, pb, dy, pe_pct, pb_pct, None))

        upsert_valuation(db, rows)
        total_inserted += len(rows)
        print(f"  → 写入 {len(rows)} 行")

    # 5. Update etf_basic
    update_etf_basic(db)
    db.close()

    print(f"\n{'='*50}")
    print(f"完成! 共写入 {total_inserted} 行到 index_valuation.")
    print(f"数据库: {DB_PATH}")


def load_existing_pe_series(db, idx_code):
    """从 DB 加载现有 PE 序列用于百分位计算"""
    rows = db.execute(
        "SELECT pe FROM index_valuation WHERE index_code=? AND pe IS NOT NULL ORDER BY trade_date",
        (idx_code,)
    ).fetchall()
    import pandas as pd
    return pd.Series([r[0] for r in rows]) if rows else None


def load_existing_pb_series(db, idx_code):
    """从 DB 加载现有 PB 序列用于百分位计算"""
    rows = db.execute(
        "SELECT pb FROM index_valuation WHERE index_code=? AND pb IS NOT NULL ORDER BY trade_date",
        (idx_code,)
    ).fetchall()
    import pandas as pd
    return pd.Series([r[0] for r in rows]) if rows else None


def update_latest():
    """增量更新: 拉取最近数据, 合并历史计算百分位"""
    import pandas as pd

    db = get_db()
    init_table(db)

    for idx_code, cfg in INDEX_MAP.items():
        name = cfg['name']
        pe_name = cfg['ak_pe_name']
        val_code = cfg['ak_val_code']

        latest_db = db.execute(
            "SELECT MAX(trade_date) FROM index_valuation WHERE index_code=?",
            (idx_code,)
        ).fetchone()[0]

        new_rows = []

        # ---- PE + 股息率 ----
        if pe_name:
            # 有 pe_lg 支持的指数: 拉 PE + PB 历史
            try:
                pe_df = fetch_pe_lg(pe_name)
                pb_df = fetch_pb_lg(pe_name)
                time.sleep(random.uniform(1.0, 2.0))

                if latest_db:
                    pe_df = pe_df[pe_df['date'] > latest_db]
                    if pb_df is not None:
                        pb_df = pb_df[pb_df['date'] > latest_db]

                if len(pe_df) == 0:
                    print(f"  {name} ({idx_code}): PE 已是最新 ({latest_db})")
                else:
                    # Build pb lookup
                    pb_map = {}
                    if pb_df is not None:
                        for _, r in pb_df.iterrows():
                            pb_map[str(r['date'])] = float(r['pb'])

                    for _, row in pe_df.iterrows():
                        date = str(row['date'])
                        pe = float(row['static_pe'])
                        pb = pb_map.get(date)
                        new_rows.append((date, idx_code, pe, pb, None, None, None, None))
                    print(f"  {name} ({idx_code}): PE 新增 {len(new_rows)} 行")

                # 股息率 (从 val_csindex, 无论 PE 是否新增)
                if val_code:
                    try:
                        dy_df = fetch_val_csindex(val_code)
                        time.sleep(random.uniform(1.0, 2.0))
                        dy_map = {}
                        for _, r in dy_df.iterrows():
                            dy_map[str(r['date'])] = float(r['dy1'])
                        if latest_db:
                            dy_map = {d: v for d, v in dy_map.items() if d > latest_db}
                        # 合并到 new_rows 或更新已有行
                        for date_str, dy in dy_map.items():
                            found = False
                            for i, (d, c, pe, pb, _, _, _, _) in enumerate(new_rows):
                                if d == date_str:
                                    new_rows[i] = (d, c, pe, pb, dy, None, None, None)
                                    found = True
                                    break
                            if not found:
                                new_rows.append((date_str, idx_code, None, None, dy, None, None, None))
                        print(f"  {name} ({idx_code}): 股息率 新增 {len(dy_map)} 行")
                    except Exception as e:
                        print(f"  {name} ({idx_code}): 股息率 FAILED - {e}")

            except Exception as e:
                print(f"  {name} ({idx_code}): FAILED - {e}")
                continue

        elif val_code:
            # 无 pe_lg 支持, 仅用 val_csindex (PE + 股息率, 约20条)
            try:
                df = fetch_val_csindex(val_code)
                time.sleep(random.uniform(1.0, 2.0))
                if latest_db:
                    df = df[df['date'] > latest_db]
                if len(df) == 0:
                    print(f"  {name} ({idx_code}): 已是最新 ({latest_db})")
                else:
                    for _, row in df.iterrows():
                        date = str(row['date'])
                        pe = float(row['pe1'])
                        dy = float(row['dy1']) if row['dy1'] else None
                        new_rows.append((date, idx_code, pe, None, dy, None, None, None))
                    print(f"  {name} ({idx_code}): PE+股息率 新增 {len(new_rows)} 行")
            except Exception as e:
                print(f"  {name} ({idx_code}): val_csindex FAILED - {e}")
                continue

        # ---- 写入新行 ----
        if new_rows:
            upsert_valuation(db, new_rows)

        # ---- 重新计算所有百分位 (合并新旧数据) ----
        pe_series = load_existing_pe_series(db, idx_code)
        pb_series = load_existing_pb_series(db, idx_code)
        # 股息率序列: 用 val_csindex 拉到的数据 + DB 中已有数据
        dy_rows = db.execute(
            "SELECT dividend_yield FROM index_valuation WHERE index_code=? AND dividend_yield IS NOT NULL ORDER BY trade_date",
            (idx_code,)
        ).fetchall()
        import pandas as pd
        dy_series = pd.Series([r[0] for r in dy_rows]) if len(dy_rows) >= 20 else None

        if pe_series is not None and len(pe_series) >= 60:
            all_rows = db.execute(
                "SELECT trade_date, pe, pb, dividend_yield FROM index_valuation WHERE index_code=? ORDER BY trade_date",
                (idx_code,)
            ).fetchall()

            update_pcts = []
            for trade_date, pe, pb, dy in all_rows:
                pe_pct = calc_percentile(pe_series, pe)
                pb_pct = calc_percentile(pb_series, pb) if pb_series is not None and pb is not None and len(pb_series) >= 60 else None
                dy_pct = calc_percentile(dy_series, dy) if dy_series is not None and dy is not None else None

                update_pcts.append((pe_pct, pb_pct, dy_pct, trade_date, idx_code))

            db.executemany(
                "UPDATE index_valuation SET pe_percentile=?, pb_percentile=?, dividend_yield_percentile=? WHERE trade_date=? AND index_code=?",
                update_pcts
            )
            db.commit()
            print(f"  {name} ({idx_code}): 百分位已更新 ({len(update_pcts)} 行)")

    update_etf_basic(db)
    db.close()
    print("\n增量更新完成.")


if __name__ == "__main__":
    if "--update" in sys.argv:
        update_latest()
    else:
        fetch_all()
