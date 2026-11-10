"""Biodynamic Gardening Calendar - Streamlit interface.
Start with:  streamlit run app.py   (or double-click 'Start app.bat')."""
import calendar
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, available_timezones

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import biodyn_engine as be   # noqa: E402
import charts                # noqa: E402
import device                # noqa: E402
import theme                 # noqa: E402

ICON = os.path.join(be.HERE, "assets", "houseplant_icon.png")
st.set_page_config(page_title="Biodynamic Gardening Calendar",
                   page_icon=ICON if os.path.exists(ICON) else "\U0001F33F", layout="wide")


def local_zone_name():
    """Visitor's browser time zone (online), else the computer's (local run), else UTC."""
    try:
        name = st.context.timezone
        if name in available_timezones():
            return name
    except Exception:
        pass
    try:
        import tzlocal
        name = tzlocal.get_localzone_name()
        if name in available_timezones():
            return name
    except Exception:
        pass
    return "UTC"


@st.cache_data(show_spinner="Calculating the Moon's path through the IAU constellations ...")
def get_events(start_iso: str, end_iso: str):
    return be.find_events(datetime.fromisoformat(start_iso), datetime.fromisoformat(end_iso))


@st.cache_data(show_spinner="Drawing the sky chart ...")
def get_band_fig(when_iso, tzkey, a_iso, b_iso, compact=False):
    tz = ZoneInfo(tzkey)
    track = be.moon_track(datetime.fromisoformat(a_iso), datetime.fromisoformat(b_iso), 1.0)
    if compact:
        return charts.sky_band_compact(datetime.fromisoformat(when_iso), tz, track)
    return charts.sky_band(datetime.fromisoformat(when_iso), tz, track)


def fmt_local(series, tz, fmt="%a %d %b %Y, %H:%M"):
    return [x.to_pydatetime().astimezone(tz).strftime(fmt) for x in pd.to_datetime(series)]


def window_cards(w, tz):
    """Phone list of windows: one card each, in large text."""
    out = []
    for r in w.itertuples():
        a = r.start.to_pydatetime().astimezone(tz); b = r.end.to_pydatetime().astimezone(tz)
        until = f"{b:%H:%M}" if a.date() == b.date() else f"{b:%a %d %b, %H:%M}"
        cls = "best" if r.rating == "Best" else "good"
        badge = "\u2b50 Best" if r.rating == "Best" else "\u2713 Good"
        out.append(f"<div class='hp-card'><span class='hp-badge {cls}'>{badge}</span>"
                   f"<span class='hp-when'>{a:%a %d %b, %H:%M} \u2192 {until}</span><br>"
                   f"<span class='hp-sub'>{r.hours:.1f} h \u00b7 Moon in {r.constellations} \u00b7 {r.direction} Moon</span></div>")
    return "".join(out)


def day_list(rows):
    """Phone list of the month: one line per day with its day types, Best/Good times and warnings."""
    out = []
    for e in rows:
        types = " ".join(theme.chip(o, f"{o} all day" if (a, b) == ("00:00", "24:00") else f"{o} {a}\u2013{b}")
                         for o, a, b in e["types"])
        mark = {"Best": "\u2b50", "Good": "\u2713"}
        extra = [f"<span class='hp-chip {k.lower()}'>{mark[k]} {k} {a}\u2013{b}</span>" for k, a, b in e["rated"]]
        extra += [f"<span class='hp-chip avoid'>\u26a0 avoid {a}\u2013{b}</span>" for _, a, b in e["avoid"]]
        extra += [f"<span class='hp-sub'>{m}</span>" for m in e["marks"]]
        out.append(f"<div class='hp-day'><b>{e['day']:%a} {e['day'].day}</b> {types}"
                   + (f"<br>{' '.join(extra)}" if extra else "") + "</div>")
    return "".join(out)


@st.cache_resource(show_spinner="First start: downloading the NASA JPL ephemeris (32 MB). This takes a minute ...")
def load_sky():
    return be.sky()


try:
    S = load_sky()
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()
groups = S.plant_groups
acts = S.activities

device.switch()                      # "Phone layout" switch in the sidebar
PHONE = device.phone()
theme.inject(PHONE)

# ------------------------------------------------------------------ settings (sidebar, or a panel on a phone)
if PHONE:
    st.title("\U0001F33F Biodynamic Gardening Calendar")
with device.input_panel("Your settings: plants, task, dates, time zone"):
    if not PHONE:
        st.header("Your settings")
    zones = sorted(available_timezones())
    default_zone = local_zone_name()
    tzkey = st.selectbox("Your time zone (type to search)", zones, index=zones.index(default_zone),
                         help="Only used to show clock times. The Moon's position is the same for everyone on Earth.")
    tz = ZoneInfo(tzkey)
    today = datetime.now(tz).date()
    c1, c2 = st.columns(2)
    year = c1.number_input("Start year", 1850, 2147, today.year, step=1)
    month = c2.selectbox("Start month", list(range(1, 13)), index=today.month - 1,
                         format_func=lambda m: calendar.month_name[m])
    n_months = st.slider("How many months to show", 1, 24, 3)

    st.subheader("Your plants")
    g_label = st.radio("Plant group", groups.plant_group.tolist(),
                       captions=groups.examples.tolist())
    organ = groups.set_index("plant_group").organ[g_label]
    activity = st.radio("What do you want to do?", acts.activity.tolist())

    with st.expander("Rule settings (advanced)"):
        stg = be.Settings()
        stg.node_hours = st.number_input("Avoid hours either side of a Moon node", 0.0, 24.0, stg.node_hours, 0.5,
                                         help="Thun: about 3 h. Stella Natura: 2 h. Some guides: 6 h.")
        stg.perigee_hours = st.number_input("Avoid hours either side of perigee", 0.0, 48.0, stg.perigee_hours, 1.0)
        stg.eclipse_hours = st.number_input("Avoid hours either side of an eclipse", 0.0, 48.0, stg.eclipse_hours, 1.0)
        stg.use_planet_nodes = st.checkbox("Also avoid Mercury and Venus nodes", stg.use_planet_nodes)
        stg.planet_node_hours = st.number_input("... hours either side", 0.0, 48.0, stg.planet_node_hours, 1.0)
        stg.changeover_hours = st.number_input("Margin around each constellation change (hours)", 0.0, 6.0,
                                               stg.changeover_hours, 0.5,
                                               help="Printed calendars grey out ~2 h around changes. "
                                                    "Set 0 to use the exact IAU boundary times.")
        oph = st.selectbox("Moon in Ophiuchus counts as",
                           ["Neutral (no day type)", "Leaf (like Scorpius)", "Fruit (like Sagittarius)"])
        stg.ophiuchus = oph.split(" ")[0]
        off = st.selectbox("Moon in Cetus, Orion, Sextans etc. counts as",
                           ["Neutral (no day type)", "Nearest zodiac constellation"])
        stg.off_zodiac = "Neutral" if off.startswith("Neutral") else "Nearest zodiac"
        min_h = st.number_input("Hide windows shorter than (hours)", 0.0, 12.0, 1.0, 0.5)

# ------------------------------------------------------------------ compute
start_local = datetime(int(year), int(month), 1, tzinfo=tz)
y2, m2 = divmod(int(month) - 1 + n_months, 12)
end_local = datetime(int(year) + y2, m2 + 1, 1, tzinfo=tz)
start_utc, end_utc = start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
ev = get_events(start_utc.isoformat(), end_utc.isoformat())
iv = be.build_intervals(ev, stg)
rated = be.rate(iv, organ, activity)
windows = be.merge_windows(rated, min_h)
fav = acts.set_index("activity").favoured_moon[activity]

# ------------------------------------------------------------------ header
if not PHONE:
    st.title("\U0001F33F Biodynamic Gardening Calendar")
st.markdown(
    f"**{g_label}** \u00b7 **{activity}** \u00b7 {calendar.month_name[int(month)]} {int(year)} "
    f"for {n_months} month{'s' if n_months > 1 else ''} \u00b7 times in **{tzkey}**  \n"
    f"Looking for **{organ} days** (Moon in front of a "
    f"{ {'Leaf':'Water','Flower':'Air / light','Fruit':'Fire / warmth','Root':'Earth'}[organ]} constellation)"
    + ("" if fav == "any" else f", with a **{fav} Moon**")
    + ", outside unfavourable times.")

TABS = (["\u2b50 Best", "\U0001F4C5 Month", "\U0001F30C Sky", "\U0001F319 Events", "\u2139\ufe0f About"] if PHONE else
        ["\u2b50 Best times", "\U0001F4C5 Month view", "\U0001F30C Sky chart", "\U0001F319 Moon events", "\u2139\ufe0f How it works"])
tab1, tab2, tab3, tab4, tab5 = st.tabs(TABS)

with tab1:
    best = windows[windows.rating == "Best"] if len(windows) else windows
    good = windows[windows.rating == "Good"] if len(windows) else windows
    c1, c2, c3 = st.columns(3)
    c1.metric("Best windows", len(best))
    c2.metric("Good windows", len(good))
    c3.metric("Hours rated Best", f"{best.hours.sum():.0f}" if len(best) else "0")
    st.caption("**Best** = right day type, right Moon direction, nothing unfavourable. "
               "**Good** = right day type but the Moon is moving the other way. "
               + ("(For sowing, the Moon direction is not used, so every matching window is Best.)" if fav == "any" else ""))
    if len(windows):
        show = pd.DataFrame({
            "Rating": windows.rating.map({"Best": "\u2b50 Best", "Good": "\u2713 Good"}),
            "From": fmt_local(windows.start, tz), "Until": fmt_local(windows.end, tz),
            "Hours": windows.hours.round(1), "Moon in (IAU)": windows.constellations,
            "Moon": windows.direction})
        only_best = st.toggle("Show only Best", value=False)
        if PHONE:
            st.markdown(window_cards(windows[windows.rating == "Best"] if only_best else windows, tz),
                        unsafe_allow_html=True)
        else:
            st.dataframe(show[show.Rating.str.contains("Best")] if only_best else show,
                         hide_index=True, width="stretch")
        d1, d2 = st.columns(2)
        d1.download_button("\U0001F4C6 Add to my calendar (.ics file)",
                           be.to_ics(windows, f"{activity} - {g_label}"),
                           file_name="houseplant_windows.ics", mime="text/calendar",
                           help="Open the downloaded file to import it into Outlook, Google or Apple Calendar.")
        d2.download_button("\U0001F4C4 Download as spreadsheet (.csv)", show.to_csv(index=False).encode("utf-8-sig"),
                           file_name="houseplant_windows.csv", mime="text/csv")
    else:
        st.info("No suitable windows in this period with the current settings.")

with tab2:
    months = []
    y, m = int(year), int(month)
    for _ in range(n_months):
        months.append((y, m)); m += 1
        if m == 13:
            y, m = y + 1, 1
    pick = st.selectbox("Month", months, format_func=lambda ym: f"{calendar.month_name[ym[1]]} {ym[0]}")
    if PHONE:
        how = st.radio("Show the month as", ["List", "Colour chart"], horizontal=True, key="month_as")
        if how == "List":
            st.markdown(day_list(charts.day_summary(rated, ev, pick[0], pick[1], tz)), unsafe_allow_html=True)
            st.caption(f"Times in {tzkey}. \u2b50 Best and \u2713 Good are for your plants and task; "
                       "\u26a0 marks unfavourable times (node, perigee, eclipse, planet node or changeover).")
        else:
            st.pyplot(charts.month_timeline_compact(rated, ev, pick[0], pick[1], tz), width="stretch")
            st.caption("Each row is a day, midnight to midnight. Hatched = unfavourable.")
    else:
        fig = charts.month_timeline(rated, ev, pick[0], pick[1], tz, f"{g_label}: {activity.lower()}")
        st.pyplot(fig, width="stretch")
        st.caption("Each row is a day, from midnight (left) to midnight (right). Colour = the day type set by the "
               "Moon's IAU constellation. Hatched = unfavourable (node, perigee, eclipse, planet node or changeover).")

with tab3:
    c1, c2 = st.columns(2)
    d0 = today if start_local.date() <= today < end_local.date() else start_local.date()
    when_d = c1.date_input("Date for the planets", d0, min_value=date(1850, 1, 2), max_value=date(2149, 12, 30))
    when_t = c2.time_input("Local time", time(12, 0))
    when = datetime.combine(when_d, when_t, tzinfo=tz)
    m_start = datetime(when_d.year, when_d.month, 1, tzinfo=tz)
    m_end = (m_start + timedelta(days=32)).replace(day=1)
    st.pyplot(get_band_fig(when.isoformat(), tzkey, m_start.isoformat(), m_end.isoformat(), PHONE), width="stretch")
    st.caption("The ecliptic band as divided by the official IAU constellation boundaries (Delporte 1930). The thin "
               "line is the Moon's path for the whole month, with dots at local midnight labelled by day; the white "
               "disc is the Moon at the chosen moment. Grey = Ophiuchus; pale = constellations outside the zodiac.")
    pos = be.sky_positions(when)
    pos["day type"] = [S.organ_of.get(a, "Neutral (outside zodiac)") for a in pos.iau_abbr]
    device.table(pos.drop(columns=["iau_abbr"]).rename(columns={
        "body": "Body", "constellation": "IAU constellation", "ecl_lon_deg": "Ecliptic longitude \u00b0",
        "ecl_lat_deg": "Ecliptic latitude \u00b0", "ra_hours": "RA (h, of date)", "dec_deg": "Dec \u00b0 (of date)"}),
        phone_cols=["Body", "IAU constellation", "day type"])

with tab4:
    rows = []
    for k in ("ingress", "turns", "nodes", "apsides", "phases", "eclipses", "planet_nodes"):
        df = ev[k]
        for r in df.itertuples():
            if not (start_utc <= r.utc.to_pydatetime() < end_utc):
                continue
            what = (f"Moon enters {S.names[r.constellation]} \u2192 {iv_organ}"
                    if k == "ingress" and (iv_organ := be._organ_for(r.constellation, stg, None)) else r.kind)
            rows.append((r.utc, what, k))
    evt = pd.DataFrame(rows, columns=["utc", "Event", "type"]).sort_values("utc")
    labels = {"ingress": "Constellation changes", "turns": "Ascending / descending", "nodes": "Moon nodes",
              "apsides": "Perigee / apogee", "phases": "Phases", "eclipses": "Eclipses",
              "planet_nodes": "Mercury / Venus nodes"}
    pick = st.multiselect("Show", list(labels), default=list(labels), format_func=labels.get)
    evt = evt[evt.type.isin(pick)]
    if PHONE:
        device.table(pd.DataFrame({"When": fmt_local(evt.utc, tz, "%a %d %b %H:%M"), "Event": evt.Event}))
    else:
        st.dataframe(pd.DataFrame({"When (local)": fmt_local(evt.utc, tz), "Event": evt.Event,
                                   "Kind": evt.type.map(labels)}), hide_index=True, width="stretch", height=520)

with tab5:
    with open(os.path.join(be.HERE, "HOW_IT_WORKS.md"), encoding="utf-8") as fh:
        st.markdown(fh.read())

st.divider()
st.caption("Positions: NASA JPL DE440s ephemeris via Skyfield. Constellation boundaries: IAU (Delporte 1930). "
           "Day-type rules after Maria Thun. This calendar is a traditional practice, not a scientific prediction.")
