"""Phone layout: one switch that the app consults to fit a small, upright screen.

The switch starts ON when the browser says it is a phone or an Android tablet (its "User-Agent" text contains
Mobile, iPhone, iPod or Android) and OFF otherwise. It sits in the sidebar ("Phone layout"), so it can be
changed by hand - for example on an iPad, which identifies itself as a Mac computer.
With it on:
  * the settings move from the sidebar into a fold-out panel at the top of the page;
  * the best times, the month and the Moon events are written as lists in large text;
  * the month chart and the sky chart are drawn at phone size (the sky band in two halves);
  * tables show their most important columns only, as plain tables that wrap long text.
Desktop screens are unchanged.
"""
import html

import streamlit as st

KEY = "phone_layout"
PHONE_WORDS = ("mobi", "iphone", "ipod", "android")


def detected():
    """True when the browser identifies itself as a phone (or an Android tablet)."""
    try:
        ua = (st.context.headers.get("User-Agent") or "").lower()
    except Exception:            # no browser (tests) or an old Streamlit
        ua = ""
    return any(w in ua for w in PHONE_WORDS)


def phone():
    if KEY not in st.session_state:
        st.session_state[KEY] = detected()
    return bool(st.session_state[KEY])


def switch():
    """The sidebar switch. Call once per run, before anything consults phone()."""
    phone()
    st.sidebar.toggle("Phone layout", key=KEY,
                      help="Fits the app to a phone or small tablet: settings in a panel at the top of the page, "
                           "lists in large text and charts drawn at phone size. It switches on by itself on phones "
                           "and Android tablets; on an iPad you can switch it on here.")


def input_panel(label, expanded=False):
    """Where the settings go: the sidebar on a computer, a fold-out panel at the top on a phone."""
    if phone():
        return st.expander(label, expanded=expanded, icon=":material/tune:")
    return st.sidebar


def where_inputs():
    return "in the settings panel at the top" if phone() else "in the sidebar on the left"


def _cell(v):
    if v is None or (isinstance(v, float) and v != v):
        return ""
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def html_table(df):
    """A plain table that wraps long text (Streamlit's grid is hard to use with a finger)."""
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    rows = "".join("<tr>" + "".join(f"<td>{html.escape(_cell(v))}</td>" for v in rec) + "</tr>"
                   for rec in df.itertuples(index=False))
    return (f"<div class='hp-table-wrap'><table class='hp-table'><thead><tr>{head}</tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")


def table(df, phone_cols=None, **kw):
    """On a computer: Streamlit's interactive table. On a phone: only the listed columns, as a plain table."""
    if phone():
        if phone_cols:
            df = df[[c for c in phone_cols if c in df.columns]]
        st.markdown(html_table(df), unsafe_allow_html=True)
        return
    st.dataframe(df, hide_index=True, width="stretch", **kw)
