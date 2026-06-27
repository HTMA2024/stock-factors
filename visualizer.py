"""
可视化模块
- 生成交互式 Plotly 多子图 HTML 报告
- 7 个面板: 价格&均线, MACD, RSI, PE/PB, 盈利能力, 成长率, 财务健康
"""

from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd


def plot_all_factors(
    df: pd.DataFrame,
    symbol: str,
    output_path: str | None = None,
    title: str | None = None,
) -> go.Figure:
    """
    生成全因子可视化 HTML

    参数
    ----
    df : factor_engine.compute_all_factors 的输出
    symbol : 股票代码
    output_path : 保存路径 (可选), 为 None 则在浏览器打开
    title : 自定义标题
    """
    if title is None:
        title = f"{symbol} 多因子分析面板"

    # 7 行, 部分行使用双 Y 轴
    fig = make_subplots(
        rows=7,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=[0.30, 0.12, 0.12, 0.12, 0.12, 0.10, 0.12],
        specs=[
            [{"secondary_y": False}],   # Row 1: 价格+均线+布林
            [{"secondary_y": False}],   # Row 2: MACD
            [{"secondary_y": True}],    # Row 3: RSI + 波动率
            [{"secondary_y": True}],    # Row 4: PE + PB
            [{"secondary_y": False}],   # Row 5: ROE + 毛利率 + 净利率
            [{"secondary_y": False}],   # Row 6: 营收/净利增长
            [{"secondary_y": True}],    # Row 7: 资产负债率 + 流动比率
        ],
        subplot_titles=(
            "价格 & 均线 & 布林带",
            "MACD (12, 26, 9)",
            "RSI(14) / 波动率(20日年化%)",
            "PE(TTM) / PB",
            "ROE(%) & 毛利率(%) & 净利率(%)",
            "营收同比(%) & 净利润同比(%)",
            "资产负债率(%) / 流动比率",
        ),
    )

    # ---- Row 1: 价格 + 均线 + 布林带 ----
    # 布林带填充
    if all(c in df.columns for c in ["bb_upper", "bb_lower"]):
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["bb_upper"], mode="lines",
                line=dict(width=0), showlegend=False, name="布林上轨",
            ),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["bb_lower"], mode="lines",
                line=dict(width=0), showlegend=False, name="布林下轨",
                fill="tonexty", fillcolor="rgba(128,128,128,0.08)",
            ),
            row=1, col=1,
        )

    # 收盘价
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df["close"], mode="lines",
            name="收盘价", line=dict(color="#1f77b4", width=1.5),
        ),
        row=1, col=1,
    )

    # 均线
    ma_configs = [
        ("ma20", "MA20", "#ff7f0e"),
        ("ma60", "MA60", "#2ca02c"),
        ("ma120", "MA120", "#d62728"),
        ("ma250", "MA250", "#9467bd"),
    ]
    for col, name, color in ma_configs:
        if col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df[col], mode="lines",
                    name=name, line=dict(color=color, width=0.8, dash="dot"),
                ),
                row=1, col=1,
            )

    # ---- Row 2: MACD ----
    if all(c in df.columns for c in ["dif", "dea", "macd"]):
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["dif"], mode="lines",
                name="DIF", line=dict(color="#ff7f0e", width=1.2),
            ),
            row=2, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["dea"], mode="lines",
                name="DEA", line=dict(color="#1f77b4", width=1.2),
            ),
            row=2, col=1,
        )

        macd_val = df["macd"]
        colors_macd = ["#ef5350" if v >= 0 else "#26a69a" for v in macd_val.fillna(0)]
        fig.add_trace(
            go.Bar(
                x=df.index, y=macd_val,
                name="MACD", marker_color=colors_macd, showlegend=False,
            ),
            row=2, col=1,
        )

    # ---- Row 3: RSI(14) + 波动率 ----
    if "rsi14" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["rsi14"], mode="lines",
                name="RSI(14)", line=dict(color="#ff7f0e", width=1.2),
            ),
            row=3, col=1, secondary_y=False,
        )
    if "vol20d" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["vol20d"], mode="lines",
                name="波动率(年化%)", line=dict(color="#7b1fa2", width=1),
            ),
            row=3, col=1, secondary_y=True,
        )

    # ---- Row 4: PE(TTM) + PB ----
    if "pe_ttm" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["pe_ttm"], mode="lines",
                name="PE(TTM)", line=dict(color="#d62728", width=1.2),
            ),
            row=4, col=1, secondary_y=False,
        )
    if "pb" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["pb"], mode="lines",
                name="PB", line=dict(color="#1f77b4", width=1.2),
            ),
            row=4, col=1, secondary_y=True,
        )

    # ---- Row 5: ROE + 毛利率 + 净利率 ----
    profitability = [
        ("roe", "ROE(%)", "#d62728"),
        ("gross_margin", "毛利率(%)", "#ff7f0e"),
        ("net_margin", "净利率(%)", "#2ca02c"),
    ]
    for col, name, color in profitability:
        if col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df[col], mode="lines",
                    name=name, line=dict(color=color, width=1.2),
                ),
                row=5, col=1,
            )

    # ---- Row 6: 营收/净利增长率 ----
    growth = [
        ("revenue_yoy", "营收同比(%)", "#1f77b4"),
        ("net_profit_yoy", "净利同比(%)", "#d62728"),
    ]
    for col, name, color in growth:
        if col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df[col], mode="lines",
                    name=name, line=dict(color=color, width=1.2),
                ),
                row=6, col=1,
            )

    # ---- Row 7: 资产负债率 + 流动比率 ----
    if "debt_ratio" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["debt_ratio"], mode="lines",
                name="资产负债率(%)", line=dict(color="#d62728", width=1.2),
            ),
            row=7, col=1, secondary_y=False,
        )
    if "current_ratio" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["current_ratio"], mode="lines",
                name="流动比率", line=dict(color="#1f77b4", width=1.2),
            ),
            row=7, col=1, secondary_y=True,
        )

    # ---- 水平参考线 ----
    # RSI 70/30
    if "rsi14" in df.columns:
        fig.add_hline(y=70, line_dash="dash", line_color="rgba(255,0,0,0.35)",
                      row=3, col=1, secondary_y=False)
        fig.add_hline(y=30, line_dash="dash", line_color="rgba(0,128,0,0.35)",
                      row=3, col=1, secondary_y=False)

    # ---- 布局 ----
    fig.update_xaxes(
        rangeslider_visible=False,
        showgrid=True, gridwidth=0.5, gridcolor="rgba(128,128,128,0.12)",
    )
    fig.update_yaxes(
        showgrid=True, gridwidth=0.5, gridcolor="rgba(128,128,128,0.12)",
    )

    # 双 Y 轴颜色同步
    if "vol20d" in df.columns:
        fig.update_yaxes(title_text="RSI", row=3, col=1, secondary_y=False)
        fig.update_yaxes(title_text="波动率(%)", row=3, col=1, secondary_y=True,
                         color="#7b1fa2")

    if "pe_ttm" in df.columns and "pb" in df.columns:
        fig.update_yaxes(title_text="PE", row=4, col=1, secondary_y=False)
        fig.update_yaxes(title_text="PB", row=4, col=1, secondary_y=True)

    if "debt_ratio" in df.columns and "current_ratio" in df.columns:
        fig.update_yaxes(title_text="负债率(%)", row=7, col=1, secondary_y=False)
        fig.update_yaxes(title_text="流动比率", row=7, col=1, secondary_y=True)

    # 日期范围标注
    if len(df) > 0:
        date_range = f"{df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}"
        title = f"{title}<br><sup>{date_range} | 共 {len(df)} 个交易日, {sum(1 for c in df.columns if not df[c].isna().all())} 个有效因子</sup>"

    fig.update_layout(
        title=dict(text=title, font=dict(size=18), x=0.5),
        height=1800,
        hovermode="x unified",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1, font=dict(size=10),
        ),
        template="plotly_white",
        margin=dict(l=60, r=60, t=80, b=30),
    )

    if output_path:
        fig.write_html(output_path)
        print(f"图表已保存至: {output_path}")
    else:
        fig.show()

    return fig


def plot_factor_heatmap(
    df: pd.DataFrame,
    symbol: str,
    factors: list[str] | None = None,
    output_path: str | None = None,
) -> go.Figure:
    """绘制因子相关性热力图"""
    if factors is None:
        default_factors = [
            "pe_ttm", "pb", "roe", "net_margin", "gross_margin",
            "revenue_yoy", "net_profit_yoy", "debt_ratio",
            "rsi14", "vol20d", "mom60d", "mom120d", "mom250d",
            "beta", "ma20_dev", "vol_ratio", "turnover",
        ]
        factors = [f for f in default_factors if f in df.columns]

    available = [f for f in factors if f in df.columns and df[f].notna().sum() > 10]
    if len(available) < 2:
        print("[警告] 可用因子不足, 无法生成相关性矩阵")
        return

    corr = df[available].corr()

    fig = go.Figure(
        data=go.Heatmap(
            z=corr.values,
            x=available,
            y=available,
            colorscale="RdBu_r",
            zmid=0,
            zmin=-1,
            zmax=1,
            text=np.round(corr.values, 2),
            texttemplate="%{text}",
            textfont=dict(size=9),
            colorbar=dict(title="相关系数"),
        )
    )
    fig.update_layout(
        title=f"{symbol} 因子相关性矩阵",
        height=max(500, 50 * len(available)),
        width=max(800, 80 * len(available)),
        template="plotly_white",
        xaxis=dict(tickangle=45),
    )

    if output_path:
        corr_path = output_path.replace(".html", "_corr.html")
        fig.write_html(corr_path)
        print(f"相关性矩阵已保存至: {corr_path}")
    else:
        fig.show()

    return fig
