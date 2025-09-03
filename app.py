# -*- coding: utf-8 -*-
# Streamlit: leer 'ratios_aeronaves_mensual_2014_2025.xlsx'
# Selección: Aerolíneas + Año + Mes inicio/fin (mismo año)
# Muestra curvas diarias (si existe 'Ratios_diarios') y sombrea TOP 1/2/3 (90d) del año.
# Soluciona StreamlitDuplicateElementId con keys únicos.

from __future__ import annotations

import io
from pathlib import Path
from typing import List, Dict

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pandas.tseries.offsets import MonthEnd

st.set_page_config(page_title="Top 90 días (Excel ratios)", layout="wide")

DEFAULT_RATIOS_XLSX = "ratios_aeronaves_mensual_2014_2025.xlsx"

COLORS = {
    "daily":   "#7F8C8D",
    "ma7":     "#111111",
    "top1":    "#2E7D32",
    "top2":    "#F39C12",
    "top3":    "#1F77B4",
    "bgband":  "rgba(0,0,0,0.06)",
}

MESES = [
    ("Enero", 1), ("Febrero", 2), ("Marzo", 3), ("Abril", 4),
    ("Mayo", 5), ("Junio", 6), ("Julio", 7), ("Agosto", 8),
    ("Septiembre", 9), ("Octubre",10), ("Noviembre",11), ("Diciembre",12)
]
MES_A_NUM = {n:i for n,i in MESES}

# ---------- carga desde el Excel de ratios ----------
@st.cache_data(show_spinner=True)
def load_from_ratios_excel(file_bytes: bytes) -> Dict:
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    sheets = set(xls.sheet_names)

    if "Top90d_por_año" not in sheets:
        raise ValueError("Falta la hoja 'Top90d_por_año' en el Excel.")

    top90 = pd.read_excel(xls, sheet_name="Top90d_por_año")
    # normaliza nombres
    if "Aerolinea" in top90.columns:
        top90 = top90.rename(columns={"Aerolinea": "Aerolínea"})
    if "Ano" in top90.columns:
        top90 = top90.rename(columns={"Ano": "Año"})

    required = {"Aerolínea","Año","Inicio_90d","Fin_90d","Ratio_90d"}
    missing = required - set(top90.columns)
    if missing:
        raise ValueError(f"Faltan columnas en 'Top90d_por_año': {missing}")

    top90["Inicio_90d"] = pd.to_datetime(top90["Inicio_90d"])
    top90["Fin_90d"]    = pd.to_datetime(top90["Fin_90d"])

    # asegura TOP 1/2/3 por (Aerolínea, Año)
    if "TOP" not in top90.columns:
        top90 = (
            top90.sort_values(["Aerolínea","Año","Ratio_90d"], ascending=[True, True, False])
                 .assign(TOP=lambda d: d.groupby(["Aerolínea","Año"]).cumcount()+1)
        )

    airlines = sorted(top90["Aerolínea"].astype(str).unique().tolist())

    ratio_day = ratio_ma7 = None
    if "Ratios_diarios" in sheets:
        rd = pd.read_excel(xls, sheet_name="Ratios_diarios")
        # detectar columna de fecha
        date_col = None
        for cand in ["Fecha","fecha","date","Date","index"]:
            if cand in rd.columns:
                date_col = cand; break
        if date_col is None:
            date_col = rd.columns[0]
        rd[date_col] = pd.to_datetime(rd[date_col], errors="coerce")
        rd = rd[rd[date_col].notna()].copy().sort_values(date_col).set_index(date_col)

        # usar sólo aerolíneas presentes en los diarios
        cols = [c for c in rd.columns if c in set(airlines)]
        if cols:
            ratio_day = rd[cols].astype(float)
            ratio_ma7 = ratio_day.rolling(window=7, min_periods=1).mean()
            airlines = cols

    return {"top90": top90, "ratio_day": ratio_day, "ratio_ma7": ratio_ma7, "airlines": airlines}

def make_figure(ser_daily: pd.Series, ser_ma7: pd.Series,
                top_rows: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=1, line_width=0, fillcolor=COLORS["bgband"], opacity=0.35)
    fig.add_trace(go.Scatter(x=ser_daily.index, y=ser_daily.values,
                             mode="lines", line=dict(color=COLORS["daily"], width=2),
                             name="Ratio diario"))
    fig.add_trace(go.Scatter(x=ser_ma7.index, y=ser_ma7.values,
                             mode="lines", line=dict(color=COLORS["ma7"], width=3),
                             name="Media móvil 7d"))

    color_map = {1: COLORS["top1"], 2: COLORS["top2"], 3: COLORS["top3"]}
    legend_used = {1: False, 2: False, 3: False}

    for _, row in top_rows.sort_values("TOP").iterrows():
        s = pd.to_datetime(row["Inicio_90d"])
        e = pd.to_datetime(row["Fin_90d"])
        color = color_map.get(int(row["TOP"]), "#000")
        fig.add_vrect(x0=s, x1=e, fillcolor=color, opacity=0.18, line_width=0)

        m = (ser_ma7.index >= s) & (ser_ma7.index <= e)
        if m.any():
            fig.add_trace(go.Scatter(
                x=ser_ma7.index[m], y=ser_ma7[m].values,
                mode="lines", line=dict(color=color, width=7),
                name=f"TOP {int(row['TOP'])} (90d)",
                showlegend=not legend_used[int(row["TOP"])]
            ))
            legend_used[int(row["TOP"])] = True

        mid = s + (e - s) / 2
        y_mid = np.nanmedian(ser_ma7[(ser_ma7.index >= s) & (ser_ma7.index <= e)].values) if m.any() else 0.6
        fig.add_annotation(x=mid, y=y_mid,
                           text=f"TOP {int(row['TOP'])}<br>{row['Ratio_90d']:.0%}",
                           showarrow=False, bgcolor="white",
                           bordercolor=color, borderwidth=1, opacity=0.95)

    fig.update_layout(
        title=title,
        margin=dict(l=50, r=20, t=70, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        yaxis=dict(title="Ratio", range=[0, 1], tickformat=".0%"),
        xaxis=dict(title="Fecha"),
    )
    return fig

# ---------- UI ----------
st.title("📊 Top 90 días por aerolínea (Excel de ratios)")
st.caption("Selecciona Aerolínea(s), **Año** y **Mes inicio/fin** (mismo año). Se sombrea TOP 1/2/3 (90 días).")

with st.sidebar:
    st.header("1) Archivo de ratios")
    origen = st.radio("Origen", ["Ruta local", "Subir Excel"], index=0)

data = None
if origen == "Ruta local":
    ruta = st.sidebar.text_input("Ruta del Excel", value=DEFAULT_RATIOS_XLSX)
    p = Path(ruta)
    if not p.exists():
        st.error(f"No encuentro el archivo: {p.resolve()}")
        st.stop()
    data = load_from_ratios_excel(p.read_bytes())
else:
    up = st.sidebar.file_uploader("Sube el Excel de ratios (*.xlsx)", type=["xlsx"])
    if up is None:
        st.info("Sube el Excel o usa 'Ruta local'.")
        st.stop()
    data = load_from_ratios_excel(up.getvalue())

top90: pd.DataFrame = data["top90"]
ratio_day: pd.DataFrame | None = data["ratio_day"]
ratio_ma7: pd.DataFrame | None = data["ratio_ma7"]
airlines: List[str] = data["airlines"]

# -- Filtros superiores --
st.header("2) Filtros")
c1, c2, c3 = st.columns([2,1,2])
with c1:
    sel_airlines = st.multiselect("Aerolíneas", options=airlines, default=airlines[:min(4,len(airlines))])
with c2:
    years_all = sorted(top90["Año"].unique().tolist())
    year = st.selectbox("Año", options=years_all, index=0)
with c3:
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        mes_ini = st.selectbox("Mes inicio", options=[n for n,_ in MESES], index=0)
    with col_m2:
        mes_fin = st.selectbox("Mes fin", options=[n for n,_ in MESES], index=11)

if MES_A_NUM[mes_ini] > MES_A_NUM[mes_fin]:
    st.warning("El mes de inicio no puede ser posterior al mes fin (rango dentro del MISMO año).")
    st.stop()

# Rango temporal para gráficas
ini = pd.Timestamp(year=int(year), month=MES_A_NUM[mes_ini], day=1)
fin = pd.Timestamp(year=int(year), month=MES_A_NUM[mes_fin], day=1) + MonthEnd(1)

# ----- GRÁFICAS -----
if ratio_day is None or ratio_ma7 is None:
    st.warning("No está la hoja 'Ratios_diarios' en el Excel. Sólo se mostrará la tabla inferior.")
else:
    st.header("3) Gráficas")
    # grid 2 columnas, keys únicos para evitar DuplicateElementId
    cols = st.columns(2)
    idx = 0
    for aer in sel_airlines:
        if aer not in ratio_day.columns:
            st.info(f"No hay serie diaria para {aer}.")
            continue
        ser = ratio_day[aer].loc[(ratio_day.index >= ini) & (ratio_day.index <= fin)].dropna()
        if ser.empty:
            st.info(f"Sin datos diarios para {aer} en {mes_ini}–{mes_fin} {year}.")
            continue
        ser_ma7 = ratio_ma7[aer].loc[ser.index]

        # TOPs del año seleccionado (se recortan visualmente al rango)
        sub_top = (top90[(top90["Aerolínea"] == aer) & (top90["Año"] == int(year))]
                   .sort_values("TOP").head(3))
        fig = make_figure(ser, ser_ma7, sub_top, f"{aer} — {mes_ini}–{mes_fin} {year}")

        with cols[idx % 2]:
            st.plotly_chart(fig, use_container_width=True, key=f"chart-{aer}-{year}-{mes_ini}-{mes_fin}")
        idx += 1

# ----- TABLA (con key único) -----
st.header("4) Ventanas TOP (tabla)")
mask = (top90["Aerolínea"].isin(sel_airlines)) & (top90["Año"] == int(year))
tabla = top90.loc[mask, ["Aerolínea","Año","Inicio_90d","Fin_90d","Ratio_90d","VERDADEROS_90d","METARS_90d","TOP"]]
st.dataframe(
    tabla.sort_values(["Aerolínea","TOP"]),
    use_container_width=True,
    hide_index=True,
    key=f"tabla-{hash((tuple(sel_airlines), year, mes_ini, mes_fin))}"
)
st.download_button(
    "⬇️ Descargar TOPs filtrados (CSV)",
    data=tabla.to_csv(index=False).encode("utf-8"),
    file_name=f"top90_{year}_{MES_A_NUM[mes_ini]:02d}-{MES_A_NUM[mes_fin]:02d}.csv",
    mime="text/csv",
    key=f"dl-{hash((tuple(sel_airlines), year, mes_ini, mes_fin))}"
)
st.caption("Rango de meses dentro del mismo año. Los TOP se asignan por el año del día inicial y se sombrean únicamente en el tramo que cae dentro del rango.")
