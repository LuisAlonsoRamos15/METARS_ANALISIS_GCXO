# -*- coding: utf-8 -*-
# App Streamlit que LEE el Excel ya calculado: ratios_aeronaves_mensual_2014_2025.xlsx
# Usa 'Top90d_por_año' y (si existe) 'Ratios_diarios' para dibujar.
# Ejecuta:  streamlit run app.py

from __future__ import annotations

import io
from pathlib import Path
from typing import List, Tuple, Dict

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ============ Config ============ #
st.set_page_config(page_title="Top 90 días (desde Excel de ratios)", layout="wide")

DEFAULT_RATIOS_XLSX = "ratios_aeronaves_mensual_2014_2025.xlsx"

COLORS = {
    "daily":   "#7F8C8D",
    "ma7":     "#111111",
    "top1":    "#2E7D32",
    "top2":    "#F39C12",
    "top3":    "#1F77B4",
    "bgband":  "rgba(0,0,0,0.06)",
}

# ============ Utilidades ============ #
def temporada_bounds_from_year(y: int):
    """Temporada: 1 Oct (y) -> 30 Sep (y+1)"""
    ini = pd.Timestamp(year=y, month=10, day=1)
    fin = pd.Timestamp(year=y+1, month=9, day=30)
    return ini, fin

def calendario_bounds_from_year(y: int):
    ini = pd.Timestamp(year=y, month=1, day=1)
    fin = pd.Timestamp(year=y, month=12, day=31)
    return ini, fin

@st.cache_data(show_spinner=True)
def load_from_ratios_excel(file_bytes: bytes) -> Dict:
    """Carga Top90 y Ratios diarios desde el Excel de ratios."""
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    sheets = set(xls.sheet_names)

    # --- Top90 obligatorio ---
    if "Top90d_por_año" not in sheets:
        raise ValueError("El Excel no contiene la hoja requerida 'Top90d_por_año'.")

    top90 = pd.read_excel(xls, sheet_name="Top90d_por_año")

    # Normalizar nombres de columnas (tolerar acentos)
    colmap = {}
    if "Aerolinea" in top90.columns: colmap["Aerolinea"] = "Aerolínea"
    if "Año" in top90.columns: colmap["Año"] = "Año"
    if "Ano" in top90.columns: colmap["Ano"] = "Año"
    if "Inicio_90d" in top90.columns: colmap["Inicio_90d"] = "Inicio_90d"
    if "Fin_90d" in top90.columns: colmap["Fin_90d"] = "Fin_90d"
    if "Ratio_90d" in top90.columns: colmap["Ratio_90d"] = "Ratio_90d"
    top90 = top90.rename(columns=colmap)

    required = {"Aerolínea","Año","Inicio_90d","Fin_90d","Ratio_90d"}
    missing = required - set(top90.columns)
    if missing:
        raise ValueError(f"Faltan columnas en 'Top90d_por_año': {missing}")

    top90["Inicio_90d"] = pd.to_datetime(top90["Inicio_90d"])
    top90["Fin_90d"] = pd.to_datetime(top90["Fin_90d"])

    # Etiquetar TOP 1/2/3 por (Aerolínea, Año) ordenando por Ratio_90d desc
    top90 = (
        top90.sort_values(["Aerolínea","Año","Ratio_90d"], ascending=[True, True, False])
             .assign(TOP=lambda d: d.groupby(["Aerolínea","Año"]).cumcount()+1)
    )

    # --- Ratios diarios opcional (recomendado para graficar) ---
    ratio_day = None
    ratio_ma7 = None
    airlines = sorted(top90["Aerolínea"].astype(str).unique().tolist())

    if "Ratios_diarios" in sheets:
        rd = pd.read_excel(xls, sheet_name="Ratios_diarios")
        # Intentar detectar columna de fecha
        date_col = None
        for cand in ["Fecha","fecha","date","Date","index"]:
            if cand in rd.columns:
                date_col = cand
                break
        if date_col is None:
            # si guardaste con índice de fecha sin nombre, podría venir como primera columna
            date_col = rd.columns[0]

        rd[date_col] = pd.to_datetime(rd[date_col], errors="coerce")
        rd = rd[rd[date_col].notna()].copy().sort_values(date_col).set_index(date_col)

        # Aerolíneas = intersección entre columnas de diarios y del Top90
        cols_aer = [c for c in rd.columns if c in set(airlines)]
        if cols_aer:
            ratio_day = rd[cols_aer].astype(float)
            ratio_ma7 = ratio_day.rolling(window=7, min_periods=1).mean()
            airlines = cols_aer  # usar sólo las que tienen serie diaria

    return dict(
        top90=top90,
        ratio_day=ratio_day,  # puede ser None si no existe hoja
        ratio_ma7=ratio_ma7,  # idem
        airlines=airlines,
    )

def make_figure(ser_daily: pd.Series, ser_ma7: pd.Series,
                top_rows: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()

    fig.add_hrect(y0=0, y1=1, line_width=0, fillcolor=COLORS["bgband"], opacity=0.35)

    # Línea base + MA7
    fig.add_trace(go.Scatter(
        x=ser_daily.index, y=ser_daily.values,
        mode="lines", line=dict(color=COLORS["daily"], width=2),
        name="Ratio diario"
    ))
    fig.add_trace(go.Scatter(
        x=ser_ma7.index, y=ser_ma7.values,
        mode="lines", line=dict(color=COLORS["ma7"], width=3),
        name="Media móvil 7d"
    ))

    color_map = {1: COLORS["top1"], 2: COLORS["top2"], 3: COLORS["top3"]}
    legend_used = {1: False, 2: False, 3: False}

    for _, row in top_rows.sort_values("TOP").iterrows():
        s = pd.to_datetime(row["Inicio_90d"])
        e = pd.to_datetime(row["Fin_90d"])
        color = color_map.get(int(row["TOP"]), "#000000")

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
        fig.add_annotation(
            x=mid, y=y_mid,
            text=f"TOP {int(row['TOP'])}<br>{row['Ratio_90d']:.0%}",
            showarrow=False, bgcolor="white",
            bordercolor=color, borderwidth=1, opacity=0.95
        )

    fig.update_layout(
        title=title,
        margin=dict(l=50, r=20, t=70, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        yaxis=dict(title="Ratio", range=[0, 1], tickformat=".0%"),
        xaxis=dict(title="Fecha")
    )
    return fig

# ============ UI ============ #
st.title("📊 Top 90 días por aerolínea (desde Excel de ratios)")
st.caption("Lee 'Top90d_por_año' y (si está) 'Ratios_diarios' del Excel generado. Pinta TOP 1/2/3 y permite vista por temporada o calendario.")

with st.sidebar:
    st.header("1) Archivo de ratios")
    modo = st.radio("Origen", ["Ruta local", "Subir Excel"], index=0)

data = None
if modo == "Ruta local":
    ruta = st.sidebar.text_input("Ruta del Excel de ratios", value=DEFAULT_RATIOS_XLSX)
    if not ruta.strip():
        st.stop()
    p = Path(ruta)
    if not p.exists():
        st.error(f"No encuentro el archivo: {p}")
        st.stop()
    try:
        data = load_from_ratios_excel(p.read_bytes())
        st.sidebar.success(f"Cargado: {p.name}")
    except Exception as e:
        st.error(f"Error leyendo el Excel: {e}")
        st.stop()
else:
    up = st.sidebar.file_uploader("Sube el Excel de ratios (*.xlsx)", type=["xlsx"])
    if up is None:
        st.info("Sube el Excel o usa la opción de 'Ruta local'.")
        st.stop()
    try:
        data = load_from_ratios_excel(up.getvalue())
        st.sidebar.success("Archivo subido y cargado.")
    except Exception as e:
        st.error(f"Error leyendo el Excel: {e}")
        st.stop()

top90: pd.DataFrame = data["top90"]
ratio_day: pd.DataFrame | None = data["ratio_day"]
ratio_ma7: pd.DataFrame | None = data["ratio_ma7"]
airlines: List[str] = data["airlines"]

# Filtros
st.header("2) Filtros")
c1, c2, c3 = st.columns([2,1,1])
with c1:
    sel_airlines = st.multiselect("Aerolíneas", options=airlines, default=airlines[:min(4,len(airlines))])
with c2:
    years_all = sorted(top90["Año"].unique().tolist())
    sel_years = st.multiselect("Año(s)", options=years_all, default=years_all)
with c3:
    view_mode = st.radio("Eje temporal", ["Temporada (oct–sep)", "Calendario (ene–dic)"], index=0)

if not sel_airlines or not sel_years:
    st.warning("Selecciona al menos una aerolínea y un año.")
    st.stop()

# Aviso si no hay serie diaria
if ratio_day is None or ratio_ma7 is None:
    st.warning("La hoja 'Ratios_diarios' no está en el Excel. No se dibujarán las curvas diarias; "
               "sólo se listarán las ventanas TOP en la tabla inferior.")
else:
    st.header("3) Gráficas")
    for aer in sel_airlines:
        sub_top = top90[(top90["Aerolínea"] == aer) & (top90["Año"].isin(sel_years))].copy()
        if sub_top.empty:
            st.info(f"No hay TOPs para **{aer}** en los años seleccionados.")
            continue

        st.subheader(aer)
        cols = st.columns(2)
        col_i = 0
        for y in sorted(sub_top["Año"].unique()):
            if view_mode == "Temporada (oct–sep)":
                ini, fin = temporada_bounds_from_year(int(y))
                subtitle = f"Temporada {y}-{y+1}"
            else:
                ini, fin = calendario_bounds_from_year(int(y))
                subtitle = f"Año {y}"

            if aer not in ratio_day.columns:
                continue
            ser = ratio_day[aer].loc[(ratio_day.index >= ini) & (ratio_day.index <= fin)].dropna()
            if ser.empty:
                continue
            ser_ma7 = ratio_ma7[aer].loc[ser.index]

            top_rows = sub_top[sub_top["Año"] == y].sort_values("TOP").head(3)
            fig = make_figure(ser, ser_ma7, top_rows, f"{subtitle} — TOP 3 ventanas de 90 días")

            with cols[col_i % 2]:
                st.plotly_chart(fig, use_container_width=True)
            col_i += 1

# Tabla de resultados (siempre)
st.header("4) Ventanas TOP (tabla)")
show = top90[top90["Aerolínea"].isin(sel_airlines) & top90["Año"].isin(sel_years)]
st.dataframe(show.sort_values(["Aerolínea","Año","TOP"]))
csv = show.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Descargar TOPs (CSV)", data=csv, file_name="top90_por_anio_desde_excel.csv", mime="text/csv")

st.caption("Lee directamente el Excel de ratios. Si quieres curvas diarias, asegúrate de incluir la hoja 'Ratios_diarios' al generarlo.")
