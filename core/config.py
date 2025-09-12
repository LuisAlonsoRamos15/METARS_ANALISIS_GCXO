from __future__ import annotations
from pathlib import Path

# Ajustes de página
PAGE_TITLE = "Top 90 días — categorías"
LAYOUT = "wide"

# Rutas candidatas (en orden de prioridad)
PATHS = [
    Path("ratios_aeronaves_mensual_2014_2025.xlsx"),
    Path("data/ratios_aeronaves_mensual_2014_2025.xlsx"),
    Path("/mnt/data/ratios_aeronaves_mensual_2014_2025.xlsx"),
]

# Dataset adicional (opcional) para RWY30 TFN (salida del script analítico)
TFN_ILS_FILE_PATHS = [
    Path("TFN_vuelos_METAR_ILS_RWY30.xlsx"),
    Path("data/TFN_vuelos_METAR_ILS_RWY30.xlsx"),
    Path("/mnt/data/TFN_vuelos_METAR_ILS_RWY30.xlsx"),
]

# Colores / estilo
COLORS = {
    "daily": "#F97316",
    "top_fill": "rgba(16,185,129,0.22)",
    "top_border": "#0F766E",
    "bgband": "rgba(255,255,255,0.05)",
    "grid": "#4B5563",
    "ils": "#22C55E",
    "diff+": "#22C55E",
    "diff-": "#F97316",
    "bar": "#0EA5E9",
    # Nuevos colores para barras Teórico vs Real
    "theoretical": "#F97316",  # gris muy oscuro
    "real": "#A3E635",         # lima
}

MESES = [
    ("Enero", 1), ("Febrero", 2), ("Marzo", 3), ("Abril", 4),
    ("Mayo", 5), ("Junio", 6), ("Julio", 7), ("Agosto", 8),
    ("Septiembre", 9), ("Octubre", 10), ("Noviembre", 11), ("Diciembre", 12),
]
MES_A_NUM = {n: i for n, i in MESES}
NUM_A_MES = {i: n for n, i in MESES}

WINDOW_DAYS = 90