# project/chart_builder.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def procesar_datos(data_points: List[Dict]) -> Tuple[List[str], List[float]]:
    parsed = []
    for p in data_points:
        x_raw = p.get("x") or p.get("timestamp") or p.get("time") or ""
        y_raw = p.get("y")
        if y_raw is None:
            y_raw = p.get("value")
        if y_raw is None:
            y_raw = p.get("valor", 0.0)
        dt_obj = None
        if isinstance(x_raw, str) and ("T" in x_raw or "-" in x_raw):
            try:
                dt_obj = datetime.fromisoformat(x_raw.replace("Z", "+00:00"))
            except Exception:
                pass
        try:
            y_val = float(y_raw)
        except (TypeError, ValueError):
            y_val = 0.0
        parsed.append({"raw_x": str(x_raw), "dt": dt_obj, "y": y_val})

    con_fecha = [p for p in parsed if p["dt"] is not None]
    if con_fecha:
        dummy = datetime.min.replace(tzinfo=timezone.utc)
        parsed.sort(key=lambda p: p["dt"] if p["dt"] else dummy)
        con_fecha.sort(key=lambda p: p["dt"])
        span = (con_fecha[-1]["dt"] - con_fecha[0]["dt"]).total_seconds() / 3600.0
        for p in parsed:
            if p["dt"] is None:
                p["x_final"] = p["raw_x"]
            elif span <= 24:
                p["x_final"] = p["dt"].strftime("%H:%M")
            elif span <= 24 * 365:
                p["x_final"] = p["dt"].strftime("%d/%m")
            else:
                p["x_final"] = p["dt"].strftime("%m/%Y")
    else:
        for p in parsed:
            p["x_final"] = p["raw_x"]
    return [p["x_final"] for p in parsed], [round(p["y"], 3) for p in parsed]


def build_chart_payload(parameter_name, data_points, chart_type="line", color_hex="#00FFFF"):
    x_labels, y_values = procesar_datos(data_points)
    return {
        "event": "chart_data",
        "chart_type": chart_type,
        "dataset": {"name": parameter_name, "values": y_values, "color": color_hex},
        "labels_x": x_labels,
        "response": "",
    }


def compute_stats(y_values: List[float]) -> Dict[str, float]:
    if not y_values:
        return {"count": 0}
    return {
        "count": len(y_values),
        "min": round(min(y_values), 3),
        "max": round(max(y_values), 3),
        "avg": round(sum(y_values) / len(y_values), 3),
        "first": round(y_values[0], 3),
        "last": round(y_values[-1], 3),
    }