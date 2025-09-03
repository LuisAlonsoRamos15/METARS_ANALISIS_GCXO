# -*- coding: utf-8 -*-
# Streamlit – Top 90d por categoría + Comparativa ILS + Análisis fino
# Carga interna del Excel 'ratios_aeronaves_mensual_2014_2025.xlsx' (en ./, ./data o /mnt/data)

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

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
    "daily": "#7F8C8D",
    "ma7":   "#111111",
    "top1":  "#2E7D32",   # verde sombreado para TOP
    "bgband":"rgba(0,0,0,0.06)",
    "op":    "#2E7D32",   # ILS operativo (verde)
    "nop":   "#E67E22",   # ILS no operativo (naranja)
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
        # aerolíneas típicas + jets clave C/D
        "AEA","RYR","VLG","VUELING","IBE","IBERIA","EZY","U2",
        "A320","A321","B737","B738","B739","B38M","B38X"
    ],
    "E295": ["E295","E190","E195"],
    "AT76": ["AT76","ATR72"],
    "AT75": ["AT75","ATR72-500","ATR75"],
}

TRUE_TOKENS = {"1","TRUE","VERDADERO","SI","SÍ","YES","Y"}
FALSE_TOKENS = {"0","FALSE","FALSO","NO","N"}

# ========= Utilidades =========
def _find_path() -> Path:
    p = next((pp for pp in PATHS if pp.exists()), None)
    if p is None:
        raise FileNotFoundError("No encuentro 'ratios_aeronaves_mensual_2014_2025.xlsx' en ./, ./data o /mnt/data")
    return p

def _map_bool_like(s: pd.Series) -> pd.Series:
    if np.issubdtype(s.dtype, np.number):
        v = s.astype(float)
        out = np.where(v==1.0, 1, np.where(v==0.0, 0, np.nan))
        return pd.Series(out, index=s.index)
    up = s.astype(str).str.strip().str.upper()
    out = np.where(up.isin(TRUE_TOKENS), 1, np.where(up.isin(FALSE_TOKENS), 0, np.nan))
    return pd.Series(out, index=s.index)

def _detect_ils_col(df: pd.DataFrame) -> str | None:
    cands = [c for c in df.columns if "ils" in c.lower()]
    best, score = None, -1.0
    for c in cands:
        s = _map_bool_like(df[c])
        r = s.notna().mean()
        if r >= 0.7 and r > score:
            best, score = c, r
    return best

@st.cache_data(show_spinner=True)
def load_all() -> Dict:
    """
    Lee:
      - 'Top90d_por_año' (obligatoria) -> nos quedamos con TOP=1 por año
      - 'Ratios_diarios' (opcional): ratios diarios por columna + posible columna ILS
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

    ratio_day = ratio_ma7 = None
    ils_flag = None
    if "Ratios_diarios" in sheets:
        rd = pd.read_excel(xls, sheet_name="Ratios_diarios")
        # detectar fecha
        date_col = None
        for cand in ["Fecha","fecha","date","Date","index"]:
            if cand in rd.columns: date_col = cand; break
        if date_col is None:
            date_col = rd.columns[0]
        rd[date_col] = pd.to_datetime(rd[date_col], errors="coerce")
        rd = rd[rd[date_col].notna()].copy().sort_values(date_col).set_index(date_col)

        # ILS dentro de la misma hoja
        ils_col = _detect_ils_col(rd)
        if ils_col:
            ils_flag = _map_bool_like(rd[ils_col]).astype(float)
            rd = rd.drop(columns=[ils_col])

        num_cols = [c for c in rd.columns if np.issubdtype(rd[c].dtype, np.number)]
        if num_cols:
            ratio_day = rd[num_cols].astype(float)
            ratio_ma7 = ratio_day.rolling(window=7, min_periods=1).mean()

    return {"top90_top1": top90_top1, "ratio_day": ratio_day, "ratio_ma7": ratio_ma7, "ils_flag": ils_flag}

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
                             line=dict(color=COLORS["daily"], width=2), name="Ratio diario"))
    fig.add_trace(go.Scatter(x=ser_ma7.index, y=ser_ma7.values, mode="lines",
                             line=dict(color=COLORS["ma7"], width=3), name="Media móvil 7d"))

    # sombreado de TOP por año (SIN trazas en leyenda)
    for _, row in tops.sort_values("Año").iterrows():
        s = pd.to_datetime(row["Inicio_90d"])
        e = pd.to_datetime(row["Fin_90d"])
        s_plot, e_plot = max(s, x0), min(e, x1)
        if s_plot > e_plot: 
            continue
        fig.add_vrect(x0=s_plot, x1=e_plot, fillcolor=COLORS["top1"], opacity=0.18, line_width=0)
        # anotación con porcentaje (sin leyenda)
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

def ils_timeseries_daily(ser_full: pd.Series, ils_flag: pd.Series,
                         x0: pd.Timestamp, x1: pd.Timestamp, title: str) -> go.Figure:
    """Serie diaria segmentada por ILS: verde (operativo) y naranja (no operativo). Sin MA7."""
    idx = ser_full.index
    ser = ser_full.copy()
    ils = ils_flag.reindex(idx).interpolate(limit_direction="both")
    # recorte
    mrange = (idx >= x0) & (idx <= x1)
    ser = ser[mrange]
    ils = ils[mrange]

    # series segmentadas con NaN fuera del estado -> líneas cortadas automáticamente
    y_op  = ser.where(ils == 1.0, np.nan)
    y_nop = ser.where(ils == 0.0, np.nan)

    fig = go.Figure()
    fig.add_hrect(y0=0, y1=1, line_width=0, fillcolor=COLORS["bgband"], opacity=0.25)

    fig.add_trace(go.Scatter(
        x=y_op.index, y=y_op.values, mode="lines",
        name="ILS operativo (diario)", line=dict(color=COLORS["op"], width=2)
    ))
    fig.add_trace(go.Scatter(
        x=y_nop.index, y=y_nop.values, mode="lines",
        name="ILS no operativo (diario)", line=dict(color=COLORS["nop"], width=2)
    ))

    year_lines(fig, x0, x1)
    fig.update_layout(
        title=title,
        yaxis=dict(title="Ratio", range=[0,1], tickformat=".0%"),
        xaxis=dict(title="Fecha"),
        legend=dict(orientation="h", y=1.02),
        margin=dict(l=50, r=20, t=70, b=40),
    )
    return fig

def ils_boxplot(op_vals: pd.Series, nop_vals: pd.Series, title: str) -> go.Figure:
    fig = go.Figure()
    if not op_vals.empty:
        fig.add_box(y=op_vals.values, name="ILS operativo", marker_color=COLORS["op"])
    if not nop_vals.empty:
        fig.add_box(y=nop_vals.values, name="ILS no operativo", marker_color=COLORS["nop"])
    fig.update_layout(title=title, yaxis=dict(title="Ratio", range=[0,1], tickformat=".0%"))
    return fig

def month_mode_plot(tops: pd.DataFrame, title: str) -> go.Figure:
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

# =============== 1) FILTROS ===============
st.title("📊 Top 90 días — por categoría")

# Carga
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

# Serie por categoría
if ratio_day is None or ratio_ma7 is None:
    st.warning("No está la hoja 'Ratios_diarios' o no es válida. Se mostrará solo la tabla.")
    ser_full = ser_full_ma7 = ser_range = ser_range_ma7 = None
else:
    members = cols_for_category(ratio_day, category)
    if not members:
        st.error(f"No encontré columnas que encajen con '{category}'. Ajusta CATEGORY_TOKENS.")
        st.stop()
    ser_full = category_series(ratio_day, members)
    ser_full_ma7 = ser_full.rolling(7, min_periods=1).mean()
    ser_range = ser_full.loc[(ser_full.index >= x0) & (ser_full.index <= x1)].dropna()
    ser_range_ma7 = ser_full_ma7.loc[ser_range.index]

# =============== 2) GRÁFICAS ===============
st.header("2) Gráficas")

# TOP1 por año (recalculado sobre serie agregada)
tops_cat = pd.DataFrame()
if ser_full is not None and not ser_full.empty:
    years_in_range = list(range(x0.year, x1.year + 1))
    tops_cat = rolling90_top1_by_year(ser_full, years_in_range)

if ser_range is not None and not ser_range.empty:
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
else:
    st.info("No hay datos diarios para ese rango/categoría.")

# Moda
st.subheader("Moda de meses de inicio (TOP 90d por año)")
st.plotly_chart(month_mode_plot(tops_cat, "Mes de inicio más frecuente"),
                use_container_width=True, key=f"mode-{category}-{x0}-{x1}")

# =============== 3) TABLA ===============
st.header("3) Tabla de ventanas TOP (recomputadas)")
st.caption("Ventanas calculadas sobre la serie agregada de la categoría (no sobre columnas individuales).")
st.dataframe(tops_cat.sort_values("Año"), use_container_width=True, hide_index=True,
             key=f"tabla-{category}-{x0}-{x1}")

# =============== 4) Comparativa ILS (sin MA7, diario) ===============
st.header("Comparativa ILS (diario)")

if ils_flag is None or ser_full is None:
    st.warning("No se detectó columna ILS en 'Ratios_diarios' o faltan series diarias. No es posible comparar.")
else:
    # Serie diaria segmentada (solo diario, sin MA7)
    fig_ils = ils_timeseries_daily(
        ser_full, ils_flag, x0, x1,
        f"{category} — Comparativa ILS ({NUM_A_MES[x0.month]} {x0.year} – {NUM_A_MES[x1.month]} {x1.year})"
    )
    st.plotly_chart(fig_ils, use_container_width=True, key=f"ils-ts-{category}-{x0}-{x1}")

    # Distribución por estado (differences)
    idx_union = ser_full.index.union(ils_flag.index)
    ils_u = ils_flag.reindex(idx_union).interpolate(limit_direction="both")
    s_u   = ser_full.reindex(idx_union).interpolate(limit_direction="both")
    mask_range = (idx_union >= x0) & (idx_union <= x1)
    op_vals  = s_u[(ils_u == 1.0) & mask_range].dropna()
    nop_vals = s_u[(ils_u == 0.0) & mask_range].dropna()

    c1, c2, c3 = st.columns(3)
    def _fmt(x): return f"{x:.0%}" if not np.isnan(x) else "—"
    with c1:
        st.metric("Mediana ILS operativo", _fmt(op_vals.median() if not op_vals.empty else np.nan))
    with c2:
        st.metric("Mediana ILS no operativo", _fmt(nop_vals.median() if not nop_vals.empty else np.nan))
    with c3:
        delta = (op_vals.median() - nop_vals.median()) if (not op_vals.empty and not nop_vals.empty) else np.nan
        st.metric("Δ mediana (op - no op)", _fmt(delta))

    st.plotly_chart(ils_boxplot(op_vals, nop_vals, "Distribución de ratios diarios por estado ILS"),
                    use_container_width=True, key=f"ils-box-{category}-{x0}-{x1}")

# =============== 5) Análisis fino ===============
st.header("Análisis fino")

if ratio_day is None:
    st.info("Sin 'Ratios_diarios' no se puede ejecutar el análisis fino.")
else:
    cc1, cc2, cc3, cc4 = st.columns(4)
    with cc1:
        dia0 = st.number_input("Día inicio", 1, 31, 1, step=1)
    with cc2:
        mes0 = st.selectbox("Mes inicio", options=[n for n,_ in MESES], index=0)
    with cc3:
        dur = st.number_input("Duración (días)", 7, 180, WINDOW_DAYS, step=1)
    with cc4:
        esc = st.selectbox("Escenario ILS", ["Todos", "Operativo", "No operativo"], index=0)

    # años históricos a usar
    years_hist_all = sorted(list(set(ser_full.index.year)))
    sel_years_hist = st.multiselect("Años históricos a considerar", options=years_hist_all, default=years_hist_all)

    # construir serie base (con o sin filtro ILS)
    base = ser_full.copy()
    if ils_flag is not None and esc != "Todos":
        ils_al = ils_flag.reindex(base.index).interpolate(limit_direction="both")
        if esc == "Operativo":
            base = base.where(ils_al == 1.0)
        else:
            base = base.where(ils_al == 0.0)

    # evaluación por año: ventana [y-mes-día ... +dur-1]
    rows = []
    m0 = MES_A_NUM[mes0]
    for y in sel_years_hist:
        try:
            start = pd.Timestamp(y, m0, int(dia0))
        except ValueError:
            # días como 30/31 en meses cortos -> ajustamos al último día válido
            start = (pd.Timestamp(y, m0, 1) + MonthEnd(0))
        end = start + pd.Timedelta(days=int(dur)-1)
        seg = base[(base.index >= start) & (base.index <= end)].dropna()
        cov = len(seg) / int(dur)
        mean = float(seg.mean()) if not seg.empty else np.nan
        rows.append({"Año": y, "Inicio": start, "Fin": end, "Media_ventana": mean, "Cobertura": cov, "N_días": len(seg)})

    fine_df = pd.DataFrame(rows)
    # métricas de estimación (solo con cobertura razonable)
    valid = fine_df[fine_df["Cobertura"] >= 0.7].copy()
    c1, c2, c3, c4 = st.columns(4)
    def pct(s, q): return float(np.nanpercentile(s, q)) if not s.empty else np.nan
    with c1:
        st.metric("Mediana esperada", f"{pct(valid['Media_ventana'], 50):.0%}" if not valid.empty else "—")
    with c2:
        st.metric("p25 – p75", (f"{pct(valid['Media_ventana'], 25):.0%} – "
                                f"{pct(valid['Media_ventana'], 75):.0%}") if not valid.empty else "—")
    with c3:
        st.metric("p10 – p90", (f"{pct(valid['Media_ventana'], 10):.0%} – "
                                f"{pct(valid['Media_ventana'], 90):.0%}") if not valid.empty else "—")
    with c4:
        st.metric("Años válidos", f"{len(valid)}/{len(fine_df)}")

    # gráfico por año (barras)
    if not fine_df.empty:
        figf = go.Figure()
        figf.add_bar(x=fine_df["Año"].astype(str), y=fine_df["Media_ventana"].values)
        figf.update_layout(title="Media de la ventana por año", yaxis=dict(range=[0,1], tickformat=".0%"),
                           xaxis_title="Año", yaxis_title="Ratio medio")
        st.plotly_chart(figf, use_container_width=True, key=f"fine-{category}-{dia0}-{mes0}-{dur}-{esc}")

        st.dataframe(fine_df.sort_values("Año"), use_container_width=True, hide_index=True,
                     key=f"fine-table-{category}-{dia0}-{mes0}-{dur}-{esc}")
        st.download_button(
            "⬇️ Descargar (CSV)",
            data=fine_df.to_csv(index=False).encode("utf-8"),
            file_name=f"analisis_fino_{category}_{int(dia0):02d}-{MES_A_NUM[mes0]:02d}_{dur}d_{esc}.csv",
            mime="text/csv",
            key=f"fine-dl-{category}-{dia0}-{mes0}-{dur}-{esc}"
        )
