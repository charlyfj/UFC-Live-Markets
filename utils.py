def fmt_vol(v):
    if v is None: return "--"
    try: v = float(v)
    except: return "--"
    if v >= 1_000_000: return f"${v/1_000_000:.2f}M"
    if v >= 1_000:     return f"${v/1_000:.1f}K"
    return f"${v:.0f}"


def american(odds):
    """American odds int → '+120' / '-200' string."""
    if odds is None: return "--"
    o = int(odds)
    return f"+{o}" if o > 0 else str(o)


def implied(odds):
    """American odds → implied probability 0-1."""
    if odds is None: return None
    o = float(odds)
    return -o / (-o + 100) if o < 0 else 100 / (o + 100)
