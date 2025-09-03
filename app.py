# -*- coding: utf-8 -*-
# Streamlit – Top 90d por categoría + Comparativa ILS (sin MA7) + Tabla + Histograma (mes de inicio)
# Carga interna del Excel 'ratios_aeronaves_mensual_2014_2025.xlsx' (./, ./data, /mnt/data)

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pandas.tseries.offsets import MonthEnd

st.set_page_config(page_title="Top 90 días — categorías", layout="wide")

# ====== Rutas candidatas ======
PATHS = [
    Path("ratios_aeronaves_mensual_2014_2025.xlsx"),
    Path("data/ratios_aeronaves_mensual_2014_2025.xlsx"),
    Path("/mnt/data/ratios_aeronaves_mensual_2014_2025.xlsx"),
]

# ====== Colores / estilo ======
COLORS = {
    "daily": "#F97316",   # naranja: categoría (diario)
    "top_fill": "rgba(16,185,129,0.22)",  # verde-teal para sombrear TOP
    "top_border": "#0F766E",              # borde/etiqueta
    "bgband":"rgba(255,255,255,0.05)",
    "grid":  "#4B5563",
    "ils":   "#22C55E",   # verde: ILS (diario)
    "diff+": "#22C55E",   # diferencia positiva (cat > ILS)
    "diff-": "#F97316",   # diferencia negativa (cat < ILS)
    "bar":   "#0EA5E9",   # barras del histograma
}

MESES = [
    ("Enero", 1), ("Febrero", 2), ("Marzo", 3), ("Abril", 4),
    ("Mayo", 5), ("Junio", 6), ("Julio", 7), ("Agosto", 8),
    ("Septiembre", 9), ("Octubre",10), ("Noviembre",11), ("Diciembre",12)
]
MES_A_NUM = {n:i for n,i in MESES}
NUM_A_MES = {i:n for n,i in MESES}

WINDOW_DAYS = 90

# ====== Categorías (tokens para buscar columnas a promediar) ======
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
      - 'Top90d_por_año' (para rango de años) — pero recalculamos TOPs desde diarios
      - 'Ratios_diarios' (series diarias + columna(s) ILS)
    """
    xls = pd.ExcelFile(_find_path())
    sheets = set(xls.sheet_names)

    # Años disponibles desde Top90d_por_año
    if "Top90d_por_año" not in sheets:
        raise ValueError("Falta la hoja 'Top90d_por_año' en el Excel.")
    t90 = pd.read_excel(xls, sheet_name="Top90d_por_año")
    ren = {}
    if "Aerolinea" in t90.columns: ren["Aerolinea"] = "Aerolínea"
    if "Ano" in t90.columns: ren["Ano"] = "Año"
    t90 = t90.rename(columns=ren)
    if "Año" not in t90.columns:
        raise ValueError("En 'Top90d_por_año' falta la columna 'Año'.")
    years_all = sorted(t90["Año"].unique().tolist())

    # Ratios_diarios
    if "Ratios_diarios" not in sheets:
        raise ValueError("Falta la hoja 'Ratios_diarios' en el Excel.")
    rd = pd.read_excel(xls, sheet_name="Ratios_diarios")
    date_col = next((c for c in ["Fecha","FECHA","fecha","date","Date","index"] if c in rd.columns), rd.columns[0])
    rd[date_col] = pd.to_datetime(rd[date_col], errors="coerce")
    rd = rd[rd[date_col].notna()].copy().sort_values(date_col).set_index(date_col)

    # numéricas
    num_cols = [c for c in rd.columns if np.issubdtype(rd[c].dtype, np.number)]
    ratio_day = rd[num_cols].astype(float)

    # ILS: prioriza 'ILS Cat.1', si no la primera que contenga 'ils'
    ils_candidates = [c for c in ratio_day.columns if "ils" in c.lower()]
    ils_col = "ILS Cat.1" if "ILS Cat.1" in ratio_day.columns else (ils_candidates[0] if ils_candidates else None)
    if ils_col is None:
        raise ValueError("No se detectó ninguna columna con 'ILS' en 'Ratios_diarios'.")

    return {"ratio_day": ratio_day, "ils_col": ils_col, "years_all": years_all}

def cols_for_category(ratio_day: pd.DataFrame, category: str) -> List[str]:
    toks = [t.upper() for t in CATEGORY_TOKENS.get(category, [])]
    return [c for c in ratio_day.columns if any(t in c.upper() for t in toks)]

def category_series(ratio_day: pd.DataFrame, members: List[str]) -> pd.Series:
    return ratio_day[members].mean(axis=1, skipna=True) if members else pd.Series(dtype=float)

def rolling90_top1_by_year(series: pd.Series, years: List[int]) -> pd.DataFrame:
    """Mejor ventana 90d por año (el año es el del día de INICIO de la ventana)."""
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
        fig.add_vline(x=pd.Timestamp(y,1,1), line_width=1, line_dash="dot", line_color=COLORS["grid"])
        y += 1

def figure_main(ser: pd.Series, tops: pd.DataFrame, title: str,
                x0: pd.Timestamp, x1: pd.Timestamp) -> go.Figure:
    """Gráfica principal sin MA7: línea diaria + sombreado y etiqueta de cada TOP."""
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=1, line_width=0, fillcolor=COLORS["bgband"], opacity=1.0)
    fig.add_trace(go.Scatter(x=ser.index, y=ser.values, mode="lines",
                             line=dict(color=COLORS["daily"], width=2.0),
                             name="Ratio diario (categoría)"))
    # TOP por año (sin leyenda)
    for _, row in tops.sort_values("Año").iterrows():
        s = pd.to_datetime(row["Inicio_90d"])
        e = pd.to_datetime(row["Fin_90d"])
        s_plot, e_plot = max(s, x0), min(e, x1)
        if s_plot > e_plot:
            continue
        fig.add_vrect(x0=s_plot, x1=e_plot, fillcolor=COLORS["top_fill"], opacity=1.0, line_width=0)
        mid = s_plot + (e_plot - s_plot)/2
        # etiqueta visible
        y_top = float(min(0.985, np.nanmax(ser[(ser.index>=s_plot)&(ser.index<=e_plot)].values)+0.01)) if not ser.empty else 0.97
        fig.add_annotation(
            x=mid, y=y_top, text=f"{row['Ratio_90d']:.0%}",
            showarrow=False, bgcolor="#FFFFFF",
            bordercolor=COLORS["top_border"], borderwidth=1.5, opacity=0.98,
            font=dict(size=16, color="#0B0F10", family="Inter, system-ui"),
        )

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
    """Naranja = categoría (diario); Verde = ILS (diario)."""
    idx = cat.index.union(ils.index)
    cat_u = cat.reindex(idx).interpolate(limit_direction="both")
    ils_u = ils.reindex(idx).interpolate(limit_direction="both")
    m = (idx >= x0) & (idx <= x1)
    cat_u, ils_u = cat_u[m], ils_u[m]

    fig = go.Figure()
    fig.add_hrect(y0=0, y1=1, line_width=0, fillcolor=COLORS["bgband"], opacity=1.0)
    fig.add_trace(go.Scatter(x=cat_u.index, y=cat_u.values, mode="lines",
                             name="Categoría (diario)", line=dict(color=COLORS["daily"], width=1.8)))
    fig.add_trace(go.Scatter(x=ils_u.index, y=ils_u.values, mode="lines",
                             name="ILS (diario)", line=dict(color=COLORS["ils"], width=1.8)))
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
    """Barras diferencia (cat − ILS). Verde si >0; Naranja si <0."""
    idx = cat.index.union(ils.index)
    cat_u = cat.reindex(idx).interpolate(limit_direction="both")
    ils_u = ils.reindex(idx).interpolate(limit_direction="both")
    m = (idx >= x0) & (idx <= x1)
    idx, diff = idx[m], (cat_u - ils_u)[m]

    colors = np.where(diff >= 0, COLORS["diff+"], COLORS["diff-"])
    fig = go.Figure()
    fig.add_bar(x=idx, y=diff.values, marker_color=list(colors))
    fig.add_hline(y=0, line_width=1, line_dash="dot", line_color=COLORS["grid"])
    fig.update_layout(
        title=title,
        yaxis=dict(title="Cat − ILS", tickformat="+.0%"),
        xaxis=dict(title="Fecha"),
        margin=dict(l=50, r=20, t=60, b=40),
    )
    return fig

def month_mode_hist(tops: pd.DataFrame, title: str) -> go.Figure:
    """Histograma del mes de inicio de los TOP90 por año del rango."""
    if tops.empty:
        return go.Figure()
    months = pd.to_datetime(tops["Inicio_90d"]).dt.month
    counts = months.value_counts().sort_index()
    fig = go.Figure()
    fig.add_bar(x=[NUM_A_MES[m] for m in counts.index], y=counts.values, marker_color=COLORS["bar"])
    mmax = counts.idxmax()
    fig.add_annotation(x=NUM_A_MES[mmax], y=counts.max(), text="Moda", showarrow=True, arrowhead=2)
    fig.update_layout(title=title, yaxis_title="Frecuencia", xaxis_title="Mes de inicio")
    return fig

# =============== 1) FILTROS ===============
st.title("Top 90 días — por categoría")

# Carga
try:
    data = load_all()
except Exception as e:
    st.error(str(e))
    st.stop()

ratio_day: pd.DataFrame = data["ratio_day"]
ils_col: str            = data["ils_col"]
years_all: List[int]    = data["years_all"]

st.header("1) Filtros")
c1, c2, c3 = st.columns([2,3,2])

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
    mode = st.radio("Modo de gráfica", ["Acumulada (rango completo)","Una por año"], index=0)

# Validación rango
start_key = (int(y_start), MES_A_NUM[m_start])
end_key   = (int(y_end),   MES_A_NUM[m_end])
if start_key > end_key:
    st.warning("El inicio debe ser anterior (o igual) al fin.")
    st.stop()

x0 = pd.Timestamp(int(y_start), MES_A_NUM[m_start], 1)
x1 = pd.Timestamp(int(y_end),   MES_A_NUM[m_end],   1) + MonthEnd(1)

# Serie por categoría
members = cols_for_category(ratio_day, category)
if not members:
    st.error(f"No encontré columnas que encajen con '{category}'. Ajusta CATEGORY_TOKENS.")
    st.stop()
ser_full = category_series(ratio_day, members)
ser_range = ser_full.loc[(ser_full.index >= x0) & (ser_full.index <= x1)].dropna()

# =============== 2) GRÁFICAS (principal) ===============
st.header("2) Gráficas")

# TOP1 por año (recalculado sobre la serie agregada)
years_in_range = list(range(x0.year, x1.year + 1))
tops_cat = rolling90_top1_by_year(ser_full, years_in_range)

if ser_range.empty:
    st.info("No hay datos diarios para ese rango/categoría.")
else:
    if mode.startswith("Acumulada"):
        fig = figure_main(
            ser_range, tops_cat,
            f"{category} — {NUM_A_MES[x0.month]} {x0.year} – {NUM_A_MES[x1.month]} {x1.year}",
            x0, x1
        )
        st.plotly_chart(fig, use_container_width=True, key=f"acc-{category}-{x0}-{x1}")
    else:
        cols = st.columns(2)
        idx = 0
        for y in years_in_range:
            y0 = max(pd.Timestamp(y,1,1), x0)
            y1 = min(pd.Timestamp(y,12,31)+MonthEnd(0), x1)
            ser_y = ser_full.loc[(ser_full.index >= y0) & (ser_full.index <= y1)].dropna()
            if ser_y.empty:
                continue
            tops_y = tops_cat[tops_cat["Año"] == y]
            figy = figure_main(ser_y, tops_y, f"{category} — {y}", y0, y1)
            with cols[idx % 2]:
                st.plotly_chart(figy, use_container_width=True, key=f"year-{category}-{y}-{y0.month}-{y1.month}")
            idx += 1

# =============== 3) Histograma: mes de inicio (moda) ===============
st.subheader("Mes de inicio de las mejores ventanas (TOP 90d por año)")
st.plotly_chart(
    month_mode_hist(tops_cat, "Mes de inicio más frecuente (en el rango seleccionado)"),
    use_container_width=True,
    key=f"mode-{category}-{x0}-{x1}"
)

# =============== 4) Tabla + descarga CSV de TOPs ===============
st.subheader("Tabla de ventanas TOP (recalculadas)")
tbl = tops_cat.sort_values("Año").copy()
st.dataframe(tbl, use_container_width=True, hide_index=True, key=f"tabla-{category}-{x0}-{x1}")
st.download_button(
    "⬇️ Descargar TOP 90d por año (CSV)",
    data=tbl.to_csv(index=False).encode("utf-8"),
    file_name=f"top90_{category}_{x0.date()}_{x1.date()}.csv",
    mime="text/csv",
    key=f"dl-{category}-{x0}-{x1}"
)

# =============== 5) Comparativa ILS (solo gráficas) ===============
st.header("Comparativa ILS (categoría vs ILS)")

ils_series = ratio_day[ils_col].astype(float)

# 5.1 Serie diaria: naranja (categoría) vs verde (ILS)
st.plotly_chart(
    ils_compare_timeseries(
        ser_full, ils_series, x0, x1,
        f"{category} vs {ils_col} — {NUM_A_MES[x0.month]} {x0.year} – {NUM_A_MES[x1.month]} {x1.year}"
    ),
    use_container_width=True,
    key=f"ils-ts-{category}-{x0}-{x1}"
)

# 5.2 Diferencia (cat − ILS)
st.plotly_chart(
    ils_diff_chart(
        ser_full, ils_series, x0, x1,
        f"Diferencia diaria (Categoría − {ils_col})"
    ),
    use_container_width=True,
    key=f"ils-diff-{category}-{x0}-{x1}"
)

