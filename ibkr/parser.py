"""
ibkr/parser.py

Parses IBKR Activity Statement CSV files.

IBKR exports are multi-section CSVs where each section starts with a header row
whose first column identifies the section name (e.g. "Trades").
Within the Trades section, options rows have an "Asset Category" of "Options".

Returns a list of dicts mapping to journal.models.Trade fields.
"""

import csv
import datetime
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class IBKRCSVParser:
    def __init__(self, filepath: Path):
        self.filepath = filepath

    def parse(self) -> list[dict]:
        """
        Returns a list of trade dicts ready to be unpacked into Trade(**row).
        Only Options rows from the Trades section are returned.
        """
        rows = []
        try:
            raw = self._extract_trades_section()
        except Exception as exc:
            logger.error('Failed to parse IBKR CSV: %s', exc)
            return []

        for row in raw:
            trade_dict = self._map_row(row)
            if trade_dict:
                rows.append(trade_dict)

        return rows

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _extract_trades_section(self) -> list[dict]:
        """
        Reads the CSV, isolates the Trades section (Options asset category),
        and returns a list of raw dicts with the column headers as keys.
        """
        trades_rows: list[dict] = []
        in_trades = False
        header: Optional[list[str]] = None

        with open(self.filepath, newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for line in reader:
                if not line:
                    continue

                section = line[0].strip()

                # Detect start of Trades section header row
                if section == 'Trades' and len(line) > 1 and line[1].strip() == 'Header':
                    # Next row (or this row after "Header") contains column names
                    header = [c.strip() for c in line[2:]]  # skip "Trades", "Header"
                    in_trades = True
                    continue

                if in_trades:
                    # Data rows in this section begin with "Trades", "Data"
                    if section == 'Trades' and len(line) > 1 and line[1].strip() == 'Data':
                        values = [c.strip() for c in line[2:]]
                        if header:
                            row = dict(zip(header, values))
                            # Filter to Options only
                            if row.get('Asset Category', '').strip() == 'Options':
                                trades_rows.append(row)
                    elif section != 'Trades':
                        # Entered a new section — stop
                        in_trades = False

        return trades_rows

    def _map_row(self, row: dict) -> Optional[dict]:
        """
        Maps a raw IBKR row dict to a Trade model field dict.
        Returns None if required fields are missing/unparseable.
        """
        try:
            # --- Date/time ---
            dt_raw = row.get('Date/Time', '')
            if ',' in dt_raw:
                date_part, time_part = dt_raw.split(',', 1)
            elif ' ' in dt_raw:
                date_part, time_part = dt_raw.split(' ', 1)
            else:
                date_part, time_part = dt_raw, '00:00:00'
            trade_date  = datetime.date.fromisoformat(date_part.strip())
            entry_time  = datetime.time.fromisoformat(time_part.strip()[:8])

            # --- Quantity & direction ---
            qty_raw = row.get('Quantity', '0').replace(',', '')
            quantity = int(float(qty_raw))
            # Negative qty = sell (opening short) — store abs and infer trade_type

            # --- Prices ---
            entry_price  = Decimal(row.get('T. Price', '0').replace(',', ''))
            realized_pnl_raw = row.get('Realized P&L', '').replace(',', '')
            pnl_override: Optional[Decimal] = None
            if realized_pnl_raw:
                try:
                    pnl_override = Decimal(realized_pnl_raw)
                except InvalidOperation:
                    pass

            # --- Option fields ---
            symbol     = (row.get('Symbol') or row.get('Underlying Symbol') or 'SPX').strip()
            option_type = 'CALL' if row.get('Put/Call', '').upper().startswith('C') else 'PUT'
            strike_raw  = row.get('Strike', '0').replace(',', '')
            strike      = Decimal(strike_raw)
            expiry_raw  = row.get('Expiry') or row.get('Exp Date', '')
            expiry_raw  = expiry_raw.strip()
            # IBKR format can be YYYYMMDD or YYYY-MM-DD
            if len(expiry_raw) == 8 and expiry_raw.isdigit():
                expiry = datetime.date(int(expiry_raw[:4]), int(expiry_raw[4:6]), int(expiry_raw[6:8]))
            else:
                expiry = datetime.date.fromisoformat(expiry_raw)

            # --- Trade type inference ---
            # quantity > 0 = buy (long), < 0 = sell (short)
            if quantity >= 0:
                trade_type = 'LONG_CALL' if option_type == 'CALL' else 'LONG_PUT'
            else:
                trade_type = 'CSP' if option_type == 'PUT' else 'CC'

            # --- Trade ID ---
            ibkr_trade_id = row.get('TradeID') or row.get('Trade ID') or None
            if ibkr_trade_id:
                ibkr_trade_id = ibkr_trade_id.strip() or None

            result: dict = {
                'trade_date':  trade_date,
                'symbol':      symbol,
                'option_type': option_type,
                'strike':      strike,
                'expiry':      expiry,
                'quantity':    abs(quantity),
                'entry_price': entry_price,
                'entry_time':  entry_time,
                'trade_type':  trade_type,
                'status':      'CLOSED' if pnl_override is not None else 'OPEN',
                'ibkr_trade_id': ibkr_trade_id,
            }

            # If IBKR gives us realized P&L, store it directly (overrides computed)
            # We'll store it as pnl and leave exit_price blank — the model will use it.
            # Assumption: imported trades with realized P&L are treated as CLOSED.
            if pnl_override is not None:
                result['pnl'] = pnl_override

            return result

        except Exception as exc:
            logger.warning('Skipping row due to parse error: %s — %s', row, exc)
            return None
