# -*- coding: utf-8 -*-
from __future__ import annotations

from pandas.tseries.offsets import MonthEnd
import pandas as pd
import streamlit as st

from core.config import PAGE_TITLE, LAYOUT, MES_A_NUM, NUM_A_MES
from core.categories import CATEGORY_TOKENS, cols_for_category, category_series
from core.data import load_all
from core.analysis import rolling90_top1_by_year
from ui.filters import render_filters
from ui.sections import (
    section_main_charts,
    section_histogram,
    section_table_download,
    section_ils_compare,
    section_tfn_rwy30_monthly,
)

# Config de página
st.set_page_config(page_title=PAGE_TITLE, layout=LAYOUT)

st.title("Top 90 días — por categoría")

# ====== Carga ======
try:
    data = load_all()
except Exception as e:
    st.error(str(e))
    st.stop()

ratio_day = data["ratio_day"]
ils_col   = data["ils_col"]
years_all = data["years_all"]

# ====== 1) Filtros ======
st.header("1) Filtros")
category, x0, x1, mode = render_filters(years_all, list(CATEGORY_TOKENS.keys()))

# Serie por categoría
members = cols_for_category(ratio_day, category)
if not members:
    st.error(f"No encontré columnas que encajen con '{category}'. Ajusta CATEGORY_TOKENS.")
    st.stop()

ser_full  = category_series(ratio_day, members)
ser_range = ser_full.loc[(ser_full.index >= x0) & (ser_full.index <= x1)].dropna()

# ====== 2) Gráficas (principal) ======
st.header("2) Gráficas")

years_in_range = list(range(x0.year, x1.year + 1))
tops_cat = rolling90_top1_by_year(ser_full, years_in_range)

section_main_charts(ser_full, tops_cat, category, x0, x1, mode)

# ====== 3) Histograma: mes de inicio (moda) ======
section_histogram(tops_cat, category, x0, x1)

# ====== 4) Tabla + descarga CSV de TOPs ======
section_table_download(tops_cat, category, x0, x1)

# ====== 5) Comparativa ILS (solo gráficas) ======
st.header("Comparativa ILS (categoría vs ILS)")
ils_series = ratio_day[ils_col].astype(float)
section_ils_compare(ser_full, ils_series, ils_col, category, x0, x1)

# ====== 6) TFN RWY30 — Teórico vs Real (mensual) ======
st.header("TFN RWY30 — Teórico vs Real (mensual)")
section_tfn_rwy30_monthly(x0, x1)
