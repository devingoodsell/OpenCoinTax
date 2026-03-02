from datetime import datetime

from pydantic import BaseModel


class Form8949Row(BaseModel):
    description: str          # (a) e.g. "0.5 BTC"
    date_acquired: datetime   # (b)
    date_sold: datetime       # (c)
    proceeds: str             # (d)
    cost_basis: str           # (e)
    adjustment_code: str      # (f)
    adjustment_amount: str    # (g)
    gain_loss: str            # (h)
    holding_period: str       # short_term or long_term
    checkbox_category: str    # G, H, J, K


class Form8949Response(BaseModel):
    tax_year: int
    short_term_rows: list[Form8949Row]
    long_term_rows: list[Form8949Row]
    short_term_totals: dict[str, str]
    long_term_totals: dict[str, str]


class ScheduleDLine(BaseModel):
    line: str
    description: str
    proceeds: str
    cost_basis: str
    gain_loss: str


class ScheduleDResponse(BaseModel):
    tax_year: int
    lines: list[ScheduleDLine]
    net_short_term: str
    net_long_term: str
    combined_net: str
