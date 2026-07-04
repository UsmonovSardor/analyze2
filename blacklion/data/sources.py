"""Market-data sources (SRS doc 06 — Market Data Engine).

One Protocol, several adapters — exactly like the broker layer. Every source
returns an indicator-enriched OHLCV DataFrame (newest row last) so the pipeline
consumes identical shapes regardless of origin.

  - ReplaySource : deterministic, in-memory — tests + backtest (doc 20 replay)
  - YahooSource  : yfinance — free live-ish data for forex/gold/stocks, no creds
  - MT5Source    : pulls candles from the MT5 bridge (needs a live terminal)

Validation (doc 07) + normalization (doc 08) run inside fetch() so no engine
ever sees raw broker data.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd

from ..core.logging import get_logger
from .indicators import add_indicators

log = get_logger("data.sources")

_REQUIRED = ("open", "high", "low", "close", "volume")


def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    """Validate schema + drop malformed candles (doc 07 §8), then add indicators."""
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"source frame missing columns: {missing}")
    clean = df[
        (df["high"] >= df["low"])
        & (df["high"] >= df["open"]) & (df["high"] >= df["close"])
        & (df["low"] <= df["open"]) & (df["low"] <= df["close"])
        & (df["close"] > 0) & (df["volume"] >= 0)
    ].reset_index(drop=True)
    return add_indicators(clean)


@runtime_checkable
class MarketDataSource(Protocol):
    def fetch(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame: ...


class ReplaySource:
    """Serves a pre-loaded frame, optionally windowed — deterministic for tests
    and historical replay (the backtester steps `count` upward over time)."""

    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self._frames = frames

    def fetch(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        df = self._frames.get(f"{symbol}:{timeframe}")
        if df is None:
            df = self._frames.get(symbol)
        if df is None:
            raise KeyError(f"no replay frame for {symbol}:{timeframe}")
        return _finalize(df.tail(count))


class YahooSource:                    # pragma: no cover - network dependent
    """yfinance adapter for forex/gold/stocks (SRS doc 06 §3 market feeds)."""

    _TF = {"M15": "15m", "H1": "1h", "H4": "1h", "D1": "1d"}
    # Explicit tickers for non-forex; forex falls back to "<PAIR>=X" (see _ticker).
    _MAP = {
        "XAUUSD": "GC=F", "XAGUSD": "SI=F",          # metals (COMEX futures)
        "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD",  # crypto (Yahoo spot)
        "SOLUSDT": "SOL-USD", "BNBUSDT": "BNB-USD", "XRPUSDT": "XRP-USD",
        "US30": "^DJI", "NAS100": "^NDX", "SPX500": "^GSPC",
        "GER40": "^GDAXI", "UK100": "^FTSE", "JP225": "^N225",
    }

    def _ticker(self, symbol: str) -> str:
        if symbol in self._MAP:
            return self._MAP[symbol]
        # 6-letter FX pair (EURUSD, NZDUSD, USDCAD, ...) → Yahoo "EURUSD=X"
        if len(symbol) == 6 and symbol.isalpha():
            return f"{symbol}=X"
        return symbol

    def fetch(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        import yfinance as yf
        ticker = self._ticker(symbol)
        interval = self._TF.get(timeframe, "1h")
        period = "60d" if interval in ("15m", "1h") else "2y"
        raw = yf.download(ticker, interval=interval, period=period, progress=False,
                          auto_adjust=True, multi_level_index=False)
        if raw is None or raw.empty:
            raise RuntimeError(f"yfinance: no data for {ticker}")
        # reset FIRST so the DatetimeIndex becomes a column, THEN lowercase all
        # columns (index name is "Datetime"/"Date" — capitalised until now).
        raw = raw.reset_index()
        raw.columns = [str(c).lower() for c in raw.columns]
        if timeframe == "H4":
            raw = self._resample_4h(raw)
        return _finalize(raw[list(_REQUIRED)].tail(count))

    @staticmethod
    def _resample_4h(df: pd.DataFrame) -> pd.DataFrame:
        ts = "datetime" if "datetime" in df.columns else "date"
        g = df.set_index(pd.to_datetime(df[ts])).resample("4h").agg(
            {"open": "first", "high": "max", "low": "min",
             "close": "last", "volume": "sum"}).dropna(subset=["close"])
        return g.reset_index(drop=True)


class MT5Source:                      # pragma: no cover - needs live terminal
    """Pulls candles from the same MT5 bridge the executor uses."""

    _TF_MIN = {"M15": 15, "H1": 60, "H4": 240, "D1": 1440}

    def __init__(self, mt5_module=None) -> None:
        self._mt5 = mt5_module        # injected connected MetaTrader5 handle/proxy

    def fetch(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        mt5 = self._mt5
        tf_const = getattr(mt5, f"TIMEFRAME_{timeframe}")
        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, count)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"MT5: no rates for {symbol} {timeframe}")
        df = pd.DataFrame(rates)
        df = df.rename(columns={"tick_volume": "volume", "real_volume": "volume2"})
        if "volume" not in df:
            df["volume"] = df.get("volume2", 0)
        return _finalize(df[list(_REQUIRED)])
