"""Unit tests for technical alert signal evaluation."""

import pandas as pd
from extensions.technical.openbb_technical.signals import (
    evaluate_signals,
    parse_signal_rules,
)


def _ohlc(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame(
        {
            "open": closes,
            "high": [value + 1 for value in closes],
            "low": [value - 1 for value in closes],
            "close": closes,
            "volume": [100.0] * n,
        },
        index=pd.date_range("2023-01-01", periods=n, freq="D"),
    )


def test_parse_signal_rules_from_condition():
    rules = parse_signal_rules(None, condition="price_above", value=150.25)
    assert rules == [
        {
            "condition": "price_above",
            "value": 150.25,
            "length": 14,
            "mult": 2.0,
            "lookback": 1,
        }
    ]


def test_parse_signal_rules_from_json():
    rules = parse_signal_rules('[{"condition": "rsi_cross_below", "value": 30}]')
    assert rules[0]["condition"] == "rsi_cross_below"
    assert rules[0]["value"] == 30


def test_price_above_cross():
    frame = _ohlc([10.0, 10.0, 10.0, 12.0])
    hits = evaluate_signals(frame, [{"condition": "price_above", "value": 11}])
    assert len(hits) == 1
    assert hits[0]["condition"] == "price_above"
    assert hits[0]["direction"] == "up"
    assert hits[0]["date"].startswith("2023-01-04")


def test_sma_cross_above():
    frame = _ohlc([10.0, 10.0, 10.0, 20.0])
    hits = evaluate_signals(
        frame, [{"condition": "sma_cross_above", "length": 3, "value": 3}]
    )
    assert hits
    assert hits[-1]["direction"] == "up"


def test_last_only_skips_earlier_hits():
    frame = _ohlc([10.0, 12.0, 10.0, 10.0])
    all_hits = evaluate_signals(frame, [{"condition": "price_above", "value": 11}])
    last = evaluate_signals(
        frame, [{"condition": "price_above", "value": 11}], last_only=True
    )
    assert len(all_hits) == 1
    assert last == []
