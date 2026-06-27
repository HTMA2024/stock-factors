#!/usr/bin/env python3
"""
命令行入口 - 单只股票全因子历史曲线分析

用法:
    python3 run.py 600519                          # 默认近3年, 保存 HTML
    python3 run.py 600519 --start 2020-01-01        # 指定起始日期
    python3 run.py 600519 --end 2025-06-26           # 指定结束日期
    python3 run.py 600519 --no-cache                 # 强制重新获取数据
    python3 run.py 600519 --corr                     # 同时生成因子相关性矩阵
    python3 run.py 600519 --show                     # 直接在浏览器打开 (不保存文件)
"""

import argparse
import sys
import os

# 确保模块可导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import (
    fetch_daily_ohlcv,
    fetch_valuation,
    fetch_financials,
    fetch_index_daily,
    correct_ohlcv_prices,
)
from factor_engine import compute_all_factors
from visualizer import plot_all_factors, plot_factor_heatmap


def main():
    parser = argparse.ArgumentParser(
        description="股票多因子历史曲线分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 run.py 600519                          茅台, 默认近5年
  python3 run.py 000858 --start 2018-01-01       五粮液, 从2018年开始
  python3 run.py 300750 --corr --show            宁德时代, 含相关性矩阵, 浏览器打开
        """,
    )
    parser.add_argument("symbol", type=str, help="股票代码 (如: 600519)")
    parser.add_argument("--start", type=str, default="20150101", help="起始日期 YYYYMMDD")
    parser.add_argument("--end", type=str, default="20301231", help="结束日期 YYYYMMDD")
    parser.add_argument("--no-cache", action="store_true", help="不使用缓存, 强制重新获取数据")
    parser.add_argument("--corr", action="store_true", help="同时生成因子相关性矩阵")
    parser.add_argument("--show", action="store_true", help="直接浏览器打开, 不保存文件")
    parser.add_argument("--output", type=str, default=None, help="输出 HTML 路径 (默认: output/<symbol>.html)")
    parser.add_argument("--index", type=str, default="000300", help="用于计算 Beta 的指数代码 (默认: 000300 沪深300)")
    args = parser.parse_args()

    use_cache = not args.no_cache
    symbol = args.symbol

    print(f"========================================")
    print(f"  股票: {symbol}")
    print(f"  日期: {args.start} ~ {args.end}")
    print(f"========================================")

    # ---- Step 1: 获取数据 ----
    print("\n[1/4] 获取日线行情...")
    df_daily_raw = fetch_daily_ohlcv(symbol, args.start, args.end, use_cache)
    print(f"     -> {len(df_daily_raw)} 个交易日")

    print("[2/4] 获取估值数据 (PE/PB/市值)...")
    df_valuation = fetch_valuation(symbol, use_cache)
    if df_valuation.empty:
        print("     [警告] 未获取到估值数据")
    else:
        print(f"     -> {len(df_valuation)} 条记录, 日期范围: {df_valuation.index[0].date()} ~ {df_valuation.index[-1].date()}")

    print("[3/4] 获取财务数据 (ROE/毛利率/增长率...)...")
    df_financials = fetch_financials(symbol, use_cache)
    if df_financials.empty:
        print("     [警告] 未获取到财务数据")
    else:
        print(f"     -> {len(df_financials)} 个报告期")

    # 用百度估值反推真实股价修正新浪数据
    df_daily = correct_ohlcv_prices(df_daily_raw, df_valuation, df_financials)

    print("[4/4] 获取指数数据 (用于 Beta)...")
    try:
        df_index = fetch_index_daily(args.index, args.start, args.end, use_cache)
        print(f"     -> {len(df_index)} 个交易日 ({args.index})")
    except Exception as e:
        print(f"     [警告] 指数数据获取失败: {e}, 跳过 Beta 计算")
        df_index = None

    # ---- Step 2: 计算因子 ----
    print("\n[计算] 计算全因子...")
    df_factors = compute_all_factors(df_daily, df_valuation, df_financials, df_index)

    # 限制日期范围
    start_ts = pd.Timestamp(args.start)
    # end_ts = pd.Timestamp(args.end)
    df_factors = df_factors[df_factors.index >= start_ts]

    factor_count = len(df_factors.columns)
    print(f"     -> 共计算 {factor_count} 个因子")
    print(f"     -> 可用因子: {', '.join(df_factors.columns[:20])}...")

    # ---- Step 3: 画图 ----
    print("\n[绘图] 生成交互式图表...")
    output_path = args.output
    if output_path is None and not args.show:
        os.makedirs("output", exist_ok=True)
        output_path = f"output/{symbol}.html"

    title = f"{symbol} 多因子分析面板 ({df_factors.index[0].date()} ~ {df_factors.index[-1].date()})"
    plot_all_factors(df_factors, symbol, output_path=output_path, title=title)

    if args.corr:
        plot_factor_heatmap(df_factors, symbol, output_path=output_path)

    print("\n完成!")


if __name__ == "__main__":
    import pandas as pd  # noqa: E402
    main()
