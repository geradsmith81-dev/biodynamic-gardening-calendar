"""preparations.py - timing of the biodynamic preparations BD 500-508.

The rules are in preparations.csv (one row per task, editable in Excel):
  months_north  months of the task in the northern hemisphere (shifted by six months in the southern)
  moon          ascending / descending / any
  day_types     Root, Leaf, Flower, Fruit, "crop" (= the day type of the plant group chosen in the settings) or any
  time_of_day   afternoon (3 h before sunset to sunset), early_morning (30 min before sunrise to 3 h after),
                morning (1 h after sunrise, when the dew has dried, to midday), day (sunrise to sunset)
  phase         before_full = the four days leading up to Full Moon (BD 508), else empty
  ignore_avoid  unfavourable kinds that do NOT count against this task (e.g. Perigee for BD 508)
Seasons come from Steiner's Agriculture Course (GA 327); Moon, day-type and time-of-day rules come from later
practice and are labelled as such in the 'practice' and 'source' columns.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import numpy as np
import pandas as pd
from skyfield.api import wgs84
from skyfield.almanac import find_risings, find_settings

import biodyn_engine as be

STEP_MIN = 10
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TIME_LABEL = {"afternoon": "late afternoon to sunset", "early_morning": "around sunrise to mid-morning",
              "morning": "morning, after the dew has dried, to midday", "day": "daylight hours"}
FALLBACK_PLACE = (51.4769, -0.0005, "Greenwich")


def table() -> pd.DataFrame:
    return pd.read_csv(os.path.join(be.HERE, "preparations.csv"), dtype=str).fillna("")


# ------------------------------------------------------------------ place (from the time zone)
def _iso6709(s):
    """'+513030-0000731' -> (51.508, -0.125)"""
    i = max(s.rfind("+"), s.rfind("-"))
    def conv(p, deg_digits):
        sign = -1 if p[0] == "-" else 1
        p = p[1:]
        d, rest = int(p[:deg_digits]), p[deg_digits:]
        m = int(rest[:2]); sec = int(rest[2:4]) if len(rest) >= 4 else 0
        return sign * (d + m / 60 + sec / 3600)
    return conv(s[:i], 2), conv(s[i:], 3)


@lru_cache(maxsize=1)
def _zone_coords():
    out = {}
    try:
        import importlib.resources as ir
        base = ir.files("tzdata.zoneinfo")
        for name in ("zone1970.tab", "zone.tab"):
            try:
                txt = (base / name).read_text(encoding="utf-8")
            except Exception:
                continue
            for line in txt.splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                f = line.split("\t")
                if len(f) >= 3 and f[2] not in out:
                    out[f[2]] = _iso6709(f[1])
    except Exception:
        pass
    return out


def place_for_zone(tzkey: str):
    """Latitude, longitude and city of the time zone's main city (tz database), else Greenwich."""
    c = _zone_coords().get(tzkey)
    if c:
        return round(c[0], 3), round(c[1], 3), tzkey.split("/")[-1].replace("_", " ")
    return FALLBACK_PLACE


def months_for(row, south: bool):
    m = [int(x) for x in row["months_north"].split(";") if x.strip()]
    return sorted({(x - 1 + 6) % 12 + 1 for x in m}) if south else sorted(m)


def months_text(months):
    """[9, 10, 11] -> 'Sep-Nov'; [3,4,5,9,10,11] -> 'Mar-May, Sep-Nov'; all 12 -> 'any month'."""
    if len(months) == 12:
        return "any month"
    s = sorted(months); runs = []; a = b = s[0]
    for x in s[1:]:
        if x == b + 1:
            b = x
        else:
            runs.append((a, b)); a = b = x
    runs.append((a, b))
    if len(runs) > 1 and runs[0][0] == 1 and runs[-1][1] == 12:          # wrap round the year (Dec-Feb)
        runs = [(runs[-1][0], runs[0][1])] + runs[1:-1]
    return ", ".join(MONTH_ABBR[a - 1] if a == b else f"{MONTH_ABBR[a - 1]}\u2013{MONTH_ABBR[b - 1]}" for a, b in runs)


# ------------------------------------------------------------------ sun
def sun_times(start: datetime, end: datetime, lat: float, lon: float, tz):
    """{local date: (sunrise_utc, sunset_utc)} for each day. Days without a rising or setting (polar day or night)
    get 06:00 and 18:00 local clock time instead."""
    S = be.sky()
    obs = S.earth + wgs84.latlon(lat, lon)
    t0, t1 = S.ts.from_datetime(start - timedelta(days=2)), S.ts.from_datetime(end + timedelta(days=2))
    tr, yr = find_risings(obs, S.sun, t0, t1)
    ts_, ys = find_settings(obs, S.sun, t0, t1)
    rise = {t.astimezone(tz).date(): t for t, ok in zip(tr.utc_datetime(), yr) if ok}
    sset = {t.astimezone(tz).date(): t for t, ok in zip(ts_.utc_datetime(), ys) if ok}
    out = {}
    d = (start - timedelta(days=1)).astimezone(tz).date()
    last = (end + timedelta(days=1)).astimezone(tz).date()
    while d <= last:
        r = rise.get(d) or datetime(d.year, d.month, d.day, 6, tzinfo=tz).astimezone(timezone.utc)
        s = sset.get(d) or datetime(d.year, d.month, d.day, 18, tzinfo=tz).astimezone(timezone.utc)
        if s <= r:                                   # setting belongs to the next day near the poles
            s = r + timedelta(hours=12)
        out[d] = (r, s)
        d += timedelta(days=1)
    return out


# ------------------------------------------------------------------ windows
class Context:
    """Everything the task windows need for one period, computed once."""
    def __init__(self, ev, intervals, start, end, tz, lat, lon):
        self.ev, self.iv, self.start, self.end, self.tz = ev, intervals.reset_index(drop=True), start, end, tz
        n = int((end - start).total_seconds() // (STEP_MIN * 60))
        self.grid = [start + timedelta(minutes=STEP_MIN * k) for k in range(n)]
        g_ns = np.array([int(t.timestamp()) for t in self.grid], dtype=np.int64)
        self.g = g_ns
        local = [t.astimezone(tz) for t in self.grid]
        self.month = np.array([x.month for x in local])
        self.date = [x.date() for x in local]
        starts = np.array([int(pd.Timestamp(x).timestamp()) for x in self.iv.start], dtype=np.int64)
        self.idx = np.clip(np.searchsorted(starts, g_ns, side="right") - 1, 0, len(self.iv) - 1)
        self.organ = self.iv.organ.to_numpy()[self.idx]
        self.direction = self.iv.direction.to_numpy()[self.idx]
        self.name = self.iv.name.to_numpy()[self.idx]
        self.avoid = self.iv.avoid.to_numpy()[self.idx]
        self.sun = sun_times(start, end, lat, lon, tz)
        rise = np.array([int(self.sun[d][0].timestamp()) for d in self.date], dtype=np.int64)
        sset = np.array([int(self.sun[d][1].timestamp()) for d in self.date], dtype=np.int64)
        self.rise, self.sset = rise, sset
        ph = ev["phases"]
        self.full = np.array([int(t.timestamp()) for t, k in zip(ph.utc, ph.kind) if k == "Full Moon"], dtype=np.int64)
        ap = ev["apsides"]
        self.perigee = np.array([int(t.timestamp()) for t, k in zip(ap.utc, ap.kind) if k == "Perigee"], dtype=np.int64)


def task_windows(ctx: Context, row, crop_organ: str, south: bool) -> pd.DataFrame:
    g = ctx.g
    ok = np.isin(ctx.month, months_for(row, south))
    if row["moon"] in ("ascending", "descending"):
        ok &= ctx.direction == row["moon"]
    ign = [x.strip() for x in row["ignore_avoid"].split(";") if x.strip()]
    if ign:
        bad = np.array([any(r and not any(i in r for i in ign) for r in a.split("; ")) for a in ctx.avoid])
    else:
        bad = np.array([len(a) > 0 for a in ctx.avoid])
    ok &= ~bad
    rule = row["time_of_day"]
    if rule in TIME_LABEL:
        r, s = ctx.rise, ctx.sset
        if rule == "afternoon":
            a, b = s - 3 * 3600, s
        elif rule == "early_morning":
            a, b = r - 1800, r + 3 * 3600
        elif rule == "morning":
            a, b = r + 3600, r + (s - r) // 2
        else:
            a, b = r, s
        ok &= (g >= a) & (g < b)
    note = np.full(len(g), "", dtype=object)
    if row["phase"] == "before_full" and len(ctx.full):
        j = np.searchsorted(ctx.full, g)                       # next Full Moon at or after each moment
        nxt = np.where(j < len(ctx.full), ctx.full[np.minimum(j, len(ctx.full) - 1)], np.iinfo(np.int64).max)
        ok &= (nxt - g) <= 4 * 86400
        if len(ctx.perigee):
            k = np.searchsorted(ctx.perigee, nxt)
            near = np.zeros(len(g), bool)
            for kk in (k - 1, k):
                kk2 = np.clip(kk, 0, len(ctx.perigee) - 1)
                near |= np.abs(ctx.perigee[kk2] - nxt) <= 2 * 86400
            note[near & ok] = "Full Moon near perigee: especially useful"
    dt = row["day_types"]
    if dt == "any":
        best, good = ok, np.zeros(len(g), bool)
    else:
        want = [crop_organ] if dt == "crop" else [x.strip() for x in dt.split(";")]
        match = np.isin(ctx.organ, want)
        best, good = ok & match, ok & ~match
    return _runs(ctx, best, good, note)


def _runs(ctx, best, good, note):
    rating = np.where(best, 2, np.where(good, 1, 0))
    out = []
    k, n = 0, len(rating)
    step = timedelta(minutes=STEP_MIN)
    while k < n:
        if rating[k] == 0:
            k += 1
            continue
        j = k
        while j + 1 < n and rating[j + 1] == rating[k] and ctx.date[j + 1] == ctx.date[k]:
            j += 1
        names = list(dict.fromkeys(ctx.name[k:j + 1]))
        organs = list(dict.fromkeys(ctx.organ[k:j + 1]))
        dirs = list(dict.fromkeys(ctx.direction[k:j + 1]))
        notes = [x for x in dict.fromkeys(note[k:j + 1]) if x]
        out.append(dict(start=ctx.grid[k], end=ctx.grid[j] + step, rating="Best" if rating[k] == 2 else "Good",
                        organ=", ".join(organs), constellations=", ".join(names), direction=", ".join(dirs),
                        note="; ".join(notes)))
        k = j + 1
    w = pd.DataFrame(out, columns=["start", "end", "rating", "organ", "constellations", "direction", "note"])
    if len(w):
        w["hours"] = [(b - a).total_seconds() / 3600 for a, b in zip(w.start, w.end)]
        w = w[w.hours >= 0.5].reset_index(drop=True)
    else:
        w["hours"] = []
    return w


def rule_text(row, south: bool, crop_organ: str) -> str:
    moon = {"ascending": "ascending", "descending": "descending"}.get(row["moon"], "any")
    dt = row["day_types"]
    day = "any" if dt == "any" else (f"{crop_organ} (your plant group)" if dt == "crop" else dt.replace(";", " or "))
    parts = [f"**Season:** {months_text(months_for(row, south))}", f"**Moon:** {moon}", f"**Day type:** {day}",
             f"**Time:** {TIME_LABEL.get(row['time_of_day'], 'any time')}"]
    if row["phase"] == "before_full":
        parts.append("**Phase:** the 4 days before Full Moon")
    return " \u00b7 ".join(parts)


def periods(w: pd.DataFrame, tz) -> pd.DataFrame:
    """Join windows on consecutive days (same rating) into periods, for a short list."""
    cols = ["rating", "first", "last", "days", "times", "constellations", "note", "n"]
    if not len(w):
        return pd.DataFrame(columns=cols)
    out = []
    for rating in ("Best", "Good"):
        sub = w[w.rating == rating]
        cur = None
        for r in sub.itertuples():
            a, b = r.start.astimezone(tz), r.end.astimezone(tz)
            if cur and (a.date() - cur["last_day"]).days <= 1:
                cur["last_day"] = a.date(); cur["last"] = b; cur["n"] += 1
                cur["names"].update(dict.fromkeys(r.constellations.split(", ")))
                if r.note:
                    cur["notes"][r.note] = None
            else:
                if cur:
                    out.append(cur)
                cur = dict(rating=rating, first=a, last=b, last_day=a.date(), n=1, times=f"{a:%H:%M}\u2013{b:%H:%M}",
                           names=dict.fromkeys(r.constellations.split(", ")), notes=dict.fromkeys([r.note] if r.note else []))
        if cur:
            out.append(cur)
    rows = [dict(rating=c["rating"], first=c["first"], last=c["last"], days=(c["last_day"] - c["first"].date()).days + 1,
                 times=c["times"], constellations=", ".join(c["names"]), note="; ".join(c["notes"]), n=c["n"]) for c in out]
    return pd.DataFrame(rows, columns=cols).sort_values("first").reset_index(drop=True)


def period_dates(p) -> str:
    a, b = p["first"], p["last"]
    if a.date() == b.date():
        return f"{a:%a %d %b %Y}"
    if a.year == b.year:
        return f"{a:%a %d %b} \u2013 {b:%a %d %b %Y}"
    return f"{a:%a %d %b %Y} \u2013 {b:%a %d %b %Y}"


def to_ics(items, prep_label: str) -> str:
    """items: list of (task, windows DataFrame). Best windows only."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Biodynamic Gardening Calendar//EN", "CALSCALE:GREGORIAN"]
    k = 0
    for task, w in items:
        for r in w[w.rating == "Best"].itertuples():
            k += 1
            desc = f"Moon in {r.constellations} (IAU)\\, {r.direction} Moon." + (f" {r.note}." if r.note else "")
            lines += ["BEGIN:VEVENT", f"UID:prep-{r.start.strftime('%Y%m%dT%H%M%S')}-{k}@houseplant-calendar",
                      f"DTSTAMP:{stamp}", f"DTSTART:{r.start.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}",
                      f"DTEND:{r.end.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}",
                      f"SUMMARY:{prep_label}: {task}".replace(",", "\\,"), f"DESCRIPTION:{desc}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
