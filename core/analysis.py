from __future__ import annotations
import pandas as pd
import numpy as np
from core.config import WINDOW_DAYS


def rolling90_top1_by_year(series: pd.Series, years: list[int]) -> pd.DataFrame:
    """Mejor ventana 90d por año (el año es el del día de INICIO de la ventana)."""
    s = series.sort_index()
    r90 = s.rolling(WINDOW_DAYS, min_periods=WINDOW_DAYS).mean().dropna()
    out = []
    for y in years:
        candidates = []
        for end_ts, val in r90.items():
            start_ts = end_ts - pd.Timedelta(days=WINDOW_DAYS - 1)
            if start_ts.year == y:
                candidates.append((start_ts, end_ts, float(val)))
        if not candidates:
            continue
        start_best, end_best, v = max(candidates, key=lambda t: t[2])
        out.append({"Año": y, "Inicio_90d": start_best, "Fin_90d": end_best, "Ratio_90d": v})
    return pd.DataFrame(out)


def monthly_ops_teo_real(resumen_diario: pd.DataFrame, x0: pd.Timestamp | None = None, x1: pd.Timestamp | None = None, *, clip_to_today: bool = True) -> pd.DataFrame:
    """Agrega por mes las columnas clave del `resumen_diario` del RWY30.
    Devuelve un DataFrame con columnas: Mes, ops_totales, ope_reales, ops_teoricas,
    metars_dia, metars_favorables, pct_metar_favorables, ope_con_ILS_False, factor_mes.

    - `clip_to_today=True` recorta filas con fecha futura (> hoy), útil para evitar meses que aún no han ocurrido.
    """
    if resumen_diario is None or resumen_diario.empty:
        return pd.DataFrame()
    df = resumen_diario.copy()
    if "fecha_utc" not in df.columns:
        return pd.DataFrame()
    df = df[df["fecha_utc"].notna()].sort_values("fecha_utc")

    if clip_to_today:
        today = pd.Timestamp.today().normalize()
        df = df[df["fecha_utc"] <= today]

    if x0 is not None:
        df = df[df["fecha_utc"] >= pd.to_datetime(x0)]
    if x1 is not None:
        df = df[df["fecha_utc"] <= pd.to_datetime(x1)]

    df["Mes"] = pd.to_datetime(df["fecha_utc"]).dt.to_period("M").dt.to_timestamp()

    agg = df.groupby("Mes").agg(
        ops_totales=("ops_totales", "sum"),
        ope_reales=("ope_reales", "sum"),
        ops_teoricas=("ops_teoricas", "sum"),
        metars_dia=("metars_dia", "sum"),
        metars_favorables=("metars_favorables", "sum"),
        ope_con_ILS_False=("ope_con_ILS_False", "sum"),
    ).reset_index()

    agg["pct_metar_favorables"] = np.where(
        agg["metars_dia"] > 0, agg["metars_favorables"] / agg["metars_dia"], np.nan
    )
    agg["factor_mes"] = np.where(
        agg["ops_teoricas"] > 0, agg["ope_reales"] / agg["ops_teoricas"], np.nan
    )
    return agg


def correction_factor_mean(df_monthly: pd.DataFrame, weighted: bool = True) -> float:
    """Factor de corrección medio.
    - Si `weighted=True`: (Σ reales) / (Σ teóricas)
    - Si `weighted=False`: media simple de `factor_mes`.
    """
    if df_monthly is None or df_monthly.empty:
        return float("nan")
    if weighted:
        den = float(df_monthly["ops_teoricas"].sum())
        return float(df_monthly["ope_reales"].sum() / den) if den > 0 else float("nan")
    s = df_monthly["factor_mes"].dropna()
    return float(s.mean()) if not s.empty else float("nan")