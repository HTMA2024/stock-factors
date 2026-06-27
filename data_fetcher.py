"""
数据获取模块
- 日线行情 (OHLCV + 换手率) - 新浪源
- 估值数据 (PE/PB/总市值) - 百度源, 日频
- 财务报表 (ROE/ROA/毛利率/增长率等) - 同花顺源, 季度频率
- 指数行情 (用于计算 Beta) - 新浪源
"""

import os
import time
import pandas as pd
import akshare as ak

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def _cache_path(prefix: str, symbol: str) -> str:
    return os.path.join(DATA_DIR, f"{prefix}_{symbol}.csv")


def _with_exchange_prefix(symbol: str) -> str:
    """自动补全交易所前缀: 6xxxx -> sh, 0xxxx/3xxxx -> sz"""
    if symbol.startswith("sh") or symbol.startswith("sz"):
        return symbol
    if symbol.startswith(("6", "9")):
        return f"sh{symbol}"
    return f"sz{symbol}"


# ===========================================================================
# 1. 日线行情 (新浪)
# ===========================================================================
def fetch_daily_ohlcv(
    symbol: str,
    start_date: str = "20150101",
    end_date: str = "20251231",
    use_cache: bool = True,
    retries: int = 3,
) -> pd.DataFrame:
    """
    获取日线行情：开高低收 + 成交量/额 + 换手率 + 流通股本
    数据源: 新浪财经
    """
    path = _cache_path("daily_sina", symbol)
    if use_cache and os.path.exists(path):
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.sort_index(inplace=True)
        # 检查缓存是否覆盖请求的日期范围
        if df.index.min().strftime("%Y%m%d") <= start_date and df.index.max().strftime("%Y%m%d") >= end_date:
            return df
        # 缓存不完整, 继续拉取并合并

    full_symbol = _with_exchange_prefix(symbol)

    for attempt in range(retries):
        try:
            df = ak.stock_zh_a_daily(
                symbol=full_symbol,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            )
            break
        except Exception as e:
            if attempt < retries - 1:
                wait = (attempt + 1) * 3
                print(f"     [重试 {attempt + 1}/{retries}] 等待 {wait}s...")
                time.sleep(wait)
            else:
                raise e

    col_map = {
        "date": "date",
        "open": "open",
        "close": "close",
        "high": "high",
        "low": "low",
        "volume": "volume",
        "amount": "amount",
        "turnover": "turnover",
        "outstanding_share": "outstanding_share",
    }
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df.sort_index(inplace=True)

    # 数值列转换
    for c in ["open", "close", "high", "low", "volume", "amount", "turnover", "outstanding_share"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # 添加涨跌幅
    if "close" in df.columns:
        df["pct_change"] = df["close"].pct_change() * 100

    df.to_csv(path)
    return df


# ===========================================================================
# 2. 估值数据 (百度, 日频)
# ===========================================================================
def _fetch_valuation_single(symbol: str, indicator: str, period: str = "全部") -> pd.Series:
    """获取单个估值指标的完整日频序列"""
    clean_name = indicator.replace("/", "_").replace("(", "").replace(")", "")
    path = _cache_path(f"val_{clean_name}", symbol)
    if os.path.exists(path):
        s = pd.read_csv(path, index_col=0, parse_dates=True).squeeze()
        return s

    try:
        df = ak.stock_zh_valuation_baidu(symbol=symbol, indicator=indicator, period=period)
        df["date"] = pd.to_datetime(df["date"])
        s = df.set_index("date")["value"]
        s = pd.to_numeric(s, errors="coerce")
        s.name = indicator
        s.to_csv(path)
        return s
    except Exception:
        return pd.Series(dtype=float, name=indicator)


def fetch_valuation(symbol: str, use_cache: bool = True) -> pd.DataFrame:
    """获取日频估值数据：总市值、PE(TTM)、PE(静)、PB、市现率"""
    path = _cache_path("valuation", symbol)
    if use_cache and os.path.exists(path):
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        return df

    indicators = {
        "总市值": "total_mv",
        "市盈率(TTM)": "pe_ttm",
        "市盈率(静)": "pe_static",
        "市净率": "pb",
        "市现率": "pcf",
    }

    series_list = []
    for cn_name, en_name in indicators.items():
        s = _fetch_valuation_single(symbol, cn_name)
        if not s.empty:
            s.name = en_name
            series_list.append(s)

    if not series_list:
        return pd.DataFrame()

    df = pd.concat(series_list, axis=1)
    df.sort_index(inplace=True)
    if "total_mv" in df.columns:
        df["total_mv"] = df["total_mv"] * 1e8

    df.to_csv(path)
    return df


# ===========================================================================
# 3. 财务报表 (同花顺, 季度)
# ===========================================================================
def fetch_financials(symbol: str, use_cache: bool = True) -> pd.DataFrame:
    """获取季度财务指标"""
    path = _cache_path("financials", symbol)
    if use_cache and os.path.exists(path):
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        return df

    raw = ak.stock_financial_abstract_ths(symbol=symbol, indicator="按报告期")

    col_map = {
        "报告期": "date",
        "营业总收入": "revenue",
        "营业总收入同比增长率": "revenue_yoy",
        "净利润": "net_profit",
        "净利润同比增长率": "net_profit_yoy",
        "基本每股收益": "eps",
        "每股净资产": "bps",
        "每股经营现金流": "cfps",
        "销售毛利率": "gross_margin",
        "销售净利率": "net_margin",
        "净资产收益率": "roe",
        "净资产收益率-摊薄": "roe_diluted",
        "资产负债率": "debt_ratio",
        "流动比率": "current_ratio",
        "速动比率": "quick_ratio",
        "产权比率": "equity_ratio",
        "存货周转率": "inventory_turnover",
        "存货周转天数": "inventory_days",
        "应收账款周转天数": "receivable_days",
        "营业周期": "operating_cycle",
        "扣非净利润": "recurring_np",
        "扣非净利润同比增长率": "recurring_np_yoy",
    }
    df = raw.rename(columns={k: v for k, v in col_map.items() if k in raw.columns})
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df.sort_index(inplace=True)

    # 清洗百分比列
    pct_cols = [
        "gross_margin", "net_margin", "roe", "roe_diluted", "debt_ratio",
        "revenue_yoy", "net_profit_yoy", "recurring_np_yoy",
    ]
    for c in pct_cols:
        if c in df.columns:
            df[c] = df[c].astype(str).str.replace("%", "", regex=False)
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # 清洗数值列
    num_cols = ["revenue", "net_profit", "recurring_np", "bps", "cfps"]
    for c in num_cols:
        if c in df.columns:
            df[c] = df[c].astype(str).str.replace("亿", "e8", regex=False)
            df[c] = df[c].astype(str).str.replace("万", "e4", regex=False)
            df[c] = df[c].astype(str).str.replace(",", "", regex=False)
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if "eps" in df.columns:
        df["eps"] = df["eps"].astype(str).str.replace("元", "", regex=False)
        df["eps"] = pd.to_numeric(df["eps"], errors="coerce")

    df.to_csv(path)
    return df


# ===========================================================================
# 4. 价格修正 (百度估值反推真实股价)
# ===========================================================================
def correct_ohlcv_prices(
    df_daily: pd.DataFrame,
    df_valuation: pd.DataFrame,
    df_financials: pd.DataFrame,
) -> pd.DataFrame:
    """
    新浪日线价格可能因近期除权除息导致前复权因子滞后,
    用百度 PB × 每股净资产(BPS) 反推真实股价进行修正。

    原理:
      真实股价 = PB × BPS
    PB 来自百度 (双周频, 插值为日频)
    BPS 来自同花顺财报 (季度频, 前向填充)
    得到日频真实价格后, 等比例缩放新浪 OHLC。
    """
    df = df_daily.copy()

    if "pb" not in df_valuation.columns or "bps" not in df_financials.columns:
        return df

    pb_raw = df_valuation["pb"].dropna()
    bps_q = df_financials["bps"].dropna()

    if pb_raw.empty or bps_q.empty:
        return df

    # PB 双周频 -> 按日期排序后线性插值为日频
    pb_sorted = pb_raw.sort_index()
    # 扩展到 df 的日期索引
    pb_daily = pb_sorted.reindex(
        pb_sorted.index.union(df.index)
    ).sort_index().interpolate(method="linear").reindex(df.index)

    # BPS 季度 -> 前向填充到日频
    bps_daily = bps_q.sort_index().reindex(df.index, method="ffill")

    # 真实日频股价
    true_price = pb_daily * bps_daily
    true_price = true_price.ffill()  # 填充插值后仍然为 NA 的头部

    # 取最近共同有效的日期计算修正因子
    valid_mask = true_price.notna() & df["close"].notna() & (df["close"] > 0)
    if not valid_mask.any():
        return df

    last_valid = valid_mask[valid_mask].index[-1]
    factor = true_price.loc[last_valid] / df.loc[last_valid, "close"]

    if abs(factor - 1.0) < 0.005:
        return df

    # 逐日等比修正 OHLC (允许修正因子随时间变化, 以 handle 多次除权)
    common = true_price.notna() & (df["close"] > 0)
    daily_factor = true_price[common] / df.loc[common, "close"]
    daily_factor = daily_factor.reindex(df.index).ffill()

    price_cols = ["open", "close", "high", "low"]
    for c in price_cols:
        if c in df.columns:
            df[c] = df[c] * daily_factor

    # 重新计算涨跌幅
    if "close" in df.columns:
        df["pct_change"] = df["close"].pct_change() * 100

    return df


# ===========================================================================
# 5. 指数日线 (新浪)
# ===========================================================================
def fetch_index_daily(
    symbol: str = "000300",
    start_date: str = "20150101",
    end_date: str = "20251231",
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    获取指数日线数据 (默认沪深300)
    数据源: 新浪财经
    """
    path = _cache_path("index", symbol)
    if use_cache and os.path.exists(path):
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        return df

    # 指数代码前缀规则: 上证指数以 000 开头, 深证指数以 399 开头
    if symbol.startswith(("sh", "sz")):
        full_symbol = symbol
    elif symbol.startswith("0"):
        full_symbol = f"sh{symbol}"
    elif symbol.startswith("3"):
        full_symbol = f"sz{symbol}"
    else:
        full_symbol = f"sh{symbol}"

    df = ak.stock_zh_index_daily(symbol=full_symbol)

    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df.sort_index(inplace=True)

    # 过滤日期范围
    if start_date:
        df = df[df.index >= start_date]
    if end_date:
        df = df[df.index <= end_date]

    for c in ["close", "open", "high", "low", "volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df.to_csv(path)
    return df
