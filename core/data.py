from __future__ import annotations
from typing import Dict, List
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from core.config import PATHS, TFN_ILS_FILE_PATHS


def _find_path() -> Path:
    p = next((pp for pp in PATHS if pp.exists()), None)
    if p is None:
        raise FileNotFoundError(
            "No encuentro 'ratios_aeronaves_mensual_2014_2025.xlsx' en ./, ./data o /mnt/data"
        )
    return p


def _find_tfn_path() -> Path | None:
    return next((pp for pp in TFN_ILS_FILE_PATHS if pp.exists()), None)


@st.cache_data(show_spinner=True)
def load_all() -> Dict:
    """Lee el Excel y devuelve {ratio_day, ils_col, years_all}."""
    xls = pd.ExcelFile(_find_path())
    sheets = set(xls.sheet_names)

    # Años disponibles desde Top90d_por_año (solo para rango)
    if "Top90d_por_año" not in sheets:
        raise ValueError("Falta la hoja 'Top90d_por_año' en el Excel.")
    t90 = pd.read_excel(xls, sheet_name="Top90d_por_año")
    ren = {}
    if "Aerolinea" in t90.columns:
        ren["Aerolinea"] = "Aerolínea"
    if "Ano" in t90.columns:
        ren["Ano"] = "Año"
    t90 = t90.rename(columns=ren)
    if "Año" not in t90.columns:
        raise ValueError("En 'Top90d_por_año' falta la columna 'Año'.")
    years_all = sorted(t90["Año"].unique().tolist())

    # Ratios_diarios
    if "Ratios_diarios" not in sheets:
        raise ValueError("Falta la hoja 'Ratios_diarios' en el Excel.")
    rd = pd.read_excel(xls, sheet_name="Ratios_diarios")
    date_col = next(
        (c for c in ["Fecha", "FECHA", "fecha", "date", "Date", "index"] if c in rd.columns),
        rd.columns[0],
    )
    rd[date_col] = pd.to_datetime(rd[date_col], errors="coerce")
    rd = rd[rd[date_col].notna()].copy().sort_values(date_col).set_index(date_col)

    # columnas numéricas
    num_cols = [c for c in rd.columns if np.issubdtype(rd[c].dtype, np.number)]
    ratio_day = rd[num_cols].astype(float)

    # ILS
    ils_candidates = [c for c in ratio_day.columns if "ils" in c.lower()]
    ils_col = (
        "ILS Cat.1"
        if "ILS Cat.1" in ratio_day.columns
        else (ils_candidates[0] if ils_candidates else None)
    )
    if ils_col is None:
        raise ValueError("No se detectó ninguna columna con 'ILS' en 'Ratios_diarios'.")

    return {"ratio_day": ratio_day, "ils_col": ils_col, "years_all": years_all}


@st.cache_data(show_spinner=True)
def load_tfn_rwy30() -> pd.DataFrame | None:
    """Carga `TFN_vuelos_METAR_ILS_RWY30.xlsx` (si existe) y devuelve la hoja `resumen_diario` parseada.
    Devuelve None si el archivo no está.
    """
    p = _find_tfn_path()
    if p is None:
        return None
    xls = pd.ExcelFile(p)
    if "resumen_diario" not in set(xls.sheet_names):
        raise ValueError("En TFN_vuelos_METAR_ILS_RWY30.xlsx falta la hoja 'resumen_diario'.")
    df = pd.read_excel(xls, sheet_name="resumen_diario")
    # Tipos
    if "fecha_utc" in df.columns:
        df["fecha_utc"] = pd.to_datetime(df["fecha_utc"], errors="coerce")
    # Forzar numéricos si existen
    for c in [
        "ops_totales",
        "ope_reales",
        "ops_teoricas",
        "metars_dia",
        "metars_favorables",
        "pct_metar_favorables",
        "ope_con_ILS_False",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df