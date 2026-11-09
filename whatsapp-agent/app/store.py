"""Persistencia mínima en SQLite: historial de conversación y mensajes ya procesados."""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path


class Store:
    def __init__(self, ruta: str):
        if ruta != ":memory:":
            Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(ruta, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS turnos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telefono TEXT NOT NULL,
                    usuario TEXT NOT NULL,
                    asistente TEXT NOT NULL,
                    ts REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_turnos_tel ON turnos (telefono, id);
                CREATE TABLE IF NOT EXISTS procesados (
                    id_mensaje TEXT PRIMARY KEY,
                    ts REAL NOT NULL
                );
                """
            )

    def marcar_procesado(self, id_mensaje: str) -> bool:
        """True si el mensaje es nuevo; False si ya lo habíamos recibido (Meta reintenta webhooks)."""
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO procesados (id_mensaje, ts) VALUES (?, ?)", (id_mensaje, time.time())
            )
            self._db.execute("DELETE FROM procesados WHERE ts < ?", (time.time() - 7 * 86400,))
            return cur.rowcount == 1

    def guardar_turno(self, telefono: str, usuario: str, asistente: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO turnos (telefono, usuario, asistente, ts) VALUES (?, ?, ?, ?)",
                (telefono, usuario, asistente, time.time()),
            )

    def historial(self, telefono: str, max_turnos: int = 15, max_horas: float = 72) -> list[tuple[str, str]]:
        """Últimos turnos (usuario, asistente) en orden cronológico."""
        with self._lock:
            filas = self._db.execute(
                "SELECT usuario, asistente FROM turnos WHERE telefono = ? AND ts >= ? ORDER BY id DESC LIMIT ?",
                (telefono, time.time() - max_horas * 3600, max_turnos),
            ).fetchall()
        return list(reversed(filas))
