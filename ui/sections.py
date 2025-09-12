from __future__ import annotations
import streamlit as st
import pandas as pd
from pandas.tseries.offsets import MonthEnd

from core.config import NUM_A_MES
from core.charts import figure_main, month_mode_hist, ils_compare_timeseries, ils_diff_chart, teo_vs_real_bar_monthly
from core.data import load_tfn_rwy30
from core.analysis import monthly_ops_teo_real, correction_factor_mean


def section_main_charts(ser_full: pd.Series, tops_cat: pd.DataFrame, category: str, x0: pd.Timestamp, x1: pd.Timestamp, mode: str):
    if ser_full.loc[(ser_full.index >= x0) & (ser_full.index <= x1)].dropna().empty:
        st.info("No hay datos diarios para ese rango/categoría.")
        return

    years_in_range = list(range(x0.year, x1.year + 1))

    if mode.startswith("Acumulada"):
        fig = figure_main(
            ser_full.loc[(ser_full.index >= x0) & (ser_full.index <= x1)].dropna(),
            tops_cat,
            f"{category} — {NUM_A_MES[x0.month]} {x0.year} – {NUM_A_MES[x1.month]} {x1.year}",
            x0,
            x1,
        )
        st.plotly_chart(fig, use_container_width=True, key=f"acc-{category}-{x0}-{x1}")
    else:
        cols = st.columns(2)
        idx = 0
        for y in years_in_range:
            y0 = max(pd.Timestamp(y, 1, 1), x0)
            y1 = min(pd.Timestamp(y, 12, 31) + MonthEnd(0), x1)
            ser_y = ser_full.loc[(ser_full.index >= y0) & (ser_full.index <= y1)].dropna()
            if ser_y.empty:
                continue
            tops_y = tops_cat[tops_cat["Año"] == y]
            figy = figure_main(ser_y, tops_y, f"{category} — {y}", y0, y1)
            with cols[idx % 2]:
                st.plotly_chart(figy, use_container_width=True, key=f"year-{category}-{y}-{y0.month}-{y1.month}")
            idx += 1


def section_histogram(tops_cat: pd.DataFrame, category: str, x0: pd.Timestamp, x1: pd.Timestamp):
    st.subheader("Mes de inicio de las mejores ventanas (TOP 90d por año)")
    st.plotly_chart(
        month_mode_hist(tops_cat, "Mes de inicio más frecuente (en el rango seleccionado)"),
        use_container_width=True,
        key=f"mode-{category}-{x0}-{x1}",
    )


def section_table_download(tops_cat: pd.DataFrame, category: str, x0: pd.Timestamp, x1: pd.Timestamp):
    st.subheader("Tabla de ventanas TOP (recalculadas)")
    tbl = tops_cat.sort_values("Año").copy()
    st.dataframe(tbl, use_container_width=True, hide_index=True, key=f"tabla-{category}-{x0}-{x1}")
    st.download_button(
        "⬇️ Descargar TOP 90d por año (CSV)",
        data=tbl.to_csv(index=False).encode("utf-8"),
        file_name=f"top90_{category}_{x0.date()}_{x1.date()}.csv",
        mime="text/csv",
        key=f"dl-{category}-{x0}-{x1}",
    )


def section_ils_compare(ser_full: pd.Series, ils_series: pd.Series, ils_col: str, category: str, x0: pd.Timestamp, x1: pd.Timestamp):
    st.plotly_chart(
        ils_compare_timeseries(
            ser_full,
            ils_series,
            x0,
            x1,
            f"{category} vs {ils_col} — {NUM_A_MES[x0.month]} {x0.year} – {NUM_A_MES[x1.month]} {x1.year}",
        ),
        use_container_width=True,
        key=f"ils-ts-{category}-{x0}-{x1}",
    )

    st.plotly_chart(
        ils_diff_chart(
            ser_full,
            ils_series,
            x0,
            x1,
            f"Diferencia diaria (Categoría − {ils_col})",
        ),
        use_container_width=True,
        key=f"ils-diff-{category}-{x0}-{x1}",
    )


def section_tfn_rwy30_monthly(x0: pd.Timestamp, x1: pd.Timestamp):
    """Sección RWY30 TFN: barras Teórico vs Real + factores de corrección."""
    df = load_tfn_rwy30()
    if df is None:
        st.info("No se encontró 'TFN_vuelos_METAR_ILS_RWY30.xlsx' en ./, ./data o /mnt/data. Sube el archivo para ver esta sección.")
        return

    dfm = monthly_ops_teo_real(df, x0, x1)
    if dfm.empty:
        st.info("No hay datos de RWY30 para el rango seleccionado.")
        return

    st.subheader("TFN RWY30 · Operaciones teóricas vs reales (mensual)")
    st.plotly_chart(
        teo_vs_real_bar_monthly(dfm, "TFN RWY30 · Operaciones teóricas vs reales (mensual)"),
        use_container_width=True,
        key=f"tfn30-bar-{x0}-{x1}",
    )

    cw = correction_factor_mean(dfm, weighted=True)
    cu = correction_factor_mean(dfm, weighted=False)

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        st.metric("Factor de corrección (ponderado por teórico)", f"{cw:.3f}" if pd.notna(cw) else "—")
    with c2:
        st.metric("Media mensual del factor", f"{cu:.3f}" if pd.notna(cu) else "—")
    with c3:
        if "ope_con_ILS_False" in dfm.columns:
            st.caption(f"⚠️ OPE con METAR incompatible (ILS False) en el periodo: {int(dfm['ope_con_ILS_False'].sum()):,}")

    with st.expander("¿Cómo se calculan Teórico y el Factor de Corrección?"):
        st.markdown(
            """
            **Metodología (resumen):**

            1. Se empareja cada vuelo de llegada en **TFN RWY30** con el **último METAR** disponible (GCXO)
               **anterior o igual** a la hora del vuelo (tolerancia ±3 h).
            2. Se marca **ILS_Cat1** del METAR y se calcula por **día** el % de METAR **favorables**.
            3. Por **día**:
               - `ops_totales`: nº de operaciones en RWY30.
               - `ope_reales`: nº de operaciones en situación **OPE**.
               - `pct_metar_favorables`: proporción de METAR favorables.
               - `ops_teoricas = ops_totales × pct_metar_favorables`.
            4. Se agregan las métricas por **mes** (sumas) para la gráfica.
            5. **Factor de corrección (mes)** = `ope_reales / ops_teoricas` (si `ops_teoricas > 0`).
               - **Ponderado** (global del periodo): `(Σ ope_reales) / (Σ ops_teoricas)`.
               - **Media mensual**: promedio simple de los factores mensuales.
            """
        )

    st.download_button(
        "⬇️ Descargar tabla mensual (CSV)",
        data=dfm.to_csv(index=False).encode("utf-8"),
        file_name=f"tfn_rwy30_teorico_vs_real_{x0.date()}_{x1.date()}.csv",
        mime="text/csv",
        key=f"tfn30-dl-{x0}-{x1}",
    )

    st.dataframe(dfm, use_container_width=True, hide_index=True, key=f"tfn30-tbl-{x0}-{x1}")