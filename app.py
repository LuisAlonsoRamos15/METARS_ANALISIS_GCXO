# -*- coding: utf-8 -*-
# Streamlit – Top 90d por categoría + Comparativa ILS (sin MA7) + Tabla + Histograma (mes de inicio)
# + Sección añadida: Teoría ILS vs Real 
# Carga interna de Excels: 'ratios_aeronaves_mensual_2014_2025.xlsx' y 'TFN_vuelos_METAR_ILS_RWY30.xlsx'

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pandas.tseries.offsets import MonthEnd

st.set_page_config(page_title="Top 90 días — categorías", layout="wide")

# ====== Rutas candidatas (ratios) ======
PATHS = [
    Path("ratios_aeronaves_mensual_2014_2025.xlsx"),
    Path("data/ratios_aeronaves_mensual_2014_2025.xlsx"),
    Path("/mnt/data/ratios_aeronaves_mensual_2014_2025.xlsx"),
]

# ====== Rutas candidatas (TFN) ======
TFN_PATHS = [
    Path("TFN_vuelos_METAR_ILS_RWY30.xlsx"),
    Path("data/TFN_vuelos_METAR_ILS_RWY30.xlsx"),
    Path("/mnt/data/TFN_vuelos_METAR_ILS_RWY30.xlsx"),
]

# ====== Colores / estilo ======
COLORS = {
    "daily": "#F97316",   # naranja: categoría (diario)
    "top_fill": "rgba(16,185,129,0.22)",  # verde-teal para sombrear TOP
    "top_border": "#0F766E",              # borde/etiqueta
    "bgband":"rgba(255,255,255,0.05)",
    "grid":  "#4B5563",
    "ils":   "#22C55E",   # verde: ILS (diario)
    "diff+": "#22C55E",
    "diff-": "#F97316",
    "bar":   "#0EA5E9",
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

# ========= Utilidades (ratios) =========
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

# =============== 5) Comparativa ILS (solo líneas) ===============
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



# ===============================================================
# 6) Teoría ILS vs Real — TFN (líneas)  (selector ILS / Sin ILS-CLAVE C y D)
#    - KPIs y errores siempre con ILS vs Real (adimensional)
#    - Sección: Factor de escala para predicción (k* global o mensual)
# ===============================================================

from typing import Optional

TFN_PATHS = [
    Path("TFN_vuelos_METAR_ILS_RWY30.xlsx"),
    Path("data/TFN_vuelos_METAR_ILS_RWY30.xlsx"),
    Path("/mnt/data/TFN_vuelos_METAR_ILS_RWY30.xlsx"),
]

def _find_tfn_path() -> Optional[Path]:
    return next((p for p in TFN_PATHS if p.exists()), None)

@st.cache_data(show_spinner=False)
def load_resumen_tfn(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="resumen_diario")

    # Normaliza fecha
    if "fecha_utc" in df.columns:
        df["fecha_utc"] = pd.to_datetime(df["fecha_utc"], errors="coerce")
    elif "fecha" in df.columns:
        df["fecha_utc"] = pd.to_datetime(df["fecha"], errors="coerce")
    else:
        return df.iloc[0:0].copy()

    # Columnas mínimas
    for col in ["ops_totales", "ope_reales"]:
        if col not in df.columns:
            df[col] = pd.NA

    # ILS teórica si no existe explícita (a partir de % favorables)
    if "ops_teoricas_ILS Cat.1" not in df.columns and "pct_metar_favorables" in df.columns:
        ops = pd.to_numeric(df.get("ops_totales"), errors="coerce")
        pct = pd.to_numeric(df.get("pct_metar_favorables"), errors="coerce")
        if pct.dropna().max() is not pd.NA and (pct.dropna().max() or 0) > 1:
            pct = pct / 100.0
        df["ops_teoricas_ILS Cat.1"] = (ops * pct).round(2)

    df = df.sort_values("fecha_utc")
    return df

# ===== Utilidades de error =====
def wape(y_real: pd.Series, y_hat: pd.Series) -> float:
    num = (y_real - y_hat).abs().sum(skipna=True)
    den = y_real.abs().sum(skipna=True)
    return float(num / den) if den and den > 0 else float("nan")

def smape_series(y_real: pd.Series, y_hat: pd.Series) -> pd.Series:
    num = (y_real - y_hat).abs()
    den = y_real.abs() + y_hat.abs()
    return pd.Series(np.where(den == 0, 0.0, 2 * num / den), index=y_real.index)

# ===== Renombrado SOLO aquí: Vueling -> CLAVE C y D =====
def _pretty_tfn(col: str) -> str:
    return "CLAVE C y D" if col == "ops_teoricas__Vueling" else col.replace("ops_teoricas__", "").replace("_", " ").strip()

st.header("Teoría ILS vs Operativa Real")

_tfn_path = _find_tfn_path()
if _tfn_path is None:
    st.info("Coloca **TFN_vuelos_METAR_ILS_RWY30.xlsx** en `./`, `./data/` o `/mnt/data/` y recarga.")
else:
    _df_tfn = load_resumen_tfn(_tfn_path)

    # Filtro por el MISMO rango x0–x1 (incluye meses)
    m_tfn = (_df_tfn["fecha_utc"] >= x0) & (_df_tfn["fecha_utc"] <= x1)
    _df_f = _df_tfn.loc[m_tfn].copy()

    if _df_f.empty:
        st.info("No hay datos de esos años.")
    else:
        # Series base (todo en numérico)
        y_real = pd.to_numeric(_df_f.get("ope_reales"), errors="coerce")
        y_ils  = pd.to_numeric(_df_f.get("ops_teoricas_ILS Cat.1"), errors="coerce")
        y_tot  = pd.to_numeric(_df_f.get("ops_totales"), errors="coerce")

        # ---------- Selector de VISTA (solo dos opciones) ----------
        view = st.radio(
            "Vista",
            options=["ILS", "Sin ILS (CLAVE C y D)"],
            index=0,
            horizontal=True,
            help="Los KPIs y los errores siempre se calculan con ILS vs Real."
        )

        # ================= KPIs del TRAMO (siempre ILS vs Real) =================
        s_real = y_real.fillna(0).sum()
        s_ils  = y_ils.fillna(0).sum() if "ops_teoricas_ILS Cat.1" in _df_f.columns else 0
        s_tot  = y_tot.fillna(0).sum()

        err_ils_wape = wape(y_real, y_ils) if "ops_teoricas_ILS Cat.1" in _df_f.columns else np.nan

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Operaciones Realizadas en el tramo", f"{int(s_real):,}".replace(",", "."))
        k2.metric("Operaciones Teoricas con ILS activo",   f"{int(s_ils):,}".replace(",", ".") if s_ils else "—")
        k3.metric("Operaciones Programadas en el tramo",      f"{int(s_tot):,}".replace(",", ".") if s_tot else "—")
        k4.metric("Error % tramo (WAPE ILS vs Real)", f"{err_ils_wape:.1%}" if pd.notna(err_ils_wape) else "—")

        # ================= Gráfica según VISTA =================
        if view == "ILS":
            fig = go.Figure()
            fig.update_layout(hovermode="x unified", xaxis_title="Fecha", yaxis_title="Operaciones", height=520)
            fig.add_trace(go.Scatter(x=_df_f["fecha_utc"], y=y_real, mode="lines", name="Real"))
            if "ops_teoricas_ILS Cat.1" in _df_f.columns:
                fig.add_trace(go.Scatter(x=_df_f["fecha_utc"], y=y_ils,  mode="lines", name="Teoría ILS"))
            fig.update_xaxes(rangeslider=dict(visible=True))
            st.plotly_chart(fig, use_container_width=True, key=f"tfn-ils-real-{x0}-{x1}")
        else:  # Sin ILS (CLAVE C y D)
            tipo_col = "ops_teoricas__Vueling" if "ops_teoricas__Vueling" in _df_f.columns else None
            if tipo_col is None:
                st.info("No hay columna teórica por tipo para CLAVE C y D en este Excel.")
            else:
                y_tipo = pd.to_numeric(_df_f[tipo_col], errors="coerce")
                figb = go.Figure()
                figb.update_layout(hovermode="x unified", xaxis_title="Fecha", yaxis_title="Operaciones", height=520)
                figb.add_trace(go.Scatter(x=_df_f["fecha_utc"], y=y_real, mode="lines", name="Real"))
                figb.add_trace(go.Scatter(x=_df_f["fecha_utc"], y=y_tipo, mode="lines", name=_pretty_tfn(tipo_col)))
                figb.update_xaxes(rangeslider=dict(visible=True))
                st.plotly_chart(figb, use_container_width=True, key=f"tfn-real-tipo-{x0}-{x1}")

        # ================= Error diario (sMAPE con ILS vs Real) =================
        if "ops_teoricas_ILS Cat.1" in _df_f.columns:
            smape_t = smape_series(y_real, y_ils)  # fracción [0..2]
            fig_err = go.Figure()
            fig_err.update_layout(
                hovermode="x",
                xaxis_title="Fecha",
                yaxis_title="% error diario (sMAPE ILS vs Real)",
                height=280
            )
            fig_err.add_trace(go.Scatter(x=_df_f["fecha_utc"], y=smape_t, mode="lines", name="sMAPE diario"))
            fig_err.update_yaxes(tickformat=".0%")
            st.plotly_chart(fig_err, use_container_width=True, key=f"err-smape-ils-{x0}-{x1}")

        # ================= Factor de escala para predicción =================
        st.subheader("Factor de escala para predicción (aplicar a ILS)")

        if "ops_teoricas_ILS Cat.1" in _df_f.columns and s_ils > 0:
            # k* global en el tramo
            k_global = float(s_real / s_ils) if s_ils > 0 else float("nan")

            # k_m por mes del año
            _df_f["_mes"] = _df_f["fecha_utc"].dt.month
            sum_real_m = y_real.groupby(_df_f["_mes"]).sum(min_count=1)
            sum_ils_m  = y_ils.groupby(_df_f["_mes"]).sum(min_count=1)
            k_month = (sum_real_m / sum_ils_m).replace([np.inf, -np.inf], np.nan)

            esquema = st.radio(
                "Esquema de escala",
                options=[f"Global (k* = {k_global:.3f})", "Mensual (k_m por mes del año)"],
                index=0,
                help="Multiplicamos ILS por k para estimar Real:  Ŷ = k · ILS."
            )

            if esquema.startswith("Global"):
                y_pred = y_ils * k_global
                k_used = pd.Series(k_global, index=_df_f.index)
            else:
                # asigna k_m por mes; si falta mes, usa k_global como reserva
                k_map = _df_f["_mes"].map(k_month)
                k_map = k_map.fillna(k_global)
                y_pred = y_ils * k_map
                k_used = k_map

            # Error del tramo con la predicción escalada
            err_pred_wape = wape(y_real, y_pred)

            # KPIs del factor
            c1, c2, c3 = st.columns(3)
            c1.metric("k* (global)", f"{k_global:.3f}")
            c2.metric("Error % tramo usando k (WAPE)", f"{err_pred_wape:.1%}" if pd.notna(err_pred_wape) else "—")
            c3.metric("Suma predicha (Ŷ)", f"{int(y_pred.fillna(0).sum()):,}".replace(",", "."))

            # Gráfica Predicho vs Real
            figp = go.Figure()
            figp.update_layout(hovermode="x unified", xaxis_title="Fecha", yaxis_title="Operaciones", height=420)
            figp.add_trace(go.Scatter(x=_df_f["fecha_utc"], y=y_real, mode="lines", name="Real"))
            figp.add_trace(go.Scatter(x=_df_f["fecha_utc"], y=y_pred, mode="lines", name="Predicho (k·ILS)"))
            figp.update_xaxes(rangeslider=dict(visible=True))
            st.plotly_chart(figp, use_container_width=True, key=f"tfn-predicho-{x0}-{x1}")

            # (Opcional) muestra k_m por mes si se eligió esquema mensual
            if esquema.startswith("Mensual"):
                km_tbl = pd.DataFrame({
                    "Mes": [NUM_A_MES[m] if 'NUM_A_MES' in globals() and m in NUM_A_MES else m for m in k_month.index],
                    "k_m": k_month.round(3)
                })
                st.dataframe(km_tbl, use_container_width=True, hide_index=True)

            # Descarga ligera de la predicción del tramo
            out = pd.DataFrame({
                "Fecha": _df_f["fecha_utc"],
                "Real": y_real,
                "ILS": y_ils,
                "k_aplicado": k_used,
                "Predicho": y_pred
            })
            st.download_button(
                "⬇️ Descargar predicción (tramo actual)",
                data=out.to_csv(index=False).encode("utf-8"),
                file_name=f"prediccion_k_{x0.date()}_{x1.date()}.csv",
                mime="text/csv"
            )
        else:
            st.info("No hay ILS teórica suficiente en el tramo para calcular el factor de escala (k*).")

        # ================= Explicación =================
        st.subheader("Qué significan los errores y cómo usar k* para predecir")
        st.markdown("- **WAPE (tramo)**: mide el desajuste **total** del periodo.\n"
                    "  ")
        st.latex(r"\mathrm{WAPE}=\frac{\sum_t |\,\text{Real}_t-\text{ILS}_t\,|}{\sum_t \text{Real}_t}")
        st.markdown("  *0 % es perfecto; >20–30 % suele indicar desajuste relevante.*")

        st.markdown("- **sMAPE (diario)**: % de error **por día** (acotado 0–200 %) y no explota si Real=0.")
        st.latex(r"\mathrm{sMAPE}_t=\frac{2\,|\,\text{Real}_t-\text{ILS}_t\,|}{|\,\text{Real}_t\,|+|\,\text{ILS}_t\,|}")

        st.markdown("- **Factor de escala (k)**: ajusta ILS al histórico para **predecir** Real.")
        st.latex(r"k^*=\frac{\sum_t \text{Real}_t}{\sum_t \text{ILS}_t}\qquad;\qquad \widehat{\text{Real}}_t=k\cdot \text{ILS}_t")
        st.markdown("  - **Global**: un único \(k^*\) para todo el tramo (simple y estable).\n"
                    "  - **Mensual**: \(k_m\) por mes del año (captura estacionalidad si existe).\n"
                    "  - Evalúa la calidad de la predicción con **WAPE del tramo** y usa la **curva sMAPE** para localizar días problemáticos.")
        

