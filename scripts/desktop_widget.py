"""
超简 ETF 桌面小组件: 系统托盘 + 实时行情 + 估值温度 + 周线MA120

依赖: tkinter (内置), pystray, Pillow (已有)
用法: python scripts/desktop_widget.py
"""

import ctypes
import json
import sqlite3
import sys
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from tkinter import Tk, Frame, Label, Button

from PIL import Image, ImageDraw
import pystray

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# =========================== 配置 ===========================
ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "etf_research.db"
REFRESH_SEC = 10  # 刷新间隔 (秒)

WATCHLIST = {
    "515180": {"name": "中证红利",     "market": "sh", "type": "etf"},
    "563020": {"name": "红利低波",     "market": "sh", "type": "etf"},
    "513630": {"name": "港股红利低波", "market": "sh", "type": "etf"},
    "513500": {"name": "标普500",      "market": "sh", "type": "etf"},
    "H30269": {"name": "红利低波指数", "market": None, "type": "index"},
}

ETF_INDEX_MAP = {"515180": "000922", "563020": "H30269", "513630": None, "513500": None}
ROE_FALLBACK = {"513630": 10.5, "515180": 11.2, "563020": 11.0, "513500": 20.0, "H30269": 11.0}

QUOTE_API = "https://hq.sinajs.cn/list={codes}"

# PushPlus 推送
PUSHPLUS_TOKEN = "f28d79309c2f4d1cb7d80cb06b7aa472"
PUSHPLUS_API = "http://www.pushplus.plus/send"
PUSH_DEVIATION_THRESHOLD = -4.0  # 偏离日MA120 低于 -4% 时推送

# 指数数据缓存
INDEX_CACHE_DIR = Path(__file__).resolve().parent.parent / "data"
INDEX_CACHE_PATH = INDEX_CACHE_DIR / "index_cache.json"

# 窗口风格
FONT_TITLE  = ("Microsoft YaHei UI", 12, "bold")
FONT_PRICE  = ("Consolas", 18, "bold")
FONT_NORMAL = ("Microsoft YaHei UI", 10)
FONT_SMALL  = ("Consolas", 9)
FONT_MINI   = ("Consolas", 8)

# 颜色体系 — 深色面板
C_BG        = "#1a1a2e"
C_CARD      = "#16213e"
C_CARD_ALT  = "#0f3460"
C_TEXT      = "#e0e0e0"
C_TEXT_DIM  = "#8892b0"
C_ACCENT    = "#64ffda"
C_RED       = "#ff6b6b"
C_ORANGE    = "#ffa726"
C_GREEN     = "#66bb6a"
C_BORDER    = "#2a2a4a"


# =========================== 数据获取 ===========================
def fetch_prices():
    """新浪行情 (ETF 实时价格)"""
    etf_codes = {c: i for c, i in WATCHLIST.items() if i.get("type") == "etf"}
    codes = ",".join(f"{info['market']}{code}" for code, info in etf_codes.items())
    url = QUOTE_API.format(codes=codes)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("gbk", errors="replace")
    except Exception:
        return None

    results = {}
    for code, info in etf_codes.items():
        symbol = f"{info['market']}{code}"
        marker = f'hq_str_{symbol}='
        start = text.find(marker)
        if start == -1:
            continue
        start += len(marker) + 1
        end = text.find('"', start)
        if end == -1:
            continue
        fields = text[start:end].split(",")
        if len(fields) < 4:
            continue
        results[code] = {
            "price": float(fields[3]) if fields[3] else None,
            "yesterday_close": float(fields[2]) if fields[2] else None,
        }
    return results


def fetch_index_history(index_code):
    """获取指数日线历史 (AKShare → JSON 缓存). 返回 [(date_str, close), ...] 降序."""
    today = datetime.now().strftime("%Y-%m-%d")

    # 读缓存
    cache = {}
    if INDEX_CACHE_PATH.exists():
        try:
            cache = json.loads(INDEX_CACHE_PATH.read_text(encoding='utf-8'))
        except Exception:
            pass

    if index_code in cache:
        entry = cache[index_code]
        if entry.get("updated") == today and entry.get("prices"):
            return entry["prices"]

    # 从 AKShare 拉取
    try:
        import akshare as ak
        df = ak.stock_zh_index_hist_csindex(symbol=index_code)
        # Columns: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 涨跌幅, 滚动市盈率
        date_col = df.columns[0]
        close_col = df.columns[2]  # 收盘
        prices = []
        for _, row in df.iterrows():
            prices.append([str(row[date_col]), float(row[close_col])])
        prices.sort(key=lambda x: x[0], reverse=True)

        cache[index_code] = {"updated": today, "prices": prices}
        INDEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        INDEX_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
        return prices
    except Exception:
        # 返回过期缓存
        if index_code in cache:
            return cache[index_code].get("prices", [])
        return []


def _compute_weekly_ma120(daily_prices, current_price):
    """
    daily_prices: [(date_str, price), ...] 降序
    current_price: 当前实时价格
    Returns: (weekly_ma120, deviation_pct) 或 (None, None)
    """
    if not daily_prices or len(daily_prices) < 120:
        return None, None

    # 按 ISO 周分组, 取每周第一条 (最新) = 该周最后交易日收盘价
    weekly = {}
    for date_str, price in daily_prices:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        week_key = dt.isocalendar()[:2]  # (year, week_number)
        if week_key not in weekly:
            weekly[week_key] = price

    sorted_weeks = sorted(weekly.keys())
    if len(sorted_weeks) < 120:
        return None, None

    recent_120 = [weekly[w] for w in sorted_weeks[-120:]]
    ma120 = sum(recent_120) / len(recent_120)

    if current_price and ma120:
        deviation = (current_price - ma120) / ma120 * 100
        return round(ma120, 4), round(deviation, 1)
    return round(ma120, 4), None


def send_pushplus(title, content):
    """PushPlus 微信推送, 静默失败"""
    try:
        data = json.dumps({"token": PUSHPLUS_TOKEN, "title": title, "content": content}).encode("utf-8")
        req = urllib.request.Request(PUSHPLUS_API, data=data, headers={
            "Content-Type": "application/json",
        })
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def load_ma_data():
    """
    加载 MA 数据: 日线 MA120 (触发) + 周线 MA120 (偏离)
    返回 {code: {ma120, trigger, weekly_ma120, weekly_dev}}
    """
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    result = {}

    for code, info in WATCHLIST.items():
        entry = {"ma120": None, "trigger": None, "weekly_ma120": None, "weekly_dev": None,
                 "index_price": None}

        if info.get("type") == "index":
            # 从缓存获取指数价格
            index_prices = fetch_index_history(code)
            if index_prices:
                current_idx_price = index_prices[0][1] if index_prices else None
                entry["index_price"] = current_idx_price
                w_ma, w_dev = _compute_weekly_ma120(index_prices, current_idx_price)
                entry["weekly_ma120"] = w_ma
                entry["weekly_dev"] = w_dev
                # 日线 MA120 也从指数数据算
                if len(index_prices) >= 120:
                    ma120 = sum(p[1] for p in index_prices[:120]) / 120
                    entry["ma120"] = round(ma120, 4)
                    entry["trigger"] = round(ma120 * 0.94, 4)
        else:
            # ETF: 不复权收盘价 (etf_daily, fallback etf_nav)
            cur.execute(
                "SELECT trade_date, close FROM etf_daily WHERE code=? ORDER BY trade_date DESC LIMIT 750",
                (code,),
            )
            daily_rows = cur.fetchall()
            if len(daily_rows) < 60:
                cur.execute(
                    "SELECT trade_date, unit_nav FROM etf_nav WHERE code=? ORDER BY trade_date DESC LIMIT 750",
                    (code,),
                )
                daily_rows = cur.fetchall()

            # 日线 MA120 (触发)
            if len(daily_rows) >= 120:
                prices = [r[1] for r in daily_rows[:120]]
                ma120 = sum(prices) / len(prices)
                entry["ma120"] = round(ma120, 4)
                entry["trigger"] = round(ma120 * 0.94, 4)

            # 周线 MA120
            daily_prices = [(r[0], r[1]) for r in daily_rows]
            if daily_prices:
                current_p = daily_prices[0][1]
                w_ma, w_dev = _compute_weekly_ma120(daily_prices, current_p)
                entry["weekly_ma120"] = w_ma
                entry["weekly_dev"] = w_dev

        result[code] = entry
    conn.close()
    return result


def load_valuation():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    result = {}
    for code, info in WATCHLIST.items():
        idx = ETF_INDEX_MAP.get(code) if info.get("type") == "etf" else code
        entry = {"pe": None, "pe_pct": None, "pb_pct": None,
                 "dy": None, "dy_pct": None, "roe": ROE_FALLBACK.get(code),
                 "temperature": None, "status": "N/A"}

        if info.get("type") == "index":
            # 指数直接从 index_valuation 查
            cur.execute(
                """SELECT pe, pb, dividend_yield, pe_percentile, pb_percentile, dividend_yield_percentile
                   FROM index_valuation WHERE index_code=? ORDER BY trade_date DESC LIMIT 1""",
                (code,),
            )
            row = cur.fetchone()
            if row:
                pe, pb, dy, pe_pct, pb_pct, dy_pct = row
                if dy_pct is None and dy is not None:
                    cur.execute(
                        "SELECT dividend_yield FROM index_valuation WHERE index_code=? AND dividend_yield IS NOT NULL ORDER BY trade_date",
                        (code,),
                    )
                    dy_list = [r[0] for r in cur.fetchall()]
                    if len(dy_list) >= 15:
                        dy_pct = round(sum(1 for v in dy_list if v < dy) / len(dy_list) * 100, 1)
                if pb is not None and pe is not None and pe > 0:
                    entry["roe"] = round(pb / pe * 100, 1)
                entry.update({"pe": pe, "pe_pct": pe_pct, "pb_pct": pb_pct,
                              "dy": dy, "dy_pct": dy_pct})
                entry["temperature"] = _calc_temp(pe_pct, pb_pct, dy_pct, code)
                entry["status"] = _temp_status(entry["temperature"])
        elif idx is None:
            # 无指数映射的 ETF: 价格分位 proxy
            cur.execute("SELECT unit_nav FROM etf_nav WHERE code=? ORDER BY trade_date DESC LIMIT 750", (code,))
            prices = [r[0] for r in cur.fetchall()]
            if len(prices) >= 60:
                cur_p = prices[0]
                pct = round(sum(1 for p in prices if p < cur_p) / len(prices) * 100, 1)
                entry["pe_pct"] = pct
                entry["pb_pct"] = pct
                entry["temperature"] = _calc_temp(pct, pct, None, code)
                entry["status"] = _temp_status(entry["temperature"])
        else:
            cur.execute(
                """SELECT pe, pb, dividend_yield, pe_percentile, pb_percentile, dividend_yield_percentile
                   FROM index_valuation WHERE index_code=? ORDER BY trade_date DESC LIMIT 1""",
                (idx,),
            )
            row = cur.fetchone()
            if row:
                pe, pb, dy, pe_pct, pb_pct, dy_pct = row
                if dy_pct is None and dy is not None:
                    cur.execute(
                        "SELECT dividend_yield FROM index_valuation WHERE index_code=? AND dividend_yield IS NOT NULL ORDER BY trade_date",
                        (idx,),
                    )
                    dy_list = [r[0] for r in cur.fetchall()]
                    if len(dy_list) >= 15:
                        dy_pct = round(sum(1 for v in dy_list if v < dy) / len(dy_list) * 100, 1)
                if pb is not None and pe is not None and pe > 0:
                    entry["roe"] = round(pb / pe * 100, 1)
                entry.update({"pe": pe, "pe_pct": pe_pct, "pb_pct": pb_pct,
                              "dy": dy, "dy_pct": dy_pct})
                entry["temperature"] = _calc_temp(pe_pct, pb_pct, dy_pct, code)
                entry["status"] = _temp_status(entry["temperature"])
        result[code] = entry
    conn.close()
    return result


def _calc_temp(pe_pct, pb_pct, dy_pct, code):
    if pe_pct is None:
        return None
    _pb = pb_pct if pb_pct is not None else pe_pct
    if code == "513500":
        return round(0.5 * pe_pct + 0.5 * _pb, 1)
    _dy_inv = (100 - dy_pct) if dy_pct is not None else None
    if _dy_inv is not None:
        return round(0.3 * pe_pct + 0.3 * _pb + 0.4 * _dy_inv, 1)
    return round(0.5 * pe_pct + 0.5 * _pb, 1)


def _temp_status(temp):
    if temp is None: return "N/A"
    if temp < 30: return "低估"
    if temp <= 70: return "正常"
    return "高估"


# =========================== 托盘图标生成 ===========================
def make_tray_icon(color=(70, 130, 180), alert=False):
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if alert:
        draw.rounded_rectangle([2, 2, 30, 30], radius=6, fill=(220, 50, 50))
        draw.text((8, 6), "!", fill="white")
    else:
        draw.rounded_rectangle([2, 2, 30, 30], radius=6, fill=color)
        draw.text((8, 6), "ETF", fill="white")
    return img

TRAY_COLOR_NORMAL = (70, 130, 180)
TRAY_COLOR_ALERT = (220, 50, 50)
FLASH_INTERVAL_MS = 700


# =========================== UI ===========================
class ETFWidget:
    def __init__(self):
        self.root = Tk()
        self.root.title("ETF 监控")
        self.root.geometry("420x560+1200+80")
        self.root.configure(bg=C_BG)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        self.prices = {}
        self.ma_data = {}
        self.val_data = {}
        self.updated_at = "加载中..."
        self._data_lock = threading.Lock()

        self._alert_codes = set()
        self._flash_state = False
        self._flash_job = None
        self._alert_notified = set()
        self._push_notified = set()  # PushPlus 去重

        self._build_ui()
        self._refresh_data()
        self._setup_tray()

        self._stop_event = threading.Event()
        self._bg_thread = threading.Thread(target=self._background_loop, daemon=True)
        self._bg_thread.start()

    # ---- UI 构建 ----
    def _build_ui(self):
        top = Frame(self.root, bg=C_BG)
        top.pack(fill="x", padx=14, pady=(10, 2))
        Label(top, text="ETF 监控", font=FONT_TITLE,
              bg=C_BG, fg=C_TEXT).pack(side="left")
        self._time_lbl = Label(top, text="--:--", font=FONT_SMALL,
                               bg=C_BG, fg=C_TEXT_DIM)
        self._time_lbl.pack(side="right")

        cards_frame = Frame(self.root, bg=C_BG)
        cards_frame.pack(fill="both", expand=True, padx=10, pady=(6, 0))

        self._cards = {}
        for code, info in WATCHLIST.items():
            card = Frame(cards_frame, bg=C_CARD, bd=0, highlightthickness=0)
            card.pack(fill="x", pady=3, padx=0, ipadx=10, ipady=6)

            # Row 1: code + name | temperature + status
            r1 = Frame(card, bg=C_CARD); r1.pack(fill="x")
            # Row 2: 现价 + 偏离日MA120
            r2 = Frame(card, bg=C_CARD); r2.pack(fill="x", pady=(0, 0))
            # Row 3: 日MA120 + 周MA120 + 触发
            r3 = Frame(card, bg=C_CARD); r3.pack(fill="x", pady=(0, 0))
            # Row 4: PE/DY + ROE
            r4 = Frame(card, bg=C_CARD); r4.pack(fill="x")

            Label(r1, text=f"{code} ", font=FONT_NORMAL, bg=C_CARD,
                  fg=C_TEXT_DIM).pack(side="left")
            Label(r1, text=info["name"], font=FONT_NORMAL, bg=C_CARD,
                  fg=C_TEXT).pack(side="left")
            temp_lbl = Label(r1, text="--°", font=FONT_NORMAL, bg=C_CARD, fg=C_ACCENT)
            temp_lbl.pack(side="right")
            status_lbl = Label(r1, text="", font=FONT_SMALL, bg=C_CARD, fg=C_TEXT_DIM, width=5)
            status_lbl.pack(side="right", padx=(0, 4))

            price_lbl = Label(r2, text="--", font=FONT_PRICE, bg=C_CARD, fg=C_TEXT)
            price_lbl.pack(side="left")
            dev_lbl = Label(r2, text="偏离 --", font=FONT_NORMAL, bg=C_CARD, fg=C_TEXT_DIM)
            dev_lbl.pack(side="right")

            daily_ma_lbl = Label(r3, text="日MA --", font=FONT_SMALL, bg=C_CARD, fg=C_TEXT_DIM)
            daily_ma_lbl.pack(side="left")
            trigger_lbl = Label(r3, text="触发 --", font=FONT_SMALL, bg=C_CARD, fg=C_TEXT_DIM)
            trigger_lbl.pack(side="right")
            weekly_ma_lbl = Label(r3, text="周MA --", font=FONT_SMALL, bg=C_CARD, fg=C_TEXT_DIM)
            weekly_ma_lbl.pack(side="right", padx=(0, 8))

            pe_lbl = Label(r4, text="", font=FONT_MINI, bg=C_CARD, fg=C_TEXT_DIM)
            pe_lbl.pack(side="left")
            roe_lbl = Label(r4, text="", font=FONT_MINI, bg=C_CARD, fg=C_TEXT_DIM)
            roe_lbl.pack(side="right")

            self._cards[code] = {
                "card":       card,
                "rows":       [r1, r2, r3, r4],
                "temp":       temp_lbl,
                "status":     status_lbl,
                "price":      price_lbl,
                "dev":        dev_lbl,
                "daily_ma":   daily_ma_lbl,
                "weekly_ma":  weekly_ma_lbl,
                "trigger":    trigger_lbl,
                "pe":         pe_lbl,
                "roe":        roe_lbl,
            }

        bottom = Frame(self.root, bg=C_BG)
        bottom.pack(fill="x", padx=12, pady=5)
        self._status_lbl = Label(bottom, text="加载中...", font=FONT_MINI,
                                 bg=C_BG, fg=C_TEXT_DIM)
        self._status_lbl.pack(side="left")
        Button(bottom, text="—", font=FONT_SMALL,
               bg=C_CARD, fg=C_TEXT_DIM, relief="flat", bd=0,
               activebackground=C_CARD_ALT, activeforeground=C_TEXT,
               command=self.hide_window).pack(side="right")

    # ---- 数据刷新 ----
    def _refresh_data(self):
        prices = fetch_prices()
        with self._data_lock:
            if prices:
                self.prices = prices
            self.ma_data = load_ma_data()
            self.val_data = load_valuation()
            self.updated_at = datetime.now().strftime("%H:%M:%S")
        self._update_ui()

    def _background_loop(self):
        while not self._stop_event.wait(REFRESH_SEC):
            try:
                prices = fetch_prices()
                with self._data_lock:
                    if prices:
                        self.prices = prices
                    self.updated_at = datetime.now().strftime("%H:%M:%S")
                now = datetime.now()
                if now.hour == 3 and now.minute < 2:
                    with self._data_lock:
                        self.ma_data = load_ma_data()
                        self.val_data = load_valuation()
                self.root.after(0, self._update_ui)
            except Exception:
                pass

    # ---- UI 更新 ----
    def _update_ui(self):
        with self._data_lock:
            prices = dict(self.prices)
            ma_data = dict(self.ma_data)
            val_data = dict(self.val_data)
            updated = self.updated_at

        self._time_lbl.config(text=updated)

        for code, info in WATCHLIST.items():
            card = self._cards.get(code)
            if not card:
                continue

            is_index = info.get("type") == "index"
            price   = prices.get(code, {}).get("price") if not is_index else None
            ma      = ma_data.get(code, {})
            trigger = ma.get("trigger")
            weekly_ma120 = ma.get("weekly_ma120")
            idx_price    = ma.get("index_price") if is_index else None
            val     = val_data.get(code, {})
            temp    = val.get("temperature")
            status  = val.get("status", "N/A")
            pe      = val.get("pe")
            dy      = val.get("dy")
            roe     = val.get("roe")

            # 用实时价格重算偏离日MA120
            daily_ma120 = ma.get("ma120")
            if (not is_index) and price and daily_ma120:
                daily_dev = round((price - daily_ma120) / daily_ma120 * 100, 1)
            elif is_index and idx_price and daily_ma120:
                daily_dev = round((idx_price - daily_ma120) / daily_ma120 * 100, 1)
            else:
                daily_dev = None

            # PushPlus 推送: 偏离日MA120 < -4%
            if daily_dev is not None and daily_dev < PUSH_DEVIATION_THRESHOLD:
                if code not in self._push_notified:
                    self._push_notified.add(code)
                    etf_name = info["name"]
                    if is_index and idx_price:
                        cur_p = f"{idx_price:.1f}"
                    elif price:
                        cur_p = f"{price:.3f}"
                    else:
                        cur_p = "--"
                    trig_str = f"{trigger:.3f}" if trigger else "--"
                    dma_str = f"{daily_ma120:.3f}" if daily_ma120 else "--"
                    threading.Thread(
                        target=send_pushplus,
                        args=(
                            f"{code} {etf_name} 日MA偏离 {daily_dev:+.1f}%",
                            f"{code} {etf_name}\n"
                            f"现价: {cur_p}\n"
                            f"日MA120: {dma_str}\n"
                            f"偏离日MA: {daily_dev:+.1f}%\n"
                            f"触发价: {trig_str}\n"
                            f"时间: {updated}",
                        ),
                        daemon=True,
                    ).start()
            elif daily_dev is not None and daily_dev >= PUSH_DEVIATION_THRESHOLD:
                self._push_notified.discard(code)

            # 偏离日MA120 颜色: 超出(+)红色, 下方(-)绿色
            if daily_dev is not None:
                if daily_dev > 0:
                    dev_color = C_RED
                else:
                    dev_color = C_GREEN
                dev_str = f"{daily_dev:+.1f}%" if daily_dev >= 0 else f"{daily_dev:.1f}%"
            else:
                dev_color = C_TEXT_DIM
                dev_str = "--"

            # 价格颜色: 相对触发价
            if price and trigger:
                if price < trigger:
                    price_color = C_RED
                    card_bg     = "#2a1a1a"
                elif price < trigger * 1.03:
                    price_color = C_ORANGE
                    card_bg     = C_CARD
                else:
                    price_color = C_GREEN
                    card_bg     = C_CARD
            elif is_index:
                price_color = C_TEXT
                card_bg     = C_CARD
            else:
                price_color = C_TEXT
                card_bg     = C_CARD

            # 温度颜色
            if temp is not None:
                temp_color = C_RED if temp > 70 else (C_GREEN if temp < 30 else C_ORANGE)
                temp_str   = f"T={temp}°"
            else:
                temp_color = C_TEXT_DIM
                temp_str   = "T=--"

            status_colors = {"低估": C_GREEN, "正常": C_ORANGE, "高估": C_RED, "N/A": C_TEXT_DIM}
            st_color = status_colors.get(status, C_TEXT_DIM)

            # 更新卡片背景
            card["card"].configure(bg=card_bg)
            for row_frame in card["rows"]:
                row_frame.configure(bg=card_bg)
                for w in row_frame.winfo_children():
                    try:
                        w.configure(bg=card_bg)
                    except Exception:
                        pass

            # Row 2: 价格
            if is_index:
                price_text = f"{idx_price:.1f}" if idx_price else "--"
            else:
                price_text = f"{price:.3f}" if price else "--"
            card["price"].config(text=price_text, fg=price_color)

            # Row 2 右: 偏离日MA
            card["dev"].config(text=f"偏离日MA {dev_str}", fg=dev_color)

            # Row 3: 日MA / 周MA / 触发
            if daily_ma120:
                dma_text = f"日MA {daily_ma120:.3f}" if not is_index else f"日MA {daily_ma120:.1f}"
            else:
                dma_text = "日MA --"
            card["daily_ma"].config(text=dma_text)

            if weekly_ma120:
                wma_text = f"周MA {weekly_ma120:.3f}" if not is_index else f"周MA {weekly_ma120:.1f}"
            else:
                wma_text = "周MA --"
            card["weekly_ma"].config(text=wma_text)

            # 触发价 (仅 ETF)
            if not is_index:
                card["trigger"].config(text=f"触发 {trigger:.3f}" if trigger else "触发 --")
            else:
                card["trigger"].config(text="")

            card["temp"].config(text=temp_str, fg=temp_color)
            card["status"].config(text=f"[{status}]", fg=st_color)

            # PE / DY / ROE 行
            pe_str = f"PE {pe:.1f}" if pe else ""
            dy_str = f"DY {dy:.2f}%" if dy else ""
            roe_str = f"ROE {roe:.1f}%" if roe else ""
            left_parts = [p for p in [pe_str, dy_str] if p]
            card["pe"].config(text="  ".join(left_parts))
            card["roe"].config(text=roe_str)

        # 状态栏
        below_count = sum(1 for code, info in WATCHLIST.items()
                         if info.get("type") == "etf"
                         and prices.get(code, {}).get("price")
                         and ma_data.get(code, {}).get("trigger")
                         and prices[code]["price"] < ma_data[code]["trigger"])
        self._status_lbl.config(
            text=f"刷新 {updated}  |  触发: {below_count}/{len([c for c,i in WATCHLIST.items() if i.get('type')=='etf'])}")

        # 托盘闪烁
        new_alerts = set()
        for code, info in WATCHLIST.items():
            if info.get("type") != "etf":
                continue
            p = prices.get(code, {}).get("price")
            t = ma_data.get(code, {}).get("trigger")
            if p and t and p < t:
                new_alerts.add(code)

        if new_alerts and new_alerts != self._alert_codes:
            for c in new_alerts - self._alert_notified:
                self._notify_alert(c)
            self._start_flash()
        elif not new_alerts:
            self._stop_flash()

        self._alert_codes = new_alerts

    # ---- 托盘闪烁 ----
    def _start_flash(self):
        self.root.title("! ETF 监控 — 信号触发")
        if self._flash_job is not None:
            return
        self._flash_tick()

    def _stop_flash(self):
        if self._flash_job is not None:
            self.root.after_cancel(self._flash_job)
            self._flash_job = None
        self._flash_state = False
        self._alert_notified.clear()
        self.root.title("ETF 监控")
        try:
            self._tray.icon = make_tray_icon(TRAY_COLOR_NORMAL, alert=False)
        except Exception:
            pass

    def _flash_tick(self):
        self._flash_state = not self._flash_state
        color = TRAY_COLOR_ALERT if self._flash_state else TRAY_COLOR_NORMAL
        try:
            self._tray.icon = make_tray_icon(color, alert=self._flash_state)
        except Exception:
            pass
        self._flash_job = self.root.after(FLASH_INTERVAL_MS, self._flash_tick)

    def _notify_alert(self, code):
        if code in self._alert_notified:
            return
        self._alert_notified.add(code)
        info = WATCHLIST.get(code, {})
        name = info.get("name", code)
        try:
            self._tray.notify(
                f"{code} {name} 触发补仓信号!",
                "ETF 监控"
            )
        except Exception:
            pass

    # ---- 窗口显隐 ----
    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_window(self):
        self.root.withdraw()

    # ---- 系统托盘 ----
    def _setup_tray(self):
        icon_img = make_tray_icon()
        menu = pystray.Menu(
            pystray.MenuItem("显示面板", lambda: self.root.after(0, self.show_window), default=True),
            pystray.MenuItem("立即刷新", lambda: self.root.after(0, self._refresh_data)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._quit),
        )
        self._tray = pystray.Icon("etf_monitor", icon_img, "ETF 监控", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _quit(self):
        self._stop_event.set()
        self._tray.stop()
        self.root.after(0, self.root.destroy)

    def run(self):
        if "--hidden" in sys.argv:
            self.root.withdraw()
        self.root.mainloop()


# =========================== 入口 ===========================
if __name__ == "__main__":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("etf.monitor.widget")
    except Exception:
        pass

    try:
        print("启动 ETF 桌面小组件...")
        print("  - 价格跌破 日MA120×0.94 → 托盘图标红蓝闪烁 + 气泡通知")
        print("  - 偏离日MA120: + 在均线之上(红) / - 在均线之下(绿)")
        print("  - 日MA120 / 周MA120 均线价格")
        print("  - H30269 红利低波指数 (日线缓存自 AKShare)")
        print("  - 左键托盘图标: 显示面板")
        print("  - 右键托盘图标: 菜单 (刷新/退出)")
        print("  - 刷新间隔: {}s".format(REFRESH_SEC))
        print("  - 关闭窗口: 隐藏到托盘 (右键托盘→退出 彻底关闭)")
    except Exception:
        pass

    app = ETFWidget()
    app.run()
