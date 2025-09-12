from __future__ import annotations
from typing import Dict, List
import pandas as pd

# ====== Categorías (tokens para buscar columnas a promediar) ======
CATEGORY_TOKENS: Dict[str, List[str]] = {
    "CLAVE C y D": [
        "AEA", "RYR", "VLG", "VUELING", "IBE", "IBERIA", "EZY", "U2",
        "A320", "A321", "B737", "B738", "B739", "B38M", "B38X",
    ],
    "E295": ["E295", "E190", "E195"],
    "AT76": ["AT76", "ATR72"],
    "AT75": ["AT75", "ATR72-500", "ATR75"],
}


def cols_for_category(ratio_day: pd.DataFrame, category: str) -> List[str]:
    toks = [t.upper() for t in CATEGORY_TOKENS.get(category, [])]
    return [c for c in ratio_day.columns if any(t in c.upper() for t in toks)]


def category_series(ratio_day: pd.DataFrame, members: List[str]) -> pd.Series:
    return ratio_day[members].mean(axis=1, skipna=True) if members else pd.Series(dtype=float)