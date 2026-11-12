"""astrolabe.py - the sky for one moment and place, drawn like an astrolabe (after the Sidereal Oracle's wheel).

* Outer limb: ecliptic longitude of date, a tick every 5 degrees.
* Ring: the 13 IAU constellations on the ecliptic at their true widths, tinted by biodynamic day type.
* Plate: sky above the horizon, earth below. The Ascendant (rising point of the ecliptic, east) is at 9 o'clock,
  as in the Oracle; the MC (where the ecliptic crosses the meridian) is marked by a line.
* Bodies: filled = above the local horizon, open = below. A brass rule points from the centre to the Moon.
* Centre: the Moon's phase as seen from the chosen hemisphere, the day type and the Moon's direction.
Positions are geocentric apparent (as in the rest of the app); above/below the horizon is topocentric.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Circle, Wedge, Polygon
from skyfield.api import wgs84
from skyfield.framelib import ecliptic_frame

import biodyn_engine as be

GLYPH = {"Sun": "\u2609", "Moon": "\u263d", "Mercury": "\u263f", "Venus": "\u2640", "Mars": "\u2642",
         "Jupiter": "\u2643", "Saturn": "\u2644", "Uranus": "\u2645", "Neptune": "\u2646", "Pluto": "\u2647"}
DIR_TEXT = {"ascending": "\u25b2 ascending Moon", "descending": "\u25bc descending Moon"}
C = dict(bg="#f7f5ef", limb="#1f3a28", limb_text="#f4e9c8", sky="#1d3b4a", earth="#3a5a2e", edge="#16281c",
         cream="#f4e9c8", brass="#d9a441", ink="#22301f", star="#f4e9c8")


def _tint(hex_colour, w):
    h = hex_colour.lstrip("#")
    c = np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)]) / 255
    return tuple(c + (1 - c) * w)


def band_colour(abbr):
    S = be.sky()
    organ = S.organ_of.get(abbr)
    if organ is None:
        return (0.88, 0.88, 0.86)
    if organ == "Neutral":
        return _tint(be.ORGAN_COLOURS["Neutral"], 0.25)
    return _tint(be.ORGAN_COLOURS[organ], 0.35)


# ------------------------------------------------------------------ astronomy
def _ecliptic_vectors_of_date(t, lons_deg):
    """Unit vectors (true equator and equinox of date) of ecliptic points with latitude 0."""
    lon = np.radians(lons_deg)
    v = np.array([np.cos(lon), np.sin(lon), np.zeros_like(lon)])
    icrs = ecliptic_frame.rotation_at(t).T @ v           # ecliptic of date -> ICRS
    return t.M @ icrs                                    # ICRS -> true equator of date


def angles(t, lat, lon):
    """(Ascendant, MC) ecliptic longitudes of date in degrees, found where the ecliptic meets the horizon
    (rising side, hour angle < 0) and the upper meridian. Works at all latitudes where the ecliptic rises."""
    lons = np.arange(0, 360, 0.02)
    x, y, z = _ecliptic_vectors_of_date(t, lons)
    ra = np.degrees(np.arctan2(y, x))
    dec = np.degrees(np.arcsin(np.clip(z, -1, 1)))
    lst = (t.gast * 15 + lon) % 360
    H = (lst - ra + 180) % 360 - 180                     # hour angle, -180..180
    phi, d, h = np.radians(lat), np.radians(dec), np.radians(H)
    alt = np.degrees(np.arcsin(np.sin(phi) * np.sin(d) + np.cos(phi) * np.cos(d) * np.cos(h)))

    def crossing(f, cond):
        s = np.sign(f)
        idx = np.where((s != np.roll(s, -1)) & cond)[0]
        out = []
        for i in idx:
            j = (i + 1) % len(lons)
            if abs(f[i] - f[j]) > 90:                     # wrap of the hour angle, not a real crossing
                continue
            frac = f[i] / (f[i] - f[j]) if f[i] != f[j] else 0
            out.append((lons[i] + frac * 0.02) % 360)
        return out
    asc = crossing(alt, H < 0)
    mc = crossing(H, np.abs(H) < 90)
    return (asc[0] if asc else float("nan")), (mc[0] if mc else float("nan"))


def ecliptic_bands(when, step=0.05):
    """[(start_lon, end_lon, abbr), ...] of the IAU constellations along the ecliptic of date."""
    S = be.sky()
    t = S.ts.from_datetime(when)
    lons = np.arange(0, 360, step) + step / 2
    ab = np.asarray(S.constellation_at(be.ecliptic_point(lons, np.zeros_like(lons), t)))
    starts = [0] + [i for i in range(1, len(ab)) if ab[i] != ab[i - 1]]
    out = [(lons[s] - step / 2, (lons[starts[k + 1]] - step / 2) if k + 1 < len(starts) else 360.0, ab[s])
           for k, s in enumerate(starts)]
    if len(out) > 1 and out[0][2] == out[-1][2]:          # the band that wraps through 0 degrees
        out = [(out[-1][0], out[0][1] + 360, out[0][2])] + out[1:-1]
    return out


def sky_state(when, lat, lon):
    """Everything the astrolabe needs for one moment and place."""
    S = be.sky()
    t = S.ts.from_datetime(when)
    pos = be.sky_positions(when)
    obs = S.earth + wgs84.latlon(lat, lon)
    alts = {}
    for label, key in be.BODIES:
        alt, _, _ = obs.at(t).observe(S.eph[key]).apparent().altaz()
        alts[label] = alt.degrees
    pos["alt"] = [alts[b] for b in pos.body]
    asc, mc = angles(t, lat, lon)
    sun = pos[pos.body == "Sun"].iloc[0]; moon = pos[pos.body == "Moon"].iloc[0]
    elong = (moon.ecl_lon_deg - sun.ecl_lon_deg) % 360
    dec_now = moon.dec_deg
    later = be.sky_positions(when + timedelta(hours=2))
    dec_later = later[later.body == "Moon"].iloc[0].dec_deg
    return dict(when=when, lat=lat, lon=lon, pos=pos, asc=asc, mc=mc, elong=elong,
                illum=(1 - np.cos(np.radians(elong))) / 2,
                direction="ascending" if dec_later > dec_now else "descending",
                moon_abbr=moon.iau_abbr, bands=ecliptic_bands(when))


def phase_name(elong):
    """Principal phases within 10 degrees of the exact angle; crescent / gibbous in between."""
    e = elong % 360
    for centre, name in ((0, "New Moon"), (90, "First quarter"), (180, "Full Moon"), (270, "Last quarter"), (360, "New Moon")):
        if abs(e - centre) <= 10:
            return name
    if e < 90:
        return "Waxing crescent"
    if e < 180:
        return "Waxing gibbous"
    return "Waning gibbous" if e < 270 else "Waning crescent"


# ------------------------------------------------------------------ drawing
def draw(state, tz, place_name="", compact=False, organ_of=None, title=None):
    S = be.sky()
    organ_of = organ_of or S.organ_of
    asc = state["asc"] if np.isfinite(state["asc"]) else 0.0
    fs = 1.25 if compact else 1.0
    fig = Figure(figsize=(6.4, 6.9) if compact else (6.6, 7.0), facecolor=C["bg"])
    ax = fig.add_axes([0.02, 0.02, 0.96, 0.855 if compact else 0.90]); ax.set_xlim(-1.24, 1.24); ax.set_ylim(-1.24, 1.24)
    ax.set_aspect("equal"); ax.axis("off")
    th = lambda lam: np.radians(180 + (lam - asc))        # ecliptic longitude -> angle on the page
    xy = lambda lam, r: (r * np.cos(th(lam)), r * np.sin(th(lam)))

    # limb with degree scale
    ax.add_patch(Circle((0, 0), 1.17, color=C["limb"], zorder=1))
    for d in range(0, 360, 5):
        r0 = 1.06 if d % 30 else 1.04
        (x0, y0), (x1, y1) = xy(d, r0), xy(d, 1.10 if d % 30 else 1.12)
        ax.plot([x0, x1], [y0, y1], color=C["limb_text"], lw=0.8 if d % 30 else 1.3, zorder=2)
    for d in range(0, 360, 30):
        x, y = xy(d, 1.145)
        ang = np.degrees(th(d)) - 90
        ang = ang + 180 if 90 < (ang % 360) < 270 else ang
        ax.text(x, y, f"{d}\u00b0", color=C["limb_text"], fontsize=6.5 * fs, ha="center", va="center", rotation=ang, zorder=3)
    # constellation ring
    for a, b, ab in state["bands"]:
        t0, t1 = sorted((np.degrees(th(a)), np.degrees(th(b))))
        ax.add_patch(Wedge((0, 0), 1.04, 180 + (a - asc), 180 + (b - asc), width=0.21,
                           facecolor=band_colour(ab), edgecolor=C["edge"], lw=0.8, zorder=2))
        width = b - a
        name = S.names.get(ab, ab)
        if width < 3:
            continue
        label = name if width >= 14 * fs else ab
        mid = (a + b) / 2
        x, y = xy(mid, 0.935)
        ang = np.degrees(th(mid)) - 90
        ang = ang + 180 if 90 < (ang % 360) < 270 else ang
        ax.text(x, y, label, fontsize=(7.2 if width >= 14 * fs else 6.4) * fs, ha="center", va="center",
                rotation=ang, color=C["ink"], style="normal" if ab in organ_of else "italic", zorder=4)
    # plate: sky above the horizon, earth below
    ax.add_patch(Wedge((0, 0), 0.83, 0, 180, facecolor=C["sky"], edgecolor="none", zorder=1.5))
    ax.add_patch(Wedge((0, 0), 0.83, 180, 360, facecolor=C["earth"], edgecolor="none", zorder=1.5))
    rng = np.random.default_rng(7)
    for _ in range(38):
        r, a = 0.25 + 0.55 * np.sqrt(rng.random()), np.pi * (0.04 + 0.92 * rng.random())
        ax.plot(r * np.cos(a), r * np.sin(a), ".", ms=rng.uniform(1.0, 2.6), color=C["star"], alpha=0.7, zorder=1.6)
    for r in (0.30, 0.55):
        ax.add_patch(Circle((0, 0), r, fill=False, ec=C["cream"], lw=0.5, alpha=0.25, zorder=1.7))
    ax.plot([-0.83, 0.83], [0, 0], color=C["cream"], lw=1.4, zorder=3)
    ax.text(-0.80, 0.035, "East \u00b7 Ascendant", color=C["cream"], fontsize=7 * fs, ha="left", va="bottom", zorder=5)
    ax.text(0.80, 0.035, "West", color=C["cream"], fontsize=7 * fs, ha="right", va="bottom", zorder=5)
    ax.text(0, -0.79, "below the horizon", color=C["cream"], alpha=0.8, fontsize=6.5 * fs, ha="center", zorder=5)
    if np.isfinite(state["mc"]):
        (x0, y0), (x1, y1) = xy(state["mc"], 0.20), xy(state["mc"], 0.83)
        ax.plot([x0, x1], [y0, y1], color=C["cream"], lw=1.0, ls=(0, (4, 3)), zorder=3)
        x, y = xy(state["mc"], 0.25)
        ax.text(x, y, "MC", color=C["cream"], fontsize=7 * fs, ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.15", fc=C["sky"], ec="none"), zorder=5)
    # the rule (alidade) pointing at the Moon
    pos = state["pos"]; moon = pos[pos.body == "Moon"].iloc[0]
    (x0, y0), (x1, y1) = xy(moon.ecl_lon_deg, 0.19), xy(moon.ecl_lon_deg, 1.04)
    ax.plot([x0, x1], [y0, y1], color=C["brass"], lw=2.2, solid_capstyle="round", zorder=4.5)
    # bodies, staggered inwards when close together
    placed = []
    order = pos.assign(k=pos.body.map({"Moon": 0, "Sun": 1}).fillna(2)).sort_values(["k", "ecl_lon_deg"])
    for r in order.itertuples():
        lam = r.ecl_lon_deg
        rad = 0.71
        for _ in range(4):
            if all(abs(((lam - l2 + 180) % 360) - 180) > 9 or abs(rad - r2) > 0.09 for l2, r2 in placed):
                break
            rad -= 0.12
        placed.append((lam, rad))
        x, y = xy(lam, rad)
        up = r.alt > 0
        big = r.body in ("Sun", "Moon")
        face = {"Sun": "#f2c14e", "Moon": C["cream"]}.get(r.body, C["cream"])
        ax.add_patch(Circle((x, y), 0.062 if big else 0.048, facecolor=face if up else C["edge"],
                            edgecolor=face, lw=1.6, zorder=6))
        ax.text(x, y - 0.004, GLYPH[r.body], ha="center", va="center", fontsize=(11 if big else 8.5) * fs,
                color=C["ink"] if up else face, zorder=7, fontfamily="DejaVu Sans")
    # centre: Moon phase as seen from the chosen hemisphere
    R0 = 0.15
    ax.add_patch(Circle((0, 0), R0 + 0.025, facecolor=C["limb"], edgecolor=C["brass"], lw=1.5, zorder=8))
    ax.add_patch(Circle((0, 0), R0, facecolor="#2c2f2a", edgecolor="none", zorder=8.5))
    e = state["elong"]
    waxing = e < 180
    ee = np.radians(e if waxing else 360 - e)
    a = np.radians(np.linspace(-90, 90, 60))
    limb = np.c_[R0 * np.cos(a), R0 * np.sin(a)]
    term = np.c_[R0 * np.cos(ee) * np.cos(a[::-1]), R0 * np.sin(a[::-1])]
    poly = np.vstack([limb, term])
    if not waxing:
        poly[:, 0] *= -1
    if state["lat"] < 0:                                   # seen from the southern hemisphere: mirrored
        poly[:, 0] *= -1
    ax.add_patch(Polygon(poly, closed=True, facecolor="#f4ecd2", edgecolor="none", zorder=9))
    organ = organ_of.get(state["moon_abbr"], "Neutral")
    day = f"{organ} day" if organ != "Neutral" else "Neutral (no day type)"
    sep = " \u00b7 "
    fig.text(0.5, 0.968 if compact else 0.955, title or ("The sky now" + (sep + place_name if place_name else "")),
             ha="center", va="center", fontsize=12.5 * (1.1 if compact else 1), color=C["ink"], fontweight="bold")
    when_l = state["when"].astimezone(tz)
    line1 = f"{when_l:%a %d %b %Y, %H:%M} \u00b7 Moon in {S.names.get(state['moon_abbr'], state['moon_abbr'])}"
    line2 = f"{day} \u00b7 {DIR_TEXT[state['direction']]} \u00b7 {phase_name(e)}"
    if compact:
        fig.text(0.5, 0.912, line1 + "\n" + line2, ha="center", va="center", fontsize=9.2, color=C["ink"], linespacing=1.35)
    else:
        fig.text(0.5, 0.918, line1 + " \u00b7 " + line2, ha="center", va="center", fontsize=8.2, color=C["ink"])
    return fig


def legend_text():
    return ("Filled symbol = above your horizon, open = below. The brass rule points to the Moon. "
            "The ring shows the 13 IAU constellations at their true widths, tinted by day type "
            "(blue Leaf, yellow Flower, red Fruit, brown Root, grey Ophiuchus). The Ascendant (east) is at 9 o'clock; "
            "the dashed line marks the MC. The centre shows the Moon's phase as you see it. "
            "\u2609 Sun \u263d Moon \u263f Mercury \u2640 Venus \u2642 Mars \u2643 Jupiter \u2644 Saturn "
            "\u2645 Uranus \u2646 Neptune \u2647 Pluto.")


# ------------------------------------------------------------------ "right now" summary
def now_summary(now, tz, settings, organ, activity):
    """Current day type, when it changes, Moon direction and next turn, unfavourable flag."""
    ev = be.find_events(now - timedelta(days=1), now + timedelta(days=6))
    iv = be.build_intervals(ev, settings)
    cur = iv[(iv.start <= now) & (iv.end > now)]
    if not len(cur):
        return None
    c = cur.iloc[0]
    after = iv[iv.start > now]
    nxt_change = next((r for r in after.itertuples() if r.organ != c.organ), None)
    turns = ev["turns"]; fut = turns[turns.utc > now]
    turn = fut.iloc[0] if len(fut) else None
    return dict(organ=c.organ, name=c["name"], direction=c.direction, avoid=c.avoid,
                until=nxt_change.start.to_pydatetime() if nxt_change else None,
                next_organ=nxt_change.organ if nxt_change else None,
                turn=turn.utc.to_pydatetime() if turn is not None else None)
