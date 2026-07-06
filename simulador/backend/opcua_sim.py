#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OPC UA Configurable Simulation Server (YAML/JSON)
-------------------------------------------------
Crea un servidor en base a un fichero de configuración que describe la jerarquía,
tipos de datos y reglas de simulación.

Incluye inyección de ruido y anomalías basadas en el simulador de ciclos original.
"""

import os
import re
import json
import time
import math
import uuid
import queue
import random
import signal
import argparse
import threading
import datetime as dt
from typing import Any, Dict, List, Optional, Union

try:
    import yaml  # PyYAML
    _YAML_OK = True
except Exception:
    _YAML_OK = False

from opcua import ua, Server

# ---------- Utilidades de tipos ----------
DT = ua.VariantType
DATA_TYPE_MAP = {
    "Boolean": DT.Boolean,
    "SByte": DT.SByte,
    "Byte": DT.Byte,
    "Int16": DT.Int16,
    "UInt16": DT.UInt16,
    "Int32": DT.Int32,
    "UInt32": DT.UInt32,
    "Int64": DT.Int64,
    "UInt64": DT.UInt64,
    "Float": DT.Float,
    "Double": DT.Double,
    "String": DT.String,
    "DateTime": DT.DateTime,
    "Guid": DT.Guid,
    "ByteString": DT.ByteString,
    "XmlElement": DT.XmlElement,
    "NodeId": DT.NodeId,
    "ExpandedNodeId": DT.ExpandedNodeId,
    "StatusCode": DT.StatusCode,
    "QualifiedName": DT.QualifiedName,
    "LocalizedText": DT.LocalizedText,
    "ExtensionObject": DT.ExtensionObject,
    "DataValue": DT.DataValue,
    "Variant": DT.Variant,
    "DiagnosticInfo": DT.DiagnosticInfo,
}

# Tipos numéricos susceptibles a ruido
NUMERIC_TYPES = (
    DT.Float, DT.Double, 
    DT.Int16, DT.Int32, DT.Int64, DT.SByte, 
    DT.UInt16, DT.UInt32, DT.UInt64, DT.Byte
)

def clamp(v, lo=None, hi=None):
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v

def parse_hex_bytes(s: str) -> bytes:
    s = s.strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    s = re.sub(r"[^0-9a-f]", "", s)
    if len(s) % 2 == 1:
        s = "0" + s
    return bytes.fromhex(s)

def now_utc():
    return dt.datetime.now(dt.UTC)

# ---------- Generadores de simulación ----------
class ValueGenerator:
    def __init__(self, cfg: dict, dtype: DT):
        self.cfg = cfg or {}
        self.dtype = dtype
        self.mode = (self.cfg.get("mode") or "uniform").lower()
        
        # Configuración de Ruido y Anomalías
        self.noise_cfg = self.cfg.get("noise", {})
        self.anomaly_cfg = self.cfg.get("anomaly", {})

        self._toggle_state = False
        self._step_val = self.cfg.get("start", self.cfg.get("min", 0))

    def _coerce(self, v):
        """Convierte Python value al tipo base adecuado respetando límites de enteros."""
        try:
            if self.dtype in (DT.Float, DT.Double):
                return float(v)
            if self.dtype in (DT.Int16, DT.Int32, DT.Int64, DT.SByte):
                return int(v)
            if self.dtype in (DT.UInt16, DT.UInt32, DT.UInt64, DT.Byte):
                return max(0, int(v)) # Prevenir negativos en unsigned
            if self.dtype == DT.Boolean:
                return bool(v)
            if self.dtype == DT.String:
                return str(v)
            if self.dtype == DT.DateTime:
                if isinstance(v, dt.datetime): return v
                return now_utc()
            if self.dtype == DT.Guid:
                if isinstance(v, uuid.UUID): return v
                return uuid.uuid4()
            if self.dtype == DT.ByteString:
                if isinstance(v, (bytes, bytearray)): return bytes(v)
                if isinstance(v, str): return parse_hex_bytes(v)
                return b""
            if self.dtype == DT.LocalizedText:
                if isinstance(v, dict): return ua.LocalizedText(v.get("text", ""), v.get("locale", ""))
                return ua.LocalizedText(str(v))
            if self.dtype == DT.QualifiedName:
                if isinstance(v, dict): return ua.QualifiedName(v.get("name", ""), int(v.get("ns", 0)))
                return ua.QualifiedName(str(v))
            if self.dtype == DT.XmlElement:
                if isinstance(v, ua.XmlElement): return v
                if isinstance(v, str): return ua.XmlElement(v.encode("utf-8"))
                return ua.XmlElement(b"<v/>")
        except (ValueError, TypeError):
            pass # Si falla la coerción (por inyectar ruido a un bool por error), devolvemos fallback
        return v

    def _apply_effects(self, val):
        """Aplica las transformaciones de ruido y anomalías si aplican al tipo de dato."""
        if self.dtype not in NUMERIC_TYPES:
            return self._coerce(val)

        v_float = float(val)

        # 1. Aplicar Anomalías (ej. un pico de tensión repentino)
        if self.anomaly_cfg.get("enabled", False):
            prob = self.anomaly_cfg.get("probability", 0.01) # 1% de probabilidad por defecto
            if random.random() < prob:
                atype = self.anomaly_cfg.get("type", "spike").lower()
                params = self.anomaly_cfg.get("params", {})
                
                if atype == "spike":
                    multiplier = params.get("multiplier", 2.0)
                    offset = params.get("offset", 10.0)
                    v_float = (v_float * multiplier) + offset
                elif atype == "drop":
                    v_float = params.get("value", 0.0) # Caída a cero o valor mínimo

        # 2. Aplicar Ruido Constante
        if self.noise_cfg.get("enabled", False):
            ntype = self.noise_cfg.get("type", "gaussian").lower()
            params = self.noise_cfg.get("params", {})

            if ntype == "gaussian":
                mean = params.get("mean", 0.0)
                std = params.get("stddev", 1.0)
                v_float += random.gauss(mean, std)
            elif ntype == "uniform":
                lo = params.get("min", -1.0)
                hi = params.get("max", 1.0)
                v_float += random.uniform(lo, hi)
            elif ntype == "white": # Variación porcentual
                pct = params.get("percent", 1.0)
                v_float += v_float * (pct / 100.0) * (random.random() * 2 - 1)

        # Volver a convertir al tipo original (int32, float, etc) para evitar cuelgues de OPC UA
        return self._coerce(v_float)

    def next_scalar(self):
        m = self.mode
        v = 0 # Fallback default

        if m == "toggle":
            self._toggle_state = not self._toggle_state
            return self._coerce(self._toggle_state) # Booleans no llevan ruido

        if m == "choice":
            choices = self.cfg.get("choices", [0, 1])
            v = random.choice(choices)
        elif m == "normal":
            mean = self.cfg.get("mean", 0)
            std = self.cfg.get("stddev", 1)
            v = random.gauss(mean, std)
            v = clamp(v, self.cfg.get("min"), self.cfg.get("max"))
        elif m == "uniform":
            lo = self.cfg.get("min", 0)
            hi = self.cfg.get("max", 1)
            if self.dtype in (DT.Float, DT.Double):
                v = random.uniform(lo, hi)
            else:
                v = random.randint(int(lo), int(hi))
        elif m == "step":
            step = self.cfg.get("step", 1)
            lo = self.cfg.get("min", None)
            hi = self.cfg.get("max", None)
            self._step_val = (self._step_val or 0) + step
            if lo is not None or hi is not None:
                if hi is not None and self._step_val > hi:
                    self._step_val = lo if lo is not None else hi
                if lo is not None and self._step_val < lo:
                    self._step_val = lo
            v = self._step_val
        elif m == "now":
            return self._coerce(now_utc())
        elif m == "guid":
            return uuid.uuid4()
        elif m == "jitter":
            base = self.cfg.get("base", 0)
            pct = self.cfg.get("percent", 1.0)
            jitter = base * (pct / 100.0) * (random.random() * 2 - 1)
            v = base + jitter

        # Aplicar el filtro final de ruido y anomalías a la señal generada
        return self._apply_effects(v)

    def next_array(self, length: int):
        return [self.next_scalar() for _ in range(length)]

    def next_matrix(self, dims: List[int]):
        if len(dims) != 2:
            total = math.prod(dims)
            return self.next_array(total)
        r, c = dims
        return [[self.next_scalar() for _ in range(c)] for _ in range(r)]


# ---------- Updater ----------
class Updater(threading.Thread):
    def __init__(self, node, dtype: DT, sim_cfg: dict, last_update_node=None, array_rank=-1, arr_len=None, arr_dims=None, name="Updater"):
        super().__init__(daemon=True, name=name)
        self.node = node
        self.dtype = dtype
        self.sim = sim_cfg or {}
        self.array_rank = array_rank
        self.arr_len = arr_len
        self.arr_dims = arr_dims
        self.last_update_node = last_update_node
        self.stop_evt = threading.Event()
        self.gen = ValueGenerator(self.sim, dtype)

        self.period = max(100, int(self.sim.get("update_ms", 0) or 0))
        if self.period <= 0:
            self.period = None 

    def run(self):
        if not self.period:
            return
        while not self.stop_evt.is_set():
            try:
                if self.array_rank == 1 and self.arr_len is not None:
                    val = self.gen.next_array(self.arr_len)
                elif self.array_rank == 2 and self.arr_dims:
                    val = self.gen.next_matrix(self.arr_dims)
                else:
                    val = self.gen.next_scalar()

                self.node.set_value(ua.Variant(val, self.dtype))
                if self.last_update_node is not None:
                    self.last_update_node.set_value(ua.Variant(now_utc(), DT.DateTime))
            except Exception as e:
                print(f"[WARN] Updater error on {self.name}: {e}")
            time.sleep(self.period / 1000.0)

    def stop(self):
        self.stop_evt.set()


# ---------- Construcción del Space ----------
class SpaceBuilder:
    def __init__(self, server: Server, cfg: dict):
        self.server = server
        self.cfg = cfg
        self.idx = server.register_namespace(cfg["server"]["namespace_uri"])
        self.objects = server.get_objects_node()
        self.last_update_nodes = []
        self.updaters: List[Updater] = []
        self.default_update_ms = int(cfg.get("simulation", {}).get("default_update_ms", 1200))

    def _variant_type(self, name: str) -> DT:
        if name not in DATA_TYPE_MAP:
            raise ValueError(f"DataType no soportado: {name}")
        return DATA_TYPE_MAP[name]

    def _add_variable(self, parent, vdef: dict):
        name = vdef["browse_name"]
        dtype = self._variant_type(vdef["data_type"])
        writable = bool(vdef.get("writable", True))
        value_rank = int(vdef.get("value_rank", -1))

        initial = vdef.get("initial", None)
        sim_cfg = vdef.get("simulation", {}) or {}
        
        if initial is not None:
            val = initial
            if dtype == DT.DateTime and isinstance(val, str) and val == "now": val = now_utc()
            if dtype == DT.Guid and isinstance(val, str): val = uuid.UUID(val)
            if dtype == DT.ByteString and isinstance(val, str): val = parse_hex_bytes(val)
        else:
            gen = ValueGenerator(sim_cfg, dtype)
            if value_rank == 1:
                arr_len = int(vdef.get("array_length", 0) or 0) or 3
                val = gen.next_array(arr_len)
            elif value_rank == 2:
                dims = vdef.get("array_dimensions", [2, 2])
                val = gen.next_matrix(dims)
            else:
                val = gen.next_scalar()

        var = parent.add_variable(self.idx, name, ua.Variant(val, dtype), dtype)
        var.set_writable(writable)

        if value_rank >= 0:
            var.set_attribute(ua.AttributeIds.ValueRank, ua.DataValue(ua.Variant(value_rank, DT.Int32)))
            if value_rank == 1 and "array_length" in vdef:
                var.set_attribute(ua.AttributeIds.ArrayDimensions, ua.DataValue(ua.Variant([int(vdef["array_length"])], DT.UInt32)))
            if value_rank == 2 and "array_dimensions" in vdef:
                dims = [int(x) for x in vdef["array_dimensions"]]
                var.set_attribute(ua.AttributeIds.ArrayDimensions, ua.DataValue(ua.Variant(dims, DT.UInt32)))

        update_ms = sim_cfg.get("update_ms", self.default_update_ms)
        if update_ms:
            arr_len = vdef.get("array_length")
            arr_dims = vdef.get("array_dimensions")
            up = Updater(
                node=var, dtype=dtype, sim_cfg=sim_cfg,
                last_update_node=None,
                array_rank=value_rank, arr_len=arr_len, arr_dims=arr_dims,
                name=f"{name}-Updater"
            )
            self.updaters.append(up)
        return var

    def _add_method(self, parent, mdef: dict):
        name = mdef["browse_name"]
        in_args = []
        out_args = []

        for arg in mdef.get("input_args", []):
            a = ua.Argument()
            a.Name = arg["name"]
            a.DataType = ua.NodeId(getattr(ua.ObjectIds, arg["data_type"]))
            a.ValueRank = -1
            in_args.append(a)

        for arg in mdef.get("output_args", []):
            a = ua.Argument()
            a.Name = arg["name"]
            a.DataType = ua.NodeId(getattr(ua.ObjectIds, arg["data_type"]))
            a.ValueRank = -1
            out_args.append(a)

        impl = (mdef.get("implementation") or "").lower()

        def on_call(_parent, variants):
            if impl == "reset_speed":
                try: speed = parent.get_child([f"{self.idx}:Speed"])
                except Exception: return [ua.Variant(0, DT.Int32), ua.Variant(0, DT.Int32)]
                try: target = int(variants[0])
                except Exception: target = 0
                old = int(speed.get_value())
                speed.set_value(ua.Variant(target, DT.Int32))
                return [ua.Variant(old, DT.Int32), ua.Variant(target, DT.Int32)]
            return [ua.Variant(int(v.Value), DT.Int32) for v in variants]

        parent.add_method(self.idx, name, on_call, in_args, out_args)

    def _walk(self, parent, items: List[dict]):
        for item in items or []:
            kind = (item.get("kind") or "Object").lower()
            if kind == "object":
                node = parent.add_object(self.idx, item["browse_name"])
                self._walk(node, item.get("children", []))
            elif kind == "variable":
                self._add_variable(parent, item)
            elif kind == "method":
                self._add_method(parent, item)
            else:
                raise ValueError(f"Kind no soportado: {kind}")

    def build(self):
        self._walk(self.objects, self.cfg.get("nodes", []))
        return self.updaters

# ---------- Carga de configuración ----------
def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        if path.lower().endswith((".yml", ".yaml")) and _YAML_OK:
            cfg = yaml.safe_load(f)
        else:
            cfg = json.load(f)
    cfg.setdefault("server", {})
    cfg["server"].setdefault("host", "0.0.0.0")
    cfg["server"].setdefault("port", 5679)
    cfg["server"].setdefault("name", "Mock OPC UA - Configurable")
    cfg["server"].setdefault("application_uri", "urn:mock:configurable:server")
    cfg["server"].setdefault("namespace_uri", "urn:Configurable:OPCUA")
    return cfg

# ---------- Main ----------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", "-c", required=True, help="Ruta a YAML/JSON de configuración")
    args = parser.parse_args()

    cfg = load_config(args.config)
    host = cfg["server"]["host"]
    port = int(cfg["server"]["port"])
    endpoint = f"opc.tcp://{host}:{port}"

    server = Server()
    server.set_endpoint(endpoint)
    server.set_server_name(cfg["server"]["name"])
    server.set_application_uri(cfg["server"]["application_uri"])
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])

    builder = SpaceBuilder(server, cfg)
    updaters = builder.build()

    server.start()
    print(f"[OPCUA] Server started on {endpoint}")

    for u in updaters:
        u.start()

    stop_evt = threading.Event()

    def _handle_sig(*_):
        stop_evt.set()

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    try:
        while not stop_evt.is_set():
            time.sleep(0.5)
    finally:
        print("[OPCUA] Stopping server...")
        for u in updaters:
            u.stop()
        for u in updaters:
            u.join(timeout=1.0)
        server.stop()
        print("[OPCUA] Server stopped.")

if __name__ == "__main__":
    main()