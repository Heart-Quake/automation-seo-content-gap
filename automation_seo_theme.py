from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

LOGO_PATH = Path(__file__).with_name("logo-sidebar-cream.png")
LOGO_DISPLAY_WIDTH = 220


def apply_automation_seo_theme() -> None:
    if LOGO_PATH.exists():
        logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
        st.sidebar.markdown(
            f"""
            <div class="sidebar-logo">
                <img src="data:image/png;base64,{logo_b64}" alt="Yuri & Neil" width="{LOGO_DISPLAY_WIDTH}">
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <style>
            :root {
                --yn-bg: #222429;
                --yn-deep: #0F1011;
                --yn-card: #27282A;
                --yn-card-strong: #1F2024;
                --yn-card-hover: #1B1C1E;
                --yn-border: #37383A;
                --yn-text: #F7F8F8;
                --yn-muted: #A1A1AA;
                --yn-muted-strong: #828282;
                --yn-accent: #49DCBC;
                --yn-success: #4CEBA6;
                --yn-danger: #FF3366;
                --yn-ring: rgba(73, 220, 188, 0.42);
                --yn-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
            }

            .stApp {
                background: var(--yn-bg);
                color: var(--yn-text);
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
            }

            [data-testid="stAppViewContainer"],
            [data-testid="stHeader"] {
                background: transparent;
            }

            .block-container {
                max-width: 1220px;
                padding-top: 2rem;
                padding-bottom: 4rem;
            }

            h1, h2, h3, h4 {
                color: var(--yn-text) !important;
                letter-spacing: 0;
            }

            h1 {
                font-size: 3rem !important;
                font-weight: 800 !important;
                line-height: 1.04 !important;
                margin-bottom: 0.75rem !important;
            }

            h2 {
                font-size: 1.55rem !important;
                margin-top: 1.6rem !important;
            }

            h3 {
                font-size: 1.12rem !important;
                margin-top: 1.1rem !important;
            }

            .tool-hero {
                border-bottom: 1px solid var(--yn-border);
                margin-bottom: 1.45rem;
                padding: 0.25rem 0 1.45rem;
            }

            .tool-kicker {
                color: var(--yn-accent);
                font-size: 0.74rem;
                font-weight: 800;
                letter-spacing: 0.12em;
                margin-bottom: 0.7rem;
                text-transform: uppercase;
            }

            .tool-title {
                color: var(--yn-text);
                font-size: 3rem;
                font-weight: 800;
                line-height: 1.04;
                margin: 0 0 0.75rem;
            }

            .tool-lead {
                color: var(--yn-muted);
                font-size: 1.05rem;
                line-height: 1.55;
                max-width: 72ch;
                margin: 0;
            }

            p, label, span, div {
                letter-spacing: 0;
            }

            p,
            [data-testid="stMarkdownContainer"] p {
                color: var(--yn-muted);
            }

            [data-testid="stSidebar"] {
                background: var(--yn-deep);
                border-right: 1px solid var(--yn-border);
            }

            .sidebar-logo {
                display: flex;
                justify-content: center;
                margin: 0.65rem 0 1.75rem;
            }

            .sidebar-logo img {
                display: block;
                width: 220px;
                max-width: 82%;
                height: auto;
                image-rendering: auto;
            }

            [data-testid="stSidebar"] h1,
            [data-testid="stSidebar"] h2,
            [data-testid="stSidebar"] h3 {
                color: var(--yn-text) !important;
            }

            [data-testid="stSidebar"] label,
            [data-testid="stSidebar"] p,
            [data-testid="stSidebar"] span {
                color: var(--yn-muted) !important;
            }

            [data-testid="stSidebar"] input,
            [data-testid="stSidebar"] textarea,
            [data-testid="stSidebar"] [role="combobox"],
            [data-testid="stAppViewContainer"] input,
            [data-testid="stAppViewContainer"] textarea,
            [data-testid="stAppViewContainer"] [role="combobox"],
            [data-testid="stSidebar"] [data-baseweb="select"] > div,
            [data-testid="stSidebar"] [data-baseweb="input"] > div,
            [data-testid="stSidebar"] [data-baseweb="textarea"] > div,
            [data-testid="stAppViewContainer"] [data-baseweb="select"] > div,
            [data-testid="stAppViewContainer"] [data-baseweb="input"] > div,
            [data-testid="stAppViewContainer"] [data-baseweb="textarea"] > div {
                background: var(--yn-card-strong) !important;
                border: 1px solid var(--yn-border) !important;
                border-radius: 8px !important;
                color: var(--yn-text) !important;
            }

            [data-testid="stSidebar"] input,
            [data-testid="stSidebar"] textarea,
            [data-testid="stAppViewContainer"] input,
            [data-testid="stAppViewContainer"] textarea,
            [data-testid="stSidebar"] [data-baseweb="select"] span,
            [data-testid="stSidebar"] [data-baseweb="select"] div,
            [data-testid="stAppViewContainer"] [data-baseweb="select"] span,
            [data-testid="stAppViewContainer"] [data-baseweb="select"] div,
            [data-testid="stSidebar"] [role="combobox"] {
                color: var(--yn-text) !important;
                -webkit-text-fill-color: var(--yn-text) !important;
            }

            input::placeholder,
            textarea::placeholder {
                color: var(--yn-muted-strong) !important;
                opacity: 1 !important;
                -webkit-text-fill-color: var(--yn-muted-strong) !important;
            }

            [data-baseweb="select"] svg {
                fill: var(--yn-muted) !important;
            }

            [data-baseweb="select"]:focus-within > div,
            [data-baseweb="input"]:focus-within > div,
            [data-baseweb="textarea"]:focus-within > div {
                border-color: var(--yn-accent) !important;
                box-shadow: 0 0 0 2px var(--yn-ring) !important;
            }

            [data-baseweb="popover"] [role="listbox"],
            [data-baseweb="menu"] {
                background: var(--yn-card-strong) !important;
                border: 1px solid var(--yn-border) !important;
                color: var(--yn-text) !important;
            }

            [data-baseweb="popover"] [role="option"],
            [data-baseweb="menu"] li {
                background: var(--yn-card-strong) !important;
                color: var(--yn-text) !important;
            }

            [data-baseweb="popover"] [role="option"]:hover,
            [data-baseweb="menu"] li:hover {
                background: var(--yn-card-hover) !important;
            }

            [data-baseweb="popover"] [role="option"][aria-selected="true"],
            [data-baseweb="popover"] [role="option"][aria-checked="true"],
            [role="option"][aria-selected="true"],
            [role="option"][aria-checked="true"] {
                background: rgba(73, 220, 188, 0.16) !important;
                color: var(--yn-text) !important;
            }

            .stButton > button,
            .stDownloadButton > button,
            [data-testid="stFormSubmitButton"] button {
                background: var(--yn-text) !important;
                border: 1px solid var(--yn-text) !important;
                border-radius: 8px !important;
                color: var(--yn-deep) !important;
                font-weight: 800 !important;
                min-height: 2.45rem;
                transition: background-color 160ms ease, border-color 160ms ease, transform 160ms ease;
            }

            .stButton > button *,
            .stDownloadButton > button *,
            [data-testid="stFormSubmitButton"] button * {
                color: inherit !important;
                -webkit-text-fill-color: inherit !important;
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover,
            [data-testid="stFormSubmitButton"] button:hover {
                background: var(--yn-accent) !important;
                border-color: var(--yn-accent) !important;
                color: var(--yn-deep) !important;
                transform: translateY(-1px);
            }

            [data-testid="stTabs"] [role="tablist"] {
                gap: 0.35rem;
                border-bottom: 1px solid var(--yn-border);
            }

            [data-testid="stTabs"] [role="tab"] {
                color: var(--yn-muted) !important;
                border-radius: 8px 8px 0 0;
                font-weight: 700;
                padding: 0.65rem 0.8rem;
            }

            [data-testid="stTabs"] [aria-selected="true"] {
                color: var(--yn-accent) !important;
            }

            [data-testid="stMetric"] {
                background: var(--yn-card) !important;
                border: 1px solid var(--yn-border) !important;
                border-radius: 8px !important;
                padding: 0.95rem 1rem;
            }

            [data-testid="stMetric"] label,
            [data-testid="stMetric"] [data-testid="stMetricLabel"] {
                color: var(--yn-muted) !important;
            }

            [data-testid="stMetricValue"] {
                color: var(--yn-text) !important;
                font-size: 1.55rem !important;
                font-weight: 800 !important;
            }

            [data-testid="stExpander"],
            [data-testid="stDataFrame"],
            div[data-testid="stAlert"] {
                background: var(--yn-card) !important;
                border: 1px solid var(--yn-border) !important;
                border-radius: 8px !important;
                box-shadow: none;
            }

            [data-testid="stFileUploader"] section {
                background: var(--yn-card-strong) !important;
                border: 1px dashed var(--yn-border) !important;
                border-radius: 8px !important;
            }

            [data-testid="stFileUploader"] section:hover {
                border-color: var(--yn-accent) !important;
            }

            .stProgress > div > div > div > div {
                background-color: var(--yn-accent) !important;
            }

            hr {
                border-color: var(--yn-border);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
