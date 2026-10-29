import math
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

import MetaTrader5 as mt5
import pandas as pd
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# ---------- CONFIGURATION ----------
SYMBOL = "EURUSD"
TIMEFRAME = mt5.TIMEFRAME_M15
MODEL = "gemini-3.8-flash"
MAGIC = 234000
RISK_PERCENT = 1.0
SL_ATR_MULT = 1.5
RR = 2.0
MAX_DAILY_LOSS_PERCENT = 3.0
MAX_OPEN_POSITIONS = 1
MAX_SPREAD_POINTS = 20
MIN_CONFIDENCE = 70
TREND_FILTER = True         
CANDLES_FOR_AI = 20
HISTORY_BARS = 200           
DEVIATION = 20
DRY_RUN = True               

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("bot")

# ---------- GEMINI CLIENT ----------
API_KEY = "AIzaSyBpgrUxuqjyZc6td9xAFu1BxDRa4Dv5WFU"
client = genai.Client(api_key=API_KEY)


class Signal(BaseModel):
    action: Literal["BUY", "SELL", "HOLD"] = Field(description="BUY, SELL yoki HOLD")
    confidence: int = Field(ge=0, le=100, description="0 dan 100 gacha ishonch darajasi")
    reason: str = Field(description="Qisqacha tahlil sababi")


# ---------- MT5 HELPERS ----------
def pip_size(info) -> float:
    return info.point * 10 if info.digits in (3, 5) else info.point


def get_data(n: int = HISTORY_BARS) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 1, n)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")

    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    df["rsi"] = (100 - 100 / (1 + rs)).fillna(50)

    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    return df


def ensure_connection() -> bool:
    if mt5.terminal_info() is not None and mt5.account_info() is not None:
        return True
    log.warning("MT5 aloqasi uzilgan, qayta ulanmoqda...")
    mt5.shutdown()
    return mt5.initialize() and mt5.symbol_select(SYMBOL, True)


# ---------- AI ----------
def analyze_with_gemini(df: pd.DataFrame) -> Signal | None:
    info = mt5.symbol_info(SYMBOL)
    d = info.digits
    pip = pip_size(info)

    cols = ["time", "open", "high", "low", "close", "ema20", "ema50", "rsi"]
    recent = df.tail(CANDLES_FOR_AI)[cols].copy()
    for c in ["open", "high", "low", "close", "ema20", "ema50"]:
        recent[c] = recent[c].round(d)
    recent["rsi"] = recent["rsi"].round(1)
    table = recent.to_string(index=False)

    last = df.iloc[-1]
    prompt = f"""Sen ehtiyotkor intraday treyder-tahlilchisan. Instrument: {SYMBOL}, taymfreym: M15.
Oxirgi {CANDLES_FOR_AI} ta YOPILGAN svecha (EMA20, EMA50, RSI14 bilan):
{table}

Joriy holat: close={last.close:.{d}f}, EMA20={last.ema20:.{d}f}, EMA50={last.ema50:.{d}f},
RSI={last.rsi:.1f}, ATR={last.atr / pip:.1f} pip.

Qoidalar:
- Faqat ushbu ma'lumotga tayan, yangilik yoki boshqa narsani taxmin qilma.
- Trend aniq bo'lmasa yoki signal ziddiyatli bo'lsa, HOLD qaytar.
- confidence — sening subyektiv ishonching (0-100).
- SL/TP berma, ularni dastur hisoblaydi."""

    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Signal,
                    temperature=0.2,
                ),
            )
            if resp.parsed is not None:
                return resp.parsed
            log.warning("Gemini bo'sh/yaroqsiz javob qaytardi")
        except Exception as e:
            log.warning(f"Gemini xatosi (urinish {attempt + 1}/3): {e}")
        time.sleep(2 ** attempt * 2)
    return None


# ---------- RISK MANAGEMENT ----------
def my_positions():
    return [p for p in (mt5.positions_get(symbol=SYMBOL) or []) if p.magic == MAGIC]


def daily_pnl() -> float:
    tick = mt5.symbol_info_tick(SYMBOL)
    now = datetime.fromtimestamp(tick.time, tz=timezone.utc).replace(tzinfo=None)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(start, start + timedelta(days=2)) or []
    closed = sum(d.profit + d.commission + d.swap for d in deals if d.magic == MAGIC)
    floating = sum(p.profit + p.swap for p in my_positions())
    return closed + floating


def pre_trade_checks(balance: float) -> str | None:
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return "symbol topilmadi"
    if info.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:
        return "bozor savdoga yopiq"
    if info.spread > MAX_SPREAD_POINTS:
        return f"spread katta ({info.spread})"
    if len(my_positions()) >= MAX_OPEN_POSITIONS:
        return "ochiq pozitsiya limiti"
    if daily_pnl() <= -balance * MAX_DAILY_LOSS_PERCENT / 100:
        return "kunlik zarar limiti oshgan"
    return None


def calc_lot(balance: float, entry: float, sl: float) -> float:
    info = mt5.symbol_info(SYMBOL)
    risk_money = balance * RISK_PERCENT / 100
    loss_per_lot = abs(entry - sl) / info.trade_tick_size * info.trade_tick_value
    if loss_per_lot <= 0:
        return 0.0

    step = info.volume_step
    decimals = max(0, -int(math.floor(math.log10(step))))
    lot = math.floor(risk_money / loss_per_lot / step + 1e-9) * step

    if lot < info.volume_min:
        if info.volume_min * loss_per_lot > risk_money * 1.5:
            return 0.0
        lot = info.volume_min
    lot = min(lot, info.volume_max)
    return round(lot, decimals)


def filling_mode() -> int:
    mode = mt5.symbol_info(SYMBOL).filling_mode
    if mode & 1:
        return mt5.ORDER_FILLING_FOK
    if mode & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


# ---------- TRADE EXECUTION ----------
def open_trade(action: str, atr: float):
    info = mt5.symbol_info(SYMBOL)
    tick = mt5.symbol_info_tick(SYMBOL)
    balance = mt5.account_info().balance

    min_dist = max(info.trade_stops_level, info.trade_freeze_level) * info.point
    sl_dist = max(atr * SL_ATR_MULT, min_dist * 1.5)

    if action == "BUY":
        price = tick.ask
        sl, tp = price - sl_dist, price + sl_dist * RR
        order_type = mt5.ORDER_TYPE_BUY
    else:
        price = tick.bid
        sl, tp = price + sl_dist, price - sl_dist * RR
        order_type = mt5.ORDER_TYPE_SELL

    sl, tp = round(sl, info.digits), round(tp, info.digits)
    lot = calc_lot(balance, price, sl)
    if lot <= 0:
        log.warning("Lot hisoblanmadi — savdo o'tkazib yuborildi")
        return

    log.info(f"-> {action} lot={lot} narx={price} SL={sl} TP={tp}")

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": "Gemini AI Bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode(),
    }

    check = mt5.order_check(request)
    if check is None or check.retcode != 0:
        log.error(f"order_check muvaffaqiyatsiz: {check.retcode if check else mt5.last_error()}")
        return

    if DRY_RUN:
        log.info("(DRY_RUN: order_check OK, buyurtma yuborilmadi)")
        return

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        log.error(f"Order xatosi: {result.retcode if result else mt5.last_error()}")
    else:
        log.info(f"Buyurtma ochildi. Ticket: {result.order}")


# ---------- MAIN LOOP ----------
def main():
    if not mt5.initialize():
        raise SystemExit(f"MT5 ishga tushmadi: {mt5.last_error()}")
    if not mt5.symbol_select(SYMBOL, True):
        mt5.shutdown()
        raise SystemExit(f"{SYMBOL} Market Watch'ga qo'shilmadi")

    acc = mt5.account_info()
    log.info(f"Hisob: {acc.login} | Balans: {acc.balance} | Server: {acc.company} | DRY_RUN={DRY_RUN}")

    last_candle_time = None
    try:
        while True:
            if not ensure_connection():
                time.sleep(30)
                continue

            df = get_data()
            if len(df) < 60:
                time.sleep(10)
                continue

            candle_time = df.iloc[-1]["time"]
            if candle_time == last_candle_time:
                time.sleep(5)
                continue
            last_candle_time = candle_time

            balance = mt5.account_info().balance
            err = pre_trade_checks(balance)
            if err:
                log.info(f"Savdo cheklovi: {err}")
                continue

            signal = analyze_with_gemini(df)
            if signal is None:
                continue
            log.info(f"AI: {signal.action} ({signal.confidence}%) - {signal.reason}")

            if signal.action == "HOLD" or signal.confidence < MIN_CONFIDENCE:
                continue

            last = df.iloc[-1]
            if TREND_FILTER:
                if signal.action == "BUY" and last.ema20 <= last.ema50:
                    log.info("Trend filtri: BUY rad etildi")
                    continue
                if signal.action == "SELL" and last.ema20 >= last.ema50:
                    log.info("Trend filtri: SELL rad etildi")
                    continue

            open_trade(signal.action, last.atr)

    except KeyboardInterrupt:
        log.info("To'xtatildi")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()