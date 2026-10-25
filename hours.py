"""
Opening hours: does a place's posted schedule cover when the player wants to go?

- parse_when("tonight after 8pm", now) -> Target(day="friday", minute=1200, label="Fri 8 PM")
- day_intervals("11 AM–2 AM")            -> [(660, 1560)]   (minutes; past midnight > 1440)
- open_at(operating_hours, target)       -> True / False / None (unknown)
- hours_note(place, target, now)         -> "Open Fri at 8 PM · 5 PM–2 AM"

Hours come from SerpApi's `operating_hours` ({"monday": "7 AM–10 PM", ...}).
The player's time zone comes from their browser, since the server runs on UTC.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DEFAULT_TZ = "America/Chicago"

# Rough times for words people use (minutes after midnight).
PART_OF_DAY = {
    "breakfast": 9 * 60, "morning": 10 * 60, "brunch": 11 * 60, "lunch": 12 * 60 + 30,
    "afternoon": 14 * 60, "happy hour": 17 * 60, "evening": 19 * 60, "dinner": 19 * 60,
    "tonight": 20 * 60, "night": 21 * 60, "late night": 23 * 60, "late": 23 * 60,
}


@dataclass
class Target:
    day: str            # "friday"
    minute: int | None  # minutes after midnight, or None = any time that day
    label: str          # "Fri 8 PM" / "Sat"


def local_now(tz_name=None):
    try:
        tz = ZoneInfo(tz_name or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo(DEFAULT_TZ)
    return datetime.now(tz)


def _fmt_minute(m):
    m %= 24 * 60
    h, mm = divmod(m, 60)
    suffix = "AM" if h < 12 else "PM"
    h = h % 12 or 12
    return f"{h}:{mm:02d} {suffix}" if mm else f"{h} {suffix}"


def _clock(text):
    """'8pm', '8:30 pm', '20:00', '8' -> minutes (8 alone is read as PM: people say 'at 8')."""
    m = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*([ap])?\.?\s*m?\.?\s*", text, re.IGNORECASE)
    if not m:
        return None
    h, mm, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if h > 23 or mm > 59:
        return None
    if ap == "p" and h < 12:
        h += 12
    elif ap == "a" and h == 12:
        h = 0
    elif not ap and 1 <= h <= 7:
        h += 12  # "at 7" means evening
    return h * 60 + mm


def parse_when(text, now):
    """Read a day and (optional) time from free text. None if nothing usable."""
    t = " ".join(str(text or "").lower().split())
    if not t:
        return None

    day_offset = None
    named_day = next((d for d in DAYS if re.search(rf"\b{d[:3]}(?:{d[3:]})?\b", t)), None)
    if re.search(r"\btomorrow\b", t):
        day_offset = 1
    elif named_day:
        day_offset = (DAYS.index(named_day) - now.weekday()) % 7
    elif re.search(r"\bthis weekend\b|\bweekend\b", t):
        day_offset = (5 - now.weekday()) % 7  # Saturday
    elif re.search(r"\b(today|tonight|now|right now|this (morning|afternoon|evening))\b", t):
        day_offset = 0

    minute = None
    # "8pm" / "8:30 p.m."  ->  "at 8" / "after 9:30"  ->  "20:00"
    for pattern in (
        r"\b(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?)",
        r"\b(?:after|around|at|by|from|before|about)\s+(\d{1,2}(?::\d{2})?)\b",
        r"\b(\d{1,2}:\d{2})\b",
    ):
        m = re.search(pattern, t)
        if m:
            minute = _clock(m.group(1))
            if minute is not None:
                break
    if minute is None:
        if re.search(r"\b(right )?now\b", t):
            minute = now.hour * 60 + now.minute
        else:
            for word in sorted(PART_OF_DAY, key=len, reverse=True):
                if re.search(rf"\b{word}\b", t):
                    minute = PART_OF_DAY[word]
                    break

    if day_offset is None and minute is None:
        return None
    if day_offset is None:
        # A time with no day: today, unless that time has already passed.
        day_offset = 0 if minute >= now.hour * 60 + now.minute - 30 else 1

    day_index = (now.weekday() + day_offset) % 7
    day = DAYS[day_index]
    label = day[:3].title()
    if day_offset == 0:
        label = "tonight" if minute is not None and minute >= 17 * 60 else "today"
    elif day_offset == 1:
        label = "tomorrow"
    if minute is not None:
        label = f"{label} at {_fmt_minute(minute)}"
    return Target(day=day, minute=minute, label=label)


_RANGE = re.compile(
    r"(\d{1,2}(?::\d{2})?)\s*([AP]M)?\s*[–—-]\s*(\d{1,2}(?::\d{2})?)\s*([AP]M)?", re.IGNORECASE
)


def _minutes(clock, ampm):
    h, _, mm = clock.partition(":")
    h, mm = int(h), int(mm or 0)
    ampm = (ampm or "").upper()
    if ampm == "PM" and h < 12:
        h += 12
    if ampm == "AM" and h == 12:
        h = 0
    return h * 60 + mm


def day_intervals(text):
    """
    One day's hours -> list of (open, close) in minutes after midnight.
    Close may exceed 1440 for places open past midnight. None = can't read it.
    Examples: "6:30 AM–5 PM", "12–2:45 PM, 4–10 PM", "8AM–5PM", "Open 24 hours", "Closed".
    """
    if text is None:
        return None
    t = str(text).replace(" ", " ").replace(" ", " ").strip()
    low = t.lower()
    if not t:
        return None
    if "closed" in low:
        return []
    if "24 hours" in low:
        return [(0, 24 * 60)]
    out = []
    for m in _RANGE.finditer(t):
        a, a_ap, b, b_ap = m.groups()
        if not b_ap:
            continue
        # "12–2:45 PM": the start borrows the end's AM/PM, unless that would
        # make it later than the end (then it's the other half of the day).
        if not a_ap:
            start = _minutes(a, b_ap)
            end = _minutes(b, b_ap)
            if start > end:
                start = _minutes(a, "AM" if b_ap.upper() == "PM" else "PM")
        else:
            start = _minutes(a, a_ap)
            end = _minutes(b, b_ap)
        if end <= start:
            end += 24 * 60  # closes after midnight
        out.append((start, end))
    return out or None


def open_at(operating_hours, target):
    """True / False if the hours say; None if there are no readable hours."""
    if not operating_hours or not target:
        return None
    hours = {str(k).lower(): v for k, v in operating_hours.items()}
    today = day_intervals(hours.get(target.day))
    prev_day = DAYS[(DAYS.index(target.day) - 1) % 7]
    yesterday = day_intervals(hours.get(prev_day)) or []
    if today is None:
        return None
    if target.minute is None:
        return bool(today)
    m = target.minute
    if any(start <= m < end for start, end in today):
        return True
    # Still open from the night before (e.g. Fri 5 PM–2 AM covers Sat 1 AM).
    return any(end > 24 * 60 and m < end - 24 * 60 for _, end in yesterday)


def hours_text(operating_hours, day):
    if not operating_hours:
        return None
    hours = {str(k).lower(): v for k, v in operating_hours.items()}
    value = hours.get(day)
    return " ".join(str(value).replace(" ", " ").split()) if value else None


def hours_note(place, target, now):
    """A short, honest line about hours for the place card."""
    oh = place.get("operating_hours")
    day = target.day if target else DAYS[now.weekday()]
    posted = hours_text(oh, day)
    day_label = day[:3].title()
    if not oh or not posted:
        if not target and place.get("open_state"):
            return " ".join(str(place["open_state"]).split())
        return "Hours not listed. Check before you go"
    status = open_at(oh, target) if target else None
    if target and status is True:
        return f"Open {target.label} · {day_label} {posted}"
    if target and status is False:
        if day_intervals(posted) == []:
            return f"Closed {target.label} (closed all day {day.title()})"
        return f"Closed {target.label} · {day_label} {posted}"
    return f"{day_label}: {posted}"


def annotate(places, when_text, tz_name=None, now=None):
    """
    Add `open_at_requested_time` (True/False/None) and `hours_note` to each
    place, and return (places, target). Doesn't drop anything.
    """
    now = now or local_now(tz_name)
    target = parse_when(when_text, now)
    out = []
    for p in places:
        q = dict(p)
        q["open_at_requested_time"] = open_at(p.get("operating_hours"), target) if target else None
        q["hours_note"] = hours_note(p, target, now)
        out.append(q)
    return out, target


def prefer_open(places):
    """Drop places known to be closed at the requested time, unless that leaves none."""
    keep = [p for p in places if p.get("open_at_requested_time") is not False]
    return keep or places
