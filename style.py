"""Shared page styling so all pages look consistent."""

import streamlit as st

CSS = """
<style>
  .block-container {padding-top: 2.2rem; max-width: 1400px;}
  h1, h2, h3 {letter-spacing: -0.01em;}
  .app-header {background: linear-gradient(90deg, #0f172a, #1e3a5f); color: #f8fafc; padding: 18px 24px;
               border-radius: 12px; margin-bottom: 18px;}
  .app-header h1 {color: #f8fafc; font-size: 1.6rem; margin: 0; padding: 0;}
  .app-header p {color: #cbd5e1; margin: 4px 0 0 0; font-size: 0.92rem;}
  .condition-card {border: 1px solid #e2e8f0; border-left: 5px solid #16a34a; border-radius: 10px;
                   padding: 10px 16px; background: #f8fafc; margin-bottom: 12px; font-size: 0.95rem;}
  .condition-card b.code {font-size: 1.15rem; color: #0f172a; margin-right: 8px;}
  div[data-testid="stMetric"] {background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 14px;}
  section[data-testid="stSidebar"] {background: #f1f5f9;}
  .small-note {color: #64748b; font-size: 0.85rem;}
</style>
"""


def apply_style():
    st.markdown(CSS, unsafe_allow_html=True)


def header(title, subtitle):
    st.markdown(f'<div class="app-header"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)
