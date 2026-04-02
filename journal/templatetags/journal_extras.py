"""
journal/templatetags/journal_extras.py
"""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Access dict by key in templates: {{ dict|get_item:key }}"""
    if isinstance(dictionary, dict):
        return dictionary.get(str(key), False)
    return False


@register.filter
def split(value, delimiter=','):
    """Split a string by delimiter: {{ "a,b,c"|split:"," }}"""
    return value.split(delimiter)


@register.filter
def abs_value(value):
    try:
        return abs(value)
    except (TypeError, ValueError):
        return value


@register.filter
def pnl_color(value):
    """Returns Tailwind text colour class based on P&L sign."""
    try:
        v = float(value)
        if v > 0:
            return 'text-profit'
        elif v < 0:
            return 'text-loss'
    except (TypeError, ValueError):
        pass
    return 'text-neutral'


@register.filter
def pnl_bg(value):
    """Returns Tailwind bg colour class based on P&L sign."""
    try:
        v = float(value)
        if v > 0:
            return 'bg-profit/10'
        elif v < 0:
            return 'bg-loss/10'
    except (TypeError, ValueError):
        pass
    return 'bg-neutral/10'


@register.filter
def pnl_str(value, decimals=2):
    """Format P&L as +$1,234.56 or -$1,234.56."""
    try:
        v = float(value)
        sign = '+' if v >= 0 else '-'
        return f'{sign}${abs(v):,.{int(decimals)}f}'
    except (TypeError, ValueError):
        return '—'


@register.filter
def startswith(value, arg):
    """Check if string starts with arg: {{ request.path|startswith:"/trades/" }}"""
    return str(value).startswith(str(arg))


@register.filter
def rr_str(value):
    """Format R:R ratio stripping trailing zeros: 4.00→'4', 4.50→'4.5', 2.75→'2.75'."""
    if value is None:
        return ''
    try:
        d = Decimal(str(value)).normalize()
        return format(d, 'f')
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
