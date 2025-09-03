# -*- coding: utf-8 -*-
# Streamlit: lee internamente 'ratios_aeronaves_mensual_2014_2025.xlsx' (sin uploader)
# Filtros: Aerolíneas (multi), Rango de fechas libre (Año+Mes inicio/fin, puede cruzar años),
#          TOP (1 o 3) y Modo de gráfico (Acumulada / Una por año).
# Gráficas: ratio diario + MA7 y sombreado de TOP 90 días (por año, asignado al año del INICIO).
# Tabla: TOPs filtrados por aerolínea y años dentro del rango.

from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pandas.tseries.offsets import MonthEnd

st.set_page_config(page_title="Top 90 días (Excel ratios)", layout="wide")

# ---- Colores y meses ----
COLORS = {
    "daily":   "#7F8C8D",
    "ma7":     "#111111",
    "top1":    "#2E7D32",   # verde
    "top2":    "#F39C12",   # naranja
    "top3":    "#1F77B4",   # azul
    "bgband":  "rgba(0,0,0,0.06)",
}

MESES = [
    ("Enero", 1), ("Febrero", 2), ("Marzo", 3), ("Abril", 4),
    ("Mayo", 5), ("Junio", 6), ("Julio", 7), ("Agosto", 8),
    ("Septiembre", 9), ("Octubre",10), ("Noviembre",11), ("Diciembre",12)
]
MES_A_NUM = {n:i for n,i in MESES}
NUM_A_MES = {i:n for n,i in MESES}

# ---- Localización del Excel en el repo / entorno ----
PATH_CANDIDATES = [
    Path("ratios_aeronaves_mensual_2014_2025.xlsx"),
    Path("data/ratios_aeronaves_mensual_2014_2025.xlsx"),
    Path("/mnt/data/ratios_aeronaves_mensual_2014_2025.xlsx"),
]

# ---------- Carga desde el Excel de ratios ----------
@st.cache_data(show_spinner=True)
def load_from_ratios_excel() -> Dict:
    p = next((pp for pp in PATH_CANDIDATES if pp.exists()), None)
    if p is None:
        raise FileNotFoundError(
            "No encuentro 'ratios_aeronaves_mensual_2014_2025.xlsx' en las rutas esperadas."
        )

    xls = pd.ExcelFile(p)
    sheets = set(xls.sheet_names)

    if "Top90d_por_año" not in sheets:
        raise ValueError("Falta la hoja 'Top90d_por_año' en el Excel.")

    top90 = pd.read_excel(xls, sheet_name="Top90d_por_año")

    # normaliza nombres (tilde/ño)
    ren = {}
    if "Aerolinea" in top90.columns: ren["Aerolinea"] = "Aerolínea"
    if "Ano" in top90.columns: ren["Ano"] = "Año"
    top90 = top90.rename(columns=ren)

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

    # Serie diaria (opcional): si existe, mejor para graficar
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

        cols = [c for c in rd.columns if c in set(airlines)]
        if cols:
            ratio_day = rd[cols].astype(float)
            ratio_ma7 = ratio_day.rolling(window=7, min_periods=1).mean()
            airlines = cols  # limitar a las que tienen diarios

    return {"top90": top90, "ratio_day": ratio_day, "ratio_ma7": ratio_ma7, "airlines": airlines}

def year_ticks_lines(fig: go.Figure, start: pd.Timestamp, end: pd.Timestamp):
    """Añade líneas verticales en cada 1 de enero dentro del rango."""
    y = start.year + 1
    while y <= end.year:
        x = pd.Timestamp(year=y, month=1, day=1)
        fig.add_vline(x=x, line_width=1, line_dash="dot", line_color="#555555")
        y += 1

def make_figure(ser_daily: pd.Series, ser_ma7: pd.Series,
                top_rows_all_years: pd.DataFrame, title: str,
                x0: pd.Timestamp, x1: pd.Timestamp,
                mode: str) -> go.Figure:
    """mode: 'acumulada' (usa todos los TOP de los años del rango) / 'por_año' (filtra por año fuera)"""
    fig = go.Figure()
    # fondo
    fig.add_hrect(y0=0, y1=1, line_width=0, fillcolor=COLORS["bgband"], opacity=0.35)

    # líneas
    fig.add_trace(go.Scatter(x=ser_daily.index, y=ser_daily.values,
                             mode="lines", line=dict(color=COLORS["daily"], width=2),
                             name="Ratio diario"))
    fig.add_trace(go.Scatter(x=ser_ma7.index, y=ser_ma7.values,
                             mode="lines", line=dict(color=COLORS["ma7"], width=3),
                             name="Media móvil 7d"))

    color_map = {1: COLORS["top1"], 2: COLORS["top2"], 3: COLORS["top3"]}
    legend_used = {1: False, 2: False, 3: False}

    # Sombrear los TOP de todos los años dentro del rango (se recortan visualmente al [x0, x1])
    for _, row in top_rows_all_years.sort_values(["Año", "TOP"]).iterrows():
        s = pd.to_datetime(row["Inicio_90d"])
        e = pd.to_datetime(row["Fin_90d"])
        color = color_map.get(int(row["TOP"]), "#000")

        s_plot = max(s, x0)
        e_plot = min(e, x1)
        if s_plot > e_plot:
            continue

        fig.add_vrect(x0=s_plot, x1=e_plot, fillcolor=color, opacity=0.18, line_width=0)

        m = (ser_ma7.index >= s_plot) & (ser_ma7.index <= e_plot)
        if m.any():
            fig.add_trace(go.Scatter(
                x=ser_ma7.index[m], y=ser_ma7[m].values,
                mode="lines", line=dict(color=color, width=7),
                name=f"TOP {int(row['TOP'])} (90d) — {row['Año']}",
                showlegend=not legend_used[int(row["TOP"])]
            ))
            legend_used[int(row["TOP"])] = True

        mid = s_plot + (e_plot - s_plot) / 2
        y_mid = np.nanmedian(ser_ma7[(ser_ma7.index >= s_plot) & (ser_ma7.index <= e_plot)].values) if m.any() else 0.6
        fig.add_annotation(x=mid, y=y_mid,
                           text=f"TOP {int(row['TOP'])}<br>{row['Ratio_90d']:.0%}",
                           showarrow=False, bgcolor="white",
                           bordercolor=color, borderwidth=1, opacity=0.95)

    year_ticks_lines(fig, x0, x1)

    fig.update_layout(
        title=title,
        margin=dict(l=50, r=20, t=70, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        yaxis=dict(title="Ratio", range=[0, 1], tickformat=".0%"),
        xaxis=dict(title="Fecha"),
    )
    return fig

# ================================
# 1) FILTROS
# ================================
st.title("📊 Top 90 días por aerolínea (Excel de ratios)")

# Cargar datos (interno, sin mostrar ruta)
try:
    data = load_from_ratios_excel()
except Exception as e:
    st.error(str(e))
    st.stop()

top90: pd.DataFrame = data["top90"]
ratio_day: pd.DataFrame | None = data["ratio_day"]
ratio_ma7: pd.DataFrame | None = data["ratio_ma7"]
airlines: List[str] = data["airlines"]

st.header("1) Filtros")
c1, c2, c3 = st.columns([2, 3, 2])

with c1:
    sel_airlines = st.multiselect("Aerolíneas", options=airlines, default=airlines[:min(4, len(airlines))])
    top_k = st.radio("TOP de 90 días por año", ["1 (mejor)", "3 (mejores)"], index=0, horizontal=True)
    top_k = 1 if top_k.startswith("1") else 3

years_all = sorted(top90["Año"].unique().tolist())

with c2:
    # Rango de fechas libre (Año+Mes inicio/fin)
    cc1, cc2 = st.columns(2)
    with cc1:
        year_start = st.selectbox("Año inicio", options=years_all, index=0)
        month_start = st.selectbox("Mes inicio", options=[n for n,_ in MESES], index=0)
    with cc2:
        year_end = st.selectbox("Año fin", options=years_all, index=len(years_all)-1)
        month_end = st.selectbox("Mes fin", options=[n for n,_ in MESES], index=11)

with c3:
    mode_graph = st.radio("Modo de gráfico", ["Acumulada (rango completo)", "Una por año"], index=0)

if not sel_airlines:
    st.warning("Selecciona al menos una aerolínea.")
    st.stop()

# Validar rango
start_key = (int(year_start), MES_A_NUM[month_start])
end_key   = (int(year_end),   MES_A_NUM[month_end])
if start_key > end_key:
    st.warning("El inicio debe ser anterior (o igual) al fin.")
    st.stop()

x0 = pd.Timestamp(year=int(year_start), month=MES_A_NUM[month_start], day=1)
x1 = pd.Timestamp(year=int(year_end),   month=MES_A_NUM[month_end],   day=1) + MonthEnd(1)

# ================================
# 2) GRÁFICAS
# ================================
st.header("2) Gráficas")

if ratio_day is None or ratio_ma7 is None:
    st.warning("No está la hoja 'Ratios_diarios' en el Excel. Sólo se muestra la tabla de TOPs.")
else:
    if mode_graph.startswith("Acumulada"):
        # Una figura por aerolínea, usando TODOS los TOP de los años tocados por [x0,x1]
        for aer in sel_airlines:
            if aer not in ratio_day.columns:
                st.info(f"No hay serie diaria para {aer}.")
                continue
            ser = ratio_day[aer].loc[(ratio_day.index >= x0) & (ratio_day.index <= x1)].dropna()
            if ser.empty:
                st.info(f"{aer} — sin datos entre {NUM_A_MES[x0.month]} {x0.year} y {NUM_A_MES[x1.month]} {x1.year}")
                continue
            ser_ma7 = ratio_ma7[aer].loc[ser.index]

            # TOPs: tomar por cada año del rango los primeros K
            years_in_range = list(range(x0.year, x1.year + 1))
            tops = (top90[(top90["Aerolínea"] == aer) & (top90["Año"].isin(years_in_range))]
                    .sort_values(["Año","TOP"])
                    .groupby("Año")
                    .head(top_k))
            title = f"{aer} — {NUM_A_MES[x0.month]} {x0.year} – {NUM_A_MES[x1.month]} {x1.year}"
            fig = make_figure(ser, ser_ma7, tops, title, x0, x1, mode="acumulada")
            st.plotly_chart(fig, use_container_width=True, key=f"chart-acc-{aer}-{x0}-{x1}-{top_k}")

    else:
        # Una figura por aerolínea × año dentro del rango
        cols = st.columns(2)
        idx = 0
        for aer in sel_airlines:
            if aer not in ratio_day.columns:
                with cols[idx % 2]:
                    st.info(f"No hay serie diaria para {aer}.")
                idx += 1
                continue

            for y in range(x0.year, x1.year + 1):
                y0 = max(pd.Timestamp(year=y, month=1,  day=1), x0)
                y1 = min(pd.Timestamp(year=y, month=12, day=31) + MonthEnd(0), x1)

                ser = ratio_day[aer].loc[(ratio_day.index >= y0) & (ratio_day.index <= y1)].dropna()
                if ser.empty:
                    continue
                ser_ma7 = ratio_ma7[aer].loc[ser.index]

                tops_y = (top90[(top90["Aerolínea"] == aer) & (top90["Año"] == y)]
                          .sort_values("TOP").head(top_k))
                title = f"{aer} — {y} ({NUM_A_MES[y0.month]}–{NUM_A_MES[y1.month]})"
                fig = make_figure(ser, ser_ma7, tops_y, title, y0, y1, mode="por_año")
                with cols[idx % 2]:
                    st.plotly_chart(fig, use_container_width=True, key=f"chart-year-{aer}-{y}-{y0.month}-{y1.month}-{top_k}")
                idx += 1

# ================================
# 3) TABLA
# ================================
st.header("3) Ventanas TOP (tabla)")

years_mask = (top90["Año"] >= x0.year) & (top90["Año"] <= x1.year)
mask = (top90["Aerolínea"].isin(sel_airlines)) & years_mask

tabla_cols = ["Aerolínea","Año","Inicio_90d","Fin_90d","Ratio_90d","VERDADEROS_90d","METARS_90d","TOP"]
tabla_cols = [c for c in tabla_cols if c in top90.columns]

tabla = (top90.loc[mask, tabla_cols]
         .sort_values(["Aerolínea","Año","TOP"])
         .groupby(["Aerolínea","Año"], as_index=False)
         .head(top_k))

st.dataframe(
    tabla,
    use_container_width=True,
    hide_index=True,
    key=f"tabla-{hash((tuple(sel_airlines), x0.year, x1.year, x0.month, x1.month, top_k))}"
)

st.download_button(
    "⬇️ Descargar TOPs filtrados (CSV)",
    data=tabla.to_csv(index=False).encode("utf-8"),
    file_name=f"top90_{x0.year}-{x1.year}_{x0.month:02d}-{x1.month:02d}_top{top_k}.csv",
    mime="text/csv",
    key=f"dl-{hash((tuple(sel_airlines), x0.year, x1.year, x0.month, x1.month, top_k))}"
)

st.caption("Los TOP se asignan al **año del día inicial**. En modo *Acumulada* se ven todos los TOP de los años del rango en una misma línea temporal con separadores de año.")
