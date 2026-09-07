"""Evaluate technical alert rules against OHLCV series."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

SIGNAL_CONDITIONS = (
    "price_above",
    "price_below",
    "pct_up",
    "pct_down",
    "rsi_cross_above",
    "rsi_cross_below",
    "sma_cross_above",
    "sma_cross_below",
    "macd_cross",
    "bb_touch_upper",
    "bb_touch_lower",
    "volume_spike",
)


def parse_signal_rules(
    rules: str | list[dict[str, Any]] | None,
    condition: str | None = None,
    value: float | None = None,
    length: int = 14,
    mult: float = 2.0,
    lookback: int = 1,
) -> list[dict[str, Any]]:
    """Normalize JSON or query params into a list of rule dicts."""
    parsed: list[dict[str, Any]] = []
    if isinstance(rules, list):
        parsed = [dict(item) for item in rules if isinstance(item, dict)]
    elif isinstance(rules, str) and rules.strip():
        loaded = json.loads(rules)
        if isinstance(loaded, dict):
            parsed = [loaded]
        elif isinstance(loaded, list):
            parsed = [dict(item) for item in loaded if isinstance(item, dict)]
        else:
            raise ValueError("rules JSON must be an object or an array of objects")
    if condition:
        parsed.append(
            {
                "condition": condition,
                "value": value,
                "length": length,
                "mult": mult,
                "lookback": lookback,
            }
        )
    if not parsed:
        raise ValueError("Provide condition or rules JSON")
    for item in parsed:
        cond = str(item.get("condition", ""))
        if cond not in SIGNAL_CONDITIONS:
            raise ValueError(
                f"Unknown condition '{cond}'. Allowed: {', '.join(SIGNAL_CONDITIONS)}"
            )
    return parsed


def _crosses_above(left: pd.Series, right: pd.Series | float, index: int) -> bool:
    if index < 1:
        return False
    current = left.iloc[index]
    previous = left.iloc[index - 1]
    right_current = right if isinstance(right, (int, float)) else right.iloc[index]
    right_previous = right if isinstance(right, (int, float)) else right.iloc[index - 1]
    if pd.isna(current) or pd.isna(previous) or pd.isna(right_current) or pd.isna(right_previous):
        return False
    return previous <= right_previous and current > right_current


def _crosses_below(left: pd.Series, right: pd.Series | float, index: int) -> bool:
    if index < 1:
        return False
    current = left.iloc[index]
    previous = left.iloc[index - 1]
    right_current = right if isinstance(right, (int, float)) else right.iloc[index]
    right_previous = right if isinstance(right, (int, float)) else right.iloc[index - 1]
    if pd.isna(current) or pd.isna(previous) or pd.isna(right_current) or pd.isna(right_previous):
        return False
    return previous >= right_previous and current < right_current


def _wilder_rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    fast = close.ewm(span=12, adjust=False).mean()
    slow = close.ewm(span=26, adjust=False).mean()
    macd = fast - slow
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


def evaluate_signals(
    data: pd.DataFrame,
    rules: list[dict[str, Any]],
    last_only: bool = False,
) -> list[dict[str, Any]]:
    """Return fired alert rows for each matching bar.

    Parameters
    ----------
    data : DataFrame
        OHLCV frame with a close column. Index values are used as ``date``.
    rules : list[dict]
        Each rule needs ``condition`` and optional ``value``, ``length``,
        ``mult``, ``lookback``. Synthetic example:
        ``{"condition": "price_above", "value": 150.25}``.
    last_only : bool
        If True, only evaluate the last bar (on-bar-close scanner).
    """
    if data.empty or not rules:
        return []
    frame = data.copy()
    if "close" not in frame.columns:
        raise ValueError("OHLCV data must include a close column")
    close = pd.to_numeric(frame["close"], errors="coerce")
    volume = (
        pd.to_numeric(frame["volume"], errors="coerce")
        if "volume" in frame.columns
        else pd.Series(0.0, index=frame.index)
    )
    events: list[dict[str, Any]] = []
    start = len(frame) - 1 if last_only else 1
    start = max(1, start)

    for rule in rules:
        condition = str(rule["condition"])
        length = int(rule.get("length") or (14 if condition.startswith("rsi") else 20))
        if condition in {"sma_cross_above", "sma_cross_below"} and rule.get("value") is not None:
            length = int(rule["value"])
        value = float(rule["value"]) if rule.get("value") is not None else (
            70.0
            if condition == "rsi_cross_above"
            else 30.0
            if condition == "rsi_cross_below"
            else 0.0
        )
        mult = float(rule.get("mult") or 2.0)
        lookback = max(1, int(rule.get("lookback") or 1))
        rsi = _wilder_rsi(close, length)
        sma = close.rolling(length).mean()
        macd, signal = _macd(close)
        bb_mid = close.rolling(length).mean()
        bb_std = close.rolling(length).std(ddof=0)
        bb_upper = bb_mid + mult * bb_std
        bb_lower = bb_mid - mult * bb_std
        vol_sma = volume.rolling(length).mean()

        for index in range(start, len(frame)):
            hit = False
            direction = "neutral"
            measured = float(close.iloc[index]) if pd.notna(close.iloc[index]) else None
            threshold: float | None = value
            if measured is None:
                continue
            if condition == "price_above":
                hit = _crosses_above(close, value, index)
                direction = "up"
            elif condition == "price_below":
                hit = _crosses_below(close, value, index)
                direction = "down"
            elif condition == "pct_up":
                if index - lookback < 0 or close.iloc[index - lookback] in (0, None) or pd.isna(
                    close.iloc[index - lookback]
                ):
                    continue
                pct = (close.iloc[index] - close.iloc[index - lookback]) / close.iloc[
                    index - lookback
                ] * 100
                prev_pct = float("-inf")
                if index - lookback - 1 >= 0 and close.iloc[index - lookback - 1] not in (0, None):
                    prev_pct = (
                        (close.iloc[index - 1] - close.iloc[index - lookback - 1])
                        / close.iloc[index - lookback - 1]
                        * 100
                    )
                hit = pct >= value and prev_pct < value
                measured = float(pct)
                direction = "up"
            elif condition == "pct_down":
                if index - lookback < 0 or close.iloc[index - lookback] in (0, None) or pd.isna(
                    close.iloc[index - lookback]
                ):
                    continue
                pct = (close.iloc[index] - close.iloc[index - lookback]) / close.iloc[
                    index - lookback
                ] * 100
                prev_pct = float("inf")
                if index - lookback - 1 >= 0 and close.iloc[index - lookback - 1] not in (0, None):
                    prev_pct = (
                        (close.iloc[index - 1] - close.iloc[index - lookback - 1])
                        / close.iloc[index - lookback - 1]
                        * 100
                    )
                hit = pct <= -value and prev_pct > -value
                measured = float(pct)
                threshold = -value
                direction = "down"
            elif condition == "rsi_cross_above":
                hit = _crosses_above(rsi, value, index)
                measured = float(rsi.iloc[index]) if pd.notna(rsi.iloc[index]) else measured
                direction = "up"
            elif condition == "rsi_cross_below":
                hit = _crosses_below(rsi, value, index)
                measured = float(rsi.iloc[index]) if pd.notna(rsi.iloc[index]) else measured
                direction = "down"
            elif condition == "sma_cross_above":
                hit = _crosses_above(close, sma, index)
                threshold = float(sma.iloc[index]) if pd.notna(sma.iloc[index]) else None
                direction = "up"
            elif condition == "sma_cross_below":
                hit = _crosses_below(close, sma, index)
                threshold = float(sma.iloc[index]) if pd.notna(sma.iloc[index]) else None
                direction = "down"
            elif condition == "macd_cross":
                if _crosses_above(macd, signal, index):
                    hit = True
                    direction = "up"
                elif _crosses_below(macd, signal, index):
                    hit = True
                    direction = "down"
                measured = float(macd.iloc[index]) if pd.notna(macd.iloc[index]) else measured
                threshold = float(signal.iloc[index]) if pd.notna(signal.iloc[index]) else None
            elif condition == "bb_touch_upper":
                if pd.isna(bb_upper.iloc[index]) or pd.isna(bb_upper.iloc[index - 1]):
                    continue
                hit = (
                    close.iloc[index] >= bb_upper.iloc[index]
                    and close.iloc[index - 1] < bb_upper.iloc[index - 1]
                )
                threshold = float(bb_upper.iloc[index])
                direction = "up"
            elif condition == "bb_touch_lower":
                if pd.isna(bb_lower.iloc[index]) or pd.isna(bb_lower.iloc[index - 1]):
                    continue
                hit = (
                    close.iloc[index] <= bb_lower.iloc[index]
                    and close.iloc[index - 1] > bb_lower.iloc[index - 1]
                )
                threshold = float(bb_lower.iloc[index])
                direction = "down"
            elif condition == "volume_spike":
                avg = vol_sma.iloc[index]
                if pd.isna(avg) or avg == 0:
                    continue
                spiked = volume.iloc[index] > mult * avg
                prev_avg = vol_sma.iloc[index - 1]
                prev_spiked = (
                    pd.notna(prev_avg)
                    and prev_avg != 0
                    and volume.iloc[index - 1] > mult * prev_avg
                )
                hit = bool(spiked and not prev_spiked)
                measured = float(volume.iloc[index])
                threshold = float(mult * avg)
                direction = "neutral"

            if not hit:
                continue
            stamp = frame.index[index]
            events.append(
                {
                    "date": stamp.isoformat() if hasattr(stamp, "isoformat") else str(stamp),
                    "condition": condition,
                    "direction": direction,
                    "value": measured,
                    "threshold": threshold,
                    "message": f"{condition} fired",
                }
            )
    return events


def register_signals(router: Any) -> None:
    """Attach POST /technical/signals to the OpenBB technical router."""
    # pylint: disable=import-outside-toplevel
    import pandas as pd
    from openbb_core.app.model.obbject import OBBject
    from openbb_core.app.utils import basemodel_to_df, df_to_basemodel
    from openbb_core.provider.abstract.data import Data
    from openbb_technical.helpers import validate_data

    @router.command(methods=["POST"])
    def signals(  # noqa: PLR0913
        data: list[Data],
        index: str = "date",
        condition: str | None = None,
        value: float | None = None,
        length: int = 14,
        mult: float = 2.0,
        lookback: int = 1,
        rules: str | None = None,
        last_only: bool = False,
    ) -> OBBject[list[Data]]:
        """Evaluate technical alert rules against OHLCV data.

        Conditions: price_above, price_below, pct_up, pct_down, rsi_cross_above,
        rsi_cross_below, sma_cross_above, sma_cross_below, macd_cross,
        bb_touch_upper, bb_touch_lower, volume_spike.

        Pass a single ``condition`` or JSON ``rules`` such as
        ``[{"condition": "price_above", "value": 150.25}]``.
        """
        validate_data(data, 2)
        parsed = parse_signal_rules(
            rules,
            condition=condition,
            value=value,
            length=length,
            mult=mult,
            lookback=lookback,
        )
        frame = basemodel_to_df(data, index=index)
        hits = evaluate_signals(frame, parsed, last_only=last_only)
        results = df_to_basemodel(pd.DataFrame(hits)) if hits else []
        return OBBject(results=results)
