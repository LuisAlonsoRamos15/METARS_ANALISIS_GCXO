# -*- coding: utf-8 -*-
# Streamlit – Top 90d por categoría + Comparativa ILS (comparando columnas de Ratios_diarios)
# Carga interna del Excel 'ratios_aeronaves_mensual_2014_2025.xlsx' (en ./, ./data o /mnt/data)

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pandas.tseries.offsets import MonthEnd

st.set_page_config(page_title="Top 90 días — categorías", layout="wide")

# ====== Rutas candidatas (carga interna) ======
PATHS = [
    Path("ratios_aeronaves_mensual_2014_2025.xlsx"),
    Path("data/ratios_aeronaves_mensual_2014_2025.xlsx"),
    Path("/mnt/data/ratios_aeronaves_mensual_2014_2025.xlsx"),
]

# ====== Apariencia / colores ======
COLORS = {
    "daily": "#E74C3C",   # rojo: categoría (diario)
    "ma7":   "#111111",   # MA7 para panel principal
    "top1":  "#2E7D32",   # sombreado TOP
    "bgband":"rgba(0,0,0,0.06)",
    "ils":   "#2ECC71",   # verde: ILS (columna elegida)
    "diff+": "#2ECC71",   # diferencia positiva (cat > ILS)
    "diff-": "#E67E22",   # diferencia negativa (cat < ILS)
}

MESES = [
    ("Enero", 1), ("Febrero", 2), ("Marzo", 3), ("Abril", 4),
    ("Mayo", 5), ("Junio", 6), ("Julio", 7), ("Agosto", 8),
    ("Septiembre", 9), ("Octubre",10), ("Noviembre",11), ("Diciembre",12)
]
MES_A_NUM = {n:i for n,i in MESES}
NUM_A_MES = {i:n for n,i in MESES}

WINDOW_DAYS = 90

# ====== Categorías (tokens para buscar columnas) ======
CATEGORY_TOKENS: Dict[str, List[str]] = {
    "CLAVE C y D": [
        "AEA","RYR","VLG","VUELING","IBE","IBERIA","EZY","U2",
        "A320","A321","B737","B738","B739","B38M","B38X"
    ],
    "E295": ["E295","E190","E195"],
    "AT76": ["AT76","ATR72"],
    "AT75": ["AT75","ATR72-500","ATR75"],
}

# ========= Utilidades =========
def _find_path() -> Path:
    p = next((pp for pp in PATHS if pp.exists()), None)
    if p is None:
        raise FileNotFoundError("No encuentro 'ratios_aeronaves_mensual_2014_2025.xlsx' en ./, ./data o /mnt/data")
    return p

@st.cache_data(show_spinner=True)
def load_all() -> Dict:
    """
    Lee:
      - 'Top90d_por_año' (obligatoria) -> nos quedamos con TOP=1 por año
      - 'Ratios_diarios' (obligatoria para gráficas): ratios diarios por columna, incluida(s) columna(s) ILS
    """
    xls = pd.ExcelFile(_find_path())
    sheets = set(xls.sheet_names)

    if "Top90d_por_año" not in sheets:
        raise ValueError("Falta la hoja 'Top90d_por_año' en el Excel.")
    top90 = pd.read_excel(xls, sheet_name="Top90d_por_año")
    ren = {}
    if "Aerolinea" in top90.columns: ren["Aerolinea"] = "Aerolínea"
    if "Ano" in top90.columns: ren["Ano"] = "Año"
    top90 = top90.rename(columns=ren)

    need = {"Aerolínea","Año","Inicio_90d","Fin_90d","Ratio_90d"}
    miss = need - set(top90.columns)
    if miss:
        raise ValueError(f"En 'Top90d_por_año' faltan columnas: {miss}")

    top90["Inicio_90d"] = pd.to_datetime(top90["Inicio_90d"])
    top90["Fin_90d"]    = pd.to_datetime(top90["Fin_90d"])

    # TOP=1 por (Aerolínea, Año)
    if "TOP" in top90.columns:
        top90_top1 = (top90.sort_values(["Aerolínea","Año","Ratio_90d"], ascending=[True, True, False])
                           .groupby(["Aerolínea","Año"], as_index=False).head(1))
    else:
        top90_top1 = top90.copy()

    if "Ratios_diarios" not in sheets:
        raise ValueError("Falta la hoja 'Ratios_diarios' en el Excel.")

    rd = pd.read_excel(xls, sheet_name="Ratios_diarios")

    # detectar columna de fecha
    date_col = None
    for cand in ["Fecha","FECHA","fecha","date","Date","index"]:
        if cand in rd.columns:
            date_col = cand; break
    if date_col is None:
        date_col = rd.columns[0]

    rd[date_col] = pd.to_datetime(rd[date_col], errors="coerce")
    rd = rd[rd[date_col].notna()].copy().sort_values(date_col).set_index(date_col)

    # numéricas
    num_cols = [c for c in rd.columns if np.issubdtype(rd[c].dtype, np.number)]
    ratio_day = rd[num_cols].astype(float)
    ratio_ma7 = ratio_day.rolling(window=7, min_periods=1).mean()

    # columnas ILS candidatas
    ils_cols = [c for c in ratio_day.columns if "ils" in c.lower()]
    # prefijar ILS Cat.1 si existe
    default_ils = "ILS Cat.1" if "ILS Cat.1" in ratio_day.columns else (ils_cols[0] if ils_cols else None)

    return {
        "top90_top1": top90_top1,
        "ratio_day": ratio_day,
        "ratio_ma7": ratio_ma7,
        "ils_cols": ils_cols,
        "default_ils": default_ils,
        "all_years": sorted(top90_top1["Año"].unique().tolist())
    }

def cols_for_category(ratio_day: pd.DataFrame, category: str) -> List[str]:
    toks = [t.upper() for t in CATEGORY_TOKENS.get(category, [])]
    return [c for c in ratio_day.columns if any(t in c.upper() for t in toks)]

def category_series(ratio_day: pd.DataFrame, members: List[str]) -> pd.Series:
    return ratio_day[members].mean(axis=1, skipna=True) if members else pd.Series(dtype=float)

def rolling90_top1_by_year(series: pd.Series, years: List[int]) -> pd.DataFrame:
    s = series.sort_index()
    r90 = s.rolling(WINDOW_DAYS, min_periods=WINDOW_DAYS).mean().dropna()
    out = []
    for y in years:
        candidates = []
        for end_ts, val in r90.items():
            start_ts = end_ts - pd.Timedelta(days=WINDOW_DAYS-1)
            if start_ts.year == y:
                candidates.append((start_ts, end_ts, float(val)))
        if not candidates: 
            continue
        start_best, end_best, v = max(candidates, key=lambda t: t[2])
        out.append({"Año": y, "Inicio_90d": start_best, "Fin_90d": end_best, "Ratio_90d": v})
    return pd.DataFrame(out)

def year_lines(fig: go.Figure, start: pd.Timestamp, end: pd.Timestamp):
    y = start.year + 1
    while y <= end.year:
        fig.add_vline(x=pd.Timestamp(y,1,1), line_width=1, line_dash="dot", line_color="#555")
        y += 1

def figure_main(ser: pd.Series, ser_ma7: pd.Series,
                tops: pd.DataFrame, title: str,
                x0: pd.Timestamp, x1: pd.Timestamp) -> go.Figure:
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=1, line_width=0, fillcolor=COLORS["bgband"], opacity=0.35)
    fig.add_trace(go.Scatter(x=ser.index, y=ser.values, mode="lines",
                             line=dict(color=COLORS["daily"], width=2), name="Ratio diario (categoría)"))
    fig.add_trace(go.Scatter(x=ser_ma7.index, y=ser_ma7.values, mode="lines",
                             line=dict(color=COLORS["ma7"], width=3), name="Media móvil 7d"))
    # sombreado de TOP por año (sin leyenda)
    for _, row in tops.sort_values("Año").iterrows():
        s = pd.to_datetime(row["Inicio_90d"])
        e = pd.to_datetime(row["Fin_90d"])
        s_plot, e_plot = max(s, x0), min(e, x1)
        if s_plot > e_plot: 
            continue
        fig.add_vrect(x0=s_plot, x1=e_plot, fillcolor=COLORS["top1"], opacity=0.18, line_width=0)
        mid = s_plot + (e_plot - s_plot)/2
        y_mid = float(np.nanmedian(ser_ma7[(ser_ma7.index >= s_plot) & (ser_ma7.index <= e_plot)].values)) if not ser_ma7.empty else 0.6
        fig.add_annotation(x=mid, y=y_mid, text=f"{row['Ratio_90d']:.0%}",
                           showarrow=False, bgcolor="white",
                           bordercolor=COLORS["top1"], borderwidth=1, opacity=0.95)

    year_lines(fig, x0, x1)
    fig.update_layout(
        title=title,
        margin=dict(l=50, r=20, t=70, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        yaxis=dict(title="Ratio", range=[0,1], tickformat=".0%"),
        xaxis=dict(title="Fecha"),
    )
    return fig

def ils_compare_timeseries(cat: pd.Series, ils: pd.Series,
                           x0: pd.Timestamp, x1: pd.Timestamp, title: str) -> go.Figure:
    """Comparativa: línea roja = categoría (diario), línea verde = columna ILS (diario)"""
    # alinear y recortar
    idx = cat.index.union(ils.index)
    cat_u = cat.reindex(idx).interpolate(limit_direction="both")
    ils_u = ils.reindex(idx).interpolate(limit_direction="both")
    m = (idx >= x0) & (idx <= x1)
    cat_u, ils_u = cat_u[m], ils_u[m]

    fig = go.Figure()
    fig.add_hrect(y0=0, y1=1, line_width=0, fillcolor=COLORS["bgband"], opacity=0.25)
    fig.add_trace(go.Scatter(x=cat_u.index, y=cat_u.values, mode="lines",
                             name="Categoría (diario)", line=dict(color=COLORS["daily"], width=2)))
    fig.add_trace(go.Scatter(x=ils_u.index, y=ils_u.values, mode="lines",
                             name="ILS (diario)", line=dict(color=COLORS["ils"], width=2)))
    year_lines(fig, x0, x1)
    fig.update_layout(
        title=title,
        yaxis=dict(title="Ratio", range=[0,1], tickformat=".0%"),
        xaxis=dict(title="Fecha"),
        legend=dict(orientation="h", y=1.02),
        margin=dict(l=50, r=20, t=70, b=40),
    )
    return fig

def ils_diff_chart(cat: pd.Series, ils: pd.Series,
                   x0: pd.Timestamp, x1: pd.Timestamp, title: str) -> go.Figure:
    """Barras de diferencia (cat − ILS). Verdes si cat>ILS; naranjas si cat<ILS."""
    idx = cat.index.union(ils.index)
    cat_u = cat.reindex(idx).interpolate(limit_direction="both")
    ils_u = ils.reindex(idx).interpolate(limit_direction="both")
    m = (idx >= x0) & (idx <= x1)
    idx, diff = idx[m], (cat_u - ils_u)[m]

    fig = go.Figure()
    colors = np.where(diff >= 0, COLORS["diff+"], COLORS["diff-"])
    fig.add_bar(x=idx, y=diff.values, marker_color=list(colors))
    fig.add_hline(y=0, line_width=1, line_dash="dot", line_color="#555")
    fig.update_layout(
        title=title,
        yaxis=dict(title="Cat − ILS", tickformat="+.0%"),
        xaxis=dict(title="Fecha"),
        margin=dict(l=50, r=20, t=60, b=40),
    )
    return fig

# =============== 1) FILTROS ===============
st.title("📊 Top 90 días — por categoría")

# Carga
try:
    data = load_all()
except Exception as e:
    st.error(str(e))
    st.stop()

top90_top1: pd.DataFrame = data["top90_top1"]
ratio_day: pd.DataFrame = data["ratio_day"]
ratio_ma7: pd.DataFrame = data["ratio_ma7"]
ils_cols:  List[str]     = data["ils_cols"]
default_ils: str | None  = data["default_ils"]
years_all: List[int]     = data["all_years"]

st.header("1) Filtros")
c1, c2, c3 = st.columns([2,3,3])

with c1:
    category = st.selectbox("Categoría", ["CLAVE C y D", "E295", "AT76", "AT75"], index=0)

with c2:
    cc1, cc2 = st.columns(2)
    with cc1:
        y_start = st.selectbox("Año inicio", options=years_all, index=0)
        m_start = st.selectbox("Mes inicio", options=[n for n,_ in MESES], index=0)
    with cc2:
        y_end   = st.selectbox("Año fin", options=years_all, index=len(years_all)-1)
        m_end   = st.selectbox("Mes fin", options=[n for n,_ in MESES], index=11)

with c3:
    ils_col = st.selectbox("Columna ILS a comparar", options=ils_cols or ["(no hay columnas ILS)"],
                           index=(ils_cols.index(default_ils) if (ils_cols and default_ils in ils_cols) else 0))
    mode = st.radio("Modo de gráfica", ["Acumulada (rango completo)","Una por año"], index=0)

# Validación rango
start_key = (int(y_start), MES_A_NUM[m_start])
end_key   = (int(y_end),   MES_A_NUM[m_end])
if start_key > end_key:
    st.warning("El inicio debe ser anterior (o igual) al fin.")
    st.stop()

x0 = pd.Timestamp(int(y_start), MES_A_NUM[m_start], 1)
x1 = pd.Timestamp(int(y_end),   MES_A_NUM[m_end],   1) + MonthEnd(1)

# Serie por categoría (diaria y MA7 para panel principal)
members = cols_for_category(ratio_day, category)
if not members:
    st.error(f"No encontré columnas que encajen con '{category}'. Ajusta CATEGORY_TOKENS.")
    st.stop()

ser_full = category_series(ratio_day, members)
ser_full_ma7 = ser_full.rolling(7, min_periods=1).mean()
ser_range = ser_full.loc[(ser_full.index >= x0) & (ser_full.index <= x1)].dropna()
ser_range_ma7 = ser_full_ma7.loc[ser_range.index]

# =============== 2) GRÁFICAS (principal) ===============
st.header("2) Gráficas")

# TOP1 por año (recalculado sobre la serie agregada)
def _top1(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    yrs = list(range(start.year, end.year+1))
    return rolling90_top1_by_year(series, yrs)

tops_cat = _top1(ser_full, x0, x1)

if ser_range.empty:
    st.info("No hay datos diarios para ese rango/categoría.")
else:
    if mode.startswith("Acumulada"):
        fig = figure_main(
            ser_range, ser_range_ma7, tops_cat,
            f"{category} — {NUM_A_MES[x0.month]} {x0.year} – {NUM_A_MES[x1.month]} {x1.year}",
            x0, x1
        )
        st.plotly_chart(fig, use_container_width=True, key=f"acc-{category}-{x0}-{x1}")
    else:
        cols = st.columns(2)
        idx = 0
        for y in range(x0.year, x1.year+1):
            y0 = max(pd.Timestamp(y,1,1), x0)
            y1 = min(pd.Timestamp(y,12,31)+MonthEnd(0), x1)
            ser_y = ser_full.loc[(ser_full.index >= y0) & (ser_full.index <= y1)].dropna()
            if ser_y.empty: 
                continue
            ser_y_ma7 = ser_full_ma7.loc[ser_y.index]
            tops_y = tops_cat[tops_cat["Año"] == y]
            figy = figure_main(ser_y, ser_y_ma7, tops_y, f"{category} — {y}", y0, y1)
            with cols[idx % 2]:
                st.plotly_chart(figy, use_container_width=True, key=f"year-{category}-{y}-{y0.month}-{y1.month}")
            idx += 1

# =============== 3) Tabla TOP ===============
st.header("3) Tabla de ventanas TOP (recomputadas)")
st.dataframe(tops_cat.sort_values("Año"), use_container_width=True, hide_index=True,
             key=f"tabla-{category}-{x0}-{x1}")

# =============== 4) Comparativa ILS (comparando columnas) ===============
st.header("Comparativa ILS (columnas de Ratios_diarios)")

if not ils_cols:
    st.warning("No se detectaron columnas con 'ILS' en 'Ratios_diarios'.")
else:
    ils_series = ratio_day[ils_col].astype(float)

    # 4.1 Serie diaria: rojo (categoría) vs verde (ILS)
    fig_ils = ils_compare_timeseries(
        ser_full, ils_series, x0, x1,
        f"{category} vs {ils_col} — {NUM_A_MES[x0.month]} {x0.year} – {NUM_A_MES[x1.month]} {x1.year}"
    )
    st.plotly_chart(fig_ils, use_container_width=True, key=f"ils-ts-{category}-{ils_col}-{x0}-{x1}")

    # 4.2 Diferencia (cat − ILS)
    fig_diff = ils_diff_chart(
        ser_full, ils_series, x0, x1,
        f"Diferencia diaria (Categoría − {ils_col})"
    )
    st.plotly_chart(fig_diff, use_container_width=True, key=f"ils-diff-{category}-{ils_col}-{x0}-{x1}")

    # 4.3 Métricas resumen del rango
    idx_union = ser_full.index.union(ils_series.index)
    cat_u = ser_full.reindex(idx_union).interpolate(limit_direction="both")
    ils_u = ils_series.reindex(idx_union).interpolate(limit_direction="both")
    mask = (idx_union >= x0) & (idx_union <= x1)
    cat_r = cat_u[mask].dropna()
    ils_r = ils_u[mask].dropna()
    diff = (cat_r - ils_r).dropna()

    def _fmt(x): return f"{x:.0%}" if x==x else "—"
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Mediana categoría", _fmt(cat_r.median() if not cat_r.empty else np.nan))
    with c2:
        st.metric(f"Mediana {ils_col}", _fmt(ils_r.median() if not ils_r.empty else np.nan))
    with c3:
        st.metric("Δ mediana (cat − ILS)", _fmt(diff.median() if not diff.empty else np.nan))
