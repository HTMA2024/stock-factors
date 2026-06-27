"""
股票多因子分析 Dashboard
用法: streamlit run app.py
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data_fetcher import (
    fetch_daily_ohlcv,
    fetch_valuation,
    fetch_financials,
    fetch_index_daily,
    correct_ohlcv_prices,
)
from factor_engine import compute_all_factors

# ===========================================================================
# 页面配置
# ===========================================================================
st.set_page_config(
    page_title="股票多因子分析",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* 全局表格居中对齐 */
    [data-testid="stDataFrame"] div[role="gridcell"],
    [data-testid="stDataFrame"] div[role="columnheader"],
    .stTable td, .stTable th {
        justify-content: center !important;
        text-align: center !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 股票多因子分析 Dashboard")
st.caption("数据源: 新浪财经 / 百度股市通 / 同花顺 | 全部免费,无需注册")


# ===========================================================================
# 缓存数据加载
# ===========================================================================
@st.cache_data(ttl=3600, show_spinner=False)
def load_all_data(symbol: str, start_date: str, end_date: str, index_code: str):
    """加载所有数据并计算因子"""
    with st.spinner(f"正在获取 {symbol} 数据..."):
        df_daily_raw = fetch_daily_ohlcv(symbol, start_date, end_date)
        df_valuation = fetch_valuation(symbol)
        df_financials = fetch_financials(symbol)

        # 用百度估值反推真实股价修正新浪数据
        df_daily = correct_ohlcv_prices(df_daily_raw, df_valuation, df_financials)

        try:
            df_index = fetch_index_daily(index_code, start_date, end_date)
        except Exception:
            df_index = None

        df_factors = compute_all_factors(df_daily, df_valuation, df_financials, df_index)

        # 过滤日期
        df_factors = df_factors[df_factors.index >= pd.Timestamp(start_date)]

    return df_factors, df_daily, df_financials


# ===========================================================================
# 侧边栏
# ===========================================================================
with st.sidebar:
    st.header("⚙️ 参数设置")

    symbol = st.text_input("股票代码", value="600519", placeholder="600519", max_chars=6)

    # 快速时间范围按钮
    st.caption("⚡ 快速时间范围")
    today = pd.Timestamp.today()
    qr_cols = st.columns(4)
    quick_labels = ["1周", "1月", "3月", "半年", "1年", "3年", "5年"]
    quick_days = [7, 30, 90, 180, 365, 365 * 3, 365 * 5]

    for i, (label, days) in enumerate(zip(quick_labels, quick_days)):
        with qr_cols[i % 4]:
            if st.button(label, key=f"qr_{i}", width='stretch'):
                st.session_state.start_date = (today - pd.Timedelta(days=days)).to_pydatetime()
                st.session_state.df_factors = None
                st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("起始日期", key="start_date", value=pd.Timestamp("2020-01-01"))
    with col2:
        end_date = st.date_input("结束日期", value=pd.Timestamp.today() + pd.Timedelta(days=365))

    index_code = st.selectbox("Beta 基准指数", ["000300", "000001", "000016", "399006"],
                              format_func=lambda x: {"000300": "沪深300", "000001": "上证综指",
                                                     "000016": "上证50", "399006": "创业板指"}.get(x, x))

    st.divider()
    run_btn = st.button("🔍 开始分析", type="primary", width='stretch')

    st.divider()
    st.caption("数据缓存 1 小时 | 修改参数后自动刷新")

# ===========================================================================
# 主逻辑
# ===========================================================================
if not run_btn and "df_factors" not in st.session_state:
    st.info("👈 在左侧输入股票代码和日期,点击「开始分析」")
    st.stop()

if run_btn:
    st.session_state.df_factors = None  # 清缓存强制重算
    st.rerun()

if "df_factors" not in st.session_state or st.session_state.df_factors is None:
    df_factors, df_daily, df_financials = load_all_data(
        symbol, start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"), index_code
    )
    st.session_state.df_factors = df_factors
    st.session_state.df_daily = df_daily
    st.session_state.df_financials = df_financials
else:
    df_factors = st.session_state.df_factors
    df_daily = st.session_state.df_daily
    df_financials = st.session_state.df_financials

if df_factors.empty:
    st.error("未获取到数据,请检查股票代码或日期范围")
    st.stop()

# ===========================================================================
# 顶部指标卡片
# ===========================================================================
st.divider()
st.subheader("📊 关键指标")

latest = df_factors.iloc[-1]
cols = st.columns(8)

metrics = [
    ("最新价", f"{latest.get('close', np.nan):.2f}", None),
    ("PE(TTM)", f"{latest.get('pe_ttm', np.nan):.1f}", "↓好"),
    ("PB", f"{latest.get('pb', np.nan):.2f}", "↓好"),
    ("ROE(%)", f"{latest.get('roe', np.nan):.1f}", "↑好"),
    ("毛利率(%)", f"{latest.get('gross_margin', np.nan):.1f}", "↑好"),
    ("净利同比(%)", f"{latest.get('net_profit_yoy', np.nan):.1f}", "↑好"),
    ("Beta(60日)", f"{latest.get('beta', np.nan):.2f}", None),
    ("总市值(亿)", f"{latest.get('total_mv', np.nan) / 1e8:.0f}", None),
]

for i, (label, value, hint) in enumerate(metrics):
    with cols[i]:
        delta_color = "normal"
        if hint == "↑好":
            delta_color = "normal"
        elif hint == "↓好":
            delta_color = "inverse"
        st.metric(label=label, value=value, delta=None, delta_color=delta_color)


# ===========================================================================
# 图表标签页
# ===========================================================================
st.divider()
tab_labels = ["📉 价格与技术", "💰 估值分析", "📊 盈利能力", "🚀 成长动量", "🏦 财务健康", "⚠️ 风险指标", "🔍 形态匹配", "📊 回测验证", "📋 数据表格"]
active_tab = st.radio("Tabs", tab_labels, horizontal=True, key="active_tab", label_visibility="collapsed")
tab_idx = tab_labels.index(active_tab)

# 因子快捷预设 (全局)
FACTOR_PRESETS = {
    "纯价格": ["close"],
    "量价组合": ["close", "vol_ratio", "rsi14"],
    "技术指标": ["close", "rsi14", "j"],
    "多维度": ["close", "vol_ratio", "j"],
    "纯技术": ["rsi14", "j", "vol_ratio"],
    "估值+价": ["close", "pe_ttm"],
    "信号+价": ["close", "sig_rsizone", "sig_volbreak"],
    "纯信号": ["sig_macross", "sig_rsizone", "sig_volbreak"],
    "全信号+价": ["close", "sig_macross", "sig_rsizone", "sig_volbreak"],
}
SIGNAL_FACTORS = ["sig_macross", "sig_rsizone", "sig_volbreak", "sig_macd", "sig_bbsqueeze"]


# ===========================================================================
# DTW (动态时间规整) 辅助函数
# ===========================================================================
from numba import njit

@njit
def _dtw_distance(s1: np.ndarray, s2: np.ndarray, w: int = 2) -> float:
    """Sakoe-Chiba 约束 DTW 距离, JIT 编译加速"""
    n, m = len(s1), len(s2)
    w = max(w, abs(n - m))
    dtw = np.full((n + 1, m + 1), np.inf)
    dtw[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(max(1, i - w), min(m + 1, i + w)):
            cost = abs(s1[i - 1] - s2[j - 1])
            dtw[i, j] = cost + min(dtw[i - 1, j], dtw[i, j - 1], dtw[i - 1, j - 1])
    return dtw[n, m]


@njit
def _lb_keogh(s1: np.ndarray, s2: np.ndarray, w: int = 2) -> float:
    """LB_Keogh 下界: O(n) 快速估算 DTW 最小距离, 用于剪枝 (零精度损失)"""
    n = len(s1)
    U = np.empty(n)
    L = np.empty(n)
    for i in range(n):
        lo = max(0, i - w)
        hi = min(n, i + w + 1)
        U[i] = np.max(s1[lo:hi])
        L[i] = np.min(s1[lo:hi])
    lb = 0.0
    for i in range(n):
        if s2[i] > U[i]:
            d = s2[i] - U[i]
            lb += d * d
        elif s2[i] < L[i]:
            d = L[i] - s2[i]
            lb += d * d
    return np.sqrt(lb)


def _dtw_similarity(s1: np.ndarray, s2: np.ndarray, w: int = 2,
                     min_similarity: float = 0.0) -> float:
    """DTW 距离转相似度 [0, 1], LB_Keogh 剪枝加速"""
    s1z = (s1 - np.mean(s1)) / (np.std(s1) + 1e-9)
    s2z = (s2 - np.mean(s2)) / (np.std(s2) + 1e-9)
    norm = 3.0 * len(s1)

    # LB_Keogh 剪枝: 下界已经超过阈值所需距离, 直接返回低分
    if min_similarity > 0:
        max_dist = norm * (1.0 / min_similarity - 1.0)
        if _lb_keogh(s1z, s2z, w) > max_dist:
            return 0.0

    dist = _dtw_distance(s1z, s2z, w)
    return 1.0 / (1.0 + dist / norm)


def _compute_single_similarity(tpl_vals: np.ndarray, win_vals: np.ndarray,
                                algo: str = "pearson", dtw_w: int = 2) -> float:
    """统一相似度接口: pearson 或 dtw, 返回值范围 [0, 1]"""
    if np.std(tpl_vals) == 0 or np.std(win_vals) == 0:
        return np.nan
    if algo == "dtw":
        return _dtw_similarity(tpl_vals, win_vals, dtw_w)
    else:
        r, _ = pearsonr(tpl_vals, win_vals)
        return (r + 1) / 2  # Pearson [-1,1] -> [0,1]


from scipy.stats import pearsonr

# ---- 策略增强辅助函数 ----
def _bt_lookaheads(bt_la, ensemble):
    return (3, 5, 10) if ensemble else (bt_la,)

def _ensemble_dir(pred_rets_by_la):
    """pred_rets_by_la: list of lists, each inner list is returns for one lookahead"""
    all_r = [r for la_rets in pred_rets_by_la for r in la_rets]
    bullish = sum(1 for r in all_r if r > 0)
    bearish = sum(1 for r in all_r if r < 0)
    if bullish > bearish: return 1
    if bearish > bullish: return -1
    return 0


def _pearson_corr_matrix(value_arrays, win, weights=None):
    """多因子滑动窗口 Pearson 相关矩阵 (加权平均)。
    value_arrays: list of 1D np.ndarray, 每个因子一条序列。
    weights: 各因子权重, 默认等权。
    """
    n_win = len(value_arrays[0]) - win + 1
    if weights is None:
        weights = [1.0 / len(value_arrays)] * len(value_arrays)
    mat = np.zeros((n_win, n_win))
    for vals, w in zip(value_arrays, weights):
        W = np.lib.stride_tricks.sliding_window_view(vals, win)
        mean = W.mean(axis=1, keepdims=True)
        std = W.std(axis=1, ddof=1, keepdims=True) + 1e-9
        Wz = (W - mean) / std
        mat += w * (Wz @ Wz.T) / (win - 1)
    return mat
    return mat


def _predict_direction(pred_by_la, ensemble):
    """从各 lookahead 的后续收益列表计算 (direction, avg_pred)。

    pred_by_la: 已过滤空列表的 list[list[float]]。
    ensemble=True 时用多窗口投票得 direction; 否则 direction=0 仅用 avg_pred。
    """
    if ensemble:
        direction = _ensemble_dir(pred_by_la)
        mid = len(pred_by_la) // 2
        avg_pred = np.mean(pred_by_la[mid]) if pred_by_la[mid] else 0
    else:
        direction = 0
        avg_pred = np.mean(pred_by_la[0])
    return direction, avg_pred


def _classify_hit(direction, avg_pred, actual_return, ensemble, ensemble_neutral_hit=False):
    """统一命中/中性判定, 返回 (hit, neutral)。

    ensemble_neutral_hit: 仅为保留慢速模式历史行为 (direction==0 且实际近乎持平
    也算命中)。设为 False 即与 fast / 自动调参路径一致 (推荐)。
    """
    if ensemble:
        hit = (direction == 1 and actual_return > 0) or \
              (direction == -1 and actual_return < 0)
        if ensemble_neutral_hit:
            hit = hit or (direction == 0 and abs(actual_return) < 0.001)
        neutral = (direction == 0)
    elif abs(avg_pred) < 0.001:
        hit, neutral = False, True
    else:
        hit = (avg_pred > 0 and actual_return > 0) or \
              (avg_pred < 0 and actual_return < 0)
        neutral = False
    return hit, neutral


def _segment_stats(df_signal):
    """信号段去重统计: 连续同向预测合并为段, 仅以段首日命中判断整段是否正确。

    df_signal: 含 pred_return / hit 列 (已排除中性日)。若含 date 列则按 date 排序,
    否则按现有行序 (调用方需保证为时间序)。
    返回 (段数, 命中段数, 段命中率%, 段均天数)。
    """
    if len(df_signal) == 0:
        return 0, 0, 0.0, 0.0
    d = df_signal.sort_values("date") if "date" in df_signal.columns else df_signal
    sign = np.sign(d["pred_return"].fillna(0))
    seg_id = (sign != sign.shift(1)).cumsum()
    segs = d.groupby(seg_id)
    seg_total = len(segs)
    seg_hits = sum(1 for _, g in segs if g["hit"].iloc[0])
    seg_rate = seg_hits / seg_total * 100 if seg_total > 0 else 0.0
    seg_avg_days = segs.size().mean() if seg_total > 0 else 0.0
    return seg_total, seg_hits, seg_rate, seg_avg_days


def _wilson_lower(hits, n, z=1.96):
    """Wilson 得分区间下界, 对样本量小的命中率自动惩罚。
    hits=3, n=3 → 0.37; hits=10, n=15 → 0.42; hits=100, n=150 → 0.60; hits→n → p"""
    if n == 0:
        return 0.0
    p = hits / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = z * np.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return max(0.0, float(center - margin))


def _hit_color(hit, neutral):
    """命中/未命中/中性 → 颜色 (绿/红/灰)。"""
    if neutral:
        return "#9e9e9e"
    return "#26a69a" if hit else "#ef5350"


def _metric_row(specs):
    """渲染一行指标卡片。specs: list of (label, value, delta, help)，delta/help 可为 None。"""
    cols = st.columns(len(specs))
    for col, (label, value, delta, help_) in zip(cols, specs):
        with col:
            st.metric(label, value, delta=delta, help=help_)


def _resolve_date_range(index, start, end, min_start):
    """把起止日期解析为 (start_idx, end_idx) 整数位置。start 不早于 min_start。"""
    s = index.get_indexer([pd.Timestamp(start)], method="bfill")[0]
    e = index.get_indexer([pd.Timestamp(end)], method="ffill")[0] + 1
    return max(s, min_start), e


# ---- 辅助函数 ----
def _plotly_chart(fig, height=400):
    """统一渲染 Plotly 图表"""
    fig.update_layout(
        height=height,
        margin=dict(l=40, r=40, t=30, b=20),
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="rgba(128,128,128,0.1)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)")
    st.plotly_chart(fig)


# ===========================================================================
# Tab 1: 价格与技术
# ===========================================================================
if tab_idx == 0:
    st.caption("K线 / 均线 / 布林带 / MACD / RSI / 成交量")

    # -- K线 + 均线 + 布林带 + 成交量 --
    has_ohlc = all(c in df_factors.columns for c in ["open", "high", "low", "close"])
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if has_ohlc:
        # K线
        fig.add_trace(
            go.Candlestick(
                x=df_factors.index, open=df_factors["open"], high=df_factors["high"],
                low=df_factors["low"], close=df_factors["close"],
                name="K线", increasing_line_color="#ef5350", decreasing_line_color="#26a69a",
                increasing_fillcolor="rgba(239,83,80,0.6)", decreasing_fillcolor="rgba(38,166,154,0.6)",
            ),
            secondary_y=False,
        )
    elif "close" in df_factors.columns:
        fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors["close"], mode="lines",
                                  name="收盘价", line=dict(color="#1f77b4", width=1.5)), secondary_y=False)

    # 布林带
    if all(c in df_factors.columns for c in ["bb_upper", "bb_lower"]):
        fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors["bb_upper"], mode="lines",
                                  line=dict(color="rgba(128,128,128,0.4)", width=1, dash="dash"),
                                  showlegend=True, name="布林上轨"), secondary_y=False)
        fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors["bb_lower"], mode="lines",
                                  line=dict(color="rgba(128,128,128,0.4)", width=1, dash="dash"),
                                  showlegend=True, name="布林下轨",
                                  fill="tonexty", fillcolor="rgba(128,128,128,0.08)"), secondary_y=False)

    # 均线
    for col, name, color in [("ma20", "MA20", "#ff7f0e"), ("ma60", "MA60", "#2ca02c"),
                              ("ma120", "MA120", "#d62728")]:
        if col in df_factors.columns:
            fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors[col], mode="lines",
                                      name=name, line=dict(color=color, width=0.8, dash="dot")), secondary_y=False)
    # 成交量
    if "volume" in df_factors.columns:
        fig.add_trace(go.Bar(x=df_factors.index, y=df_factors["volume"], name="成交量",
                              marker_color="rgba(31,119,180,0.2)", showlegend=True), secondary_y=True)
    fig.update_yaxes(title_text="价格 (元)", secondary_y=False)
    fig.update_yaxes(title_text="成交量 (手)", secondary_y=True)
    fig.update_layout(title="K线 & 均线 & 布林带")
    _plotly_chart(fig, height=500)

    # -- MACD --
    col_l, col_r = st.columns(2)
    with col_l:
        if all(c in df_factors.columns for c in ["dif", "dea", "macd"]):
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors["dif"], mode="lines",
                                      name="DIF", line=dict(color="#ff7f0e", width=1)))
            fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors["dea"], mode="lines",
                                      name="DEA", line=dict(color="#1f77b4", width=1)))
            macd_colors = ["#ef5350" if v >= 0 else "#26a69a" for v in df_factors["macd"].fillna(0)]
            fig.add_trace(go.Bar(x=df_factors.index, y=df_factors["macd"], name="MACD",
                                  marker_color=macd_colors, showlegend=False))
            fig.update_layout(title="MACD (12, 26, 9)")
            _plotly_chart(fig, height=350)
    
    with col_r:
        if "rsi14" in df_factors.columns:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors["rsi14"], mode="lines",
                                      name="RSI(14)", line=dict(color="#ff7f0e", width=1.5)))
            fig.add_hline(y=70, line_dash="dash", line_color="rgba(255,0,0,0.4)")
            fig.add_hline(y=30, line_dash="dash", line_color="rgba(0,128,0,0.4)")
            fig.add_hline(y=50, line_dash="dot", line_color="rgba(128,128,128,0.3)")
            fig.update_yaxes(range=[0, 100])
            fig.update_layout(title="RSI (14)")
            _plotly_chart(fig, height=350)

    # -- 成交量 & 换手率 --
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if "vol_ratio" in df_factors.columns:
        fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors["vol_ratio"], mode="lines",
                                  name="量比", line=dict(color="#2ca02c", width=1)), secondary_y=False)
    if "turnover" in df_factors.columns:
        fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors["turnover"], mode="lines",
                                  name="换手率(%)", line=dict(color="#d62728", width=1)), secondary_y=True)
    fig.add_hline(y=1, line_dash="dash", line_color="rgba(128,128,128,0.4)", secondary_y=False)
    fig.update_yaxes(title_text="量比", secondary_y=False)
    fig.update_yaxes(title_text="换手率(%)", secondary_y=True)
    fig.update_layout(title="量比 & 换手率")
    _plotly_chart(fig, height=300)


# ===========================================================================
# Tab 2: 估值分析
# ===========================================================================
if tab_idx == 1:
    st.caption("PE / PB / 市值 / PEG | 估值历史分位")

    col1, col2 = st.columns(2)

    with col1:
        # PE + PB 双 Y 轴
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        for col, name, color, secondary in [("pe_ttm", "PE(TTM)", "#d62728", False),
                                             ("pb", "PB", "#1f77b4", True)]:
            if col in df_factors.columns:
                fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors[col], mode="lines",
                                          name=name, line=dict(color=color, width=1.3)), secondary_y=secondary)
        fig.update_yaxes(title_text="PE (倍)", secondary_y=False)
        fig.update_yaxes(title_text="PB (倍)", secondary_y=True)
        fig.update_layout(title="PE(TTM) & PB")
        _plotly_chart(fig, height=380)

    with col2:
        # 市值
        fig = go.Figure()
        if "total_mv" in df_factors.columns:
            mv = df_factors["total_mv"].dropna()
            fig.add_trace(go.Scatter(x=mv.index, y=mv / 1e8, mode="lines",
                                      name="总市值(亿)", fill="tozeroy",
                                      line=dict(color="#1f77b4", width=1.5),
                                      fillcolor="rgba(31,119,180,0.1)"))
        fig.update_layout(title="总市值 (亿元)")
        _plotly_chart(fig, height=380)

    # PE 分位数
    if "pe_ttm" in df_factors.columns:
        pe_data = df_factors["pe_ttm"].dropna()
        if len(pe_data) > 0:
            current_pe = pe_data.iloc[-1]
            pct = (pe_data < current_pe).mean() * 100
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("当前 PE(TTM)", f"{current_pe:.1f}")
            with col_b:
                st.metric("历史分位", f"{pct:.0f}%", delta=f"高于{pct:.0f}%的历史值" if pct > 50 else f"低于{100-pct:.0f}%的历史值")
            with col_c:
                st.metric("PEG", f"{df_factors.get('peg', pd.Series([np.nan])).iloc[-1]:.2f}" if "peg" in df_factors.columns else "N/A")

    # PE 分布直方图
    if "pe_ttm" in df_factors.columns and len(pe_data) > 30:
        fig = go.Figure()
        fig.add_trace(go.Histogram(x=pe_data, nbinsx=40, name="PE分布",
                                    marker_color="rgba(31,119,180,0.6)"))
        if not np.isnan(current_pe):
            fig.add_vline(x=current_pe, line_dash="dash", line_color="red",
                          annotation_text=f"当前: {current_pe:.1f}")
        fig.update_layout(title="PE(TTM) 历史分布", xaxis_title="PE", yaxis_title="频次")
        _plotly_chart(fig, height=300)


# ===========================================================================
# Tab 3: 盈利能力
# ===========================================================================
if tab_idx == 2:
    st.caption("ROE / 毛利率 / 净利率 / EPS / 每股净资产")

    col1, col2 = st.columns(2)

    with col1:
        # 杜邦三要素
        fig = go.Figure()
        for col, name, color in [("roe", "ROE(%)", "#d62728"),
                                  ("gross_margin", "毛利率(%)", "#ff7f0e"),
                                  ("net_margin", "净利率(%)", "#2ca02c")]:
            if col in df_factors.columns:
                s = df_factors[col].dropna()
                if len(s) > 0:
                    fig.add_trace(go.Scatter(x=s.index, y=s, mode="lines+markers",
                                              name=name, line=dict(color=color, width=1.5), marker=dict(size=3)))
        fig.update_layout(title="ROE / 毛利率 / 净利率")
        _plotly_chart(fig, height=400)

    with col2:
        # EPS & BPS
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        for col, name, color, sec in [("eps", "EPS(元)", "#1f77b4", False),
                                       ("bps", "每股净资产(元)", "#2ca02c", True)]:
            if col in df_factors.columns:
                s = df_factors[col].dropna()
                if len(s) > 0:
                    fig.add_trace(go.Bar(x=s.index, y=s, name=name,
                                          marker_color=color, opacity=0.7), secondary_y=sec)
        fig.update_yaxes(title_text="EPS (元)", secondary_y=False)
        fig.update_yaxes(title_text="每股净资产 (元)", secondary_y=True)
        fig.update_layout(title="每股收益 & 每股净资产")
        _plotly_chart(fig, height=400)

    # 杜邦分解 (季度)
    if df_financials is not None and not df_financials.empty:
        fin_dupont = df_financials[["roe", "net_margin", "gross_margin"]].dropna(how="all")
        if not fin_dupont.empty:
            st.subheader("季度杜邦分解")
            dupont_df = fin_dupont.tail(20).copy()
            dupont_df.index = dupont_df.index.strftime("%Y-%m")
            # 转置为列 = 报告期, 行为指标
            fig = go.Figure()
            for col, name, color in [("roe", "ROE(%)", "#d62728"),
                                      ("gross_margin", "毛利率(%)", "#ff7f0e"),
                                      ("net_margin", "净利率(%)", "#2ca02c")]:
                if col in fin_dupont.columns:
                    y_vals = fin_dupont[col].dropna()
                    x_vals = [d.strftime("%Y-%m") for d in y_vals.index]
                    fig.add_trace(go.Bar(name=name, x=x_vals, y=y_vals.values,
                                          marker=dict(color=color, opacity=0.7)))
            fig.update_layout(barmode="group", xaxis_tickangle=-45, height=350)
            _plotly_chart(fig, height=400)


# ===========================================================================
# Tab 4: 成长动量
# ===========================================================================
if tab_idx == 3:
    st.caption("营收/净利同比增长 | 价格动量 | 均线偏离度")

    col1, col2 = st.columns(2)

    with col1:
        # 营收/净利 同比增长
        fig = go.Figure()
        for col, name, color in [("revenue_yoy", "营收同比(%)", "#1f77b4"),
                                  ("net_profit_yoy", "净利同比(%)", "#d62728"),
                                  ("recurring_np_yoy", "扣非净利同比(%)", "#2ca02c")]:
            if col in df_factors.columns:
                s = df_factors[col].dropna()
                if len(s) > 0:
                    fig.add_trace(go.Scatter(x=s.index, y=s, mode="lines+markers",
                                              name=name, line=dict(color=color, width=1.5), marker=dict(size=3)))
        fig.add_hline(y=0, line_dash="solid", line_color="rgba(128,128,128,0.5)")
        fig.update_layout(title="营收 / 净利润同比增长率")
        _plotly_chart(fig, height=380)

    with col2:
        # 价格动量
        fig = go.Figure()
        for col, name, color in [("mom20d", "20日动量(%)", "#ff7f0e"),
                                  ("mom60d", "60日动量(%)", "#2ca02c"),
                                  ("mom120d", "120日动量(%)", "#d62728"),
                                  ("mom250d", "年动量(%)", "#9467bd")]:
            if col in df_factors.columns:
                fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors[col], mode="lines",
                                          name=name, line=dict(color=color, width=1)))
        fig.add_hline(y=0, line_dash="solid", line_color="rgba(128,128,128,0.5)")
        fig.update_layout(title="价格动量 (多周期)")
        _plotly_chart(fig, height=380)

    # 均线偏离度
    fig = go.Figure()
    for col, name, color in [("ma20_dev", "MA20偏离(%)", "#ff7f0e"),
                              ("ma60_dev", "MA60偏离(%)", "#2ca02c"),
                              ("ma120_dev", "MA120偏离(%)", "#d62728"),
                              ("ma250_dev", "MA250偏离(%)", "#9467bd")]:
        if col in df_factors.columns:
            fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors[col], mode="lines",
                                      name=name, line=dict(color=color, width=0.8)))
    fig.add_hline(y=0, line_dash="solid", line_color="rgba(128,128,128,0.5)")
    fig.update_layout(title="均线偏离度 (%)")
    _plotly_chart(fig, height=350)


# ===========================================================================
# Tab 5: 财务健康
# ===========================================================================
if tab_idx == 4:
    st.caption("资产负债率 / 流动/速动比率 / 经营现金流")

    col1, col2 = st.columns(2)

    with col1:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        for col, name, color, sec in [("debt_ratio", "资产负债率(%)", "#d62728", False),
                                       ("current_ratio", "流动比率", "#1f77b4", True),
                                       ("quick_ratio", "速动比率", "#2ca02c", True)]:
            if col in df_factors.columns:
                s = df_factors[col].dropna()
                if len(s) > 0:
                    fig.add_trace(go.Scatter(x=s.index, y=s, mode="lines+markers",
                                              name=name, line=dict(color=color, width=1.5),
                                              marker=dict(size=3)), secondary_y=sec)
        fig.update_yaxes(title_text="负债率(%)", secondary_y=False)
        fig.update_yaxes(title_text="比率", secondary_y=True)
        fig.update_layout(title="资产负债率 / 流动比率 / 速动比率")
        _plotly_chart(fig, height=400)

    with col2:
        # 每股经营现金流
        fig = go.Figure()
        if "cfps" in df_factors.columns:
            s = df_factors["cfps"].dropna()
            if len(s) > 0:
                colors_cf = ["#ef5350" if v >= 0 else "#26a69a" for v in s.values]
                fig.add_trace(go.Bar(x=s.index, y=s.values, name="每股经营现金流",
                                      marker_color=colors_cf, opacity=0.7))
        fig.update_layout(title="每股经营现金流 (元)")
        _plotly_chart(fig, height=400)

    # 季度详细财务指标表格
    if df_financials is not None and not df_financials.empty:
        st.subheader("季度财务摘要")
        display_cols = ["revenue", "net_profit", "eps", "roe", "gross_margin",
                        "net_margin", "debt_ratio", "current_ratio"]
        avail = [c for c in display_cols if c in df_financials.columns]
        if avail:
            recent = df_financials[avail].tail(8).sort_index(ascending=False)
            # 格式化
            fmt = recent.copy()
            for c in fmt.columns:
                if "margin" in c or c in ["roe", "debt_ratio"]:
                    fmt[c] = fmt[c].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "-")
                elif c in ["eps"]:
                    fmt[c] = fmt[c].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "-")
                elif c in ["revenue", "net_profit"]:
                    fmt[c] = fmt[c].apply(lambda x: f"{x/1e8:.2f}亿" if pd.notna(x) else "-")
                elif c in ["current_ratio"]:
                    fmt[c] = fmt[c].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "-")
            fmt.index = fmt.index.strftime("%Y-%m")
            st.dataframe(fmt, width='stretch')


# ===========================================================================
# Tab 6: 风险指标
# ===========================================================================
if tab_idx == 5:
    st.caption("Beta / 波动率 / 最大回撤")

    col1, col2 = st.columns(2)

    with col1:
        # Beta + 波动率
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        if "beta" in df_factors.columns:
            fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors["beta"], mode="lines",
                                      name="Beta(60日)", line=dict(color="#d62728", width=1.2)), secondary_y=False)
        if "vol60d" in df_factors.columns:
            fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors["vol60d"], mode="lines",
                                      name="年化波动率(%)", line=dict(color="#7b1fa2", width=1)), secondary_y=True)
        fig.add_hline(y=1, line_dash="dash", line_color="rgba(128,128,128,0.4)", secondary_y=False)
        fig.update_yaxes(title_text="Beta", secondary_y=False)
        fig.update_yaxes(title_text="波动率(%)", secondary_y=True)
        fig.update_layout(title="Beta(60日) & 年化波动率")
        _plotly_chart(fig, height=400)

    with col2:
        # 最大回撤
        fig = go.Figure()
        for col, name, color in [("mdd60d", "60日回撤(%)", "#ff7f0e"),
                                  ("mdd120d", "120日回撤(%)", "#d62728"),
                                  ("mdd250d", "250日回撤(%)", "#1f77b4")]:
            if col in df_factors.columns:
                fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors[col], mode="lines",
                                          name=name, line=dict(color=color, width=0.8)))
        fig.update_layout(title="滚动最大回撤 (%)", yaxis=dict(autorange="reversed"))
        _plotly_chart(fig, height=400)

    # 波动率多周期
    fig = go.Figure()
    for col, name, color in [("vol20d", "20日波动率", "#ff7f0e"),
                              ("vol60d", "60日波动率", "#2ca02c"),
                              ("vol120d", "120日波动率", "#1f77b4")]:
        if col in df_factors.columns:
            fig.add_trace(go.Scatter(x=df_factors.index, y=df_factors[col], mode="lines",
                                      name=name, line=dict(color=color, width=1)))
    fig.update_layout(title="历史波动率 (年化 %)")
    _plotly_chart(fig, height=350)


# ===========================================================================
# Tab 8: 数据表格
# ===========================================================================

# ===========================================================================
# Tab 6: 历史形态匹配 (Pearson)
# ===========================================================================
if tab_idx == 6:
    st.caption("用 Pearson 相关系数在历史上搜索与当前窗口最相似的因子形态")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        window_days = st.selectbox("匹配窗口", [5, 10, 20, 30, 60], index=1,
                                    format_func=lambda x: f"{x} 个交易日")
    with col2:
        top_n = st.slider("显示前 N 名", 1, 20, 5)
    with col3:
        lookahead = st.slider("预测展望 (天)", 0, 60, window_days)
    with col4:
        algo = st.radio("匹配算法", ["pearson", "dtw", "pearson_dtw"], horizontal=True, key="match_algo",
                        format_func=lambda x: {"pearson": "Pearson", "dtw": "DTW", "pearson_dtw": "Pearson+DTW"}.get(x, x),
                        help="Pearson: 快 | DTW: LB_Keogh剪枝 | Pearson+DTW: 初筛+精选")

    template_end = st.date_input("模板截止日", value=df_factors.index[-1],
                                  min_value=df_factors.index[0],
                                  max_value=df_factors.index[-1],
                                  key="template_end",
                                  help="模板窗口为 [截止日 - 窗口天数, 截止日]")

    # 选择匹配因子
    signal_factors = ["sig_macross", "sig_rsizone", "sig_volbreak", "sig_macd", "sig_bbsqueeze"]
    matchable_base = [c for c in df_factors.columns if c not in
                      ["open", "high", "low", "volume", "amount", "turnover",
                       "pct_change", "dif", "dea", "macd"] +
                      [c for c in df_factors.columns if c.startswith("bb_") and c not in ["bb_pct_b"]]]
    matchable_factors = matchable_base
    default_match = ["close", "pe_ttm", "pb", "rsi14"]

    # 快捷预设
    preset_valid = {k: [f for f in v if f in matchable_factors] for k, v in FACTOR_PRESETS.items()}
    st.caption("快捷预设")
    pcols = st.columns(len(preset_valid))
    for i, (name, factors) in enumerate(preset_valid.items()):
        with pcols[i]:
            if st.button(name, key=f"preset_match_{i}", width='stretch',
                         help=", ".join(factors)):
                st.session_state.match_factors = factors
                st.rerun()

    if "match_factors" not in st.session_state:
        st.session_state.match_factors = [f for f in default_match if f in df_factors.columns]

    selected_factors = st.multiselect(
        "选择匹配因子", matchable_factors,
        key="match_factors",
        help="选择多个因子后会取平均相关系数作为综合得分"
    )

    if not selected_factors:
        st.info("请至少选择一个因子")
    else:
        # ---- 因子权重配置 ----
        st.caption("因子权重 (总和自动归一化为 1)")
        raw_weights = {}
        wcols = st.columns(min(len(selected_factors), 4))
        for i, factor in enumerate(selected_factors):
            with wcols[i % 4]:
                raw_weights[factor] = st.slider(
                    factor, 0, 100, 100 // len(selected_factors),
                    key=f"w_{factor}", help=f"{factor} 的匹配权重"
                )
        total = sum(raw_weights.values()) or 1
        weights = {f: w / total for f, w in raw_weights.items()}
        if len(selected_factors) > 1:
            st.caption(" → ".join(f"{f}: {weights[f]:.1%}" for f in selected_factors))

        valid = df_factors[selected_factors].dropna()
        if len(valid) < window_days * 2:
            st.warning(f"有效数据点不足 (最少需要 {window_days * 2})")
        else:
            # ---- 回溯搜索 (缓存相关系数, 权重变化不重算) ----
            # 找到模板截止日在 valid 中的位置
            template_end_dt = pd.Timestamp(template_end)
            if template_end_dt in valid.index:
                tpl_end_pos = valid.index.get_loc(template_end_dt)
            else:
                # 取最接近的日期
                valid_sorted = valid.index.sort_values()
                nearest = valid_sorted[valid_sorted <= template_end_dt]
                tpl_end_pos = valid.index.get_loc(nearest[-1]) if len(nearest) > 0 else len(valid) - 1

            @st.cache_data(ttl=3600, show_spinner=False)
            def _compute_scores(valid_df, selected, win, tpl_pos, algo_name):
                detail = {}
                tpl = valid_df.iloc[tpl_pos - win + 1 : tpl_pos + 1]
                n = len(valid_df)

                # pearson_dtw: 预计算 Pearson 矩阵做初筛
                pearson_mat = None
                if algo_name == "pearson_dtw":
                    pearson_mat = _pearson_corr_matrix([valid_df[f].values for f in selected], win,
                                                         [weights.get(f, 1.0 / len(selected)) for f in selected])

                for factor in selected:
                    tpl_vals = tpl[factor].values
                    if np.std(tpl_vals) == 0:
                        detail[factor] = pd.Series(0.0, index=valid_df.index)
                        continue
                    sim_s = pd.Series(np.nan, index=valid_df.index)
                    vals = valid_df[factor].values

                    for i in range(win, tpl_pos - win + 2):  # 只搜索模板开始前的窗口
                        w = vals[i - win:i]
                        if algo_name == "dtw":
                            s = _dtw_similarity(tpl_vals, w, min_similarity=0.5)
                        elif algo_name == "pearson_dtw":
                            tpl_widx = tpl_pos - win + 1
                            cand_widx = i - win + 1
                            if pearson_mat[tpl_widx, cand_widx] >= 0.3:
                                s = _dtw_similarity(tpl_vals, w, min_similarity=0.5)
                            else:
                                continue
                        else:
                            s = _compute_single_similarity(tpl_vals, w, algo_name)
                        if not np.isnan(s):
                            sim_s.iloc[i - 1] = s
                    detail[factor] = sim_s
                return detail

            detail_scores = _compute_scores(valid, selected_factors, window_days, tpl_end_pos, algo)

            # 加权综合得分
            scores = pd.DataFrame(0.0, index=valid.index, columns=["综合得分"])
            for factor in selected_factors:
                scores["综合得分"] += detail_scores[factor].fillna(0) * weights.get(factor, 1.0)

            top_matches = scores.dropna().sort_values("综合得分", ascending=False).head(top_n)

            # ---- 可视化 ----
            st.subheader(f"与最近 {window_days} 天最相似的历史片段 (Pearson r)")

            if top_matches.empty or top_matches["综合得分"].iloc[0] < 0.3:
                st.info("未找到高相似度片段 (最高 r < 0.3)，尝试增加窗口或更换因子")
            else:
                # -- 图1: 当前模板 --
                fig = go.Figure()
                tpl_slice = valid.iloc[tpl_end_pos - window_days + 1 : tpl_end_pos + 1]
                x_rel = list(range(-len(tpl_slice) + 1, 1))
                tpl_dates = [d.strftime("%Y-%m-%d") for d in tpl_slice.index]
                for factor, color in zip(selected_factors,
                                         ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd", "#8c564b"]):
                    if factor in valid.columns:
                        vals = tpl_slice[factor].dropna()
                        if len(vals) > 0:
                            fig.add_trace(go.Scatter(
                                x=x_rel, y=vals.values, mode="lines+markers",
                                name=f"当前 {factor}", line=dict(color=color, width=2),
                                customdata=[tpl_dates[i] for i in vals.index.get_indexer(tpl_slice.index)],
                                hovertemplate="%{customdata}<br>%{y:.2f}<extra></extra>",
                            ))
                fig.update_layout(title=f"当前模板 ({tpl_slice.index[0].strftime('%Y-%m-%d')} ~ {tpl_slice.index[-1].strftime('%Y-%m-%d')})",
                                  xaxis_title="距截止日 (天)", height=300)
                _plotly_chart(fig, height=350)

                # -- 按排名展示 (综合评分选 match, 每个因子单独画图) --
                factor_colors = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd", "#8c564b"]

                for rank_idx, (match_date, score_row) in enumerate(top_matches.iterrows()):
                    score_val = score_row["综合得分"]
                    st.subheader(f"匹配排名 #{rank_idx + 1}  综合 r={score_val:.3f}")
                    cols = st.columns(min(len(selected_factors), 3))

                    for fi, factor in enumerate(selected_factors):
                        with cols[fi % 3]:
                            color = factor_colors[fi % len(factor_colors)]
                            pos = valid.index.get_loc(match_date)
                            match_start = pos - window_days + 1

                            hist_win = valid[factor].iloc[match_start:pos + 1]
                            future_end = min(pos + 1 + lookahead, len(valid))
                            hist_fut = valid[factor].iloc[pos + 1:future_end]
                            cur_win = valid[factor].iloc[tpl_end_pos - window_days + 1 : tpl_end_pos + 1]

                            single_r = detail_scores[factor].get(match_date, np.nan)

                            # 对齐到相对时间轴 (x=0 为匹配截止日)
                            x_match = list(range(-len(hist_win) + 1, 1))
                            x_future = list(range(1, len(hist_fut) + 1))
                            x_current = list(range(-len(cur_win) + 1, 1))

                            # 悬停提示: 显示实际日期
                            h_match = [d.strftime("%Y-%m-%d") for d in hist_win.index]
                            h_future = [d.strftime("%Y-%m-%d") for d in hist_fut.index]
                            h_current = [d.strftime("%Y-%m-%d") for d in cur_win.index]
                            hover_tpl = "%{customdata}<br>%{y:.2f}<extra></extra>"

                            sub_fig = go.Figure()
                            sub_fig.add_trace(go.Scatter(
                                x=x_match, y=hist_win.values,
                                mode="lines", name="历史",
                                line=dict(color=color, width=1.5),
                                customdata=h_match, hovertemplate=hover_tpl,
                            ))
                            sub_fig.add_trace(go.Scatter(
                                x=x_future, y=hist_fut.values,
                                mode="lines", name="预测",
                                line=dict(color=color, width=1.5, dash="dash"),
                                customdata=h_future, hovertemplate=hover_tpl,
                            ))
                            sub_fig.add_trace(go.Scatter(
                                x=x_current, y=cur_win.values,
                                mode="lines+markers", name="当前",
                                line=dict(color="#d62728", width=2),
                                marker=dict(size=3),
                                customdata=h_current, hovertemplate=hover_tpl,
                            ))
                            sub_fig.add_vline(x=0, line_dash="dot",
                                              line_color="gray", line_width=0.8, opacity=0.5)
                            match_label = match_date.strftime("%Y-%m-%d")
                            sub_fig.update_layout(
                                title=f"{factor}  r={single_r:.3f}  →{match_label}",
                                height=220,
                                margin=dict(l=20, r=20, t=30, b=15),
                                template="plotly_white",
                                legend=dict(orientation="h", font=dict(size=8)),
                            )
                            sub_fig.update_xaxes(gridcolor="rgba(128,128,128,0.1)")
                            sub_fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)")
                            st.plotly_chart(sub_fig)

                # ---- 汇总预测图 (基于第一个因子) ----
                if lookahead > 0:
                    primary = selected_factors[0]
                    st.subheader(f"共识预测 — {primary}")
                    pred_fig = go.Figure()

                    all_predictions = []
                    for _, (match_date, _) in enumerate(top_matches.iterrows()):
                        pos = valid.index.get_loc(match_date)
                        future_end = min(pos + 1 + lookahead, len(valid))
                        future_vals = valid[primary].iloc[pos + 1:future_end].values
                        if len(future_vals) == lookahead:
                            all_predictions.append(future_vals)

                    if all_predictions:
                        preds = np.array(all_predictions)
                        avg_pred = np.mean(preds, axis=0)
                        std_pred = np.std(preds, axis=0)
                        x_future = list(range(1, lookahead + 1))

                        for i, p in enumerate(preds):
                            pred_fig.add_trace(go.Scatter(
                                x=x_future, y=p, mode="lines",
                                line=dict(width=0.5, color="rgba(31,119,180,0.3)"),
                                showlegend=(i == 0), name="各匹配预测",
                            ))
                        pred_fig.add_trace(go.Scatter(
                            x=x_future, y=avg_pred + std_pred, mode="lines",
                            line=dict(width=0), showlegend=False,
                        ))
                        pred_fig.add_trace(go.Scatter(
                            x=x_future, y=avg_pred - std_pred, mode="lines",
                            line=dict(width=0), showlegend=False,
                            fill="tonexty", fillcolor="rgba(31,119,180,0.08)",
                        ))
                        pred_fig.add_trace(go.Scatter(
                            x=x_future, y=avg_pred, mode="lines+markers",
                            name=f"均值预测 (n={len(preds)})",
                            line=dict(color="#1f77b4", width=2.5),
                            marker=dict(size=5),
                        ))
                        last_price = valid[primary].iloc[tpl_end_pos]
                        pred_fig.add_hline(y=last_price, line_dash="dot",
                                           line_color="gray", line_width=1,
                                           annotation_text=f"当前: {last_price:.2f}")
                        pred_fig.update_layout(
                            title=f"{primary} — 共识预测 (基于 {len(preds)} 个相似片段, 置信带 ±1σ)",
                            xaxis_title="未来交易日",
                            yaxis_title=primary,
                            height=350,
                        )
                        _plotly_chart(pred_fig, height=400)

                # -- 得分详情表 --
                st.caption("Top 匹配详情")
                detail_df = pd.DataFrame({
                    "排名": range(1, len(top_matches) + 1),
                    "匹配日期": [d.strftime("%Y-%m-%d") for d in top_matches.index],
                    "综合得分": top_matches["综合得分"].round(4).values,
                })
                # 添加各因子得分
                for factor, corr_s in detail_scores.items():
                    detail_df[f"{factor}_r"] = [corr_s.get(d, np.nan) for d in top_matches.index]
                    detail_df[f"{factor}_r"] = detail_df[f"{factor}_r"].round(3)
                st.dataframe(detail_df, width='stretch', hide_index=True)


# ===========================================================================
# Tab 7: 回测验证
# ===========================================================================
if tab_idx == 7:
    st.caption("逐日回测: 每一天生成模板 → 匹配历史 → 记录预测 vs 实际, 计算命中率")

    # 匹配因子池
    bt_factors_pool = [c for c in df_factors.columns if c not in
                        ["open", "high", "low", "volume", "amount", "turnover",
                         "pct_change", "dif", "dea", "macd"] +
                        [c for c in df_factors.columns if c.startswith("bb_") and c not in ["bb_pct_b"]]]

    # ---- 滑动条 ----
    st.caption("参数设置")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        bt_window = st.selectbox("模板窗口", [5, 10, 20, 30], index=1, key="bt_win",
                                  format_func=lambda x: f"{x} 天")
    with c2:
        bt_lookahead = st.slider("预测天数", 1, 20, 5, key="bt_la")
    with c3:
        bt_threshold = st.slider("相似度阈值", 0.5, 1.0, 0.9, 0.05, key="bt_th")
    with c4:
        bt_topk = st.slider("Top K 平均", 1, 10, 3, key="bt_k",
                            help="取前 K 个匹配的后续收益率均值作为预测")

    # ---- 选项 ----
    st.caption("算法与日期")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        bt_algo = st.radio("匹配算法", ["pearson", "dtw", "pearson_dtw"], horizontal=True, key="bt_algo",
                           format_func=lambda x: {"pearson": "Pearson", "dtw": "DTW", "pearson_dtw": "Pearson+DTW"}.get(x, x),
                           help="Pearson: 矩阵加速快 | DTW: LB_Keogh剪枝 | Pearson+DTW: 初筛+精选")
    with d2:
        bt_start = st.date_input("回测起始日", value=pd.Timestamp("2025-01-01"),
                                  min_value=df_factors.index[0],
                                  max_value=df_factors.index[-1], key="bt_start")
    with d3:
        bt_end = st.date_input("回测截止日", value=pd.Timestamp("2026-06-01"),
                                min_value=df_factors.index[0],
                                max_value=df_factors.index[-1], key="bt_end")

    # 策略开关
    st.caption("策略增强")
    e1, e2 = st.columns(2)
    with e1:
        ensemble_mode = st.toggle("集成预测 (多窗口投票)", key="bt_ensemble",
                                  help="同时看 3/5/10 天, 多数表决方向")
    with e2:
        timing_filter = st.toggle("择时过滤 (高波动日跳过)", key="bt_timing",
                                  help="vol20d > 历史80%分位时不出信号")

    # 快捷预设
    bt_preset_valid = {k: [f for f in v if f in bt_factors_pool] for k, v in FACTOR_PRESETS.items()}
    st.caption("快捷预设")
    bpcols = st.columns(len(bt_preset_valid))
    for i, (name, factors) in enumerate(bt_preset_valid.items()):
        with bpcols[i]:
            if st.button(name, key=f"preset_bt_{i}", width='stretch',
                         help=", ".join(factors)):
                st.session_state.bt_factors = factors
                st.rerun()

    if "bt_factors" not in st.session_state:
        st.session_state.bt_factors = [f for f in ["close", "rsi14"] if f in bt_factors_pool]

    bt_factors = st.multiselect(
        "匹配因子", bt_factors_pool,
        key="bt_factors",
        help="选择2-3个核心因子以提高计算速度"
    )

    # 因子权重
    if bt_factors:
        st.caption("因子权重 (总和自动归一化)")
        raw_w = {}
        wcols = st.columns(min(len(bt_factors), 4))
        for i, factor in enumerate(bt_factors):
            with wcols[i % 4]:
                raw_w[factor] = st.slider(factor, 0, 100, 100 // len(bt_factors), key=f"btw_{factor}")
        total_w = sum(raw_w.values()) or 1
        bt_weights = {f: w / total_w for f, w in raw_w.items()}
        if len(bt_factors) > 1:
            st.caption(" → ".join(f"{f}: {bt_weights[f]:.0%}" for f in bt_factors))
    else:
        bt_weights = {}

    bt_weight_list = [bt_weights.get(f, 0.0) for f in bt_factors] if bt_factors else []

    fast_mode = st.checkbox("⚡ 快速模式 (仅 Pearson, 矩阵加速)", value=True, key="bt_fast",
                            help="预计算相关系数矩阵, 秒级出结果。关闭后逐日滑动计算, 较慢但支持 DTW。")

    use_lgbm = st.checkbox("🤖 LightGBM 自动权重", value=False, key="bt_lgbm",
                            help="用 LightGBM 从回测数据中学习各因子最优权重, 替代手动滑块")

    walk_forward = st.checkbox("🔬 三段切分验证 (50%训练/20%验证/30%测试)", value=True, key="bt_wf",
                                help="三段切分, 仅显示测试集结果。关闭则全量回测。")

    col_btns = st.columns(2)
    with col_btns[0]:
        run_bt = st.button("🚀 开始回测", type="primary", key="bt_run", width='stretch')
    with col_btns[1]:
        run_tune = st.button("🔧 自动调参", key="bt_tune", width='stretch',
                             help="搜索窗口/预测天数/阈值/TopK 的最优组合")

    if run_bt or run_tune:
        if not bt_factors:
            st.warning("请选择匹配因子")
        else:
            valid_bt = df_factors[bt_factors].dropna()
            # ---- 趋势分层: 为每个交易日贴牛/熊/震荡标签 ----
            regime_labels = np.full(len(valid_bt), "震荡", dtype=object)
            if "ma60" in df_factors.columns and "ma250" in df_factors.columns:
                close_all = df_factors["close"].reindex(valid_bt.index)
                ma60_all = df_factors["ma60"].reindex(valid_bt.index)
                ma250_all = df_factors["ma250"].reindex(valid_bt.index)
                ma60_rising = ma60_all > ma60_all.shift(20)
                regime_labels[(close_all > ma250_all) & ma60_rising] = "牛市"
                regime_labels[(close_all < ma250_all) & ~ma60_rising] = "熊市"
            regime_series = pd.Series(regime_labels, index=valid_bt.index)
            st.session_state.regime_series = regime_series  # 持久化供展示用
            n = len(valid_bt)

            if n < bt_window * 5:
                st.warning(f"数据不足 (需要至少 {bt_window * 5} 天, 当前 {n} 天)")
            else:
                start_idx, end_idx = _resolve_date_range(valid_bt.index, bt_start, bt_end, bt_window * 2)
                # Bug 1 fix: ensemble 模式下 outer loop bound 用 10 天 (ensemble max horizon)
                end_idx = min(end_idx, n - (10 if ensemble_mode else bt_lookahead))
                full_start = start_idx  # 记住原始起始位, walk-forward 时切分要用

                if walk_forward:
                    total_range = end_idx - full_start
                    train_end = full_start + int(total_range * 0.5)
                    valid_end = full_start + int(total_range * 0.7)
                    test_start = valid_end
                    start_idx = test_start

                total_days = end_idx - start_idx

                if total_days <= 0:
                    msg = "日期范围内无有效回测日"
                    if walk_forward:
                        msg += " (Walk-forward 测试集不足, 尝试延长日期范围或关闭 Walk-forward)"
                    else:
                        msg += " (需要至少窗口×2 天历史数据)"
                    st.warning(msg)
                else:
                    vals_dict = {f: valid_bt[f].values for f in bt_factors}
                    price_vals = df_factors.loc[valid_bt.index, "close"].values
                    win = bt_window

                    # 择时过滤阈值 (两个 helper 共享)
                    vol_data, vol_thresh = None, None
                    if timing_filter:
                        vol_data = df_factors["vol20d"].reindex(valid_bt.index).fillna(0)
                        vol_thresh = np.percentile(vol_data[vol_data > 0], 80)

                    def _run_bt_fast(eval_start, eval_end, combined_corr):
                        res = []
                        edays = eval_end - eval_start
                        for ti, t in enumerate(range(eval_start, eval_end)):
                            # 择时过滤
                            if timing_filter and vol_thresh is not None:
                                if vol_data.iloc[t] > vol_thresh:
                                    continue
                            tpl_idx = t - win
                            hist_end = tpl_idx - win
                            if hist_end >= 0:
                                row = combined_corr[tpl_idx, :hist_end + 1]
                                row_sim = (row + 1) / 2
                                match_indices = np.where(row_sim >= bt_threshold)[0]
                                if len(match_indices) > 0:
                                    match_scores = row[match_indices]
                                    top_k_idx = match_indices[np.argsort(-match_scores)[:bt_topk]]
                                    top_scores = row[top_k_idx]
                                    lheads = _bt_lookaheads(bt_lookahead, ensemble_mode)
                                    eval_la = lheads[len(lheads) // 2]
                                    pred_by_la = [[] for _ in lheads]
                                    for s_idx in top_k_idx:
                                        s_end = s_idx + win - 1
                                        for li, la in enumerate(lheads):
                                            if s_end + 1 + la <= n:
                                                r = (price_vals[s_end + la] - price_vals[s_end + 1]) / price_vals[s_end + 1]
                                                pred_by_la[li].append(r)
                                    pred_by_la = [pr for pr in pred_by_la if pr]
                                    if pred_by_la:
                                        direction, avg_pred = _predict_direction(pred_by_la, ensemble_mode)
                                        actual_return = (price_vals[t + eval_la - 1] - price_vals[t]) / price_vals[t]
                                        hit, neutral = _classify_hit(direction, avg_pred, actual_return, ensemble_mode)
                                        res.append({
                                            "date": valid_bt.index[t], "matches": len(match_indices),
                                            "top_r": top_scores[0], "pred_return": avg_pred,
                                            "actual_return": actual_return, "hit": hit,
                                            "neutral": neutral,
                                        })
                        return res

                    def _run_bt_slow(eval_start, eval_end, pearson_mat):
                        res = []
                        edays = eval_end - eval_start
                        for ti, t in enumerate(range(eval_start, eval_end)):
                            # 择时过滤
                            if timing_filter and vol_thresh is not None:
                                if vol_data.iloc[t] > vol_thresh:
                                    continue
                            tpl_vals = {f: vals_dict[f][t - win:t] for f in bt_factors}
                            scores = []
                            for s in range(win, t - win + 1):
                                win_vals = {f: vals_dict[f][s - win:s] for f in bt_factors}
                                sims = []
                                if bt_algo == "dtw":
                                    for f in bt_factors:
                                        s_val = _dtw_similarity(tpl_vals[f], win_vals[f],
                                                                min_similarity=bt_threshold)
                                        if not np.isnan(s_val):
                                            sims.append(s_val)
                                elif bt_algo == "pearson_dtw":
                                    if pearson_mat[t - win, s - win] >= 0.3:
                                        for f in bt_factors:
                                            s_val = _dtw_similarity(tpl_vals[f], win_vals[f],
                                                                    min_similarity=bt_threshold)
                                            if not np.isnan(s_val):
                                                sims.append(s_val)
                                else:
                                    for f in bt_factors:
                                        s_val = _compute_single_similarity(tpl_vals[f], win_vals[f], bt_algo)
                                        if not np.isnan(s_val):
                                            sims.append(s_val)
                                if sims and np.mean(sims) >= bt_threshold:
                                    lheads = _bt_lookaheads(bt_lookahead, ensemble_mode)
                                    futs = [price_vals[s:min(s + la, n)] for la in lheads]
                                    scores.append((np.mean(sims), s, futs))
                            if scores:
                                scores.sort(key=lambda x: -x[0])
                                top = scores[:bt_topk]
                                lheads = _bt_lookaheads(bt_lookahead, ensemble_mode)
                                eval_la = lheads[len(lheads) // 2]
                                pred_by_la = [[] for _ in lheads]
                                for _, _, futs in top:
                                    for li, fut in enumerate(futs):
                                        if len(fut) >= 2:
                                            pred_by_la[li].append((fut[-1] - fut[0]) / fut[0])
                                pred_by_la = [pr for pr in pred_by_la if pr]
                                if not pred_by_la:
                                    continue
                                direction, avg_pred = _predict_direction(pred_by_la, ensemble_mode)
                                actual_return = (price_vals[t + eval_la - 1] - price_vals[t]) / price_vals[t]
                                hit, neutral = _classify_hit(direction, avg_pred, actual_return, ensemble_mode)
                                res.append({
                                    "date": valid_bt.index[t],
                                    "matches": len(scores),
                                    "top_r": scores[0][0],
                                    "pred_return": avg_pred,
                                    "actual_return": actual_return,
                                    "hit": hit,
                                    "neutral": neutral,
                                })
                        return res

                    # ---- 执行回测 ----
                    if fast_mode and bt_algo == "pearson":
                        with st.spinner(f"预计算相关系数矩阵 ({len(bt_factors)} 因子 × {n - win + 1} 窗口)..."):
                            combined_corr = _pearson_corr_matrix([vals_dict[f] for f in bt_factors], win, bt_weight_list)

                        if walk_forward:
                            st.caption(f"三段切分: 训练 {train_end - full_start}天 → 验证 {valid_end - train_end}天 → 测试 {end_idx - test_start}天")
                            results_train = _run_bt_fast(full_start, train_end, combined_corr)
                            results_valid = _run_bt_fast(train_end, valid_end, combined_corr)
                            results_test = _run_bt_fast(test_start, end_idx, combined_corr)
                            st.session_state.bt_train_results = results_train if results_train else None
                            st.session_state.bt_valid_results = results_valid if results_valid else None
                            st.session_state.bt_results = results_test if results_test else None
                        else:
                            results = _run_bt_fast(start_idx, end_idx, combined_corr)
                            st.session_state.bt_results = results if results else None
                            st.session_state.bt_train_results = None
                            st.session_state.bt_valid_results = None
                    else:
                        pearson_mat_bt = None
                        if bt_algo == "pearson_dtw":
                            pearson_mat_bt = _pearson_corr_matrix([vals_dict[f] for f in bt_factors], win, bt_weight_list)

                        with st.spinner(f"正在回测 {total_days} 个交易日..."):
                            if walk_forward:
                                st.caption(f"三段切分: 训练 {train_end - full_start}天 → 验证 {valid_end - train_end}天 → 测试 {end_idx - test_start}天")
                                results_train = _run_bt_slow(full_start, train_end, pearson_mat_bt)
                                results_valid = _run_bt_slow(train_end, valid_end, pearson_mat_bt)
                                results_test = _run_bt_slow(test_start, end_idx, pearson_mat_bt)
                                st.session_state.bt_train_results = results_train if results_train else None
                                st.session_state.bt_valid_results = results_valid if results_valid else None
                                st.session_state.bt_results = results_test if results_test else None
                            else:
                                results = _run_bt_slow(start_idx, end_idx, pearson_mat_bt)
                                st.session_state.bt_results = results if results else None
                                st.session_state.bt_train_results = None
                                st.session_state.bt_valid_results = None

    # ---- 回测结果展示 (从缓存读取, 参数变动不清空) ----
    if "tune_df" in st.session_state and st.session_state.tune_df is not None:
        df_t = st.session_state.tune_df
        tune_cols = [c for c in df_t.columns if not c.startswith("_")]
        with st.expander("📊 三段切分最优参数 (训练→验证→测试)", expanded=True):
            col_cfg = {}
            for c in tune_cols:
                if "命中率" in c:
                    col_cfg[c] = st.column_config.NumberColumn(format="%.1f%%")
                elif "Wilson" in c:
                    col_cfg[c] = st.column_config.NumberColumn("验证Wilson下界%", format="%.1f",
                        help="95%置信区间下界, 段数少时自动惩罚")
            st.dataframe(df_t[tune_cols], width='stretch', hide_index=True, column_config=col_cfg)

    if "bt_results" in st.session_state and st.session_state.bt_results is None:
        has_train = ("bt_train_results" in st.session_state and
                     st.session_state.bt_train_results is not None)
        has_valid = ("bt_valid_results" in st.session_state and
                     st.session_state.bt_valid_results is not None)
        if not has_train and not has_valid:
            st.info(f"未找到任何满足阈值 {bt_threshold} 的匹配, 尝试降低阈值")
        elif has_train or has_valid:
            st.info("测试集无有效信号, 训练/验证集有结果但未在测试集复现 — 可能过拟合了")

    if "bt_results" in st.session_state and st.session_state.bt_results is not None:
        df_res = pd.DataFrame(st.session_state.bt_results)
        if "neutral" not in df_res.columns:
            df_res["neutral"] = False
        neutral_count = int(df_res["neutral"].sum())

        df_signal = df_res[~df_res["neutral"]]
        total = len(df_signal)
        hits = int(df_signal["hit"].sum())
        hit_rate = hits / total * 100 if total > 0 else 0

        # Walk-forward 三段切分: 训练/验证/测试对比
        has_train = ("bt_train_results" in st.session_state and
                     st.session_state.bt_train_results is not None)
        has_valid = ("bt_valid_results" in st.session_state and
                     st.session_state.bt_valid_results is not None)
        has_threeway = has_train and has_valid

        train_total, train_hits, train_rate, train_neutral, train_n_total = 0, 0, 0, 0, 0
        valid_total, valid_hits, valid_rate, valid_neutral, valid_n_total = 0, 0, 0, 0, 0

        if has_train:
            df_train = pd.DataFrame(st.session_state.bt_train_results)
            if "neutral" not in df_train.columns:
                df_train["neutral"] = False
            df_train_sig = df_train[~df_train["neutral"]]
            train_total = len(df_train_sig)
            train_hits = int(df_train_sig["hit"].sum()) if train_total > 0 else 0
            train_rate = train_hits / train_total * 100 if train_total > 0 else 0
            train_neutral = int(df_train["neutral"].sum())
            train_n_total = train_total + train_neutral

        if has_valid:
            df_valid = pd.DataFrame(st.session_state.bt_valid_results)
            if "neutral" not in df_valid.columns:
                df_valid["neutral"] = False
            df_valid_sig = df_valid[~df_valid["neutral"]]
            valid_total = len(df_valid_sig)
            valid_hits = int(df_valid_sig["hit"].sum()) if valid_total > 0 else 0
            valid_rate = valid_hits / valid_total * 100 if valid_total > 0 else 0
            valid_neutral = int(df_valid["neutral"].sum())
            valid_n_total = valid_total + valid_neutral

        if has_threeway:
            n_total = total + neutral_count
            # 训练集
            _metric_row([
                ("训练集 有效信号日", train_total, None, None),
                ("训练集 命中次数", train_hits, None, None),
                ("训练集 命中率", f"{train_rate:.1f}%", None, None),
                ("训练集 中性日", train_neutral,
                 f"{(train_neutral / train_n_total * 100):.0f}%" if train_n_total > 0 else None, None),
            ])
            # 验证集
            _metric_row([
                ("验证集 有效信号日", valid_total, None, None),
                ("验证集 命中次数", valid_hits, None, None),
                ("验证集 命中率", f"{valid_rate:.1f}%",
                 f"{valid_rate - train_rate:+.1f}% vs 训练" if train_total > 0 else None, None),
                ("验证集 中性日", valid_neutral,
                 f"{(valid_neutral / valid_n_total * 100):.0f}%" if valid_n_total > 0 else None, None),
            ])
            # 测试集
            _metric_row([
                ("测试集 有效信号日", total, None, None),
                ("测试集 命中次数", hits, None, None),
                ("测试集 命中率", f"{hit_rate:.1f}%", f"{hit_rate - valid_rate:+.1f}% vs 验证", None),
                ("测试集 中性日", neutral_count,
                 f"{(neutral_count / n_total * 100):.0f}%" if n_total > 0 else None,
                 "预测方向中性 (|预测收益| < 0.1%), 不参与命中率计算"),
            ])
        elif has_train:
            n_total = total + neutral_count
            _metric_row([
                ("训练集 有效信号日", train_total, None, None),
                ("训练集 命中次数", train_hits, None, None),
                ("训练集 命中率", f"{train_rate:.1f}%", None, None),
                ("训练集 中性日", train_neutral,
                 f"{(train_neutral / train_n_total * 100):.0f}%" if train_n_total > 0 else None, None),
            ])
            _metric_row([
                ("测试集 有效信号日", total, None, None),
                ("测试集 命中次数", hits, None, None),
                ("测试集 命中率", f"{hit_rate:.1f}%", f"{hit_rate - train_rate:+.1f}% vs 训练", None),
                ("测试集 中性日", neutral_count,
                 f"{(neutral_count / n_total * 100):.0f}%" if n_total > 0 else None,
                 "预测方向中性 (|预测收益| < 0.1%), 不参与命中率计算"),
            ])
        else:
            # 无 walk-forward: 一行
            n_total = total + neutral_count
            _metric_row([
                ("有效信号日", total, None, "排除预测方向不明确的中性日"),
                ("命中次数", hits, None, None),
                ("方向命中率", f"{hit_rate:.1f}%", None, None),
                ("中性日 (已排除)", neutral_count,
                 f"{(neutral_count / n_total * 100):.0f}%" if n_total > 0 else None,
                 "预测方向中性 (|预测收益| < 0.1%), 不参与命中率计算"),
            ])

        # ---- 去重叠统计 ----
        if len(df_signal) > 0:
            df_sig_sorted = df_signal.sort_values("date")  # 下方图表复用
            seg_total, seg_hits, seg_hitrate, test_seg_avg_days = _segment_stats(df_signal)
        else:
            seg_total, seg_hits, seg_hitrate, test_seg_avg_days = 0, 0, 0.0, 0.0
            df_sig_sorted = df_signal

        st.divider()
        st.caption("去重叠统计: 连续同方向预测合并为 1 个信号段 (中性日已排除), 仅段首日命中即算正确 (避免重叠模板重复投票虚高)")
        if has_threeway and len(df_train_sig) > 0 and len(df_valid_sig) > 0:
            train_seg_total, train_seg_hits, train_seg_rate, train_seg_avg_days = _segment_stats(df_train_sig)
            valid_seg_total, valid_seg_hits, valid_seg_rate, valid_seg_avg_days = _segment_stats(df_valid_sig)
            # 训练段
            _metric_row([
                ("训练段命中率", f"{train_seg_rate:.1f}%", None, None),
                ("训练信号段数", train_seg_total, None, None),
                ("训练命中段数", train_seg_hits, None, None),
                ("训练段均天数", f"{train_seg_avg_days:.1f}", None, None),
            ])
            # 验证段
            _metric_row([
                ("验证段命中率", f"{valid_seg_rate:.1f}%", f"{valid_seg_rate - train_seg_rate:+.1f}% vs 训练", None),
                ("验证信号段数", valid_seg_total, None, None),
                ("验证命中段数", valid_seg_hits, None, None),
                ("验证段均天数", f"{valid_seg_avg_days:.1f}", None, None),
            ])
            # 测试段
            _metric_row([
                ("测试段命中率", f"{seg_hitrate:.1f}%", f"{seg_hitrate - valid_seg_rate:+.1f}% vs 验证", None),
                ("测试信号段数", seg_total, None, None),
                ("测试命中段数", seg_hits, None, None),
                ("测试段均天数", f"{test_seg_avg_days:.1f}", None, None),
            ])
        elif has_train and len(df_train_sig) > 0:
            train_seg_total, train_seg_hits, train_seg_rate, train_seg_avg_days = _segment_stats(df_train_sig)
            _metric_row([
                ("训练段命中率", f"{train_seg_rate:.1f}%", None, None),
                ("训练信号段数", train_seg_total, None, None),
                ("训练命中段数", train_seg_hits, None, None),
                ("训练段均天数", f"{train_seg_avg_days:.1f}", None, None),
            ])
            _metric_row([
                ("测试段命中率", f"{seg_hitrate:.1f}%", f"{seg_hitrate - train_seg_rate:+.1f}% vs 训练", None),
                ("测试信号段数", seg_total, None, None),
                ("测试命中段数", seg_hits, None, None),
                ("测试段均天数", f"{test_seg_avg_days:.1f}", None, None),
            ])
        else:
            _metric_row([
                ("信号段数", seg_total, None, None),
                ("命中段数", seg_hits, None, None),
                ("去重叠命中率", f"{seg_hitrate:.1f}%",
                 f"{seg_hitrate - hit_rate:+.1f}% vs 原始" if total > 0 else None, None),
                 ("段均天数", f"{test_seg_avg_days:.1f}" if seg_total > 0 else "-", None, None),
            ])

        # ---- 趋势分层命中率 ----
        if "regime_series" in st.session_state and st.session_state.regime_series is not None and len(df_res) > 0:
            df_res_sorted = df_res.sort_values("date").copy()
            df_res_sorted["regime"] = regime_series.reindex(df_res_sorted["date"]).values
            by_regime = df_res_sorted.groupby("regime").agg(总数=("hit", "count"), 命中=("hit", "sum"))
            by_regime["命中率%"] = (by_regime["命中"] / by_regime["总数"] * 100).round(1)
            st.caption("趋势分层命中率")
            st.dataframe(by_regime[["总数", "命中", "命中率%"]].sort_index(), width='stretch')

        # 预测 vs 实际散点图 (全部日, 3色: 绿=命中 红=未命中 灰=中性)
        fig = go.Figure()
        hover_texts = [
            f"{d.strftime('%Y-%m-%d')}<br>预测: {p*100:+.2f}%<br>实际: {a*100:+.2f}%<br>匹配数: {m}"
            for d, p, a, m in zip(df_res["date"], df_res["pred_return"],
                                  df_res["actual_return"], df_res.get("matches", [0] * len(df_res)))
        ]
        color_map = [_hit_color(h, n) for h, n in zip(df_res["hit"], df_res["neutral"])]
        fig.add_trace(go.Scatter(
            x=df_res["pred_return"] * 100, y=df_res["actual_return"] * 100,
            mode="markers",
            marker=dict(color=color_map, size=7, opacity=0.6),
            customdata=hover_texts,
            hovertemplate="%{customdata}<extra></extra>",
            name="绿=命中 红=未命中 灰=中性",
        ))
        fig.add_hline(y=0, line_dash="dot", line_color="gray")
        fig.add_vline(x=0, line_dash="dot", line_color="gray")
        fig.update_layout(
            title=f"预测 vs 实际 (命中率 {hit_rate:.1f}%, 排除 {neutral_count} 个中性日)",
            xaxis_title="预测收益率 (%)", yaxis_title="实际收益率 (%)",
            height=400,
        )
        _plotly_chart(fig, height=450)

        # 按预测方向分组的统计 (仅有效信号)
        if len(df_signal) > 0:
            st.subheader("按预测方向分组 (仅有效信号)")
            df_signal["pred_dir"] = df_signal["pred_return"].apply(
                lambda x: "看涨" if x > 0.001 else "看跌"
            )
            dir_stats = df_signal.groupby("pred_dir").agg(
                次数=("hit", "count"),
                命中率=("hit", lambda x: x.sum() / len(x) * 100),
                平均实际收益=("actual_return", lambda x: np.mean(x) * 100),
            ).round(1)
            st.dataframe(dir_stats, width='stretch')

        # ---- 时间分布 ----
        st.subheader("命中/未命中 时间分布")

        # 命中/未命中时间线
        fig_tl = go.Figure()
        timeline_colors = [_hit_color(h, n) for h, n in zip(df_res["hit"], df_res["neutral"])]
        fig_tl.add_trace(go.Scatter(
            x=df_res["date"], y=[1] * len(df_res),
            mode="markers",
            marker=dict(
                color=timeline_colors, size=6, symbol="square",
            ),
            name="绿=命中, 红=未命中, 灰=中性",
            customdata=[
                f"{d.strftime('%Y-%m-%d')}<br>{'中性' if n else ('✓ 命中' if h else '✗ 未命中')}<br>预测: {p*100:+.2f}% 实际: {a*100:+.2f}%"
                for d, h, n, p, a in zip(df_res["date"], df_res["hit"], df_res["neutral"],
                                          df_res["pred_return"], df_res["actual_return"])
            ],
            hovertemplate="%{customdata}<extra></extra>",
        ))
        fig_tl.update_layout(
            title="命中/未命中时间线 (每个方块 = 一次预测, 灰=中性已排除)",
            height=120, yaxis=dict(showticklabels=False, range=[0.5, 1.5]),
            margin=dict(l=20, r=20, t=30, b=20),
        )
        _plotly_chart(fig_tl, height=160)

        # 月度命中率 (仅有效信号)
        if len(df_signal) > 0:
            df_sig_sorted["month"] = df_sig_sorted["date"].dt.to_period("M")
            monthly = df_sig_sorted.groupby("month").agg(
                信号数=("hit", "count"),
                命中=("hit", "sum"),
            )
            monthly["命中率"] = (monthly["命中"] / monthly["信号数"] * 100).round(1)
            monthly.index = monthly.index.astype(str)

            fig_monthly = go.Figure()
            fig_monthly.add_trace(go.Bar(
                x=monthly.index, y=monthly["信号数"],
                name="信号数", marker_color="rgba(128,128,128,0.3)", yaxis="y",
            ))
            fig_monthly.add_trace(go.Scatter(
                x=monthly.index, y=monthly["命中率"],
                name="命中率%", mode="lines+markers",
                line=dict(color="#1f77b4", width=2), yaxis="y2",
            ))
            min_x = monthly.index[0] if len(monthly) > 0 else ""
            max_x = monthly.index[-1] if len(monthly) > 0 else ""
            fig_monthly.add_shape(type="line", x0=min_x, x1=max_x, y0=50, y1=50,
                                  line=dict(dash="dot", color="gray", width=1), yref="y2")
            fig_monthly.update_layout(
                title="逐月命中率 (排除中性日)",
                yaxis=dict(title="信号数", side="left"),
                yaxis2=dict(title="命中率%", overlaying="y", side="right", range=[0, 100]),
                height=300,
                legend=dict(x=0.01, y=0.99),
            )
            _plotly_chart(fig_monthly, height=350)

            # 如果数据足够, 加滚动命中率
            if len(df_sig_sorted) >= 30:
                df_sig_sorted["rolling_hit"] = df_sig_sorted["hit"].rolling(30, min_periods=10).mean() * 100
                fig_roll = go.Figure()
                fig_roll.add_trace(go.Scatter(
                    x=df_sig_sorted["date"], y=df_sig_sorted["rolling_hit"],
                    mode="lines", name="30日滚动命中率%",
                    line=dict(color="#1f77b4", width=2),
                    fill="tozeroy", fillcolor="rgba(31,119,180,0.1)",
                ))
                fig_roll.add_hline(y=50, line_dash="dot", line_color="gray")
                fig_roll.update_layout(title="30 日滚动命中率 (排除中性日)", height=250)
                _plotly_chart(fig_roll, height=300)

        # 详细结果表格
        st.subheader("最近 30 次预测")
        recent = df_res.tail(30).sort_values("date", ascending=False)
        display = recent[["date", "top_r", "pred_return", "actual_return", "hit", "neutral"]].copy()
        display["date"] = display["date"].apply(lambda x: x.strftime("%Y-%m-%d"))
        display["pred_return"] = (display["pred_return"] * 100).round(2)
        display["actual_return"] = (display["actual_return"] * 100).round(2)
        display["top_r"] = display["top_r"].round(4)
        display.columns = ["日期", "最高r", "预测收益%", "实际收益%", "命中", "中性"]
        st.dataframe(display, width='stretch', hide_index=True)


        # ===========================================================================
        # 自动调参 (独立于单次回测)
        # ===========================================================================
        if run_tune:
            if not bt_factors:
                st.warning("请选择匹配因子")
            else:
                valid_tune = df_factors[bt_factors].dropna()
                n_tune = len(valid_tune)
                tune_start, tune_end = _resolve_date_range(valid_tune.index, bt_start, bt_end, bt_window * 2)
                tune_end = min(tune_end, n_tune - (10 if ensemble_mode else bt_lookahead))

                if tune_end - tune_start < 60:
                    st.warning("数据不足 (walk-forward 需要至少 60 个有效回测日)")
                else:
                    windows = [5, 10, 20, 30]
                    lookaheads = [3, 5, 10, 15]
                    thresholds = [0.7, 0.8, 0.85, 0.9, 0.95]
                    topks = [1, 3, 5]

                    # Walk-forward 三段切分: 训练50% → 验证20% → 测试30%
                    total_range = tune_end - tune_start
                    train_end = tune_start + int(total_range * 0.5)
                    valid_start = train_end
                    valid_end = tune_start + int(total_range * 0.7)
                    test_start = valid_end
                    train_days = train_end - tune_start
                    valid_days = valid_end - valid_start
                    test_days = tune_end - test_start

                    total_trials = len(windows) * len(lookaheads) * len(thresholds) * len(topks)
                    algo_label = {"pearson": "Pearson", "dtw": "DTW", "pearson_dtw": "Pearson+DTW"}.get(bt_algo, bt_algo)
                    st.caption(f"算法: {algo_label} | 三段切分: 训练 {train_days}天 → 验证 {valid_days}天 → 测试 {test_days}天 | 搜索 {total_trials} 种参数组合...")

                    price_vals_t = df_factors.loc[valid_tune.index, "close"].values

                    def _eval_trial(win, la, th, tk, bt_algo, bt_factors, vals_dict_t,
                                    combined_corr, price_vals_t, n_tune, eval_start, eval_end):
                        results_t = []
                        lheads_t = _bt_lookaheads(la, ensemble_mode)
                        la_eff = max(lheads_t)
                        la_eval = lheads_t[len(lheads_t) // 2]
                        s_start = max(eval_start, win * 2)
                        s_end = min(eval_end, n_tune - la_eff)
                        # 择时过滤阈值
                        vol_thresh_t = None
                        if timing_filter:
                            vt_data = df_factors["vol20d"].reindex(valid_tune.index).fillna(0)
                            vol_thresh_t = np.percentile(vt_data[vt_data > 0], 80)
                        for t in range(s_start, s_end):
                            # 择时过滤
                            if timing_filter and vol_thresh_t is not None:
                                if vt_data.iloc[t] > vol_thresh_t:
                                    continue
                            tpl_idx = t - win
                            hist_end = tpl_idx - win
                            if hist_end >= 0:
                                row = combined_corr[tpl_idx, :hist_end + 1]
                                if bt_algo == "dtw":
                                    loose_mask = np.ones(len(row), dtype=bool)
                                else:
                                    loose_mask = (row + 1) / 2 >= 0.65
                                if loose_mask.any():
                                    if bt_algo in ("dtw", "pearson_dtw"):
                                        dtw_scores = []
                                        for mi in np.where(loose_mask)[0]:
                                            dtw_sim = 0.0
                                            for f in bt_factors:
                                                tpl_v = vals_dict_t[f][t - win:t]
                                                win_v = vals_dict_t[f][mi:mi + win]
                                                s = _dtw_similarity(tpl_v, win_v, min_similarity=th)
                                                if not np.isnan(s):
                                                    dtw_sim += s
                                            dtw_sim /= len(bt_factors)
                                            if dtw_sim >= th:
                                                dtw_scores.append((mi, dtw_sim))
                                        if dtw_scores:
                                            dtw_scores.sort(key=lambda x: -x[1])
                                            top_k_idx = [x[0] for x in dtw_scores[:tk]]
                                        else:
                                            continue
                                    else:
                                        row_sim = (row + 1) / 2
                                        match_idx = np.where(row_sim >= th)[0]
                                        top_k_idx = match_idx[np.argsort(-row_sim[match_idx])[:tk]]

                                    pred_by_la = [[] for _ in lheads_t]
                                    for s_idx in top_k_idx:
                                        s_end_pos = s_idx + win - 1
                                        for li, lh in enumerate(lheads_t):
                                            if s_end_pos + 1 + lh <= n_tune:
                                                pred_by_la[li].append(
                                                    (price_vals_t[s_end_pos + lh] - price_vals_t[s_end_pos + 1])
                                                    / price_vals_t[s_end_pos + 1]
                                                )
                                    pred_by_la = [pr for pr in pred_by_la if pr]
                                    if pred_by_la:
                                        direction, avg_pred = _predict_direction(pred_by_la, ensemble_mode)
                                        act_ret = (price_vals_t[t + la_eval - 1] - price_vals_t[t]) / price_vals_t[t]
                                        hit, neutral = _classify_hit(direction, avg_pred, act_ret, ensemble_mode)
                                        results_t.append({
                                            "pred_return": avg_pred,
                                            "actual_return": act_ret,
                                            "hit": hit,
                                            "neutral": neutral,
                                        })
                        return results_t

                    def _compute_metrics(results):
                        if not results:
                            return None
                        df = pd.DataFrame(results)
                        sig = df[~df["neutral"]]
                        if len(sig) == 0:
                            return None
                        seg_total, seg_hit, seg_rate, _ = _segment_stats(sig)
                        return {
                            "信号段数": seg_total,
                            "命中段数": seg_hit,
                            "段命中率%": round(seg_rate, 1),
                            "原始命中率%": round(sig["hit"].sum() / len(sig) * 100, 1),
                            "有效信号日": len(sig),
                            "中性日": int(df["neutral"].sum()),
                        }

                    train_results = []
                    tune_progress = st.progress(0)
                    trial_idx = 0

                    for win in windows:
                        vals_dict_t = {f: valid_tune[f].values for f in bt_factors}
                        combined_corr = _pearson_corr_matrix([vals_dict_t[f] for f in bt_factors], win, bt_weight_list)

                        for la in lookaheads:
                            for th in thresholds:
                                for tk in topks:
                                    results_t = _eval_trial(
                                        win, la, th, tk, bt_algo, bt_factors, vals_dict_t,
                                        combined_corr, price_vals_t, n_tune,
                                        tune_start, train_end,
                                    )
                                    metrics = _compute_metrics(results_t)
                                    if metrics:
                                        train_results.append({
                                            "窗口": win, "预测天": la, "阈值": th, "TopK": tk,
                                            "训练段命中率%": metrics["段命中率%"],
                                            "训练原始命中率%": metrics["原始命中率%"],
                                            "训练信号段数": metrics["信号段数"],
                                            "训练有效日": metrics["有效信号日"],
                                            "训练中性日": metrics["中性日"],
                                            "_win": win, "_la": la, "_th": th, "_tk": tk,
                                        })
                                    trial_idx += 1
                                    tune_progress.progress(trial_idx / total_trials)

                    if not train_results:
                        st.warning("训练集未找到任何有效参数组合")
                    else:
                        df_train = pd.DataFrame(train_results).sort_values("训练段命中率%", ascending=False)
                        top_n_valid = min(15, len(df_train))

                        # 阶段2: 验证集从 Top 15 中选出最优
                        st.caption(f"验证集 ({valid_days} 天) 评估训练 Top {top_n_valid} 参数...")
                        valid_progress = st.progress(0)
                        valid_rows = []
                        for ti in range(top_n_valid):
                            row = df_train.iloc[ti]
                            win, la, th, tk = int(row["_win"]), int(row["_la"]), row["_th"], int(row["_tk"])
                            vals_dict_t = {f: valid_tune[f].values for f in bt_factors}
                            combined_corr = _pearson_corr_matrix([vals_dict_t[f] for f in bt_factors], win, bt_weight_list)
                            results_t = _eval_trial(
                                win, la, th, tk, bt_algo, bt_factors, vals_dict_t,
                                combined_corr, price_vals_t, n_tune,
                                valid_start, valid_end,
                            )
                            metrics = _compute_metrics(results_t)
                            if metrics:
                                valid_rows.append({
                                    "窗口": win, "预测天": la, "阈值": th, "TopK": tk,
                                    "训练段命中率%": row["训练段命中率%"],
                                    "验证段命中率%": metrics["段命中率%"],
                                    "验证段数": metrics["信号段数"],
                                    "验证命中段数": metrics["命中段数"],
                                    "训练原始命中率%": row["训练原始命中率%"],
                                    "验证原始命中率%": metrics["原始命中率%"],
                                    "训练信号段数": row["训练信号段数"],
                                    "验证有效日": metrics["有效信号日"],
                                    "验证中性日": metrics["中性日"],
                                    "_win": win, "_la": la, "_th": th, "_tk": tk,
                                })
                            valid_progress.progress((ti + 1) / top_n_valid)

                        if not valid_rows:
                            st.warning("验证集未找到任何有效参数组合")
                        else:
                            df_valid = pd.DataFrame(valid_rows)
                            df_valid["_wilson"] = df_valid.apply(
                                lambda r: _wilson_lower(int(r["验证命中段数"]), int(r["验证段数"])), axis=1
                            )
                            df_valid = df_valid.sort_values("_wilson", ascending=False)

                            # 阶段3: 测试集对 Top 5 参数评估
                            top_n_test = min(5, len(df_valid))
                            st.caption(f"测试集 ({test_days} 天) 对验证 Top {top_n_test} 参数做无偏评估...")
                            test_progress = st.progress(0)
                            test_rows = []
                            for ti in range(top_n_test):
                                vrow = df_valid.iloc[ti]
                                win, la, th, tk = int(vrow["_win"]), int(vrow["_la"]), vrow["_th"], int(vrow["_tk"])
                                vals_dict_t = {f: valid_tune[f].values for f in bt_factors}
                                combined_corr = _pearson_corr_matrix([vals_dict_t[f] for f in bt_factors], win, bt_weight_list)
                                results_t = _eval_trial(
                                    win, la, th, tk, bt_algo, bt_factors,
                                    vals_dict_t, combined_corr, price_vals_t, n_tune,
                                    test_start, tune_end,
                                )
                                test_metrics = _compute_metrics(results_t)
                                if test_metrics:
                                    test_rows.append({
                                        "窗口": win, "预测天": la, "阈值": th, "TopK": tk,
                                        "训练段命中率%": vrow["训练段命中率%"],
                                        "验证段命中率%": vrow["验证段命中率%"],
                                        "测试段命中率%": test_metrics["段命中率%"],
                                        "训练原始%": vrow["训练原始命中率%"],
                                        "验证原始%": vrow["验证原始命中率%"],
                                        "测试原始%": test_metrics["原始命中率%"],
                                        "训练信号段": vrow["训练信号段数"],
                                        "验证信号段": vrow["验证段数"],
                                        "测试信号段": test_metrics["信号段数"],
                                        "验证Wilson": round(vrow["_wilson"] * 100, 1),
                                        "_win": win, "_la": la, "_th": th, "_tk": tk,
                                    })
                                test_progress.progress((ti + 1) / top_n_test)

                            if not test_rows:
                                st.warning("测试集未找到有效信号")
                            else:
                                st.session_state.tune_df = pd.DataFrame(test_rows)
                                st.session_state.tune_valid_df = df_valid  # 缓存验证集详情

                                st.subheader(f"三段切分 Top {len(test_rows)} 参数 (训练 → 验证 → 测试)")
                                st.caption("验证集按 Wilson 下界排序选 Top 5, 测试集全程未参与选参, 为无偏 out-of-sample 估计")
                                show_cols = [c for c in st.session_state.tune_df.columns if not c.startswith("_")]
                                st.dataframe(
                                    st.session_state.tune_df[show_cols],
                                    width='stretch',
                                    hide_index=True,
                                    column_config={
                                        "训练段命中率%": st.column_config.NumberColumn(format="%.1f%%"),
                                        "验证段命中率%": st.column_config.NumberColumn(format="%.1f%%"),
                                        "测试段命中率%": st.column_config.NumberColumn(format="%.1f%%"),
                                        "训练原始%": st.column_config.NumberColumn(format="%.1f%%"),
                                        "验证原始%": st.column_config.NumberColumn(format="%.1f%%"),
                                        "测试原始%": st.column_config.NumberColumn(format="%.1f%%"),
                                        "验证Wilson": st.column_config.NumberColumn("验证Wilson下界%", format="%.1f",
                                            help="95%置信区间下界, 段数少时自动惩罚"),
                                    }
                                )

                                with st.expander("验证集 Top 5 参数 (按 Wilson 下界排序)"):
                                    vshow = [c for c in df_valid.columns if not c.startswith("_") or c == "_wilson"]
                                    st.dataframe(
                                        df_valid[vshow].head(5),
                                        width='stretch',
                                        hide_index=True,
                                        column_config={
                                            "训练段命中率%": st.column_config.NumberColumn(format="%.1f%%"),
                                            "验证段命中率%": st.column_config.NumberColumn(format="%.1f%%"),
                                            "训练原始命中率%": st.column_config.NumberColumn(format="%.1f%%"),
                                            "验证原始命中率%": st.column_config.NumberColumn(format="%.1f%%"),
                                            "_wilson": st.column_config.NumberColumn("验证Wilson下界", format="%.3f"),
                                        }
                                    )
# Tab 8: 数据表格
# ===========================================================================
if tab_idx == 8:
    st.caption("完整因子数据 | 可按列搜索/排序/下载")

    # 列选择器
    all_cols = [c for c in df_factors.columns if not c.startswith("bb_") or c in ["bb_pct_b", "bb_width"]]
    default_cols = ["open", "high", "low", "close", "pe_ttm", "pb", "roe", "gross_margin", "net_margin",
                    "revenue_yoy", "net_profit_yoy", "debt_ratio", "current_ratio",
                    "rsi14", "mom60d", "vol60d", "beta", "turnover"]
    default_cols = [c for c in default_cols if c in df_factors.columns]

    selected_cols = st.multiselect(
        "选择要显示的因子", all_cols, default=default_cols[:12],
        help="可多选, 支持搜索"
    )

    if selected_cols:
        display_df = df_factors[selected_cols].sort_index(ascending=False)

        # 下载按钮
        csv = display_df.to_csv().encode("utf-8")
        st.download_button(
            label="📥 下载 CSV",
            data=csv,
            file_name=f"{symbol}_factors.csv",
            mime="text/csv",
        )

        st.dataframe(
            display_df,
            width='stretch',
            height=600,
            column_config={c: st.column_config.NumberColumn(format="%.2f") for c in selected_cols},
        )
        st.caption(f"共 {len(df_factors)} 个交易日, {len(selected_cols)} 个因子")
    else:
        st.info("请选择至少一个因子列")

# ===========================================================================
# 页脚
# ===========================================================================
st.divider()
st.caption(
    f"数据范围: {df_factors.index[0].strftime('%Y-%m-%d')} ~ {df_factors.index[-1].strftime('%Y-%m-%d')} "
    f"| {len(df_factors)} 个交易日 | {sum(1 for c in df_factors.columns if df_factors[c].notna().sum() > 0)} 个有效因子 "
    f"| 股票: {symbol}"
)
