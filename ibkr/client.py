"""
ibkr/client.py

IBKRClient — persistent daemon thread with its own asyncio event loop.
All public methods are synchronous Django-safe wrappers.
If TWS is not running or times out, methods raise RuntimeError — callers
should catch and degrade gracefully.

Assumption: ib_insync ≥ 0.9.86 is installed.
"""

import asyncio
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class IBKRClient:
    """
    Wraps ib_insync's IB() object in a dedicated background thread/event loop
    so Django synchronous views can call it without blocking or creating nested
    event loops.
    """

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ib   = None
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='ibkr-event-loop')
        self._ready  = threading.Event()
        self._thread.start()
        self._ready.wait(timeout=5)

    # ------------------------------------------------------------------
    # Internal — runs in the daemon thread
    # ------------------------------------------------------------------

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            from ib_insync import IB
            self._ib = IB()
        except ImportError:
            logger.warning('ib_insync not importable — IBKR client disabled.')
            self._ib = None
        self._ready.set()
        self._loop.run_forever()

    def _run(self, coro, timeout: float = 10):
        """Submit a coroutine to the event loop and block until result."""
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError('IBKR event loop is not running.')
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # ------------------------------------------------------------------
    # Public API (synchronous, Django-safe)
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        if self._ib is None:
            return False
        try:
            return self._ib.isConnected()
        except Exception:
            return False

    def connect(self, host: str = None, port: int = None, client_id: int = None):
        from django.conf import settings
        host      = host      or settings.IBKR_HOST
        port      = port      or settings.IBKR_PORT
        client_id = client_id or settings.IBKR_CLIENT_ID

        if self._ib is None:
            raise RuntimeError('ib_insync not available.')

        async def _connect():
            if not self._ib.isConnected():
                await self._ib.connectAsync(host, port, clientId=client_id)

        self._run(_connect, timeout=15)

    def disconnect(self):
        if self._ib and self._ib.isConnected():
            async def _disconnect():
                self._ib.disconnect()
            self._run(_disconnect, timeout=5)

    def fetch_greeks(self, symbol: str, expiry: str, strike: float, right: str) -> dict:
        """
        Fetches live bid/ask and model Greeks for a single SPX contract.
        Returns dict with keys: delta, theta, vega, iv, bid, ask
        expiry format: 'YYYYMMDD'
        right: 'C' or 'P'
        """
        from ib_insync import Option, util

        async def _fetch():
            contract = Option(symbol, expiry, strike, right, 'CBOE')
            await self._ib.qualifyContractsAsync(contract)
            tickers  = await self._ib.reqTickersAsync(contract)
            if not tickers:
                raise RuntimeError('No ticker data returned from TWS.')
            ticker   = tickers[0]
            greeks   = ticker.modelGreeks or ticker.lastGreeks
            return {
                'delta': float(greeks.delta)  if greeks and greeks.delta  is not None else None,
                'theta': float(greeks.theta)  if greeks and greeks.theta  is not None else None,
                'vega':  float(greeks.vega)   if greeks and greeks.vega   is not None else None,
                'iv':    float(greeks.impliedVol) if greeks and greeks.impliedVol is not None else None,
                'bid':   float(ticker.bid)    if ticker.bid  is not None else None,
                'ask':   float(ticker.ask)    if ticker.ask  is not None else None,
            }

        return self._run(_fetch, timeout=15)

    def fetch_chain(self, expiry: str) -> list[dict]:
        """
        Fetches SPX 0DTE options chain for the given expiry (YYYYMMDD).
        Returns list of {strike, right, bid, ask, iv, delta} dicts.
        Limits to ±50 strikes around ATM for performance.
        """
        from ib_insync import Index, util

        async def _fetch():
            spx = Index('SPX', 'CBOE')
            await self._ib.qualifyContractsAsync(spx)
            chains = await self._ib.reqSecDefOptParamsAsync(
                spx.symbol, '', spx.secType, spx.conId
            )
            chain = next((c for c in chains if c.exchange == 'CBOE'), None)
            if not chain:
                return []

            if expiry not in chain.expirations:
                return []

            # Fetch a snapshot of ATM price for strike filtering
            tickers_idx = await self._ib.reqTickersAsync(spx)
            atm = tickers_idx[0].marketPrice() if tickers_idx else 0
            strikes = sorted(
                s for s in chain.strikes
                if atm == 0 or abs(float(s) - atm) <= 100  # ±100 pts
            )

            # Build contracts
            from ib_insync import Option
            contracts = [
                Option('SPX', expiry, s, r, 'CBOE')
                for s in strikes
                for r in ('C', 'P')
            ]
            await self._ib.qualifyContractsAsync(*contracts)
            tickers = await self._ib.reqTickersAsync(*contracts)

            result = []
            for t in tickers:
                c = t.contract
                greeks = t.modelGreeks or t.lastGreeks
                result.append({
                    'strike': float(c.strike),
                    'right':  c.right,
                    'bid':    float(t.bid)  if t.bid  is not None else None,
                    'ask':    float(t.ask)  if t.ask  is not None else None,
                    'iv':     float(greeks.impliedVol) if greeks and greeks.impliedVol is not None else None,
                    'delta':  float(greeks.delta)      if greeks and greeks.delta      is not None else None,
                })
            return result

        return self._run(_fetch, timeout=30)


# Module-level singleton — imported by views
ib_client = IBKRClient()
