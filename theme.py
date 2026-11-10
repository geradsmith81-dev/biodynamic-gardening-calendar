"""Page styles. Everything here is either inside a touch-screen / narrow-screen @media rule or only used by
the phone layout, so a computer with a mouse looks exactly as before."""
import streamlit as st

import biodyn_engine as be

GREEN, CREAM, INK = "#3f7d4e", "#f7f5ef", "#22301f"

BASE_CSS = f"""
<style>
/* touch screens (phones, tablets): leave room at the bottom of the page, the sidebar and the settings panel,
   so the last lines and the box being typed in can be scrolled clear of the browser's toolbars and the
   on-screen keyboard; make buttons and switches easy to hit with a finger */
@media (pointer: coarse) {{
    [data-testid="stMainBlockContainer"], .block-container {{
        padding-bottom: calc(10rem + env(safe-area-inset-bottom)) !important; }}
    [data-testid="stSidebarUserContent"] {{ padding-bottom: calc(9rem + env(safe-area-inset-bottom)) !important; }}
    html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stSidebarContent"] {{
        scroll-padding-bottom: 40vh; }}
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"],
    [data-testid="stDownloadButton"] button {{ min-height: 2.9rem; }}
    [data-testid="stTab"] {{ padding-top: 0.55rem; padding-bottom: 0.55rem; }}
}}
/* narrow screens (phones held upright): less empty space, smaller headings */
@media (max-width: 640px) {{
    [data-testid="stMainBlockContainer"], .block-container {{ padding-left: 0.8rem !important;
        padding-right: 0.8rem !important; padding-top: 2.6rem !important; }}
    h1 {{ font-size: 1.5rem !important; line-height: 1.25 !important; }}
    h2 {{ font-size: 1.25rem !important; }}
    h3 {{ font-size: 1.1rem !important; }}
    [data-testid="stMetricValue"] {{ font-size: 1.5rem; }}
}}
/* phone lists and tables (only drawn in the phone layout) */
.hp-card {{ border: 1px solid #d5dccf; border-radius: 12px; padding: 0.6rem 0.8rem; margin: 0 0 0.55rem 0;
    background: #ffffff; line-height: 1.5; font-size: 1.02rem; color: {INK}; }}
.hp-card .hp-when {{ font-weight: 650; }}
.hp-card .hp-sub {{ color: #4d5a49; font-size: 0.95rem; }}
.hp-day {{ border-bottom: 1px solid #dfe5da; padding: 0.45rem 0.1rem; line-height: 1.75; font-size: 1.02rem; }}
.hp-day b {{ display: inline-block; min-width: 4.3rem; }}
.hp-chip {{ display: inline-block; padding: 0.02rem 0.5rem; margin: 0.1rem 0.25rem 0.1rem 0; border-radius: 0.35rem;
    font-size: 0.93rem; white-space: nowrap; color: {INK}; border-left: 0.5rem solid; }}
.hp-chip.best {{ background: {INK}; color: #ffffff; }}
.hp-chip.good {{ background: #ffffff; color: {INK}; border: 1px dashed {INK}; }}
.hp-chip.avoid {{ background: #5b5b5b; color: #ffffff; }}
.hp-badge {{ display: inline-block; padding: 0.05rem 0.55rem; border-radius: 0.7rem; font-weight: 650;
    margin-right: 0.35rem; font-size: 0.95rem; }}
.hp-badge.best {{ background: {INK}; color: #ffffff; }}
.hp-badge.good {{ background: #ffffff; color: {INK}; border: 1px dashed {INK}; }}
.hp-table-wrap {{ overflow-x: auto; margin-bottom: 0.8rem; }}
.hp-table {{ border-collapse: collapse; width: 100%; font-size: 0.98rem; color: {INK}; background: #ffffff; }}
.hp-table th {{ background: #e8efe4; text-align: left; padding: 0.4rem 0.5rem; border-bottom: 2px solid #c9d4c2; }}
.hp-table td {{ padding: 0.4rem 0.5rem; border-bottom: 1px solid #e3e8df; vertical-align: top; }}
</style>
"""

# phone layout only: slightly larger text everywhere, tab labels that fit
PHONE_CSS = """
<style>
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li { font-size: 1.03rem; }
[data-testid="stTab"] p { font-size: 0.98rem; }
[data-testid="stCaptionContainer"] { font-size: 0.92rem; }
</style>
"""


def inject(phone: bool):
    """Add the styles. st.html with only <style> takes no room on the page (st.markdown would add a gap)."""
    put = getattr(st, "html", None) or (lambda h: st.markdown(h, unsafe_allow_html=True))
    put(BASE_CSS)
    if phone:
        put(PHONE_CSS)


def tint(hex_colour: str, w: float = 0.6) -> str:
    """Mix a colour with white (w = share of white). Dark text on these tints is at least 7:1."""
    h = hex_colour.lstrip("#")
    c = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (255 - x) * w):02x}" for x in c)


def chip(organ: str, text: str) -> str:
    """A day-type label: pale tint with dark text (readable), solid colour bar on the left (recognisable)."""
    col = be.ORGAN_COLOURS.get(organ, "#b9b9b9")
    return f"<span class='hp-chip' style='background:{tint(col)};border-left-color:{col}'>{text}</span>"
