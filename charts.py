"""charts.py - figures for the Biodynamic Gardening Calendar (matplotlib)."""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
import numpy as np
from matplotlib.colors import to_rgb
from matplotlib.patches import Patch

import biodyn_engine as be

PHASE_MARK = {"New Moon": "\u25cf", "First Quarter": "\u25d1", "Full Moon": "\u25cb", "Last Quarter": "\u25d0"}


def _split_local(start, end, tz):
    """Yield (day, h0, h1) pieces of a UTC interval in local time."""
    start = start.to_pydatetime() if hasattr(start, "to_pydatetime") else start
    end = end.to_pydatetime() if hasattr(end, "to_pydatetime") else end
    a, b = start.astimezone(tz), end.astimezone(tz)
    while a < b:
        nxt = (a + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        piece_end = min(b, nxt)
        h0 = a.hour + a.minute / 60 + a.second / 3600
        h1 = 24.0 if piece_end == nxt else piece_end.hour + piece_end.minute / 60 + piece_end.second / 3600
        yield a.date(), h0, h1
        a = piece_end


def month_timeline(rated, events, year, month, tz, title):
    """Rows = days of the month, x = local clock hours. Colour = day type,
    grey hatch = unfavourable, thick outline = Best window for the selection."""
    ndays = calendar.monthrange(year, month)[1]
    fig = Figure(figsize=(11, 0.32 * ndays + 1.9)); ax = fig.subplots()
    days = {datetime(year, month, d).date(): d for d in range(1, ndays + 1)}
    for r in rated.itertuples():
        for day, h0, h1 in _split_local(r.start, r.end, tz):
            if day not in days:
                continue
            y = days[day]
            ax.broken_barh([(h0, h1 - h0)], (y - 0.42, 0.84), facecolors=be.ORGAN_COLOURS.get(r.organ, "#ccc"), lw=0)
            if r.avoid:
                ax.broken_barh([(h0, h1 - h0)], (y - 0.42, 0.84), facecolors=(0.25, 0.25, 0.25, 0.55),
                               hatch="////", edgecolor="white", lw=0)
            if r.rating == "Best":
                ax.broken_barh([(h0, h1 - h0)], (y - 0.46, 0.92), facecolors="none", edgecolor="black", lw=1.8)
            elif r.rating == "Good":
                ax.broken_barh([(h0, h1 - h0)], (y - 0.46, 0.92), facecolors="none", edgecolor="black", lw=0.9, ls=(0, (2, 2)))
    # direction label + phases
    for t, k in zip(events["phases"].utc, events["phases"].kind):
        lt = t.astimezone(tz)
        if lt.date() in days:
            ax.text(lt.hour + lt.minute / 60, days[lt.date()], PHASE_MARK[k], ha="center", va="center",
                    fontsize=11, color="black")
    for t, k in zip(events["turns"].utc, events["turns"].kind):
        lt = t.astimezone(tz)
        if lt.date() in days:
            ax.text(24.3, days[lt.date()], "\u25bc desc." if "highest" in k else "\u25b2 asc.", va="center", fontsize=8)
    ax.set_ylim(ndays + 0.7, 0.3)
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel(f"Local clock time ({tz.key})")
    ax.set_yticks(range(1, ndays + 1))
    ax.set_yticklabels([f"{datetime(year, month, d):%a} {d}" for d in range(1, ndays + 1)], fontsize=8)
    ax.grid(axis="x", color="white", lw=0.6)
    ax.set_title(f"{calendar.month_name[month]} {year} - {title}", loc="left", fontsize=12)
    handles = [Patch(color=be.ORGAN_COLOURS[o], label=f"{o} day") for o in be.ORGANS]
    handles += [Patch(color=be.ORGAN_COLOURS["Neutral"], label="Neutral (Ophiuchus / outside zodiac)"),
                Patch(facecolor=(0.25, 0.25, 0.25, 0.55), hatch="////", edgecolor="white", label="Unfavourable"),
                Patch(facecolor="none", edgecolor="black", lw=1.8, label="Best for your choice"),
                Patch(facecolor="none", edgecolor="black", lw=0.9, ls=(0, (2, 2)), label="Good")]
    H = 0.32 * ndays + 1.9
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=8, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.text(0.5, 0.95 / H, "\u25cf new  \u25d1 first quarter  \u25cb full  \u25d0 last quarter      "
             "\u25b2 Moon starts ascending   \u25bc Moon starts descending", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 1.15 / H, 1, 1))
    return fig


def _circmean(deg):
    r = np.radians(deg)
    return np.degrees(np.arctan2(np.sin(r).mean(), np.cos(r).mean())) % 360


def sky_band(when, tz, track=None, title=None):
    """IAU constellations along the ecliptic band (true, unequal widths),
    coloured by biodynamic day type, with the Moon's path and the planets."""
    S = be.sky()
    lons, lats, grid = be.constellation_band(when, lon_step=0.25, lat_step=0.2, lat_lim=7.5)
    rgb = np.ones(grid.shape + (3,))
    for ab in np.unique(grid):
        organ = S.organ_of.get(ab)
        if organ is None:
            col = (0.93, 0.93, 0.93)
        elif organ == "Neutral":
            col = to_rgb(be.ORGAN_COLOURS["Neutral"])
        else:
            col = to_rgb(be.ORGAN_COLOURS[organ])
            col = tuple(0.55 * np.array(col) + 0.45)   # lighten
        rgb[grid == ab] = col
    edge = np.zeros(grid.shape, bool)
    edge[:, 1:] |= grid[:, 1:] != grid[:, :-1]
    edge[1:, :] |= grid[1:, :] != grid[:-1, :]
    rgb[edge] = (0.2, 0.2, 0.2)

    fig = Figure(figsize=(13, 3.6)); ax = fig.subplots()
    ax.imshow(rgb, origin="lower", aspect="auto", extent=[0, 360, lats[0], lats[-1]], interpolation="nearest")
    ax.axhline(0, color="black", lw=0.6, ls=":")
    for ab in np.unique(grid):
        sel = grid == ab
        if sel.sum() < (40 if ab in S.organ_of else 150):
            continue
        lo = _circmean(np.broadcast_to(lons, grid.shape)[sel])
        la = np.broadcast_to(lats[:, None], grid.shape)[sel].mean()
        if ab in S.organ_of:
            la = 5.8 if ab != "Oph" else 6.3
        ax.text(lo, la, S.names[ab], ha="center", va="center", fontsize=8,
                style="normal" if ab in S.organ_of else "italic", color="#222")
    if track is not None and len(track):
        lo = track.lon.to_numpy(); la = track.lat.to_numpy()
        brk = np.where(np.abs(np.diff(lo)) > 180)[0] + 1
        for seg_lo, seg_la in zip(np.split(lo, brk), np.split(la, brk)):
            ax.plot(seg_lo, seg_la, color="#333", lw=1)
        for t, x, y in zip(track.utc, lo, la):
            lt = t.astimezone(tz)
            if lt.hour == 0 and lt.minute == 0:
                ax.plot(x, y, "o", ms=3, color="#333")
                ax.text(x, y - 0.75, str(lt.day), fontsize=7, ha="center", va="top")
    pos = be.sky_positions(when)
    sym = {"Sun": ("*", "#f2a900", 16), "Moon": ("o", "white", 10)}
    for r in pos.itertuples():
        m, c, s = sym.get(r.body, ("D", "#5b3f8c", 6))
        ax.plot(r.ecl_lon_deg, r.ecl_lat_deg, m, color=c, ms=s, mec="black", mew=0.8, zorder=5)
        ax.annotate(r.body, (r.ecl_lon_deg, r.ecl_lat_deg), xytext=(0, 9), textcoords="offset points",
                    ha="center", fontsize=8, fontweight="bold", zorder=6)
    ax.set_xlim(0, 360)
    ax.set_xticks(range(0, 361, 30))
    ax.set_xlabel("Ecliptic longitude of date (deg) - boundaries are the IAU 1930 constellation borders, not 30\u00b0 signs")
    ax.set_ylabel("Ecliptic latitude (deg)")
    lt = when.astimezone(tz)
    ax.set_title(title or f"Sidereal sky band, IAU constellations - planets at {lt:%d %b %Y %H:%M} ({tz.key})",
                 loc="left", fontsize=11)
    handles = [Patch(color=tuple(0.55 * np.array(to_rgb(be.ORGAN_COLOURS[o])) + 0.45), label=f"{o}") for o in be.ORGANS]
    handles += [Patch(color=be.ORGAN_COLOURS["Neutral"], label="Ophiuchus"), Patch(color=(0.93, 0.93, 0.93), label="Non-zodiacal")]
    ax.legend(handles=handles, loc="lower left", ncol=6, fontsize=7, framealpha=0.9)
    fig.tight_layout()
    return fig


# =========================================================================== phone versions
# (separate functions, so the computer figures above are drawn exactly as before)

def _hhmm(h):
    m = int(round(h * 60))
    return f"{m // 60:02d}:{m % 60:02d}"


def day_summary(rated, events, year, month, tz):
    """One entry per day of the month for the phone list: the day types with their clock times, the Best/Good
    stretches for the current choice, the unfavourable stretches, Moon phases and ascending/descending turns."""
    ndays = calendar.monthrange(year, month)[1]
    out = {datetime(year, month, d).date(): dict(types=[], rated=[], avoid=[], marks=[]) for d in range(1, ndays + 1)}

    def add(lst, key, h0, h1):
        if lst and lst[-1][0] == key and abs(lst[-1][2] - h0) < 1e-6:
            lst[-1] = (key, lst[-1][1], h1)
        else:
            lst.append((key, h0, h1))

    for r in rated.itertuples():
        for day, h0, h1 in _split_local(r.start, r.end, tz):
            if day not in out:
                continue
            e = out[day]
            add(e["types"], r.organ, h0, h1)
            if r.rating in ("Best", "Good"):
                add(e["rated"], r.rating, h0, h1)
            if r.avoid:
                add(e["avoid"], "avoid", h0, h1)
    for t, k in zip(events["phases"].utc, events["phases"].kind):
        lt = t.astimezone(tz)
        if lt.date() in out:
            out[lt.date()]["marks"].append(f"{PHASE_MARK[k]} {k} {lt:%H:%M}")
    for t, k in zip(events["turns"].utc, events["turns"].kind):
        lt = t.astimezone(tz)
        if lt.date() in out:
            out[lt.date()]["marks"].append(("\u25bc descending" if "highest" in k else "\u25b2 ascending") + f" from {lt:%H:%M}")
    rows = []
    for day, e in out.items():
        for k in ("types", "rated", "avoid"):
            e[k] = [(key, _hhmm(a), _hhmm(b)) for key, a, b in e[k] if b - a > 1 / 120]
        rows.append(dict(day=day, **e))
    return rows


def month_timeline_compact(rated, events, year, month, tz):
    """The month chart at phone width: larger text, ticks every 6 hours, legend in two columns."""
    ndays = calendar.monthrange(year, month)[1]
    H = 0.36 * ndays + 2.6
    fig = Figure(figsize=(6.2, H)); ax = fig.subplots()
    days = {datetime(year, month, d).date(): d for d in range(1, ndays + 1)}
    for r in rated.itertuples():
        for day, h0, h1 in _split_local(r.start, r.end, tz):
            if day not in days:
                continue
            y = days[day]
            ax.broken_barh([(h0, h1 - h0)], (y - 0.42, 0.84), facecolors=be.ORGAN_COLOURS.get(r.organ, "#ccc"), lw=0)
            if r.avoid:
                ax.broken_barh([(h0, h1 - h0)], (y - 0.42, 0.84), facecolors=(0.25, 0.25, 0.25, 0.55),
                               hatch="////", edgecolor="white", lw=0)
            if r.rating == "Best":
                ax.broken_barh([(h0, h1 - h0)], (y - 0.46, 0.92), facecolors="none", edgecolor="black", lw=2.0)
            elif r.rating == "Good":
                ax.broken_barh([(h0, h1 - h0)], (y - 0.46, 0.92), facecolors="none", edgecolor="black", lw=1.0, ls=(0, (2, 2)))
    for t, k in zip(events["phases"].utc, events["phases"].kind):
        lt = t.astimezone(tz)
        if lt.date() in days:
            ax.text(lt.hour + lt.minute / 60, days[lt.date()], PHASE_MARK[k], ha="center", va="center", fontsize=13)
    for t, k in zip(events["turns"].utc, events["turns"].kind):
        lt = t.astimezone(tz)
        if lt.date() in days:
            ax.text(24.4, days[lt.date()], "\u25bc" if "highest" in k else "\u25b2", va="center", fontsize=11)
    ax.set_ylim(ndays + 0.7, 0.3)
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 6))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 6)], fontsize=10)
    ax.set_xlabel("Local clock time", fontsize=10)
    ax.set_yticks(range(1, ndays + 1))
    ax.set_yticklabels([f"{datetime(year, month, d):%a} {d}" for d in range(1, ndays + 1)], fontsize=9.5)
    ax.grid(axis="x", color="white", lw=0.8)
    ax.set_title(f"{calendar.month_name[month]} {year}", loc="left", fontsize=14)
    handles = [Patch(color=be.ORGAN_COLOURS[o], label=f"{o} day") for o in be.ORGANS]
    handles += [Patch(color=be.ORGAN_COLOURS["Neutral"], label="Neutral"),
                Patch(facecolor=(0.25, 0.25, 0.25, 0.55), hatch="////", edgecolor="white", label="Unfavourable"),
                Patch(facecolor="none", edgecolor="black", lw=2.0, label="Best for your choice"),
                Patch(facecolor="none", edgecolor="black", lw=1.0, ls=(0, (2, 2)), label="Good")]
    fig.legend(handles=handles, loc="lower center", ncol=2, fontsize=10, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.text(0.5, 1.33 / H, "\u25cf new  \u25d1 first qtr  \u25cb full  \u25d0 last qtr\n"
             "\u25b2 Moon starts ascending   \u25bc starts descending", ha="center", va="center", fontsize=9.5)
    fig.tight_layout(rect=(0, 1.58 / H, 1, 1))
    return fig


def sky_band_compact(when, tz, track=None):
    """The sky band at phone width: the 360 degrees split into two stacked halves, larger labels."""
    S = be.sky()
    lons, lats, grid = be.constellation_band(when, lon_step=0.25, lat_step=0.2, lat_lim=7.5)
    rgb = np.ones(grid.shape + (3,))
    for ab in np.unique(grid):
        organ = S.organ_of.get(ab)
        if organ is None:
            col = (0.93, 0.93, 0.93)
        elif organ == "Neutral":
            col = to_rgb(be.ORGAN_COLOURS["Neutral"])
        else:
            col = tuple(0.55 * np.array(to_rgb(be.ORGAN_COLOURS[organ])) + 0.45)
        rgb[grid == ab] = col
    edge = np.zeros(grid.shape, bool)
    edge[:, 1:] |= grid[:, 1:] != grid[:, :-1]
    edge[1:, :] |= grid[1:, :] != grid[:-1, :]
    rgb[edge] = (0.2, 0.2, 0.2)
    pos = be.sky_positions(when)
    sym = {"Sun": ("*", "#f2a900", 17), "Moon": ("o", "white", 11)}
    fig = Figure(figsize=(6.4, 7.6))
    axes = fig.subplots(2, 1)
    for ax, (x0, x1) in zip(axes, ((0, 180), (180, 360))):
        ax.imshow(rgb, origin="lower", aspect="auto", extent=[0, 360, lats[0], lats[-1]], interpolation="nearest")
        ax.axhline(0, color="black", lw=0.6, ls=":")
        labels = []
        for ab in np.unique(grid):
            sel = grid == ab
            if sel.sum() < (40 if ab in S.organ_of else 150):
                continue
            lo = _circmean(np.broadcast_to(lons, grid.shape)[sel])
            if not (x0 + 3 <= lo <= x1 - 3):
                continue
            labels.append((lo, ab, np.broadcast_to(lats[:, None], grid.shape)[sel].mean()))
        prev_lo = -99.0
        for lo, ab, la in sorted(labels):
            if ab in S.organ_of:
                la = 6.5 if ab == "Oph" else 5.8
                if ab != "Oph" and lo - prev_lo < 24:       # neighbours too close: drop this name lower
                    la = 4.6
                if la != 4.6:
                    prev_lo = lo
                else:
                    prev_lo = -99.0
            ax.text(lo, la, S.names[ab], ha="center", va="center", fontsize=9.5,
                    style="normal" if ab in S.organ_of else "italic", color="#222")
        if track is not None and len(track):
            lo = track.lon.to_numpy(); la = track.lat.to_numpy()
            brk = np.where(np.abs(np.diff(lo)) > 180)[0] + 1
            for seg_lo, seg_la in zip(np.split(lo, brk), np.split(la, brk)):
                ax.plot(seg_lo, seg_la, color="#333", lw=1.1)
            for t, x, y in zip(track.utc, lo, la):
                lt = t.astimezone(tz)
                if lt.hour == 0 and lt.minute == 0 and x0 <= x <= x1:
                    ax.plot(x, y, "o", ms=3.5, color="#333")
                    ax.text(x, y - 0.8, str(lt.day), fontsize=8.5, ha="center", va="top")
        for r in pos.itertuples():
            if not (x0 <= r.ecl_lon_deg < x1):
                continue
            m, c, s = sym.get(r.body, ("D", "#5b3f8c", 7))
            ax.plot(r.ecl_lon_deg, r.ecl_lat_deg, m, color=c, ms=s, mec="black", mew=0.8, zorder=5)
            ax.annotate(r.body, (r.ecl_lon_deg, r.ecl_lat_deg), xytext=(0, 10), textcoords="offset points",
                        ha="center", fontsize=10, fontweight="bold", zorder=6)
        ax.set_xlim(x0, x1)
        ax.set_xticks(range(x0, x1 + 1, 30))
        ax.tick_params(labelsize=9.5)
        ax.set_ylabel("Latitude \u00b0", fontsize=10)
    axes[1].set_xlabel("Ecliptic longitude of date (\u00b0), IAU 1930 boundaries", fontsize=10)
    lt = when.astimezone(tz)
    axes[0].set_title(f"Sky band, IAU constellations\nplanets at {lt:%d %b %Y %H:%M}", loc="left", fontsize=12)
    handles = [Patch(color=tuple(0.55 * np.array(to_rgb(be.ORGAN_COLOURS[o])) + 0.45), label=o) for o in be.ORGANS]
    handles += [Patch(color=be.ORGAN_COLOURS["Neutral"], label="Ophiuchus"), Patch(color=(0.93, 0.93, 0.93), label="Non-zodiacal")]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=10, frameon=False, bbox_to_anchor=(0.5, 0.012))
    fig.tight_layout(rect=(0, 0.11, 1, 1))
    return fig
