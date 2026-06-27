"""
因子计算引擎
- 基于日线数据计算技术指标
- 基于财报数据计算基本面因子
- 合并为统一日频 DataFrame
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


# ===========================================================================
# 技术指标计算
# ===========================================================================

def calc_ma(df: pd.DataFrame, windows=(5, 10, 20, 60, 120, 250)) -> pd.DataFrame:
    """计算移动均线"""
    result = pd.DataFrame(index=df.index)
    for w in windows:
        result[f"ma{w}"] = df["close"].rolling(w).mean()
    return result


def calc_ma_deviation(df_close: pd.DataFrame, windows=(20, 60, 120, 250)) -> pd.DataFrame:
    """均线偏离度 (%)"""
    result = pd.DataFrame(index=df_close.index)
    for w in windows:
        ma = df_close.rolling(w).mean()
        result[f"ma{w}_dev"] = (df_close - ma) / ma * 100
    return result


def calc_rsi(df_close: pd.Series, windows=(6, 14, 24)) -> pd.DataFrame:
    """RSI"""
    result = pd.DataFrame(index=df_close.index)
    delta = df_close.diff()
    for w in windows:
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(alpha=1 / w, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / w, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        result[f"rsi{w}"] = 100 - (100 / (1 + rs))
    return result


def calc_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """
    KDJ 随机指标
    RSV = (close - low_n) / (high_n - low_n) * 100
    K = SMA(RSV, m1)
    D = SMA(K, m2)
    J = 3*K - 2*D
    """
    result = pd.DataFrame(index=df.index)
    low_n = df["low"].rolling(n).min()
    high_n = df["high"].rolling(n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    k = rsv.ewm(alpha=1 / m1, adjust=False).mean()
    d = k.ewm(alpha=1 / m2, adjust=False).mean()
    j = 3 * k - 2 * d
    result["k"] = k
    result["d"] = d
    result["j"] = j
    result["kdj_rsv"] = rsv
    return result


def calc_macd(df_close: pd.Series, fast=12, slow=26, signal=9) -> pd.DataFrame:
    """MACD"""
    result = pd.DataFrame(index=df_close.index)
    ema_fast = df_close.ewm(span=fast, adjust=False).mean()
    ema_slow = df_close.ewm(span=slow, adjust=False).mean()
    result["dif"] = ema_fast - ema_slow
    result["dea"] = result["dif"].ewm(span=signal, adjust=False).mean()
    result["macd"] = 2 * (result["dif"] - result["dea"])
    return result


def calc_bollinger(df_close: pd.Series, window=20, num_std=2) -> pd.DataFrame:
    """布林带"""
    result = pd.DataFrame(index=df_close.index)
    ma = df_close.rolling(window).mean()
    std = df_close.rolling(window).std()
    result["bb_upper"] = ma + num_std * std
    result["bb_middle"] = ma
    result["bb_lower"] = ma - num_std * std
    result["bb_pct_b"] = (df_close - result["bb_lower"]) / (
        result["bb_upper"] - result["bb_lower"]
    )
    result["bb_width"] = (result["bb_upper"] - result["bb_lower"]) / ma
    return result


def calc_volume_ratio(df_volume: pd.Series, window=20) -> pd.Series:
    """量比"""
    ma_vol = df_volume.rolling(window).mean()
    return (df_volume / ma_vol).rename("vol_ratio")


def calc_historical_volatility(
    df_close: pd.Series, windows=(20, 60, 120), annualize=252
) -> pd.DataFrame:
    """历史波动率 (年化)"""
    result = pd.DataFrame(index=df_close.index)
    log_ret = np.log(df_close / df_close.shift(1))
    for w in windows:
        result[f"vol{w}d"] = log_ret.rolling(w).std() * np.sqrt(annualize) * 100
    return result


def calc_momentum(df_close: pd.Series, windows=(5, 10, 20, 60, 120, 250)) -> pd.DataFrame:
    """价格动量 (%)"""
    result = pd.DataFrame(index=df_close.index)
    for w in windows:
        result[f"mom{w}d"] = df_close.pct_change(w) * 100
    return result


def calc_max_drawdown(df_close: pd.Series, windows=(60, 120, 250)) -> pd.DataFrame:
    """滚动最大回撤 (%)"""
    result = pd.DataFrame(index=df_close.index)
    for w in windows:
        rolling_max = df_close.rolling(w).max()
        drawdown = (df_close - rolling_max) / rolling_max * 100
        result[f"mdd{w}d"] = drawdown
    return result


def calc_beta(
    df_close: pd.Series, index_close: pd.Series, window=60
) -> pd.Series:
    """滚动 Beta"""
    common_idx = df_close.index.intersection(index_close.index)
    if len(common_idx) < window:
        return pd.Series(index=df_close.index, dtype=float, name="beta")

    stock_ret = df_close.reindex(common_idx).pct_change().dropna()
    index_ret = index_close.reindex(common_idx).pct_change().dropna()

    beta_series = pd.Series(index=df_close.index, dtype=float, name="beta")
    for i in range(window, len(common_idx)):
        end = common_idx[i]
        start_loc = i - window
        start = common_idx[start_loc]
        try:
            y = stock_ret.loc[start:end].values
            x = index_ret.loc[start:end].values
            mask = ~(np.isnan(y) | np.isnan(x))
            if mask.sum() > 10:
                slope, _, _, _, _ = stats.linregress(x[mask], y[mask])
                beta_series.loc[end] = slope
        except Exception:
            pass
    return beta_series


def calc_avg_turnover(df_turnover: pd.Series, window=20) -> pd.Series:
    """平均换手率"""
    return df_turnover.rolling(window).mean().rename("avg_turnover")


def calc_turnover_ma_volume(df: pd.DataFrame, windows=(5, 20)) -> pd.DataFrame:
    """成交额均线 (亿)"""
    result = pd.DataFrame(index=df.index)
    for w in windows:
        result[f"amount_ma{w}"] = df["amount"].rolling(w).mean() / 1e8
    return result


# ===========================================================================
# 主计算函数
# ===========================================================================

def compute_all_factors(
    df_daily: pd.DataFrame,
    df_valuation: pd.DataFrame,
    df_financials: pd.DataFrame,
    df_index: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    计算所有因子并合并为日频 DataFrame

    参数
    ----
    df_daily : 日线 OHLCV
    df_valuation : 日频估值数据 (PE, PB, 总市值等)
    df_financials : 季度财务数据
    df_index : 指数日线 (用于计算 Beta)

    返回
    ----
    pd.DataFrame, 每列为一种因子, 每日一行
    """
    result = pd.DataFrame(index=df_daily.index)

    # ---- 基础价格数据 ----
    for col in ["open", "high", "low", "close"]:
        if col in df_daily.columns:
            result[col] = df_daily[col]
    result["volume"] = df_daily["volume"]
    result["amount"] = df_daily["amount"]
    result["turnover"] = df_daily["turnover"]
    result["pct_change"] = df_daily["pct_change"]

    # ---- 均线 ----
    ma_df = calc_ma(df_daily)
    for c in ma_df.columns:
        result[c] = ma_df[c]

    # ---- 均线偏离 ----
    dev_df = calc_ma_deviation(df_daily["close"])
    for c in dev_df.columns:
        result[c] = dev_df[c]

    # ---- RSI ----
    rsi_df = calc_rsi(df_daily["close"])
    for c in rsi_df.columns:
        result[c] = rsi_df[c]

    # ---- KDJ (随机指标) ----
    kdj_df = calc_kdj(df_daily)
    for c in kdj_df.columns:
        result[c] = kdj_df[c]

    # ---- MACD ----
    macd_df = calc_macd(df_daily["close"])
    for c in macd_df.columns:
        result[c] = macd_df[c]

    # ---- 布林带 ----
    bb_df = calc_bollinger(df_daily["close"])
    for c in bb_df.columns:
        result[c] = bb_df[c]

    # ---- 量比 ----
    result["vol_ratio"] = calc_volume_ratio(df_daily["volume"])

    # ---- 波动率 ----
    vol_df = calc_historical_volatility(df_daily["close"])
    for c in vol_df.columns:
        result[c] = vol_df[c]

    # ---- 动量 ----
    mom_df = calc_momentum(df_daily["close"])
    for c in mom_df.columns:
        result[c] = mom_df[c]

    # ---- 最大回撤 ----
    mdd_df = calc_max_drawdown(df_daily["close"])
    for c in mdd_df.columns:
        result[c] = mdd_df[c]

    # ---- Beta ----
    if df_index is not None and "close" in df_index.columns:
        result["beta"] = calc_beta(df_daily["close"], df_index["close"])

    # ---- 成交额均线 ----
    amt_df = calc_turnover_ma_volume(df_daily)
    for c in amt_df.columns:
        result[c] = amt_df[c]

    # ---- 平均换手率 ----
    result["avg_turnover20"] = calc_avg_turnover(df_daily["turnover"])

    # ---- 估值因子 (日频, 百度双周数据需前向填充) ----
    for col in ["pe_ttm", "pe_static", "pb", "pcf", "total_mv"]:
        if col in df_valuation.columns:
            # 前向填充使双周频 PE/PB 变为日频, 避免形态匹配时大量 NaN
            result[col] = df_valuation[col].reindex(result.index, method="ffill")

    # ---- 基本面因子 (季度 -> 日频 forward fill) ----
    fin_cols = [
        "roe", "roe_diluted", "gross_margin", "net_margin",
        "revenue_yoy", "net_profit_yoy", "recurring_np_yoy",
        "eps", "bps", "cfps", "debt_ratio", "current_ratio",
        "quick_ratio", "inventory_turnover",
    ]
    for col in fin_cols:
        if col in df_financials.columns:
            s = df_financials[col].sort_index()
            # 向前填充到日频
            daily_s = s.reindex(result.index, method="ffill")
            result[col] = daily_s

    # ---- 衍生指标 ----
    # PEG = PE_TTM / (净利润同比增长率), 增长率需转为数值 (非百分比)
    if "pe_ttm" in result.columns and "net_profit_yoy" in result.columns:
        growth = result["net_profit_yoy"].clip(lower=0.1)  # 避免负增长导致 PEG 异常
        result["peg"] = result["pe_ttm"] / growth

    # 市值因子 (对数市值, 避免极端值)
    if "total_mv" in result.columns:
        result["ln_mv"] = np.log(result["total_mv"].clip(lower=1))

    return result
