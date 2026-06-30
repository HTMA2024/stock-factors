"""
回测引擎 — 统一的形态匹配评估逻辑
供手动回测和自动调参共用, 消除重复代码。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from numba import njit


# ===========================================================================
# DTW (动态时间规整)
# ===========================================================================
@njit
def dtw_distance(s1: np.ndarray, s2: np.ndarray, w: int = 2) -> float:
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
def lb_keogh(s1: np.ndarray, s2: np.ndarray, w: int = 2) -> float:
    """LB_Keogh 下界: O(n) 快速估算 DTW 最小距离, 用于剪枝"""
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


def dtw_similarity(s1: np.ndarray, s2: np.ndarray, w: int = 2,
                   min_similarity: float = 0.0) -> float:
    """DTW 距离转相似度 [0, 1], LB_Keogh 剪枝"""
    s1z = (s1 - np.mean(s1)) / (np.std(s1) + 1e-9)
    s2z = (s2 - np.mean(s2)) / (np.std(s2) + 1e-9)
    norm = 3.0 * len(s1)
    if min_similarity > 0:
        max_dist = norm * (1.0 / min_similarity - 1.0)
        if lb_keogh(s1z, s2z, w) > max_dist:
            return 0.0
    dist = dtw_distance(s1z, s2z, w)
    return 1.0 / (1.0 + dist / norm)


# ===========================================================================
# 相似度计算
# ===========================================================================
def compute_similarity(tpl_vals: np.ndarray, win_vals: np.ndarray,
                       algo: str = "pearson") -> float:
    """统一相似度接口: pearson / dtw / pearson_dtw, 返回 [0, 1]"""
    if np.std(tpl_vals) == 0 or np.std(win_vals) == 0:
        return np.nan
    if algo == "dtw":
        return dtw_similarity(tpl_vals, win_vals)
    else:
        r, _ = pearsonr(tpl_vals, win_vals)
        return (r + 1) / 2


# ===========================================================================
# 相关矩阵
# ===========================================================================
def pearson_corr_matrix(value_arrays, win, weights=None):
    """多因子滑动窗口 Pearson 相关矩阵 (加权平均)"""
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


# ===========================================================================
# 策略辅助
# ===========================================================================
def bt_lookaheads(bt_la, ensemble):
    return (3, 5, 10) if ensemble else (bt_la,)


def ensemble_dir(pred_rets_by_la):
    """多窗口投票方向"""
    all_r = [r for la_rets in pred_rets_by_la for r in la_rets]
    bullish = sum(1 for r in all_r if r > 0)
    bearish = sum(1 for r in all_r if r < 0)
    if bullish > bearish: return 1
    if bearish > bullish: return -1
    return 0


def predict_direction(pred_by_la, ensemble):
    """从各 lookahead 的后续收益列表计算 (direction, avg_pred)"""
    if ensemble:
        direction = ensemble_dir(pred_by_la)
        mid = len(pred_by_la) // 2
        avg_pred = np.mean(pred_by_la[mid]) if pred_by_la[mid] else 0
    else:
        direction = 0
        avg_pred = np.mean(pred_by_la[0])
    return direction, avg_pred


def classify_hit(direction, avg_pred, actual_return, ensemble):
    """统一命中/中性判定, 返回 (hit, neutral)"""
    if ensemble:
        hit = (direction == 1 and actual_return > 0) or (direction == -1 and actual_return < 0)
        neutral = (direction == 0)
    elif abs(avg_pred) < 0.001:
        hit, neutral = False, True
    else:
        hit = (avg_pred > 0 and actual_return > 0) or (avg_pred < 0 and actual_return < 0)
        neutral = False
    return hit, neutral


def resolve_date_range(index, start_str, end_str, min_offset=0):
    """从日期字符串解析为 dataframe 索引范围"""
    s = pd.Timestamp(start_str)
    e = pd.Timestamp(end_str)
    si = max(index.get_indexer([s], method="bfill")[0], min_offset)
    ei = index.get_indexer([e], method="ffill")[0] + 1
    return si, ei


# ===========================================================================
# 统计指标
# ===========================================================================
def segment_stats(df_signal):
    """信号段去重统计"""
    if len(df_signal) == 0:
        return 0, 0, 0.0, 0.0
    d = df_signal.sort_values("date") if "date" in df_signal.columns else df_signal
    sign = np.sign(d["pred_return"].fillna(0))
    seg_id = (sign != sign.shift(1)).cumsum()
    segs = d.groupby(seg_id)
    seg_total = len(segs)
    seg_hits = sum(1 for _, g in segs if g["hit"].iloc[0])
    seg_rate = seg_hits / seg_total * 100 if seg_total > 0 else 0.0
    seg_avg = segs.size().mean() if seg_total > 0 else 0.0
    return seg_total, seg_hits, seg_rate, seg_avg


def wilson_lower(hits, n, z=1.96):
    """Wilson 得分区间下界, 自动惩罚小样本"""
    if n == 0:
        return 0.0
    p = hits / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = z * np.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return max(0.0, float(center - margin))


def compute_metrics(results):
    """从评价结果列表计算汇总指标"""
    if not results:
        return None
    df = pd.DataFrame(results)
    sig = df[~df["neutral"]]
    if len(sig) == 0:
        return None
    seg_total, seg_hit, seg_rate, _ = segment_stats(sig)
    returns = sig["actual_return"].values
    avg_ret = np.mean(returns) * 100
    std_ret = np.std(returns) * 100
    # 年化 Sharpe: 假设每笔交易持有 predict_days 天, 年化系数 sqrt(252/holding_days)
    holding_days = max(sig["actual_return"].notna().sum() / max(len(sig), 1) * 3, 1)  # 估算持仓天数
    ann_factor = np.sqrt(252 / max(holding_days, 1))
    sharpe = (avg_ret / 100) / (std_ret / 100 + 1e-9) * ann_factor
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    win_loss = abs(np.mean(wins) / np.mean(losses)) if len(losses) > 0 and len(wins) > 0 else float('inf')
    return {
        "信号段数": seg_total,
        "命中段数": seg_hit,
        "段命中率%": round(seg_rate, 1),
        "原始命中率%": round(sig["hit"].sum() / len(sig) * 100, 1),
        "有效信号日": len(sig),
        "中性日": int(df["neutral"].sum()),
        "均收益%": round(avg_ret, 2),
        "波动%": round(std_ret, 2),
        "Sharpe": round(sharpe, 2),
        "盈亏比": round(win_loss, 2),
    }


# ===========================================================================
# 统一评价函数 — 手动回测和自动调参共用
# ===========================================================================
def eval_trial(win, la, th, tk, algo, factor_names, vals_dict,
               combined_corr, price_vals, n_data, eval_start, eval_end,
               w_list=None, ensemble_mode=False, timing_filter=False,
               vol_data=None, vol_thresh=None, index=None,
               stop_loss=0.015):
    """
    在 [eval_start, eval_end) 区间内逐日评价策略。

    stop_loss: 止损阈值 (如 0.015 = -1.5%), 持有期最低收盘价跌破 entry×(1-stop_loss) 则截断
    """
    if w_list is None:
        w_list = [1.0 / len(factor_names)] * len(factor_names)
    n_factors = len(factor_names)
    lheads = bt_lookaheads(la, ensemble_mode)
    la_eff = max(lheads)
    la_eval = lheads[len(lheads) // 2]
    s_start = max(eval_start, win * 2)
    s_end = min(eval_end, n_data - la_eff)

    results_t = []
    for t in range(s_start, s_end):
        if timing_filter and vol_thresh is not None:
            if vol_data.iloc[t] > vol_thresh:
                continue

        tpl_idx = t - win
        hist_end = tpl_idx - win
        if hist_end < 0:
            continue

        row = combined_corr[tpl_idx, :hist_end + 1]

        if algo == "dtw":
            loose_mask = np.ones(len(row), dtype=bool)
        else:
            loose_mask = (row + 1) / 2 >= 0.65  # r >= 0.3

        if not loose_mask.any():
            continue

        if algo in ("dtw", "pearson_dtw"):
            dtw_scores = []
            for mi in np.where(loose_mask)[0]:
                dtw_sim = 0.0
                for fi, f in enumerate(factor_names):
                    tpl_v = vals_dict[f][t - win:t]
                    win_v = vals_dict[f][mi:mi + win]
                    s = dtw_similarity(tpl_v, win_v, min_similarity=th)
                    if not np.isnan(s):
                        dtw_sim += w_list[fi] * s
                if dtw_sim >= th:
                    dtw_scores.append((mi, dtw_sim))
            if dtw_scores:
                dtw_scores.sort(key=lambda x: -x[1])
                top_k = dtw_scores[:tk]
                top_k_idx = [x[0] for x in top_k]
                top_k_w = [x[1] for x in top_k]
            else:
                continue
        else:
            row_sim = (row + 1) / 2
            match_idx = np.where(row_sim >= th)[0]
            top_k_idx = match_idx[np.argsort(-row_sim[match_idx])[:tk]]
            top_k_w = list(row_sim[top_k_idx])

        # 置信度加权预测
        pred_by_la = [[] for _ in lheads]
        wt_by_la = [[] for _ in lheads]
        for si, s_idx in enumerate(top_k_idx):
            s_end_pos = s_idx + win - 1
            w = top_k_w[si] if si < len(top_k_w) else 1.0
            for li, lh in enumerate(lheads):
                if s_end_pos + 1 + lh <= n_data:
                    r = (price_vals[s_end_pos + lh] - price_vals[s_end_pos + 1]) / price_vals[s_end_pos + 1]
                    pred_by_la[li].append(r)
                    wt_by_la[li].append(w)

        # 加权平均替代简单 mean
        for li in range(len(pred_by_la)):
            if wt_by_la[li]:
                pred_by_la[li] = [np.average(pred_by_la[li], weights=wt_by_la[li])]
        pred_by_la = [pr for pr in pred_by_la if pr]
        if not pred_by_la:
            continue

        direction, avg_pred = predict_direction(pred_by_la, ensemble_mode)
        act_ret = (price_vals[t + la_eval - 1] - price_vals[t]) / price_vals[t]
        hit, neutral = classify_hit(direction, avg_pred, act_ret, ensemble_mode)

        result = {
            "pred_return": avg_pred,
            "actual_return": act_ret,
            "hit": hit,
            "neutral": neutral,
            "matches": len(top_k_idx),
            "top_r": float(combined_corr[tpl_idx, top_k_idx[0]]) if len(top_k_idx) > 0 else 0.0,
        }
        if index is not None:
            result["date"] = index[t]
        results_t.append(result)

    return results_t
