import os
import re
import json
import html
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import MetaTrader5 as mt5
import plotly.graph_objects as go

# ======================= SOZLAMALAR =======================
MAGIC = 234000            # bot.py dagi MAGIC bilan bir xil bo'lsin
LOG_FILE = "bot.log"
BOT_ACTIVE_MINUTES = 20   # shu vaqt ichida log yozilmasa, bot "jim" hisoblanadi

TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

# Ranglar (tilla mavzu)
INK, PANEL, LINE = "#07090d", "#0e1218", "#1f2630"
TEXT, MUTED = "#eef0f3", "#8b93a1"
UP, DOWN = "#2ebd85", "#f6465d"
GOLD, GOLD_SOFT, GOLD_DEEP = "#f5c542", "#ffe08a", "#b8860b"
ORANGE, BLUE = "#ff9f43", "#6ea8fe"
AMBER = ORANGE

st.set_page_config(page_title="Savdo paneli", page_icon="📈", layout="wide")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap');

html, body, [class*="css"], .stApp {{ font-family: 'IBM Plex Sans', sans-serif; }}
.stApp {{
  background:
    radial-gradient(1100px 520px at 85% -8%, rgba(245,197,66,.10), transparent 60%),
    radial-gradient(800px 400px at -5% 105%, rgba(245,197,66,.05), transparent 60%),
    {INK};
  color: {TEXT};
}}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2rem; max-width: 1400px; }}
section[data-testid="stSidebar"] {{ background: #05070a; border-right: 1px solid rgba(245,197,66,.18); }}
section[data-testid="stSidebar"] h3 {{ color: {GOLD}; text-shadow: 0 0 14px rgba(245,197,66,.35); }}

.top {{ display:flex; align-items:center; justify-content:space-between; margin-bottom: 1.2rem; }}
.top h1 {{
  font-size: 1.8rem; font-weight: 600; margin: 0; letter-spacing: -0.01em;
  background: linear-gradient(90deg, #fff3c4 0%, {GOLD} 55%, {GOLD_DEEP} 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
  filter: drop-shadow(0 0 14px rgba(245,197,66,.35));
}}
.top .sub {{ color: {MUTED}; font-size: .9rem; margin-top: .15rem; }}
.pill {{ display:inline-flex; align-items:center; gap:.5rem; padding:.4rem .9rem;
        border:1px solid rgba(245,197,66,.30); border-radius: 999px; font-size:.85rem; color:{TEXT};
        background:{PANEL}; box-shadow: 0 0 22px rgba(245,197,66,.08); }}
.dot {{ width:.55rem; height:.55rem; border-radius:50%; display:inline-block; }}
.dot.on {{ background:{UP}; box-shadow:0 0 0 4px rgba(46,189,133,.20), 0 0 12px {UP}; }}
.dot.off {{ background:{DOWN}; box-shadow:0 0 10px {DOWN}; }}
.dot.idle {{ background:{ORANGE}; box-shadow:0 0 10px {ORANGE}; }}

/* Asosiy ko'rsatkichlar */
.strip {{ display:grid; grid-template-columns: 1.6fr repeat(5, 1fr); background:{PANEL};
         border:1px solid rgba(245,197,66,.25); border-radius: 16px; overflow:hidden; margin-bottom:1.4rem;
         box-shadow: 0 0 50px rgba(245,197,66,.07), inset 0 1px 0 rgba(255,255,255,.04); }}
.cell {{ padding: 1rem 1.25rem; border-left: 1px solid {LINE}; }}
.cell:first-child {{ border-left: none; }}
.cell .k {{ color:{MUTED}; font-size:.82rem; margin-bottom:.3rem; }}
.cell .v {{ font-family:'IBM Plex Mono', monospace; font-size:1.25rem; font-weight:500; }}
.cell .s {{ color:{MUTED}; font-size:.8rem; margin-top:.2rem; }}
.cell.hero {{ background: linear-gradient(135deg, rgba(245,197,66,.18) 0%, {PANEL} 72%); }}
.cell.hero .v {{ font-size: 2.3rem; letter-spacing:-0.02em; text-shadow: 0 0 22px rgba(245,197,66,.40); }}
.up {{ color:{UP}; }} .down {{ color:{DOWN}; }}
@media (max-width: 900px) {{
  .strip {{ grid-template-columns: 1fr 1fr; }}
  .cell {{ border-left:none; border-top:1px solid {LINE}; }}
  .cell.hero {{ grid-column: 1 / -1; border-top:none; }}
}}

/* Tablar */
.stTabs [data-baseweb="tab-list"] {{ gap: 1.6rem; border-bottom: 1px solid {LINE}; }}
.stTabs [data-baseweb="tab"] {{ background: transparent; padding: .6rem 0; color:{MUTED}; }}
.stTabs [aria-selected="true"] {{ color:{GOLD}; text-shadow: 0 0 12px rgba(245,197,66,.45); }}
.stTabs [data-baseweb="tab-highlight"] {{ background:{GOLD}; box-shadow: 0 0 12px {GOLD}; height:2px; }}

/* Grafik ramkasi */
iframe {{ border-radius: 14px; }}
div[data-testid="stIFrame"], div[data-testid="stCustomComponentV1"] {{
  border: 1px solid rgba(245,197,66,.28); border-radius: 14px;
  box-shadow: 0 0 45px rgba(245,197,66,.08); overflow:hidden; background:#0a0d12;
}}

/* Metrikalar, tugmalar */
[data-testid="stMetric"] {{ background:{PANEL}; border:1px solid {LINE}; border-radius:12px; padding:.7rem .9rem; }}
[data-testid="stMetricValue"] {{ font-family:'IBM Plex Mono', monospace; }}
.stButton > button, .stDownloadButton > button {{
  background: transparent; color:{GOLD}; border:1px solid rgba(245,197,66,.5); border-radius:10px;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
  border-color:{GOLD}; color:#111; background:{GOLD}; box-shadow:0 0 18px rgba(245,197,66,.5);
}}

.logbox {{ background:#05070a; border:1px solid {LINE}; border-radius:12px; padding:.9rem 1rem;
          font-family:'IBM Plex Mono', monospace; font-size:.82rem; line-height:1.55;
          max-height: 480px; overflow:auto; }}
.logbox .t {{ color:{MUTED}; }}
.lv-INFO {{ color:{BLUE}; }} .lv-WARNING {{ color:{ORANGE}; }}
.lv-ERROR, .lv-CRITICAL {{ color:{DOWN}; }}

.sig {{ display:flex; gap:.8rem; padding:.7rem 0; border-bottom:1px solid {LINE}; }}
.sig .tag {{ min-width:3.6rem; text-align:center; font-weight:600; border-radius:6px; padding:.15rem 0; height:fit-content; }}
.tag.BUY {{ background:rgba(46,189,133,.15); color:{UP}; }}
.tag.SELL {{ background:rgba(246,70,93,.15); color:{DOWN}; }}
.tag.HOLD {{ background:rgba(139,147,161,.15); color:{MUTED}; }}
.sig .meta {{ color:{MUTED}; font-size:.82rem; }}
.empty {{ color:{MUTED}; padding:1.2rem 0; }}
</style>
""", unsafe_allow_html=True)


# ======================= YORDAMCHI FUNKSIYALAR =======================
def show_df(df: pd.DataFrame):
    """Yangi va eski Streamlit versiyalarida ishlaydi."""
    try:
        st.dataframe(df, width="stretch", hide_index=True)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True)


def show_fig(fig: go.Figure):
    try:
        st.plotly_chart(fig, width="stretch")
    except Exception:
        st.plotly_chart(fig, use_container_width=True)


def money(x: float, cur: str = "", sign: bool = False) -> str:
    s = f"{x:+,.2f}" if sign else f"{x:,.2f}"
    return f"{s} {cur}".strip()


def tone(x: float) -> str:
    return "up" if x > 0 else "down" if x < 0 else ""


def connect() -> bool:
    if mt5.terminal_info() is not None and mt5.account_info() is not None:
        return True
    return bool(mt5.initialize())


def server_now(symbol: str) -> datetime:
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return datetime.utcnow()
    return datetime.fromtimestamp(tick.time, tz=timezone.utc).replace(tzinfo=None)


def load_symbols() -> list[tuple]:
    """(nom, guruh, tavsif, market_watch'da_bormi)"""
    syms = mt5.symbols_get()
    rows = []
    for s in syms or []:
        path = s.path or ""
        group = path.split("\\")[0] if "\\" in path else "Boshqa"
        rows.append((s.name, group, s.description or "", bool(s.visible)))
    return rows


def get_positions(symbol: str, only_bot: bool) -> pd.DataFrame:
    pos = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if not pos:
        return pd.DataFrame()
    df = pd.DataFrame([p._asdict() for p in pos])
    if only_bot:
        df = df[df["magic"] == MAGIC]
    if df.empty:
        return df
    df["yo'nalish"] = df["type"].map({0: "BUY", 1: "SELL"})
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def get_deals(symbol: str, days: int, only_bot: bool) -> pd.DataFrame:
    now = server_now(symbol)
    deals = mt5.history_deals_get(now - timedelta(days=days), now + timedelta(days=2))
    if not deals:
        return pd.DataFrame()
    df = pd.DataFrame([d._asdict() for d in deals])
    df = df[(df["entry"] == mt5.DEAL_ENTRY_OUT) & (df["type"].isin([0, 1]))]
    if only_bot:
        df = df[df["magic"] == MAGIC]
    if df.empty:
        return df
    fee = df["fee"] if "fee" in df else 0
    df["net"] = df["profit"] + df["commission"] + df["swap"] + fee
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df.sort_values("time").reset_index(drop=True)


LOG_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \| (\w+) \| (.*)$")
SIG_RE = re.compile(r"AI: (BUY|SELL|HOLD) \((\d+)%\) - (.*)")


def read_logs(max_lines: int = 3000) -> list[dict]:
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()[-max_lines:]
    out: list[dict] = []
    for line in lines:
        m = LOG_RE.match(line.rstrip("\n"))
        if m:
            out.append({"time": datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"),
                        "level": m.group(2), "msg": m.group(3)})
        elif out:  # traceback va ko'p qatorli xabarlar
            out[-1]["msg"] += "\n" + line.rstrip("\n")
    return out


def bot_status(logs: list[dict]) -> tuple[str, str, str]:
    """(css sinfi, sarlavha, tafsilot)"""
    if not logs:
        return "off", "Bot hali ishga tushmagan", f"{LOG_FILE} topilmadi"
    last = logs[-1]["time"]
    mins = (datetime.now() - last).total_seconds() / 60
    if mins <= BOT_ACTIVE_MINUTES:
        return "on", "Bot ishlayapti", f"oxirgi yozuv {int(mins)} daqiqa oldin"
    return "idle", "Bot jim", f"oxirgi yozuv {last:%d.%m %H:%M} da"


# ======================= TRADINGVIEW USLUBIDAGI GRAFIK =======================
TV_HTML = """
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
  html, body { margin:0; padding:0; background:#0a0d12; overflow:hidden;
               font-family:'IBM Plex Sans', -apple-system, 'Segoe UI', sans-serif; }
  #wrap { position:relative; width:100%; }
  #main { width:100%; height:470px; }
  #rsi  { width:100%; height:150px; border-top:1px solid #1f2630; }
  #legend { position:absolute; top:10px; left:14px; z-index:5; pointer-events:none;
            color:#eef0f3; font-size:13px; line-height:1.5; }
  #legend .sym { font-size:16px; font-weight:600; color:#f5c542; text-shadow:0 0 12px rgba(245,197,66,.55); }
  #legend .tf  { color:#8b93a1; margin-left:6px; }
  #legend .row { font-family:'IBM Plex Mono', monospace; font-size:12px; margin-top:2px; }
  #legend .l   { color:#8b93a1; } .up { color:#2ebd85; } .down { color:#f6465d; }
  #legend .ma  { margin-top:2px; font-size:12px; }
  #rsilbl { position:absolute; left:14px; z-index:5; pointer-events:none; color:#8b93a1; font-size:11px; }
  #err { color:#f6465d; padding:20px; font-size:14px; display:none; }
</style></head>
<body>
<div id="wrap">
  <div id="legend">
    <div><span class="sym" id="sym"></span><span class="tf" id="tf"></span></div>
    <div class="row" id="ohlc"></div>
    <div class="ma"><span style="color:#f5c542">&#9679; EMA20</span> &nbsp; <span style="color:#6ea8fe">&#9679; EMA50</span></div>
  </div>
  <div id="main"></div>
  <div id="rsilbl">RSI 14</div>
  <div id="rsi"></div>
  <div id="err">Grafik kutubxonasi yuklanmadi. Internet ulanishini tekshiring.</div>
</div>
<script>
(function () {
  if (typeof LightweightCharts === 'undefined') { document.getElementById('err').style.display = 'block'; return; }
  const D = __DATA__;
  const GOLD = '#f5c542', UP = '#2ebd85', DOWN = '#f6465d', GRID = 'rgba(255,255,255,0.045)';
  document.getElementById('sym').textContent = D.symbol;
  document.getElementById('tf').textContent = D.tf;

  const base = {
    layout: { background: { type: 'solid', color: '#0a0d12' }, textColor: '#8b93a1', fontFamily: 'IBM Plex Sans, sans-serif', fontSize: 12 },
    grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: 'rgba(245,197,66,.75)', width: 1, style: 3, labelBackgroundColor: GOLD },
      horzLine: { color: 'rgba(245,197,66,.75)', width: 1, style: 3, labelBackgroundColor: GOLD },
    },
    rightPriceScale: { borderColor: '#1f2630', minimumWidth: 72 },
    timeScale: { borderColor: '#1f2630', timeVisible: true, secondsVisible: false, rightOffset: 6, barSpacing: 9 },
    handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
    handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
    kineticScroll: { mouse: true, touch: true },
  };

  const mainEl = document.getElementById('main'), rsiEl = document.getElementById('rsi');
  const chart = LightweightCharts.createChart(mainEl, Object.assign({}, base, { width: mainEl.clientWidth, height: 470 }));
  const rsiChart = LightweightCharts.createChart(rsiEl, Object.assign({}, base, { width: rsiEl.clientWidth, height: 150 }));
  rsiChart.applyOptions({ timeScale: { visible: false } });
  document.getElementById('rsilbl').style.top = (470 + 8) + 'px';

  chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.08, bottom: 0.24 } });
  const pf = { type: 'price', precision: D.digits, minMove: D.minMove };

  const candles = chart.addCandlestickSeries({
    upColor: UP, downColor: DOWN, borderVisible: false, wickUpColor: UP, wickDownColor: DOWN, priceFormat: pf,
  });
  candles.setData(D.candles);

  const vol = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'vol', lastValueVisible: false, priceLineVisible: false });
  chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
  vol.setData(D.volume);

  const lineOpts = (c) => ({ color: c, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
  const ema20 = chart.addLineSeries(lineOpts(GOLD)); ema20.setData(D.ema20);
  const ema50 = chart.addLineSeries(lineOpts('#6ea8fe')); ema50.setData(D.ema50);

  (D.lines || []).forEach(function (l) {
    candles.createPriceLine({ price: l.price, color: l.color, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: l.title });
  });

  const rsiS = rsiChart.addLineSeries({
    color: GOLD, lineWidth: 2, priceLineVisible: false, lastValueVisible: true,
    priceFormat: { type: 'price', precision: 1, minMove: 0.1 },
    autoscaleInfoProvider: function () { return { priceRange: { minValue: 0, maxValue: 100 } }; },
  });
  rsiS.setData(D.rsi);
  [30, 70].forEach(function (v) {
    rsiS.createPriceLine({ price: v, color: 'rgba(139,147,161,.55)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: '' });
  });

  // --- Legend (OHLC) ---
  const ohlcEl = document.getElementById('ohlc');
  function fmt(v) { return Number(v).toFixed(D.digits); }
  function showBar(b) {
    if (!b) return;
    const up = b.close >= b.open, cls = up ? 'up' : 'down';
    const chg = b.close - b.open, pct = b.open ? chg / b.open * 100 : 0;
    ohlcEl.innerHTML =
      '<span class="l">O</span> <span class="' + cls + '">' + fmt(b.open) + '</span> ' +
      '<span class="l">H</span> <span class="' + cls + '">' + fmt(b.high) + '</span> ' +
      '<span class="l">L</span> <span class="' + cls + '">' + fmt(b.low) + '</span> ' +
      '<span class="l">C</span> <span class="' + cls + '">' + fmt(b.close) + '</span> ' +
      '<span class="' + cls + '">' + (chg >= 0 ? '+' : '') + fmt(chg) + ' (' + (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%)</span>';
  }
  const last = D.candles[D.candles.length - 1];
  showBar(last);
  chart.subscribeCrosshairMove(function (p) {
    const b = p && p.seriesData ? p.seriesData.get(candles) : null;
    showBar(b || last);
    // RSI crosshair sync
    if (p && p.time) { rsiChart.setCrosshairPosition(NaN, p.time, rsiS); } else { rsiChart.clearCrosshairPosition(); }
  });

  // --- Vaqt shkalalarini sinxronlash ---
  let syncing = false;
  const n = D.candles.length;
  const key = 'rng_' + D.symbol + '_' + D.tf;
  chart.timeScale().subscribeVisibleLogicalRangeChange(function (r) {
    if (!r || syncing) return;
    syncing = true; rsiChart.timeScale().setVisibleLogicalRange(r); syncing = false;
    try { sessionStorage.setItem(key, JSON.stringify({ from: r.from - n, to: r.to - n })); } catch (e) {}
  });
  rsiChart.timeScale().subscribeVisibleLogicalRangeChange(function (r) {
    if (!r || syncing) return;
    syncing = true; chart.timeScale().setVisibleLogicalRange(r); syncing = false;
  });

  // --- Oldingi zoom/surish holatini tiklash ---
  let restored = false;
  try {
    const s = JSON.parse(sessionStorage.getItem(key));
    if (s && isFinite(s.from) && isFinite(s.to)) {
      chart.timeScale().setVisibleLogicalRange({ from: s.from + n, to: s.to + n });
      restored = true;
    }
  } catch (e) {}
  if (!restored) {
    chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 110), to: n + 6 });
  }

  // --- O'lcham o'zgarsa ---
  function resize() {
    chart.applyOptions({ width: mainEl.clientWidth });
    rsiChart.applyOptions({ width: rsiEl.clientWidth });
  }
  window.addEventListener('resize', resize);
  new ResizeObserver(resize).observe(document.getElementById('wrap'));
})();
</script>
</body></html>
"""


def tv_chart(symbol: str, tf_name: str, bars: int, positions: pd.DataFrame, info) -> bool:
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAMES[tf_name], 0, bars + 60)
    if rates is None or len(rates) == 0:
        return False
    df = pd.DataFrame(rates)
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    d = df["close"].diff()
    gain = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = (100 - 100 / (1 + gain / loss.replace(0, float("nan")))).fillna(50)
    df = df.tail(bars)

    t = df["time"].astype(int).tolist()
    candles = [{"time": t[i], "open": float(r.open), "high": float(r.high),
                "low": float(r.low), "close": float(r.close)}
               for i, r in enumerate(df.itertuples())]
    volume = [{"time": t[i], "value": float(r.tick_volume),
               "color": "rgba(46,189,133,.40)" if r.close >= r.open else "rgba(246,70,93,.40)"}
              for i, r in enumerate(df.itertuples())]
    ema20 = [{"time": t[i], "value": float(v)} for i, v in enumerate(df["ema20"])]
    ema50 = [{"time": t[i], "value": float(v)} for i, v in enumerate(df["ema50"])]
    rsi = [{"time": t[i], "value": float(v)} for i, v in enumerate(df["rsi"])]

    lines = []
    if not positions.empty:
        for _, p in positions.iterrows():
            lines.append({"price": float(p["price_open"]), "color": TEXT,
                          "title": f"{p['yonalish']} {p['volume']}"})
            if p["sl"]:
                lines.append({"price": float(p["sl"]), "color": DOWN, "title": "SL"})
            if p["tp"]:
                lines.append({"price": float(p["tp"]), "color": UP, "title": "TP"})

    payload = {
        "symbol": symbol, "tf": tf_name, "digits": int(info.digits),
        "minMove": float(info.point) if info.point else 0.00001,
        "candles": candles, "volume": volume, "ema20": ema20, "ema50": ema50,
        "rsi": rsi, "lines": lines,
    }
    page = TV_HTML.replace("__DATA__", json.dumps(payload))
    components.html(page, height=640, scrolling=False)
    return True


def equity_chart(deals: pd.DataFrame) -> go.Figure:
    cum = deals["net"].cumsum()
    positive = cum.iloc[-1] >= 0
    color = GOLD if positive else DOWN
    fig = go.Figure(go.Scatter(x=deals["time"], y=cum, mode="lines", fill="tozeroy",
                               line=dict(color=color, width=2.5),
                               fillcolor="rgba(245,197,66,.12)" if positive else "rgba(246,70,93,.12)"))
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=300, margin=dict(l=10, r=10, t=10, b=10), font=dict(family="IBM Plex Sans"))
    fig.update_yaxes(gridcolor=LINE, zerolinecolor=LINE)
    fig.update_xaxes(showgrid=False)
    return fig


# ======================= ASOSIY SAHIFA =======================
def render(symbol: str, bars: int, only_bot: bool, days: int):
    logs = read_logs()
    cls, status_title, status_detail = bot_status(logs)

    st.markdown(f"""
    <div class="top">
      <div><h1>Savdo paneli</h1><div class="sub">{html.escape(symbol)} · Gemini AI va MetaTrader 5</div></div>
      <div class="pill"><span class="dot {cls}"></span><b>{status_title}</b>
        <span style="color:{MUTED}">{status_detail}</span></div>
    </div>""", unsafe_allow_html=True)

    if not connect():
        st.error("MT5 terminaliga ulanib bo'lmadi. MetaTrader 5 ochiq va tizimga kirilganini tekshiring.")
        return
    acc = mt5.account_info()
    info = mt5.symbol_info(symbol)
    if acc is None or info is None:
        st.error(f"{symbol} topilmadi. Market Watch'da borligini tekshiring.")
        return
    mt5.symbol_select(symbol, True)

    positions = get_positions(symbol, only_bot)
    deals_today_src = get_deals(symbol, max(days, 1), only_bot)
    today0 = server_now(symbol).replace(hour=0, minute=0, second=0, microsecond=0)
    closed_today = float(deals_today_src[deals_today_src["time"] >= today0]["net"].sum()) \
        if not deals_today_src.empty else 0.0
    floating = float(positions["profit"].sum()) if not positions.empty else 0.0
    today = closed_today + floating
    pct = today / acc.balance * 100 if acc.balance else 0
    cur = acc.currency

    st.markdown(f"""
    <div class="strip">
      <div class="cell hero"><div class="k">Bugungi natija</div>
        <div class="v {tone(today)}">{money(today, cur, True)}</div>
        <div class="s">{pct:+.2f}% balansdan · yopilgan {money(closed_today, '', True)} + ochiq {money(floating, '', True)}</div></div>
      <div class="cell"><div class="k">Balans</div><div class="v">{money(acc.balance)}</div><div class="s">{cur}</div></div>
      <div class="cell"><div class="k">Equity</div><div class="v">{money(acc.equity)}</div>
        <div class="s">marja darajasi {acc.margin_level:.0f}%</div></div>
      <div class="cell"><div class="k">Ochiq pozitsiyalar</div><div class="v">{len(positions)}</div>
        <div class="s">{'faqat bot' if only_bot else 'hammasi'}</div></div>
      <div class="cell"><div class="k">Spread</div><div class="v">{info.spread}</div><div class="s">punkt</div></div>
      <div class="cell"><div class="k">Hisob</div><div class="v" style="font-size:1.05rem">{acc.login}</div>
        <div class="s">{html.escape(acc.company[:22])}</div></div>
    </div>""", unsafe_allow_html=True)

    tab_market, tab_pos, tab_hist, tab_ai, tab_log = st.tabs(
        ["Bozor", "Pozitsiyalar", "Tarix", "AI signallar", "Loglar"])

    # ---- Bozor ----
    with tab_market:
        tf_name = None
        try:
            tf_name = st.segmented_control("Taymfreym", list(TIMEFRAMES), default="M15",
                                           key="tf", label_visibility="collapsed")
        except Exception:
            tf_name = st.radio("Taymfreym", list(TIMEFRAMES), index=2, horizontal=True,
                               key="tf_radio", label_visibility="collapsed")
        tf_name = tf_name or "M15"
        if not tv_chart(symbol, tf_name, bars, positions, info):
            st.markdown('<div class="empty">Narx ma\'lumoti olinmadi.</div>', unsafe_allow_html=True)

    # ---- Pozitsiyalar ----
    with tab_pos:
        if positions.empty:
            st.markdown('<div class="empty">Hozir ochiq pozitsiya yo\'q. DRY_RUN yoqilgan bo\'lsa, '
                        'bot buyurtma yubormaydi, shuning uchun bu normal.</div>', unsafe_allow_html=True)
        else:
            view = positions[["ticket", "time", "yo'nalish", "volume", "price_open",
                              "price_current", "sl", "tp", "profit"]].rename(columns={
                "ticket": "Ticket", "time": "Ochilgan", "yo'nalish": "Yo'nalish", "volume": "Lot",
                "price_open": "Kirish", "price_current": "Hozirgi", "sl": "SL", "tp": "TP", "profit": "Foyda"})
            show_df(view)

    # ---- Tarix ----
    with tab_hist:
        deals = get_deals(symbol, days, only_bot)
        if deals.empty:
            st.markdown(f'<div class="empty">So\'nggi {days} kunda yopilgan savdo yo\'q.</div>',
                        unsafe_allow_html=True)
        else:
            wins, losses = deals[deals["net"] > 0], deals[deals["net"] < 0]
            pf = wins["net"].sum() / abs(losses["net"].sum()) if not losses.empty else float("inf")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Savdolar", len(deals))
            c2.metric("Yutuq foizi", f"{len(wins) / len(deals) * 100:.0f}%")
            c3.metric("Sof natija", money(deals["net"].sum(), cur, True))
            c4.metric("Profit factor", "∞" if pf == float("inf") else f"{pf:.2f}")
            c5.metric("Eng yomon savdo", money(deals["net"].min(), cur, True))
            show_fig(equity_chart(deals))
            view = deals[["time", "symbol", "volume", "price", "net"]].sort_values("time", ascending=False)
            view = view.rename(columns={"time": "Yopilgan", "symbol": "Symbol", "volume": "Lot",
                                        "price": "Narx", "net": "Natija"})
            show_df(view)

    # ---- AI signallar ----
    with tab_ai:
        sigs = []
        for r in logs:
            m = SIG_RE.search(r["msg"])
            if m:
                sigs.append({"time": r["time"], "action": m.group(1), "conf": int(m.group(2)), "reason": m.group(3)})
        if not sigs:
            st.markdown('<div class="empty">Hali AI signali yo\'q. Bot yangi svecha yopilganda tahlil qiladi.</div>',
                        unsafe_allow_html=True)
        else:
            sdf = pd.DataFrame(sigs)
            counts = sdf["action"].value_counts()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Jami signal", len(sdf))
            c2.metric("BUY", int(counts.get("BUY", 0)))
            c3.metric("SELL", int(counts.get("SELL", 0)))
            c4.metric("O'rtacha ishonch", f"{sdf['conf'].mean():.0f}%")
            for s in reversed(sigs[-25:]):
                st.markdown(
                    f'<div class="sig"><div class="tag {s["action"]}">{s["action"]}</div>'
                    f'<div><div>{html.escape(s["reason"])}</div>'
                    f'<div class="meta">{s["time"]:%d.%m %H:%M} · ishonch {s["conf"]}%</div></div></div>',
                    unsafe_allow_html=True)

    # ---- Loglar ----
    with tab_log:
        f1, f2, f3 = st.columns([2, 2, 1])
        levels = f1.multiselect("Daraja", ["INFO", "WARNING", "ERROR", "CRITICAL"],
                                default=["INFO", "WARNING", "ERROR", "CRITICAL"], key="lv")
        query = f2.text_input("Qidirish", "", key="q", placeholder="masalan: AI, spread, xato")
        n = f3.number_input("Qatorlar", 10, 500, 80, step=10, key="n")
        rows = [r for r in logs if r["level"] in levels and query.lower() in r["msg"].lower()]
        rows = rows[-int(n):]
        if not rows:
            st.markdown('<div class="empty">Filtrga mos yozuv topilmadi.</div>', unsafe_allow_html=True)
        else:
            body = "".join(
                f'<div><span class="t">{r["time"]:%d.%m %H:%M:%S}</span> '
                f'<span class="lv-{r["level"]}">{r["level"]:<7}</span> {html.escape(r["msg"])}</div>'
                for r in reversed(rows))
            st.markdown(f'<div class="logbox">{body}</div>', unsafe_allow_html=True)
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "rb") as fh:
                st.download_button("Logni yuklab olish", fh.read(), file_name="bot.log")


# ======================= YON PANEL =======================
with st.sidebar:
    st.markdown("### Bozor")
    connect()
    all_syms = load_symbols()

    if all_syms:
        groups = sorted({g for _, g, _, _ in all_syms})
        group = st.selectbox("Bozor turi", ["Hammasi"] + groups)
        only_watch = st.checkbox("Faqat Market Watch", value=True,
                                 help="O'chirsangiz, brokerdagi barcha instrumentlar ko'rinadi.")
        q = st.text_input("Qidirish", "", placeholder="EURUSD, BTC, XAU, US30...").strip().lower()

        pool = [s for s in all_syms
                if (group == "Hammasi" or s[1] == group)
                and (not only_watch or s[3])
                and (not q or q in s[0].lower() or q in s[2].lower())]
        if not pool:
            st.warning("Mos instrument topilmadi. Filtrni o'zgartiring.")
            pool = [s for s in all_syms if s[0] == "EURUSD"] or all_syms[:1]

        names = [s[0] for s in pool]
        desc = {s[0]: s[2] for s in pool}
        default_idx = names.index("EURUSD") if "EURUSD" in names else 0
        symbol = st.selectbox(
            "Symbol", names, index=default_idx,
            format_func=lambda n: f"{n} — {desc[n]}" if desc.get(n) else n)
    else:
        st.caption("MT5'dan ro'yxat olinmadi, symbolni qo'lda kiriting.")
        symbol = st.text_input("Symbol", "EURUSD").strip().upper()

    st.markdown("### Sozlamalar")
    bars = st.slider("Grafikdagi shamlar", 60, 1000, 300, step=20)
    days = st.slider("Tarix (kun)", 1, 90, 30)
    only_bot = st.checkbox("Faqat bot savdolari (MAGIC)", value=True)
    st.divider()
    auto = st.toggle("Avto-yangilash", value=True)
    every = st.slider("Har necha soniyada", 5, 60, 15, disabled=not auto)
    if not auto and st.button("Yangilash"):
        st.rerun()

runner = st.fragment(run_every=f"{every}s" if auto else None)(render)
runner(symbol, bars, only_bot, days)