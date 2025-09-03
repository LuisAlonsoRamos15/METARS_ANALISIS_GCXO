# -*- coding: utf-8 -*-
# App Streamlit — lee internamente 'ratios_aeronaves_mensual_2014_2025.xlsx'
# - Selección: 1 categoría (CLAVE C y D / E295 / AT76 / AT75)
# - Rango de fechas libre (puede cruzar años)
# - TOP = 1 (mejor 90d por año)
# - ILS: detectado en la HOJA 'Ratios_diarios' (columna con "ILS")
# - Secciones: 1) Filtros  2) Gráficas (+ Moda)  3) Tabla  + pestaña Comparativa ILS

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pandas.tseries.offsets import MonthEnd

st.set_page_config(page_title="Top 90 días — categorías", layout="wide")

# ====== Rutas candidatas (carga interna, sin mostrar al usuario) ======
PATH_CANDIDATES = [
    Path("ratios_aeronaves_mensual_2014_2025.xlsx"),
    Path("data/ratios_aeronaves_mensual_2014_2025.xlsx"),
    Path("/mnt/data/ratios_aeronaves_mensual_2014_2025.xlsx"),
]

# ====== Apariencia / colores ======
COLORS = {
    "daily": "#7F8C8D",
    "ma7":   "#111111",
    "top1":  "#2E7D32",   # verde
    "bgband":"rgba(0,0,0,0.06)",
    "op":    "#2E7D32",   # ILS operativo
    "nop":   "#C0392B",   # ILS no operativo
}

MESES = [
    ("Enero", 1), ("Febrero", 2), ("Marzo", 3), ("Abril", 4),
    ("Mayo", 5), ("Junio", 6), ("Julio", 7), ("Agosto", 8),
    ("Septiembre", 9), ("Octubre",10), ("Noviembre",11), ("Diciembre",12)
]
MES_A_NUM = {n:i for n,i in MESES}
NUM_A_MES = {i:n for n,i in MESES}

WINDOW_DAYS = 90

# ====== Definición de categorías (tokens para buscar columnas) ======
CATEGORY_TOKENS: Dict[str, List[str]] = {
    "CLAVE C y D": [
        "AEA","RYR","VLG","VUELING","IBE","IBERIA","EZY","U2",
        "A320","A321","B737","B738","B739","B38M","B38X"
    ],
    "E295": ["E295","E190","E195"],
    "AT76": ["AT76","ATR72"],
    "AT75": ["AT75","ATR72-500","ATR75"],
}

# ====== Utilidades ======
def find_excel_path() -> Path:
    p = next((pp for pp in PATH_CANDIDATES if pp.exists()), None)
    if p is None:
        raise FileNotFoundError("No encuentro 'ratios_aeronaves_mensual_2014_2025.xlsx' en ./, ./data/ o /mnt/data/")
    return p

TRUE_TOKENS = {"1","TRUE","VERDADERO","SI","SÍ","YES","Y"}
FALSE_TOKENS = {"0","FALSE","FALSO","NO","N"}

def map_to_bool_like(s: pd.Series) -> pd.Series:
    """Mapea a 0/1 si es posible (numérico 0/1 o strings TRUE/FALSE/SI/NO). NaN -> NaN."""
    if np.issubdtype(s.dtype, np.number):
        v = s.astype(float)
        m = v.isin([0.0,1.0])
        out = pd.Series(np.where(v==1.0, 1, np.where(v==0.0, 0, np.nan)), index=s.index)
        return out.where(m, np.nan)
    up = s.astype(str).str.strip().str.upper()
    out = np.where(up.isin(TRUE_TOKENS), 1, np.where(up.isin(FALSE_TOKENS), 0, np.nan))
    return pd.Series(out, index=s.index)

def detect_ils_column(df: pd.DataFrame) -> str | None:
    """Devuelve el nombre de la mejor columna candidata de ILS en Ratios_diarios."""
    cands = [c for c in df.columns if "ils" in c.lower()]
    best = None; best_score = -1.0
    for c in cands:
        mapped = map_to_bool_like(df[c])
        score = mapped.notna().mean()
        # exigimos reconocimiento >= 0.7
        if score >= 0.7 and score > best_score:
            best = c; best_score = score
    return best

@st.cache_data(show_spinner=True)
def load_all() -> Dict:
    """
    Lee:
      - Top90d_por_año (obligatoria) -> usaremos solo TOP=1 por año
      - Ratios_diarios (opcional): ratios diarios por columna (aerolíneas/tipos) + posible columna ILS
    """
    p = find_excel_path()
    xls = pd.ExcelFile(p)
    sheets = set(xls.sheet_names)

    # ---- Top90d_por_año ----
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

    # Quedarnos con TOP=1 por (Aerolínea, Año)
    if "TOP" in top90.columns:
        top90_top1 = (top90.sort_values(["Aerolínea","Año","Ratio_90d"], ascending=[True, True, False])
                           .groupby(["Aerolínea","Año"], as_index=False).head(1))
    else:
        top90_top1 = top90.copy()

    # ---- Ratios_diarios ----
    ratio_day = ratio_ma7 = None
    ils_flag = None  # Serie 0/1 (ILS operativo)
    if "Ratios_diarios" in sheets:
        rd = pd.read_excel(xls, sheet_name="Ratios_diarios")

        # detectar columna de fecha
        date_col = None
        for cand in ["Fecha","fecha","date","Date","index"]:
            if cand in rd.columns: date_col = cand; break
        if date_col is None:
            date_col = rd.columns[0]
        rd[date_col] = pd.to_datetime(rd[date_col], errors="coerce")
        rd = rd[rd[date_col].notna()].copy().sort_values(date_col).set_index(date_col)

        # detectar columna ILS en la propia hoja
        ils_col = detect_ils_column(rd)
        if ils_col:
            ils_mapped = map_to_bool_like(rd[ils_col]).astype(float)
            ils_flag = ils_mapped.where(ils_mapped.isin([0.0,1.0])).astype("float")
            # limpiar columna ILS del dataframe de ratios
            rd = rd.drop(columns=[ils_col])

        # ratios diarios (todas las demás columnas numéricas)
        num_cols = [c for c in rd.columns if np.issubdtype(rd[c].dtype, np.number)]
        if num_cols:
            ratio_day = rd[num_cols].astype(float)
            ratio_ma7 = ratio_day.rolling(window=7, min_periods=1).mean()

    return {"top90_top1": top90_top1, "ratio_day": ratio_day, "ratio_ma7": ratio_ma7, "ils_flag": ils_flag}

def columns_for_category(ratio_day: pd.DataFrame, category: str) -> List[str]:
    toks = [t.upper() for t in CATEGORY_TOKENS.get(category, [])]
    cols = [c for c in ratio_day.columns if any(t in c.upper() for t in toks)]
    return cols

def category_series(ratio_day: pd.DataFrame, members: List[str]) -> pd.Series:
    """Promedio fila a fila (no ponderado) de las columnas miembro."""
    if not members:
        return pd.Series(dtype=float)
    return ratio_day[members].mean(axis=1, skipna=True)

def rolling90_top1_by_year(series: pd.Series, years: List[int]) -> pd.DataFrame:
    """TOP 1 ventana 90d por año (inicio en ese año)."""
    s = series.sort_index()
    r90 = s.rolling(WINDOW_DAYS, min_periods=WINDOW_DAYS).mean()
    out = []
    for y in years:
        r = r90.dropna()
        if r.empty: continue
        candidates = []
        for end_ts, val in r.items():
            start_ts = end_ts - pd.Timedelta(days=WINDOW_DAYS-1)
            if start_ts.year == y:
                candidates.append((start_ts, end_ts, float(val)))
        if not candidates: continue
        start_best, end_best, v = max(candidates, key=lambda t: t[2])
        out.append({"Año": y, "Inicio_90d": start_best, "Fin_90d": end_best, "Ratio_90d": v})
    return pd.DataFrame(out)

def year_ticks_lines(fig: go.Figure, start: pd.Timestamp, end: pd.Timestamp):
    y = start.year + 1
    while y <= end.year:
        fig.add_vline(x=pd.Timestamp(y,1,1), line_width=1, line_dash="dot", line_color="#555")
        y += 1

def make_range_figure(ser: pd.Series, ser_ma7: pd.Series,
                      tops: pd.DataFrame, title: str,
                      x0: pd.Timestamp, x1: pd.Timestamp) -> go.Figure:
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=1, line_width=0, fillcolor=COLORS["bgband"], opacity=0.35)
    fig.add_trace(go.Scatter(x=ser.index, y=ser.values, mode="lines",
                             line=dict(color=COLORS["daily"], width=2), name="Ratio diario"))
    fig.add_trace(go.Scatter(x=ser_ma7.index, y=ser_ma7.values, mode="lines",
                             line=dict(color=COLORS["ma7"], width=3), name="Media móvil 7d"))

    for _, row in tops.sort_values("Año").iterrows():
        s = pd.to_datetime(row["Inicio_90d"])
        e = pd.to_datetime(row["Fin_90d"])
        s_plot, e_plot = max(s, x0), min(e, x1)
        if s_plot > e_plot: continue
        fig.add_vrect(x0=s_plot, x1=e_plot, fillcolor=COLORS["top1"], opacity=0.18, line_width=0)
        m = (ser_ma7.index >= s_plot) & (ser_ma7.index <= e_plot)
        if m.any():
            fig.add_trace(go.Scatter(x=ser_ma7.index[m], y=ser_ma7[m].values, mode="lines",
                                     line=dict(color=COLORS["top1"], width=7),
                                     name=f"TOP 90d — {int(row['Año'])}",
                                     showlegend=True))
        mid = s_plot + (e_plot - s_plot)/2
        y_mid = float(np.nanmedian(ser_ma7[(ser_ma7.index >= s_plot) & (ser_ma7.index <= e_plot)].values)) if m.any() else 0.6
        fig.add_annotation(x=mid, y=y_mid, text=f"{row['Ratio_90d']:.0%}",
                           showarrow=False, bgcolor="white",
                           bordercolor=COLORS["top1"], borderwidth=1, opacity=0.95)

    year_ticks_lines(fig, x0, x1)
    fig.update_layout(
        title=title,
        margin=dict(l=50, r=20, t=70, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        yaxis=dict(title="Ratio", range=[0,1], tickformat=".0%"),
        xaxis=dict(title="Fecha"),
    )
    return fig

def month_mode_plot(tops: pd.DataFrame, title: str) -> go.Figure:
    """Barra con el mes de inicio más frecuente (moda)."""
    if tops.empty:
        return go.Figure()
    months = pd.to_datetime(tops["Inicio_90d"]).dt.month
    counts = months.value_counts().sort_index()
    fig = go.Figure()
    fig.add_bar(x=[NUM_A_MES[m] for m in counts.index], y=counts.values, marker_color=COLORS["top1"])
    mmax = counts.idxmax()
    fig.add_annotation(x=NUM_A_MES[mmax], y=counts.max(), text="Moda", showarrow=True, arrowhead=2)
    fig.update_layout(title=title, yaxis_title="Frecuencia", xaxis_title="Mes de inicio")
    return fig

# ============================
# 1) FILTROS
# ============================
st.title("📊 Top 90 días — por categoría (acumulado)")

# Carga interna
try:
    data = load_all()
except Exception as e:
    st.error(str(e))
    st.stop()

top90_top1: pd.DataFrame = data["top90_top1"]
ratio_day: pd.DataFrame | None = data["ratio_day"]
ratio_ma7: pd.DataFrame | None = data["ratio_ma7"]
ils_flag:  pd.Series  | None = data["ils_flag"]

st.header("1) Filtros")
c1, c2, c3 = st.columns([2,3,2])

with c1:
    category = st.selectbox("Categoría", ["CLAVE C y D", "E295", "AT76", "AT75"], index=0)
    years_all = sorted(top90_top1["Año"].unique().tolist())

with c2:
    cc1, cc2 = st.columns(2)
    with cc1:
        y_start = st.selectbox("Año inicio", options=years_all, index=0)
        m_start = st.selectbox("Mes inicio", options=[n for n,_ in MESES], index=0)
    with cc2:
        y_end = st.selectbox("Año fin", options=years_all, index=len(years_all)-1)
        m_end = st.selectbox("Mes fin", options=[n for n,_ in MESES], index=11)

with c3:
    mode = st.radio("Modo de gráfica", ["Acumulada (rango completo)","Una por año"], index=0)

# Validación rango
start_key = (int(y_start), MES_A_NUM[m_start])
end_key   = (int(y_end),   MES_A_NUM[m_end])
if start_key > end_key:
    st.warning("El inicio debe ser anterior (o igual) al fin.")
    st.stop()

x0 = pd.Timestamp(int(y_start), MES_A_NUM[m_start], 1)
x1 = pd.Timestamp(int(y_end),   MES_A_NUM[m_end],   1) + MonthEnd(1)

# ============================
# Preparar serie por categoría
# ============================
if ratio_day is None or ratio_ma7 is None:
    st.warning("No está la hoja 'Ratios_diarios' o no es válida. Se mostrará solo la tabla.")
    ser_cat = ser_cat_ma7 = ser_full = ser_full_ma7 = None
else:
    members = columns_for_category(ratio_day, category)
    if not members:
        st.error(f"No encontré columnas que encajen con '{category}'. Ajusta los tokens en CATEGORY_TOKENS.")
        st.stop()
    ser_full = category_series(ratio_day, members)
    ser_full_ma7 = ser_full.rolling(7, min_periods=1).mean()
    ser_cat = ser_full.loc[(ser_full.index >= x0) & (ser_full.index <= x1)].dropna()
    ser_cat_ma7 = ser_full_ma7.loc[ser_cat.index]

# ============================
# 2) GRÁFICAS
# ============================
st.header("2) Gráficas")

# TOP1 por año (recomputado sobre la serie de categoría completa)
tops_cat = pd.DataFrame()
if ser_full is not None and not ser_full.empty:
    years_in_range = list(range(x0.year, x1.year + 1))
    tops_cat = rolling90_top1_by_year(ser_full, years_in_range)

if ser_cat is None or ser_cat.empty:
    st.info("No hay datos diarios para ese rango/categoría.")
else:
    if mode.startswith("Acumulada"):
        title = f"{category} — {NUM_A_MES[x0.month]} {x0.year} – {NUM_A_MES[x1.month]} {x1.year}"
        fig = make_range_figure(ser_cat, ser_cat_ma7, tops_cat, title, x0, x1)
        st.plotly_chart(fig, use_container_width=True, key=f"acc-{category}-{x0}-{x1}")
    else:
        cols = st.columns(2)
        idx = 0
        for y in range(x0.year, x1.year+1):
            y0 = max(pd.Timestamp(y,1,1), x0)
            y1 = min(pd.Timestamp(y,12,31)+MonthEnd(0), x1)
            ser_y = ser_full.loc[(ser_full.index >= y0) & (ser_full.index <= y1)].dropna()
            if ser_y.empty: continue
            ser_y_ma7 = ser_full_ma7.loc[ser_y.index]
            tops_y = tops_cat[tops_cat["Año"] == y]
            fig = make_range_figure(ser_y, ser_y_ma7, tops_y, f"{category} — {y}", y0, y1)
            with cols[idx % 2]:
                st.plotly_chart(fig, use_container_width=True, key=f"year-{category}-{y}-{y0.month}-{y1.month}")
            idx += 1

# ---- Moda (mes de inicio más frecuente) ----
st.subheader("Moda de meses de inicio (TOP 90d por año)")
fig_mode = month_mode_plot(tops_cat, "Mes de inicio más frecuente")
st.plotly_chart(fig_mode, use_container_width=True, key=f"mode-{category}-{x0}-{x1}")

# ============================
# 3) TABLA
# ============================
st.header("3) Tabla de ventanas TOP (recomputadas)")
st.caption("Ventanas calculadas sobre la serie agregada de la categoría (no sobre columnas individuales).")
st.dataframe(tops_cat.sort_values("Año"), use_container_width=True, hide_index=True,
             key=f"tabla-{category}-{x0}-{x1}")

# ============================
# Comparativa ILS (usando columna ILS de Ratios_diarios)
# ============================
st.header("Comparativa ILS (desde 'Ratios_diarios')")

tab1, tab2 = st.tabs(["Descripción / requisitos", "Comparar operativo vs no operativo"])

with tab1:
    st.markdown("""
**Qué hace:** separa el rango en días con **ILS operativo** (1) y **no operativo** (0) usando la **columna ILS detectada en `Ratios_diarios`**, y calcula el **TOP 90d** de la categoría para cada caso.

**Necesario:** que la hoja `Ratios_diarios` contenga una columna cuyo nombre incluya **“ILS”** y que sea booleana (0/1 o TRUE/FALSE o SI/NO).
""")

with tab2:
    if ils_flag is None or ser_full is None:
        st.warning("No se detectó columna ILS en 'Ratios_diarios' o faltan series diarias. No es posible comparar.")
    else:
        ils = ils_flag.copy().astype(float)
        # alinación con la serie de categoría completa
        idx_union = ser_full.index.union(ils.index)
        ils = ils.reindex(idx_union).interpolate(limit_direction="both")  # relleno suave si faltan días
        ser_full_al = ser_full.reindex(idx_union).interpolate(limit_direction="both")

        mask_range = (idx_union >= x0) & (idx_union <= x1)
        op_mask  = (ils == 1.0) & mask_range
        nop_mask = (ils == 0.0) & mask_range

        def top90_from_series(s: pd.Series) -> Tuple[pd.Timestamp, pd.Timestamp, float]:
            if s is None or s.empty: return None, None, np.nan
            r = s.rolling(WINDOW_DAYS, min_periods=WINDOW_DAYS).mean().dropna()
            if r.empty: return None, None, np.nan
            end = r.idxmax()
            start = end - pd.Timedelta(days=WINDOW_DAYS-1)
            return start, end, float(r.loc[end])

        s1, e1, v1 = top90_from_series(ser_full_al[op_mask])
        s2, e2, v2 = top90_from_series(ser_full_al[nop_mask])

        c1, c2 = st.columns(2)
        with c1:
            st.metric("TOP 90d — ILS **operativo**", f"{v1:.0%}" if not np.isnan(v1) else "—",
                      help=f"{s1.date()} → {e1.date()}" if s1 else "Sin ventana completa")
        with c2:
            st.metric("TOP 90d — ILS **no operativo**", f"{v2:.0%}" if not np.isnan(v2) else "—",
                      help=f"{s2.date()} → {e2.date()}" if s2 else "Sin ventana completa")

        # Gráfica comparativa en el rango
        ser_ma7_full = ser_full_al.rolling(7, min_periods=1).mean()
        fig = go.Figure()
        fig.add_hrect(y0=0, y1=1, line_width=0, fillcolor=COLORS["bgband"], opacity=0.25)
        fig.add_trace(go.Scatter(x=ser_ma7_full[op_mask].index,  y=ser_ma7_full[op_mask].values,
                                 mode="lines", name="MA7 — ILS operativo",
                                 line=dict(color=COLORS["op"], width=3)))
        fig.add_trace(go.Scatter(x=ser_ma7_full[nop_mask].index, y=ser_ma7_full[nop_mask].values,
                                 mode="lines", name="MA7 — ILS no operativo",
                                 line=dict(color=COLORS["nop"], width=3)))
        if s1 and e1: fig.add_vrect(x0=s1, x1=e1, fillcolor=COLORS["op"],  opacity=0.18, line_width=0)
        if s2 and e2: fig.add_vrect(x0=s2, x1=e2, fillcolor=COLORS["nop"], opacity=0.18, line_width=0)
        fig.update_layout(
            title=f"{category} — Comparativa ILS ({NUM_A_MES[x0.month]} {x0.year} – {NUM_A_MES[x1.month]} {x1.year})",
            yaxis=dict(title="Ratio", range=[0,1], tickformat=".0%"),
            xaxis=dict(title="Fecha"),
            legend=dict(orientation="h", y=1.02)
        )
        st.plotly_chart(fig, use_container_width=True, key=f"ils-{category}-{x0}-{x1}")
