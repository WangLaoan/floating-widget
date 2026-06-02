"""
Headless ETF Monitor — GitHub Actions / cron 定时任务
无 GUI, 无 DB — 纯 API 拉数据 → 算 MA120 偏离 → PushPlus 推送

用法:
  python scripts/monitor_pushplus.py           # 单次运行
  python scripts/monitor_pushplus.py --test    # 强制发送测试推送
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# =========================== 配置 ===========================
PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN", "f28d79309c2f4d1cb7d80cb06b7aa472")
PUSHPLUS_API = "http://www.pushplus.plus/send"
PUSH_DEVIATION_THRESHOLD = -4.0  # 偏离日MA120 < -4% 时推送

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR.parent / "data" / "monitor_state.json"

WATCHLIST = {
    "515180": {"name": "中证红利",     "market": "sh"},
    "563020": {"name": "红利低波",     "market": "sh"},
    "513630": {"name": "港股红利低波", "market": "sh"},
    "513500": {"name": "标普500",      "market": "sh"},
}

SINA_QUOTE  = "https://hq.sinajs.cn/list={codes}"
SINA_KLINE  = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"

# 北京时间
CST = timezone(timedelta(hours=8))


# =========================== 数据获取 ===========================
def fetch_prices():
    """新浪实时行情 → {code: {price, yesterday_close}}"""
    codes = ",".join(f"{i['market']}{c}" for c, i in WATCHLIST.items())
    url = SINA_QUOTE.format(codes=codes)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("gbk", errors="replace")
    except Exception as e:
        print(f"[ERROR] 行情请求失败: {e}")
        return {}

    results = {}
    for code, info in WATCHLIST.items():
        symbol = f"{info['market']}{code}"
        marker = f"hq_str_{symbol}="
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
        try:
            results[code] = {
                "price": float(fields[3]) if fields[3] else None,
                "yesterday_close": float(fields[2]) if fields[2] else None,
            }
        except (ValueError, IndexError):
            continue
    return results


def fetch_kline(market, code):
    """新浪 K 线全量日线 → [(date_str, close), ...] 升序"""
    symbol = f"{market}{code}"
    url = f"{SINA_KLINE}?symbol={symbol}&scale=240&ma=no&datalen=10000"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [WARN] {code} K线请求失败: {e}")
        return []

    if not text or text.strip() == "null":
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    result = []
    for row in data:
        try:
            result.append((row["day"], float(row["close"])))
        except (KeyError, ValueError):
            continue
    return result  # 保持升序


# =========================== MA120 计算 ===========================
def compute_daily_ma120(daily_prices):
    """
    daily_prices: [(date, close), ...] 升序
    Returns: (ma120, deviation_pct) or (None, None)
    """
    if len(daily_prices) < 120:
        return None, None
    closes = [p[1] for p in daily_prices[-120:]]
    ma120 = sum(closes) / len(closes)
    current = closes[-1]
    dev = (current - ma120) / ma120 * 100
    return round(ma120, 4), round(dev, 1)


def compute_weekly_ma120(daily_prices):
    """
    daily_prices: [(date, close), ...] 升序
    Returns: (weekly_ma120, None) or (None, None)
    """
    if len(daily_prices) < 120:
        return None

    weekly = {}
    for date_str, price in daily_prices:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        week_key = dt.isocalendar()[:2]
        weekly[week_key] = price  # 同周取最后一天 (升序遍历自然覆盖)

    sorted_weeks = sorted(weekly.keys())
    if len(sorted_weeks) < 120:
        return None

    recent_120 = [weekly[w] for w in sorted_weeks[-120:]]
    ma120 = sum(recent_120) / len(recent_120)
    return round(ma120, 4)


# =========================== PushPlus ===========================
def send_pushplus(title, content):
    """返回 True 表示推送成功"""
    try:
        data = json.dumps({
            "token": PUSHPLUS_TOKEN,
            "title": title,
            "content": content,
        }).encode("utf-8")
        req = urllib.request.Request(PUSHPLUS_API, data=data, headers={
            "Content-Type": "application/json",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
        print(f"  PushPlus 响应: {body}")
        return True
    except Exception as e:
        print(f"  [WARN] PushPlus 推送失败: {e}")
        return False


# =========================== 状态管理 ===========================
def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# =========================== 主逻辑 ===========================
def run(test_mode=False):
    now = datetime.now(CST)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*50}")
    print(f"ETF Monitor — {now_str} CST")
    print(f"{'='*50}")

    if test_mode:
        print("\n[TEST MODE] 强制发送测试推送...")
        send_pushplus(
            "ETF Monitor 测试",
            f"测试推送成功!\n时间: {now_str}\n监控 {len(WATCHLIST)} 只 ETF",
        )
        return

    # 1. 获取实时价格
    print("\n[1/3] 获取实时行情...")
    prices = fetch_prices()
    if not prices:
        print("[ERROR] 未获取到任何实时价格, 终止")
        return
    for code, p in prices.items():
        name = WATCHLIST[code]["name"]
        print(f"  {code} {name}: {p['price']}")

    # 2. 获取 K 线 & 计算 MA120
    print("\n[2/3] 计算 MA120 偏离...")
    state = load_state()
    alerts = []

    for code, info in WATCHLIST.items():
        name = info["name"]
        market = info["market"]

        # 获取 K 线
        kline = fetch_kline(market, code)
        if not kline:
            print(f"  {code} {name}: K线无数据, 跳过")
            continue

        # 日线 MA120
        daily_ma, daily_dev = compute_daily_ma120(kline)
        # 周线 MA120
        weekly_ma = compute_weekly_ma120(kline)

        realtime = prices.get(code, {}).get("price")
        if realtime and daily_ma:
            daily_dev = round((realtime - daily_ma) / daily_ma * 100, 1)

        dma_str = f"{daily_ma:.3f}" if daily_ma else "--"
        wma_str = f"{weekly_ma:.3f}" if weekly_ma else "--"
        dev_str = f"{daily_dev:+.1f}%" if daily_dev is not None else "--"
        price_str = f"{realtime:.3f}" if realtime else "--"

        print(f"  {code} {name}: 现价={price_str}  日MA={dma_str}  周MA={wma_str}  偏离={dev_str}")

        # 检查阈值
        if daily_dev is not None and daily_dev < PUSH_DEVIATION_THRESHOLD:
            prev = state.get(code, {})
            if not prev.get("alert_active"):
                alerts.append((code, name, realtime, daily_ma, daily_dev, now_str))
                state[code] = {"alert_active": True, "last_push": now_str,
                               "deviation": daily_dev, "price": realtime, "daily_ma": daily_ma}
                print(f"    → 触发! 偏离 {daily_dev:+.1f}% < {PUSH_DEVIATION_THRESHOLD:+.0f}%")
            else:
                print(f"    → 持续触发 (已推送于 {prev.get('last_push', '?')})")
        else:
            prev = state.get(code, {})
            if prev.get("alert_active"):
                state[code] = {"alert_active": False}
                print(f"    → 恢复: 偏离回到 {dev_str} (阈值 {PUSH_DEVIATION_THRESHOLD:+.0f}%)")

    # 3. 发送推送
    print(f"\n[3/3] 推送通知: {len(alerts)} 条")
    for code, name, price, dma, dev, ts in alerts:
        title = f"{code} {name} 日MA偏离 {dev:+.1f}%"
        content = (
            f"{code} {name}\n"
            f"现价: {price:.3f}\n"
            f"日MA120: {dma:.3f}\n"
            f"偏离日MA: {dev:+.1f}%\n"
            f"触发价(日MA×0.94): {dma*0.94:.3f}\n"
            f"时间: {ts}"
        )
        send_pushplus(title, content)

    # 4. 保存状态
    save_state(state)
    print(f"\n状态已保存 → {STATE_FILE}")
    print("完成.")


if __name__ == "__main__":
    test_mode = "--test" in sys.argv
    run(test_mode=test_mode)
