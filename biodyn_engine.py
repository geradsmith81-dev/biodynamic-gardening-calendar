"""
biodyn_engine.py - astronomy + biodynamic rules for the Biodynamic Gardening Calendar.

Astronomy
  * JPL DE440s ephemeris through Skyfield (valid 1850-2149).
  * Geocentric apparent Moon (the convention of printed biodynamic calendars).
  * Constellations = official IAU boundaries (Delporte 1930, defined at
    equinox B1875; Skyfield precesses positions to B1875 and uses the
    Roman 1987 boundary table). 13 constellations lie on the ecliptic and the
    Moon (latitude up to +/-5.3 deg) also clips a few others (Cetus, Orion,
    Sextans ...). Their meaning comes from constellation_organs.csv.

Biodynamic rules (Maria Thun's calendar, developed from Steiner's 1924
Agriculture Course):
  * Moon in a Fire / Earth / Air / Water constellation -> Fruit / Root /
    Flower / Leaf day.
  * Ascending Moon (declination increasing) -> "harvest time";
    descending Moon (declination decreasing) -> "planting time".
  * Unfavourable windows: lunar nodes, perigee, eclipses, Mercury and Venus
    heliocentric nodes, plus an optional margin around constellation changes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from skyfield import almanac, eclipselib
from skyfield.api import Loader, load_constellation_map, load_constellation_names
from skyfield.framelib import ecliptic_frame
from skyfield.positionlib import position_of_radec
from skyfield.searchlib import find_discrete, find_maxima, find_minima

HERE = os.path.dirname(os.path.abspath(__file__))
EPHEM_DIR = os.path.join(HERE, "ephem")
EPHEM_FILE = "de440s.bsp"                 # NASA JPL DE440s, 32 MB, 1850-2149
EPHEM_URL = "https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp"


def ephemeris_present() -> bool:
    return os.path.exists(os.path.join(EPHEM_DIR, EPHEM_FILE))

ORGANS = ["Leaf", "Flower", "Fruit", "Root"]
ORGAN_COLOURS = {"Leaf": "#4a90c2", "Flower": "#e3b23c", "Fruit": "#c8553d",
                 "Root": "#8a6a43", "Neutral": "#b9b9b9"}
EARLIEST, LATEST = datetime(1850, 1, 1, tzinfo=timezone.utc), datetime(2149, 12, 31, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- data
class _Sky:
    """Loads the ephemeris and boundary tables once."""
    def __init__(self):
        os.makedirs(EPHEM_DIR, exist_ok=True)
        load = Loader(EPHEM_DIR, verbose=False)
        self.ts = load.timescale(builtin=True)
        try:   # downloaded automatically from NASA JPL on first start if missing
            self.eph = load(EPHEM_FILE)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load or download the NASA JPL ephemeris {EPHEM_FILE}. "
                f"Check the internet connection, or download it by hand from {EPHEM_URL} "
                f"and put it in the folder {EPHEM_DIR}.") from exc
        self.earth, self.moon, self.sun = self.eph["earth"], self.eph["moon"], self.eph["sun"]
        self.constellation_at = load_constellation_map()
        self.names = dict(load_constellation_names())
        self.abbr_list = sorted(self.names)
        self.abbr_index = {a: i for i, a in enumerate(self.abbr_list)}
        self.organ_table = pd.read_csv(os.path.join(HERE, "constellation_organs.csv"))
        self.plant_groups = pd.read_csv(os.path.join(HERE, "plant_groups.csv"))
        self.activities = pd.read_csv(os.path.join(HERE, "activities.csv"))
        self.organ_of = dict(zip(self.organ_table.iau_abbr, self.organ_table.organ))
        self.element_of = dict(zip(self.organ_table.iau_abbr, self.organ_table.element))

    def moon_app(self, t):
        return self.earth.at(t).observe(self.moon).apparent()


_SKY = None


def sky() -> _Sky:
    global _SKY
    if _SKY is None:
        _SKY = _Sky()
    return _SKY


# --------------------------------------------------------------------------- settings
@dataclass
class Settings:
    node_hours: float = 3.0          # Moon node +/- (Thun ~3 h; Stella Natura 2 h; others 6 h)
    perigee_hours: float = 12.0      # perigee +/-
    eclipse_hours: float = 12.0      # solar & lunar eclipse +/-
    planet_node_hours: float = 12.0  # Mercury / Venus heliocentric nodes +/-
    changeover_hours: float = 2.0    # margin around each constellation change
    use_planet_nodes: bool = True
    ophiuchus: str = "Neutral"       # "Neutral", or an organ to borrow (e.g. "Leaf" like Scorpius)
    off_zodiac: str = "Neutral"      # Cetus, Orion, Sextans...: "Neutral" or "Nearest zodiac"


# --------------------------------------------------------------------------- events
def _dt(t):
    """Skyfield Time (array) -> list of aware UTC datetimes."""
    out = t.utc_datetime()
    return list(out) if np.ndim(out) else [out]


def find_events(start: datetime, end: datetime) -> dict:
    """All lunar / planetary events between start and end (aware datetimes)."""
    S = sky()
    ts = S.ts
    t0, t1 = ts.from_datetime(start), ts.from_datetime(end)

    # constellation ingresses ---------------------------------------------------
    def f_con(t):
        ab = S.constellation_at(S.moon_app(t))
        return np.array([S.abbr_index[a] for a in np.atleast_1d(ab)])
    f_con.step_days = 1 / 48          # 30 min grid; boundaries refined to < 1 s
    first = S.constellation_at(S.moon_app(t0))
    tc, vc = find_discrete(t0, t1, f_con)
    ingress = pd.DataFrame({"utc": _dt(tc) if len(tc) else [],
                            "constellation": [S.abbr_list[v] for v in vc]})

    # declination turning points (ascending / descending Moon) -------------------
    def f_dec(t):
        return S.moon_app(t).radec(epoch="date")[1].degrees
    f_dec.step_days = 1.0
    tmax, vmax = find_maxima(t0 - 16, t1 + 2, f_dec)
    tmin, vmin = find_minima(t0 - 16, t1 + 2, f_dec)
    turns = pd.DataFrame({"utc": _dt(tmax) + _dt(tmin),
                          "kind": ["Moon highest (starts descending)"] * len(tmax)
                                  + ["Moon lowest (starts ascending)"] * len(tmin),
                          "dec_deg": list(np.round(vmax, 2)) + list(np.round(vmin, 2))}).sort_values("utc")

    # lunar nodes ------------------------------------------------------------------
    def f_node(t):
        lat, _, _ = S.moon_app(t).frame_latlon(ecliptic_frame)
        return (lat.degrees >= 0).astype(int)
    f_node.step_days = 0.5
    tn, vn = find_discrete(t0 - 2, t1 + 2, f_node)
    nodes = pd.DataFrame({"utc": _dt(tn), "kind": ["Moon ascending node" if v else "Moon descending node" for v in vn]})

    # perigee / apogee -------------------------------------------------------------
    def f_dist(t):   # instantaneous geometric Earth-Moon centre distance (standard perigee definition)
        return (S.moon - S.earth).at(t).distance().km
    f_dist.step_days = 0.5
    tp, vp = find_minima(t0 - 2, t1 + 2, f_dist)
    ta, va = find_maxima(t0 - 2, t1 + 2, f_dist)
    apsides = pd.DataFrame({"utc": _dt(tp) + _dt(ta),
                            "kind": ["Perigee"] * len(tp) + ["Apogee"] * len(ta),
                            "distance_km": list(np.round(vp)) + list(np.round(va))}).sort_values("utc")

    # phases -----------------------------------------------------------------------
    tph, vph = almanac.find_discrete(t0 - 2, t1 + 2, almanac.moon_phases(S.eph))
    phases = pd.DataFrame({"utc": _dt(tph), "kind": [almanac.MOON_PHASES[v] for v in vph]})

    # eclipses ---------------------------------------------------------------------
    ecl = []
    tle, yle, _ = eclipselib.lunar_eclipses(t0 - 2, t1 + 2, S.eph)
    for t, y in zip(_dt(tle), yle):
        ecl.append((t, f"Lunar eclipse ({eclipselib.LUNAR_ECLIPSES[y].lower()})"))
    # solar: at each New Moon test the geocentric Sun-Moon separation against the
    # limit for an eclipse visible somewhere on Earth (semidiameters + parallax)
    nm = tph[vph == 0]
    if len(nm):
        e = S.earth.at(nm)
        m, s = e.observe(S.moon).apparent(), e.observe(S.sun).apparent()
        dm, ds = m.distance().km, s.distance().km
        limit = (np.degrees(np.arcsin(1737.4 / dm)) + np.degrees(np.arcsin(696000 / ds))
                 + np.degrees(np.arcsin(6378.14 / dm)) - np.degrees(np.arcsin(6378.14 / ds)))
        sep = m.separation_from(s).degrees
        for t, ok in zip(_dt(nm), sep < limit):
            if ok:
                ecl.append((t, "Solar eclipse (visible somewhere on Earth)"))
    eclipses = pd.DataFrame(ecl, columns=["utc", "kind"]).sort_values("utc") if ecl else pd.DataFrame(columns=["utc", "kind"])

    # Mercury & Venus heliocentric nodes --------------------------------------------
    pn = []
    for name, step in (("mercury", 2.0), ("venus", 5.0)):
        body = S.eph[name] - S.sun
        def f_pl(t, body=body):
            lat, _, _ = body.at(t).frame_latlon(ecliptic_frame)
            return (lat.degrees >= 0).astype(int)
        f_pl.step_days = step
        tt, vv = find_discrete(t0 - 2, t1 + 2, f_pl)
        for t, v in zip(_dt(tt), vv):
            pn.append((t, f"{name.capitalize()} {'ascending' if v else 'descending'} node"))
    planet_nodes = pd.DataFrame(pn, columns=["utc", "kind"]).sort_values("utc") if pn else pd.DataFrame(columns=["utc", "kind"])

    return dict(start=start, end=end, first_constellation=str(first), ingress=ingress, turns=turns,
                nodes=nodes, apsides=apsides, phases=phases, eclipses=eclipses, planet_nodes=planet_nodes)


# --------------------------------------------------------------------------- intervals
def _organ_for(abbr: str, settings: Settings, nearest: str | None) -> str:
    S = sky()
    if abbr == "Oph":
        return settings.ophiuchus
    if abbr in S.organ_of:
        return S.organ_of[abbr]
    if settings.off_zodiac == "Nearest zodiac" and nearest:
        return S.organ_of.get(nearest, "Neutral")
    return "Neutral"


def avoid_windows(ev: dict, st: Settings) -> pd.DataFrame:
    rows = []
    h = lambda x: timedelta(hours=x)
    for t, k in zip(ev["nodes"].utc, ev["nodes"].kind):
        if st.node_hours > 0:
            rows.append((t - h(st.node_hours), t + h(st.node_hours), k, t))
    for t, k in zip(ev["apsides"].utc, ev["apsides"].kind):
        if k == "Perigee" and st.perigee_hours > 0:
            rows.append((t - h(st.perigee_hours), t + h(st.perigee_hours), "Perigee", t))
    for t, k in zip(ev["eclipses"].utc, ev["eclipses"].kind):
        if st.eclipse_hours > 0:
            rows.append((t - h(st.eclipse_hours), t + h(st.eclipse_hours), k, t))
    if st.use_planet_nodes and st.planet_node_hours > 0:
        for t, k in zip(ev["planet_nodes"].utc, ev["planet_nodes"].kind):
            rows.append((t - h(st.planet_node_hours), t + h(st.planet_node_hours), k, t))
    if st.changeover_hours > 0:
        for t, c in zip(ev["ingress"].utc, ev["ingress"].constellation):
            rows.append((t - h(st.changeover_hours), t + h(st.changeover_hours), f"Changeover into {c}", t))
    return pd.DataFrame(rows, columns=["start", "end", "reason", "exact"])


def _nearest_zodiac(times: list[datetime]) -> list[str | None]:
    """For off-zodiac stretches: zodiacal constellation at the Moon's ecliptic
    longitude, latitude 0 (i.e. the band directly 'above/below' the Moon)."""
    S = sky()
    if not times:
        return []
    t = S.ts.from_datetimes(times)
    lat, lon, _ = S.moon_app(t).frame_latlon(ecliptic_frame)
    pos = ecliptic_point(lon.degrees, np.zeros(len(times)), t)
    return list(S.constellation_at(pos))


def build_intervals(ev: dict, st: Settings) -> pd.DataFrame:
    """Split the period into stretches of constant constellation, Moon direction
    and unfavourable flags."""
    S = sky()
    start, end = ev["start"], ev["end"]
    av = avoid_windows(ev, st)
    cuts = {start, end}
    cuts.update(t for t in ev["ingress"].utc if start < t < end)
    cuts.update(t for t in ev["turns"].utc if start < t < end)
    for a, b in zip(av.start, av.end):
        for x in (a, b):
            if start < x < end:
                cuts.add(x)
    cuts = sorted(cuts)

    ing_t = list(ev["ingress"].utc); ing_c = list(ev["ingress"].constellation)
    tr = ev["turns"]; tr_t = list(tr.utc); tr_k = list(tr.kind)
    rows = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        if (b - a).total_seconds() < 30:
            continue
        mid = a + (b - a) / 2
        i = np.searchsorted(np.array(ing_t, dtype=object), mid) if ing_t else 0
        con = ev["first_constellation"] if i == 0 else ing_c[i - 1]
        j = np.searchsorted(np.array(tr_t, dtype=object), mid) - 1
        direction = ("descending" if "highest" in tr_k[j] else "ascending") if j >= 0 else "?"
        why = [r for s0, e0, r in zip(av.start, av.end, av.reason) if s0 <= mid < e0]
        rows.append(dict(start=a, end=b, constellation=con, name=S.names.get(con, con),
                         direction=direction, avoid="; ".join(why)))
    df = pd.DataFrame(rows)
    off = [k for k, c in enumerate(df.constellation) if c not in S.organ_of]
    near = _nearest_zodiac([df.start[k] + (df.end[k] - df.start[k]) / 2 for k in off]) if off else []
    nearest = dict(zip(off, near))
    df["organ"] = [_organ_for(c, st, nearest.get(k)) for k, c in enumerate(df.constellation)]
    df["element"] = [S.element_of.get(c, "outside the zodiac band") for c in df.constellation]
    df["hours"] = [(b - a).total_seconds() / 3600 for a, b in zip(df.start, df.end)]
    return df


def rate(intervals: pd.DataFrame, organ: str, activity: str) -> pd.DataFrame:
    """Add 'rating' for one plant organ and one activity."""
    S = sky()
    fav = S.activities.set_index("activity").favoured_moon.get(activity, "any")
    df = intervals.copy()
    match = df.organ == organ
    dir_ok = (df.direction == fav) if fav != "any" else pd.Series(True, index=df.index)
    bad = df.avoid.str.len() > 0
    df["rating"] = np.select([bad & match, match & dir_ok, match], ["Avoid", "Best", "Good"], default="")
    return df


def merge_windows(rated: pd.DataFrame, min_hours: float = 1.0) -> pd.DataFrame:
    """Join neighbouring stretches that share a rating into windows."""
    out = []
    cur = None
    for r in rated.itertuples():
        if r.rating not in ("Best", "Good"):
            if cur:
                out.append(cur); cur = None
            continue
        if cur and cur["rating"] == r.rating and cur["end"] == r.start:
            cur["end"] = r.end
            if r.name not in cur["constellations"]:
                cur["constellations"].append(r.name)
        else:
            if cur:
                out.append(cur)
            cur = dict(start=r.start, end=r.end, rating=r.rating, organ=r.organ,
                       direction=r.direction, constellations=[r.name])
    if cur:
        out.append(cur)
    w = pd.DataFrame(out, columns=["start", "end", "rating", "organ", "direction", "constellations"])
    if len(w):
        w["hours"] = [(b - a).total_seconds() / 3600 for a, b in zip(w.start, w.end)]
        w["constellations"] = [", ".join(c) for c in w.constellations]
        w = w[w.hours >= min_hours].reset_index(drop=True)
    return w


# --------------------------------------------------------------------------- sky chart helpers
def ecliptic_point(lon_deg, lat_deg, t):
    """Skyfield position for ecliptic-of-date coordinates at time(s) t."""
    lon, lat = np.radians(lon_deg), np.radians(lat_deg)
    v = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    R = ecliptic_frame.rotation_at(t)                 # ICRS -> ecliptic of date
    if R.ndim == 3:
        vi = np.einsum("jin,jn->in", R, v)             # R^T v for each time
    else:
        vi = R.T @ v
    ra = np.degrees(np.arctan2(vi[1], vi[0])) % 360 / 15
    dec = np.degrees(np.arcsin(np.clip(vi[2], -1, 1)))
    return position_of_radec(ra, dec)


def constellation_band(when: datetime, lon_step=0.25, lat_step=0.25, lat_lim=8.0):
    """Grid of IAU constellation abbreviations across the ecliptic band."""
    S = sky()
    t = S.ts.from_datetime(when)
    lons = np.arange(0, 360, lon_step) + lon_step / 2
    lats = np.arange(-lat_lim, lat_lim + 1e-9, lat_step)
    LO, LA = np.meshgrid(lons, lats)
    ab = S.constellation_at(ecliptic_point(LO.ravel(), LA.ravel(), t))
    return lons, lats, np.asarray(ab).reshape(LA.shape)


BODIES = [("Sun", "sun"), ("Moon", "moon"), ("Mercury", "mercury"), ("Venus", "venus"),
          ("Mars", "mars barycenter"), ("Jupiter", "jupiter barycenter"), ("Saturn", "saturn barycenter"),
          ("Uranus", "uranus barycenter"), ("Neptune", "neptune barycenter"), ("Pluto", "pluto barycenter")]


def sky_positions(when: datetime) -> pd.DataFrame:
    """Geocentric apparent positions and IAU constellations of Sun, Moon and planets."""
    S = sky()
    t = S.ts.from_datetime(when)
    e = S.earth.at(t)
    rows = []
    for label, key in BODIES:
        p = e.observe(S.eph[key]).apparent()
        lat, lon, _ = p.frame_latlon(ecliptic_frame)
        ra, dec, _ = p.radec(epoch="date")
        c = S.constellation_at(p)
        rows.append(dict(body=label, constellation=S.names[c], iau_abbr=c,
                         ecl_lon_deg=round(lon.degrees, 2), ecl_lat_deg=round(lat.degrees, 2),
                         ra_hours=round(ra.hours, 4), dec_deg=round(dec.degrees, 3)))
    return pd.DataFrame(rows)


def moon_track(start: datetime, end: datetime, step_hours=6.0) -> pd.DataFrame:
    S = sky()
    n = max(2, int((end - start).total_seconds() / 3600 / step_hours) + 1)
    times = [start + timedelta(hours=step_hours * k) for k in range(n)]
    t = S.ts.from_datetimes(times)
    lat, lon, _ = S.moon_app(t).frame_latlon(ecliptic_frame)
    return pd.DataFrame({"utc": times, "lon": lon.degrees, "lat": lat.degrees})


# --------------------------------------------------------------------------- calendar export
def to_ics(windows: pd.DataFrame, title: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Biodynamic Gardening Calendar//EN", "CALSCALE:GREGORIAN"]
    for k, w in windows.iterrows():
        lines += ["BEGIN:VEVENT",
                  f"UID:biodyn-{w.start.strftime('%Y%m%dT%H%M%S')}-{k}@houseplant-calendar",
                  f"DTSTAMP:{stamp}",
                  f"DTSTART:{w.start.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
                  f"DTEND:{w.end.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
                  f"SUMMARY:{w.rating}: {title} ({w.organ} day)",
                  f"DESCRIPTION:Moon in {w.constellations} (IAU)\\, {w.direction} Moon.",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
