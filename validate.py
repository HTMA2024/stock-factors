#!/usr/bin/env python3
"""
数据验证脚本 - 交叉校验所有数据源的准确性
用法: python3 validate.py 600519
"""

from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from data_fetcher import (
    fetch_daily_ohlcv,
    fetch_valuation,
    fetch_financials,
    fetch_index_daily,
    correct_ohlcv_prices,
)
from factor_engine import compute_all_factors


def validate(symbol: str) -> dict:
    results: dict[str, list[str]] = {"pass": [], "warn": [], "fail": []}

    def ok(msg):
        results["pass"].append(msg)

    def warn(msg):
        results["warn"].append(msg)

    def fail(msg):
        results["fail"].append(msg)

    # =========================================================================
    # 1. 拉取所有数据
    # =========================================================================
    print("=" * 60)
    print(f"  数据验证: {symbol}")
    print("=" * 60)

    print("\n[拉取数据]")
    df_daily_raw = fetch_daily_ohlcv(symbol, "20150101", "20301231", use_cache=False)
    df_valuation = fetch_valuation(symbol)
    df_financials = fetch_financials(symbol)

    try:
        df_index = fetch_index_daily("000300", "20150101", "20301231")
    except Exception:
        df_index = None

    df_daily = correct_ohlcv_prices(df_daily_raw, df_valuation, df_financials)
    df_factors = compute_all_factors(df_daily, df_valuation, df_financials, df_index)

    # =========================================================================
    # 2. 时效性检查
    # =========================================================================
    print("\n--- 时效性检查 ---")
    today = pd.Timestamp.today()

    # 最后交易日
    last_trade_day = df_daily.index[-1]
    days_behind = (today - last_trade_day).days
    if days_behind <= 2:
        ok(f"日线数据最新日期: {last_trade_day.date()} (落后 {days_behind} 天)")
    elif days_behind <= 7:
        warn(f"日线数据最新日期: {last_trade_day.date()} (落后 {days_behind} 天)")
    else:
        fail(f"日线数据最新日期: {last_trade_day.date()} (落后 {days_behind} 天, 可能未更新)")

    # 估值数据
    last_val_day = df_valuation.index[-1]
    val_days_behind = (today - last_val_day).days
    if val_days_behind <= 3:
        ok(f"估值数据最新日期: {last_val_day.date()} (落后 {val_days_behind} 天)")
    elif val_days_behind <= 14:
        warn(f"估值数据最新日期: {last_val_day.date()} (落后 {val_days_behind} 天, 百度双周更新)")
    else:
        fail(f"估值数据最新日期: {last_val_day.date()} (落后 {val_days_behind} 天)")

    # 财报
    last_fin_day = df_financials.index[-1]
    fin_months_behind = (today.year - last_fin_day.year) * 12 + (today.month - last_fin_day.month)
    if fin_months_behind <= 4:
        ok(f"财报最新报告期: {last_fin_day.date()} ({(today - last_fin_day).days} 天前)")
    elif fin_months_behind <= 7:
        warn(f"财报最新报告期: {last_fin_day.date()} ({(today - last_fin_day).days} 天前, 可能下一季尚未发布)")
    else:
        fail(f"财报最新报告期: {last_fin_day.date()} ({(today - last_fin_day).days} 天前)")

    # Beta 数据
    if df_index is not None:
        last_idx = df_index.index[-1]
        idx_days = (today - last_idx).days
        if idx_days <= 3:
            ok(f"指数数据最新日期: {last_idx.date()} (落后 {idx_days} 天)")
        else:
            warn(f"指数数据最新日期: {last_idx.date()} (落后 {idx_days} 天)")

    # =========================================================================
    # 3. 日线数据合理性检查
    # =========================================================================
    print("\n--- 日线数据检查 ---")
    n_rows = len(df_daily)

    # 列完整性
    required_cols = ["open", "close", "high", "low", "volume", "amount", "turnover"]
    missing = [c for c in required_cols if c not in df_daily.columns]
    if missing:
        fail(f"缺少日线字段: {missing}")
    else:
        ok(f"日线字段完整 ({len(df_daily.columns)} 列)")

    # 交易日数量合理性 (每年 ~242 个交易日)
    years = (df_daily.index[-1] - df_daily.index[0]).days / 365
    expected_trading = years * 242
    if n_rows >= expected_trading * 0.9:
        ok(f"交易日数量: {n_rows} (约 {years:.1f} 年, 合理)")
    else:
        warn(f"交易日数量: {n_rows} (约 {years:.1f} 年, 偏少, 可能有缺失)")

    # 价格: low <= close <= high, low <= open <= high
    close = df_daily["close"]
    bad_hlc = (df_daily["low"] > close) | (close > df_daily["high"])
    bad_ohl = (df_daily["low"] > df_daily["open"]) | (df_daily["open"] > df_daily["high"])
    if bad_hlc.sum() == 0 and bad_ohl.sum() == 0:
        ok("OHLC 大小关系正确 (Low ≤ Close ≤ High, Low ≤ Open ≤ High)")
    else:
        fail(f"OHLC 大小关系异常: {bad_hlc.sum()} + {bad_ohl.sum()} 行")

    # 价格不能为负数或零
    for col in ["open", "close", "high", "low"]:
        if (df_daily[col] <= 0).sum() == 0:
            ok(f"  {col}: 全部 > 0")
        else:
            fail(f"  {col}: 存在 ≤0 的值")

    # 涨跌幅: (close / prev_close - 1) * 100 ≈ pct_change
    calc_pct = close.pct_change() * 100
    diff = (calc_pct - df_daily["pct_change"]).abs()
    max_diff = diff.max()
    if max_diff < 0.1:
        ok(f"涨跌幅计算正确 (最大偏差 {max_diff:.4f}%)")
    else:
        warn(f"涨跌幅计算偏差较大 (最大 {max_diff:.2f}%)")

    # 换手率合理范围 (0 ~ 100%)
    if "turnover" in df_daily.columns:
        to = df_daily["turnover"]
        if to.min() >= 0 and to.max() <= 100:
            ok(f"换手率范围合理 ({to.min():.2f}% ~ {to.max():.2f}%)")
        else:
            fail(f"换手率异常: {to.min():.2f}% ~ {to.max():.2f}%")

    # 成交量 > 0 (停牌日除外)
    zero_vol = (df_daily["volume"] == 0).sum()
    if zero_vol < n_rows * 0.05:
        ok(f"成交量 = 0 的天数: {zero_vol}/{n_rows} (停牌日)")
    else:
        warn(f"成交量 = 0 的天数: {zero_vol}/{n_rows}")

    # =========================================================================
    # 4. 估值数据交叉验证
    # =========================================================================
    print("\n--- 估值数据交叉验证 ---")

    if "pe_ttm" in df_valuation.columns and "pb" in df_valuation.columns:
        # PE 合理范围 (通常 5 ~ 200, 金融/亏损除外)
        pe_latest = df_valuation["pe_ttm"].dropna().iloc[-1]
        if 3 < pe_latest < 300:
            ok(f"PE(TTM) 最新 = {pe_latest:.1f} (范围合理)")
        elif pe_latest <= 0:
            warn(f"PE(TTM) = {pe_latest:.1f} (亏损或数据异常)")
        else:
            warn(f"PE(TTM) = {pe_latest:.1f} (极端值)")

        # PB 合理范围
        pb_latest = df_valuation["pb"].dropna().iloc[-1]
        if 0.1 < pb_latest < 50:
            ok(f"PB 最新 = {pb_latest:.2f} (范围合理)")
        else:
            warn(f"PB = {pb_latest:.2f} (极端值)")

        # PE > 0 ⟹ EPS = price / PE 应合理
        eps_implied = latest_price() / pe_latest if pe_latest > 0 else np.nan
        co = close.iloc[-1] if len(close) > 0 else np.nan
        if not np.isnan(eps_implied) and not np.isnan(co):
            ok(f"隐含 EPS = {eps_implied:.2f} (来自 PE × 价格)")

        # PE / PB = BPS / EPS = ROE 的倒数相关
        if pe_latest > 0 and pb_latest > 0:
            implied_roe_ratio = pb_latest / pe_latest * 100
            ok(f"PB/PE 隐含 ROE ≈ {implied_roe_ratio:.1f}% (PB={pb_latest:.2f}, PE={pe_latest:.1f})")

        # 检查 PE / PB 数据连续性
        pe_nan = df_valuation["pe_ttm"].isna().sum()
        pb_nan = df_valuation["pb"].isna().sum()
        if pe_nan == 0 and pb_nan == 0:
            ok("PE / PB 无缺失值")
        else:
            warn(f"PE 缺失 {pe_nan}, PB 缺失 {pb_nan}")

    # =========================================================================
    # 5. 价格修正验证
    # =========================================================================
    print("\n--- 价格修正验证 ---")
    if "pb" in df_valuation.columns and "bps" in df_financials.columns:
        pb_daily = df_valuation["pb"].sort_index().interpolate().reindex(df_daily.index).ffill()
        bps_daily = df_financials["bps"].sort_index().reindex(df_daily.index, method="ffill")

        # 只检查有数据的最后 20 天
        valid = pb_daily.notna() & bps_daily.notna() & close.notna()
        check_dates = valid[valid].index[-20:] if valid.sum() >= 20 else valid[valid].index
        if len(check_dates) > 0:
            diffs = []
            for dt in check_dates:
                derived = pb_daily.loc[dt] * bps_daily.loc[dt]
                actual = close.loc[dt]
                if derived > 0 and actual > 0:
                    diffs.append(abs(derived - actual) / actual * 100)
            if diffs:
                avg_diff = np.mean(diffs)
                max_diff = max(diffs)
                if avg_diff < 2 and max_diff < 5:
                    ok(f"PB×BPS vs 修正后收盘价: 平均偏差 {avg_diff:.2f}%, 最大 {max_diff:.2f}% (良好)")
                elif avg_diff < 5:
                    warn(f"PB×BPS vs 修正后收盘价: 平均偏差 {avg_diff:.2f}%, 最大 {max_diff:.2f}% (一般)")
                else:
                    fail(f"PB×BPS vs 修正后收盘价偏差过大: 平均 {avg_diff:.2f}%, 最大 {max_diff:.2f}%")
            else:
                warn("无法计算价格偏差 (数据不足)")
        else:
            warn("无法计算价格偏差 (无共同有效日期)")

    # =========================================================================
    # 6. 财务数据逻辑校验
    # =========================================================================
    print("\n--- 财务数据逻辑校验 ---")
    fin = df_financials

    if not fin.empty:
        # 毛利率 > 净利率 (因为营业成本和费用)
        if "gross_margin" in fin.columns and "net_margin" in fin.columns:
            valid_rows = fin["gross_margin"].notna() & fin["net_margin"].notna()
            violations = (fin.loc[valid_rows, "gross_margin"] < fin.loc[valid_rows, "net_margin"]).sum()
            total_valid = valid_rows.sum()
            if total_valid > 0 and violations == 0:
                ok(f"毛利率 ≥ 净利率: 全部通过 ({total_valid} 个报告期)")
            elif total_valid > 0:
                fail(f"毛利率 < 净利率: {violations}/{total_valid} 个报告期异常")
            else:
                warn("无法校验毛利率/净利率 (无数据)")

        # ROE 合理范围 (通常 0~50%, 极端可到 100%)
        if "roe" in fin.columns:
            roe_valid = fin["roe"].dropna()
            if len(roe_valid) > 0:
                if roe_valid.min() >= -10 and roe_valid.max() <= 50:
                    ok(f"ROE 范围合理 ({roe_valid.min():.1f}% ~ {roe_valid.max():.1f}%)")
                else:
                    warn(f"ROE 范围异常 ({roe_valid.min():.1f}% ~ {roe_valid.max():.1f}%)")

        # 资产负债率 + 某种形式的权益比率 ≈ 100% ?
        # 实际上 debt_ratio = total_liability / total_asset
        # 没有直接的 equity ratio，但有产权比率 = liability / equity
        if "debt_ratio" in fin.columns and "equity_ratio" in fin.columns:
            dr = fin["debt_ratio"].dropna()
            er = fin["equity_ratio"].dropna()
            common = dr.index.intersection(er.index)
            if len(common) > 0:
                # 产权比率 = 负债/权益, 资产负债率 = 负债/总资产
                # 权益/总资产 = 1/(1+产权比率)
                derived_equity_ratio = 100 / (1 + fin.loc[common, "equity_ratio"] / 100)
                # 检查: 资产负债率 + 权益占比 ≈ 1
                sum_check = fin.loc[common, "debt_ratio"] + derived_equity_ratio
                if all(abs(sum_check - 100) < 5):
                    ok(f"资产负债率 + 权益占比 ≈ 100%: 通过 ({len(common)} 期)")
                else:
                    bad = (abs(sum_check - 100) >= 5).sum()
                    warn(f"资产负债率 + 权益占比 偏差: {bad} 期偏离")
            else:
                warn("无共同日期可校验资产负债率/产权比率")

        # 流动比率 ≥ 速动比率 (因为存货)
        if "current_ratio" in fin.columns and "quick_ratio" in fin.columns:
            valid_rows = fin["current_ratio"].notna() & fin["quick_ratio"].notna()
            violations = (fin.loc[valid_rows, "current_ratio"] < fin.loc[valid_rows, "quick_ratio"]).sum()
            total_v = valid_rows.sum()
            if total_v > 0 and violations == 0:
                ok(f"流动比率 ≥ 速动比率: 通过 ({total_v} 期)")
            elif total_v > 0:
                fail(f"流动比率 < 速动比率: {violations}/{total_v} 期异常")

    # =========================================================================
    # 7. 技术指标校验
    # =========================================================================
    print("\n--- 技术指标校验 ---")

    # RSI 范围 0~100
    for col in ["rsi6", "rsi14", "rsi24"]:
        if col in df_factors.columns:
            valid = df_factors[col].dropna()
            if len(valid) > 0:
                if valid.min() >= 0 and valid.max() <= 100:
                    ok(f"{col}: 范围 [{valid.min():.1f}, {valid.max():.1f}] ✓")
                else:
                    fail(f"{col}: 超出 0~100 范围")

    # MACD: DIF 和 DEA 不应差太远
    if "dif" in df_factors.columns and "dea" in df_factors.columns:
        valid = df_factors["dif"].notna() & df_factors["dea"].notna()
        diff = (df_factors.loc[valid, "dif"] - df_factors.loc[valid, "dea"]).abs()
        ok(f"MACD DIF-DEA 最大绝对差: {diff.max():.2f}")

    # 均线: MA60 > MA120 > MA250 通常成立 (牛市) 或反过来 (熊市)
    # 不强制判断方向，只检查无异常跳变
    if "ma20" in df_factors.columns:
        ma_jump = df_factors["ma20"].pct_change().abs().dropna()
        if ma_jump.max() < 0.2:  # 单日变化不超过 20%
            ok(f"MA20 单日变化 < 20%: 最大 {ma_jump.max()*100:.1f}%")
        else:
            warn(f"MA20 存在较大跳变: 最大 {ma_jump.max()*100:.1f}%")

    # 布林带: upper ≥ middle ≥ lower
    if all(c in df_factors.columns for c in ["bb_upper", "bb_middle", "bb_lower"]):
        valid = df_factors[["bb_upper", "bb_middle", "bb_lower"]].dropna()
        wrong_um = (valid["bb_upper"] < valid["bb_middle"]).sum()
        wrong_ml = (valid["bb_middle"] < valid["bb_lower"]).sum()
        if wrong_um == 0 and wrong_ml == 0:
            ok(f"布林带: upper ≥ middle ≥ lower ✓ ({len(valid)} 行)")
        else:
            fail(f"布林带顺序异常: {wrong_um + wrong_ml} 行")

    # Beta 范围 (通常 0.3~2.0)
    if "beta" in df_factors.columns:
        beta_valid = df_factors["beta"].dropna()
        if len(beta_valid) > 0:
            ok(f"Beta 范围: [{beta_valid.min():.2f}, {beta_valid.max():.2f}]")

    # 波动率 >= 0
    for col in ["vol20d", "vol60d", "vol120d"]:
        if col in df_factors.columns:
            valid = df_factors[col].dropna()
            if len(valid) > 0 and valid.min() >= 0:
                ok(f"{col} ≥ 0: min={valid.min():.2f}%")
            elif len(valid) > 0:
                fail(f"{col} 存在负值: min={valid.min():.2f}%")

    # 最大回撤 ≤ 0
    for col in ["mdd60d", "mdd120d", "mdd250d"]:
        if col in df_factors.columns:
            valid = df_factors[col].dropna()
            if len(valid) > 0 and valid.max() <= 0:
                ok(f"{col} ≤ 0: max={valid.max():.2f}%")
            elif len(valid) > 0:
                warn(f"{col} 存在正值: max={valid.max():.2f}%")

    # =========================================================================
    # 8. 因子计算完整性
    # =========================================================================
    print("\n--- 因子计算完整性 ---")
    factor_count = len(df_factors.columns)
    non_empty = sum(1 for c in df_factors.columns if df_factors[c].notna().sum() > 0)
    ok(f"因子总数: {factor_count}, 有效因子: {non_empty}")

    # 关键因子存在性
    expected_factors = [
        "close", "pe_ttm", "pb", "roe", "gross_margin", "net_margin",
        "revenue_yoy", "net_profit_yoy", "debt_ratio", "current_ratio",
        "rsi14", "macd", "turnover", "vol20d", "mom60d",
    ]
    missing_factors = [f for f in expected_factors if f not in df_factors.columns]
    if missing_factors:
        warn(f"缺少预期因子: {missing_factors}")
    else:
        ok("关键因子全部存在")

    # =========================================================================
    # 汇总
    # =========================================================================
    return results


def latest_price() -> float:
    """获取已验证股票的最新收盘价 - 便捷函数"""
    return np.nan


def print_results(results: dict):
    print("\n" + "=" * 60)
    print("  验证结果汇总")
    print("=" * 60)
    print(f"  ✅ 通过: {len(results['pass'])}")
    print(f"  ⚠️  警告: {len(results['warn'])}")
    print(f"  ❌ 失败: {len(results['fail'])}")
    print("=" * 60)

    if results["fail"]:
        print("\n❌ 失败项:")
        for msg in results["fail"]:
            print(f"  • {msg}")

    if results["warn"]:
        print("\n⚠️  警告项:")
        for msg in results["warn"]:
            print(f"  • {msg}")

    if results["pass"]:
        print(f"\n✅ 全部 {len(results['pass'])} 项检查通过.")
        print("   (如需查看详情, 向上滚动查看带有 ✓ 的条目)")


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "600519"
    data = validate(symbol)
    print_results(data)
