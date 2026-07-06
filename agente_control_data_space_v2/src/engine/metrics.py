# src/engine/metrics.py
# -*- coding: utf-8 -*-
"""
Sistema de Métricas Mejorado v2
Fecha: 13 Febrero 2026

TRACKING REAL:
- TokenTracker: Callback handler que captura usage REAL de cada llamada LLM
- Tokens IN (prompt) vs OUT (completion) acumulados por request
- Costos diferenciados por tipo de token
- Acumulación por sesión
- Métricas por request
"""

import time
import asyncio
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

# ============================================================
# COSTOS POR PROVEEDOR Y MODELO
# ============================================================

# Precios por 1K tokens (Febrero 2026)
#
# PATCH: se añade la familia gpt-4.1 (incl. gpt-4.1-nano), que faltaba y
# provocaba que calculate_cost() devolviera 0 para el modelo en uso. El
# matching de calculate_cost() es por substring, así que las claves más
# específicas ("gpt-4.1-nano") deben ir ANTES que las genéricas ("gpt-4")
# para no colisionar. Los dicts conservan el orden de inserción (Py3.7+).
PRICING = {
    "azure": {
        "gpt-4.1-nano": {"prompt": 0.0001,  "completion": 0.0004},
        "gpt-4.1-mini": {"prompt": 0.0004,  "completion": 0.0016},
        "gpt-4.1":      {"prompt": 0.002,   "completion": 0.008},
        "gpt-4o-mini":  {"prompt": 0.00015, "completion": 0.0006},
        "gpt-4o":       {"prompt": 0.0025,  "completion": 0.01},
        "gpt-4":        {"prompt": 0.03,    "completion": 0.06},
        "gpt-3.5-turbo":{"prompt": 0.0005,  "completion": 0.0015},
    },
    "openai": {
        "gpt-4.1-nano": {"prompt": 0.0001,  "completion": 0.0004},
        "gpt-4.1-mini": {"prompt": 0.0004,  "completion": 0.0016},
        "gpt-4.1":      {"prompt": 0.002,   "completion": 0.008},
        "gpt-4o-mini":  {"prompt": 0.00015, "completion": 0.0006},
        "gpt-4o":       {"prompt": 0.0025,  "completion": 0.01},
        "gpt-4":        {"prompt": 0.03,    "completion": 0.06},
        "gpt-3.5-turbo":{"prompt": 0.0005,  "completion": 0.0015},
    },
    "local": {
        "default": {"prompt": 0.0, "completion": 0.0}
    }
}

def calculate_cost(prompt_tokens: int, completion_tokens: int, provider: str, model: str) -> float:
    """
    Calcula costo de tokens basado en proveedor y modelo.
    
    Args:
        prompt_tokens: Tokens de entrada
        completion_tokens: Tokens de salida
        provider: 'azure', 'openai', 'local'
        model: Nombre del modelo/deployment
    
    Returns:
        Costo en USD
    """
    provider = provider.lower()
    model = model.lower()
    
    # Buscar pricing del proveedor
    provider_pricing = PRICING.get(provider, PRICING.get("local", {}))
    
    # Buscar modelo específico o usar default
    for model_key, prices in provider_pricing.items():
        if model_key in model:
            prompt_cost = (prompt_tokens / 1000) * prices["prompt"]
            completion_cost = (completion_tokens / 1000) * prices["completion"]
            return prompt_cost + completion_cost
    
    # Si es local o no encontrado, costo 0
    return 0.0


# ============================================================
# TOKEN TRACKER - Captura usage real de TODAS las llamadas LLM
# ============================================================

class TokenTracker:
    """
    Rastreador de tokens que captura el 'usage' real de cada llamada
    a la API de OpenAI/Azure. Se usa como wrapper alrededor del LLM
    para interceptar todas las respuestas (aggregator + especialistas).
    
    Thread-safe: usa threading.Lock para contextos sync/async mixtos.
    
    Uso:
        tracker = TokenTracker()
        tracker.reset()  # Al inicio de cada request
        
        # ... se ejecutan las llamadas LLM ...
        
        totals = tracker.get_totals()
        # {'prompt_tokens': 1234, 'completion_tokens': 567, 'total_tokens': 1801}
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._calls: List[Dict[str, int]] = []
    
    def reset(self):
        """Limpia contadores para una nueva request."""
        with self._lock:
            self._calls.clear()
    
    def record(self, prompt_tokens: int = 0, completion_tokens: int = 0, total_tokens: int = 0):
        """Registra tokens de una llamada LLM individual."""
        with self._lock:
            self._calls.append({
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens or (prompt_tokens + completion_tokens),
                "timestamp": time.time()
            })
    
    def get_totals(self) -> Dict[str, int]:
        """Devuelve totales acumulados de todas las llamadas."""
        with self._lock:
            prompt = sum(c["prompt_tokens"] for c in self._calls)
            completion = sum(c["completion_tokens"] for c in self._calls)
            total = sum(c["total_tokens"] for c in self._calls)
            return {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total if total > 0 else (prompt + completion),
                "num_llm_calls": len(self._calls)
            }
    
    def get_call_details(self) -> List[Dict[str, int]]:
        """Devuelve detalle de cada llamada individual."""
        with self._lock:
            return list(self._calls)


# Instancia global del tracker
token_tracker = TokenTracker()


# ============================================================
# DATACLASSES DE MÉTRICAS
# ============================================================

@dataclass
class RequestMetrics:
    """Métricas de una request individual."""
    request_id: str
    session_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Proveedor y modelo
    provider: str = "local"
    model: str = "unknown"
    
    # Tiempos
    total_time: float = 0.0
    llm_time: float = 0.0
    
    # Tokens (separados IN/OUT) - REALES del API
    tokens_prompt: float = 0.0  # IN
    tokens_completion: float = 0.0  # OUT
    tokens_total: int = 0
    
    # Número de llamadas LLM en esta request
    num_llm_calls: int = 0
    
    # Costo
    estimated_cost: float = 0.0
    
    # Metadata
    error: Optional[str] = None
    tool_calls: int = 0


@dataclass
class SessionStats:
    """Estadísticas acumuladas de una sesión."""
    session_id: str
    started_at: datetime = field(default_factory=datetime.now)
    
    # Contadores
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Tokens acumulados
    total_prompt_tokens: float = 0.0
    total_completion_tokens: float = 0.0
    total_tokens: int = 0
    
    # Tiempos
    total_time: float = 0.0
    avg_time: float = 0.0
    
    # Costos
    total_cost: float = 0.0
    
    # LLM calls
    total_llm_calls: int = 0
    
    def update(self, metrics: RequestMetrics):
        """Actualiza estadísticas con una nueva request."""
        self.total_requests += 1
        
        if metrics.error:
            self.failed_requests += 1
        else:
            self.successful_requests += 1
        
        self.total_prompt_tokens += metrics.tokens_prompt
        self.total_completion_tokens += metrics.tokens_completion
        self.total_tokens += metrics.tokens_total
        
        self.total_time += metrics.total_time
        self.avg_time = self.total_time / self.total_requests
        
        self.total_cost += metrics.estimated_cost
        self.total_llm_calls += metrics.num_llm_calls


class RequestTimer:
    """Context manager para medir tiempos de request."""
    
    def __init__(self, metrics: RequestMetrics):
        self.metrics = metrics
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            self.metrics.total_time = time.time() - self.start_time


# ============================================================
# COLECTOR DE MÉTRICAS
# ============================================================

class MetricsCollector:
    """
    Colector global de métricas.
    Mantiene histórico de requests y estadísticas por sesión.
    """
    
    def __init__(self):
        self._lock = asyncio.Lock()
        
        # Histórico de requests
        self.requests: List[RequestMetrics] = []
        
        # Estadísticas por sesión
        self.sessions: Dict[str, SessionStats] = {}
        
        # Contadores globales
        self.global_requests = 0
        self.global_tokens = 0
        self.global_cost = 0.0
    
    async def record_request(self, metrics: RequestMetrics):
        """Registra una request y actualiza estadísticas."""
        async with self._lock:
            # Añadir al histórico
            self.requests.append(metrics)
            
            # Actualizar sesión
            if metrics.session_id not in self.sessions:
                self.sessions[metrics.session_id] = SessionStats(
                    session_id=metrics.session_id
                )
            
            self.sessions[metrics.session_id].update(metrics)
            
            # Actualizar globales
            self.global_requests += 1
            self.global_tokens += metrics.tokens_total
            self.global_cost += metrics.estimated_cost
    
    async def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas globales."""
        async with self._lock:
            total_time = sum(r.total_time for r in self.requests)
            
            return {
                "global": {
                    "total_requests": self.global_requests,
                    "total_tokens": self.global_tokens,
                    "total_cost_usd": round(self.global_cost, 6),
                    "avg_time_per_request": round(
                        total_time / self.global_requests, 2
                    ) if self.global_requests > 0 else 0
                },
                "sessions": {
                    sid: {
                        "requests": stats.total_requests,
                        "success_rate": round(
                            (stats.successful_requests / stats.total_requests * 100), 1
                        ) if stats.total_requests > 0 else 0,
                        "total_tokens": stats.total_tokens,
                        "total_cost_usd": round(stats.total_cost, 6),
                        "avg_time": round(stats.avg_time, 2)
                    }
                    for sid, stats in self.sessions.items()
                }
            }
    
    async def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Obtiene estadísticas de una sesión específica."""
        async with self._lock:
            if session_id not in self.sessions:
                return {
                    "error": f"Session '{session_id}' not found"
                }
            
            stats = self.sessions[session_id]
            
            return {
                "session_id": session_id,
                "started_at": stats.started_at.isoformat(),
                "requests": {
                    "total": stats.total_requests,
                    "successful": stats.successful_requests,
                    "failed": stats.failed_requests,
                    "success_rate": round(
                        (stats.successful_requests / stats.total_requests * 100), 1
                    ) if stats.total_requests > 0 else 0
                },
                "tokens": {
                    "prompt": int(stats.total_prompt_tokens),
                    "completion": int(stats.total_completion_tokens),
                    "total": stats.total_tokens
                },
                "time": {
                    "total": round(stats.total_time, 2),
                    "average": round(stats.avg_time, 2)
                },
                "cost_usd": round(stats.total_cost, 6),
                "llm_calls": stats.total_llm_calls
            }
    
    async def print_summary(self):
        """Imprime resumen bonito en consola."""
        stats = await self.get_stats()
        
        print("\n" + "="*70)
        print("📊 RESUMEN DE MÉTRICAS")
        print("="*70)
        
        global_stats = stats["global"]
        print(f"📝 Total Requests: {global_stats['total_requests']}")
        print(f"🔢 Total Tokens: {global_stats['total_tokens']:,}")
        print(f"💰 Costo Total: ${global_stats['total_cost_usd']:.6f}")
        print(f"⏱️  Tiempo Promedio: {global_stats['avg_time_per_request']:.2f}s")
        
        if stats["sessions"]:
            print(f"\n📊 Sesiones Activas: {len(stats['sessions'])}")
            for sid, sess_stats in stats["sessions"].items():
                print(f"\n  Session: {sid}")
                print(f"    Requests: {sess_stats['requests']}")
                print(f"    Success Rate: {sess_stats['success_rate']}%")
                print(f"    Tokens: {sess_stats['total_tokens']:,}")
                print(f"    Cost: ${sess_stats['total_cost_usd']:.6f}")
        
        print("="*70 + "\n")


# Instancia global
metrics_collector = MetricsCollector()