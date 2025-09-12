from __future__ import annotations
import streamlit as st
import pandas as pd
from pandas.tseries.offsets import MonthEnd

from core.config import MES_A_NUM, NUM_A_MES


def render_filters(years_all: list[int], categories: list[str]):
    c1, c2, c3 = st.columns([2, 3, 2])

    with c1:
        category = st.selectbox("Categoría", categories, index=0)

    with c2:
        cc1, cc2 = st.columns(2)
        with cc1:
            y_start = st.selectbox("Año inicio", options=years_all, index=0)
            m_start = st.selectbox("Mes inicio", options=[n for n in NUM_A_MES.values()], index=0)
        with cc2:
            y_end = st.selectbox("Año fin", options=years_all, index=len(years_all) - 1)
            m_end = st.selectbox("Mes fin", options=[n for n in NUM_A_MES.values()], index=11)

    with c3:
        mode = st.radio("Modo de gráfica", ["Acumulada (rango completo)", "Una por año"], index=0)

    # Validación rango
    start_key = (int(y_start), MES_A_NUM[m_start])
    end_key = (int(y_end), MES_A_NUM[m_end])
    if start_key > end_key:
        st.warning("El inicio debe ser anterior (o igual) al fin.")
        st.stop()

    x0 = pd.Timestamp(int(y_start), MES_A_NUM[m_start], 1)
    x1 = pd.Timestamp(int(y_end), MES_A_NUM[m_end], 1) + MonthEnd(1)

    return category, x0, x1, mode