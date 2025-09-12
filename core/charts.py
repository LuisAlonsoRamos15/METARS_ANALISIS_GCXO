from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.config import COLORS, NUM_A_MES


def year_lines(fig: go.Figure, start: pd.Timestamp, end: pd.Timestamp):
    y = start.year + 1
    while y <= end.year:
        fig.add_vline(x=pd.Timestamp(y, 1, 1), line_width=1, line_dash="dot", line_color=COLORS["grid"])
        y += 1


def figure_main(ser: pd.Series, tops: pd.DataFrame, title: str, x0: pd.Timestamp, x1: pd.Timestamp) -> go.Figure:
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=1, line_width=0, fillcolor=COLORS["bgband"], opacity=1.0)
    fig.add_trace(
        go.Scatter(
            x=ser.index,
            y=ser.values,
            mode="lines",
            line=dict(color=COLORS["daily"], width=2.0),
            name="Ratio diario (categoría)",
        )
    )
    # TOP por año
    for _, row in tops.sort_values("Año").iterrows():
        s = pd.to_datetime(row["Inicio_90d"]) ; e = pd.to_datetime(row["Fin_90d"])
        s_plot, e_plot = max(s, x0), min(e, x1)
        if s_plot > e_plot:
            continue
        fig.add_vrect(x0=s_plot, x1=e_plot, fillcolor=COLORS["top_fill"], opacity=1.0, line_width=0)
        mid = s_plot + (e_plot - s_plot) / 2
        y_top = float(min(0.985, np.nanmax(ser[(ser.index >= s_plot) & (ser.index <= e_plot)].values) + 0.01)) if not ser.empty else 0.97
        fig.add_annotation(
            x=mid,
            y=y_top,
            text=f"{row['Ratio_90d']:.0%}",
            showarrow=False,
            bgcolor="#FFFFFF",
            bordercolor=COLORS["top_border"],
            borderwidth=1.5,
            opacity=0.98,
            font=dict(size=16, color="#0B0F10", family="Inter, system-ui"),
        )

    year_lines(fig, x0, x1)
    fig.update_layout(
        title=title,
        margin=dict(l=50, r=20, t=70, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        yaxis=dict(title="Ratio", range=[0, 1], tickformat=".0%"),
        xaxis=dict(title="Fecha"),
    )
    return fig


def ils_compare_timeseries(cat: pd.Series, ils: pd.Series, x0: pd.Timestamp, x1: pd.Timestamp, title: str) -> go.Figure:
    idx = cat.index.union(ils.index)
    cat_u = cat.reindex(idx).interpolate(limit_direction="both")
    ils_u = ils.reindex(idx).interpolate(limit_direction="both")
    m = (idx >= x0) & (idx <= x1)
    cat_u, ils_u = cat_u[m], ils_u[m]

    fig = go.Figure()
    fig.add_hrect(y0=0, y1=1, line_width=0, fillcolor=COLORS["bgband"], opacity=1.0)
    fig.add_trace(go.Scatter(x=cat_u.index, y=cat_u.values, mode="lines", name="Categoría (diario)", line=dict(color=COLORS["daily"], width=1.8)))
    fig.add_trace(go.Scatter(x=ils_u.index, y=ils_u.values, mode="lines", name="ILS (diario)", line=dict(color=COLORS["ils"], width=1.8)))
    year_lines(fig, x0, x1)
    fig.update_layout(title=title, yaxis=dict(title="Ratio", range=[0, 1], tickformat=".0%"), xaxis=dict(title="Fecha"), legend=dict(orientation="h", y=1.02), margin=dict(l=50, r=20, t=70, b=40))
    return fig


def ils_diff_chart(cat: pd.Series, ils: pd.Series, x0: pd.Timestamp, x1: pd.Timestamp, title: str) -> go.Figure:
    idx = cat.index.union(ils.index)
    cat_u = cat.reindex(idx).interpolate(limit_direction="both")
    ils_u = ils.reindex(idx).interpolate(limit_direction="both")
    m = (idx >= x0) & (idx <= x1)
    idx, diff = idx[m], (cat_u - ils_u)[m]

    colors = np.where(diff >= 0, COLORS["diff+"], COLORS["diff-"])
    fig = go.Figure()
    fig.add_bar(x=idx, y=diff.values, marker_color=list(colors))
    fig.add_hline(y=0, line_width=1, line_dash="dot", line_color=COLORS["grid"])
    fig.update_layout(title=title, yaxis=dict(title="Cat − ILS", tickformat="+.0%"), xaxis=dict(title="Fecha"), margin=dict(l=50, r=20, t=60, b=40))
    return fig


def month_mode_hist(tops: pd.DataFrame, title: str) -> go.Figure:
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


def teo_vs_real_bar_monthly(df_monthly: pd.DataFrame, title: str) -> go.Figure:
    """Barras agrupadas Teórico vs Real por mes."""
    if df_monthly is None or df_monthly.empty:
        return go.Figure()
    x = df_monthly["Mes"]
    fig = go.Figure()
    fig.add_bar(name="Teórico", x=x, y=df_monthly["ops_teoricas"], marker_color=COLORS["theoretical"])
    fig.add_bar(name="Real", x=x, y=df_monthly["ope_reales"], marker_color=COLORS["real"])
    fig.update_layout(
        title=title,
        barmode="group",
        xaxis=dict(title="Mes", tickformat="%Y-%m"),
        yaxis=dict(title="Nº operaciones"),
        margin=dict(l=50, r=20, t=70, b=60),
        legend=dict(orientation="h", y=1.02),
    )
    return fig