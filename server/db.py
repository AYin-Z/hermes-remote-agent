"""
SQLite 持久化 — 机器注册表 + 命令审计日志 + 文件传输记录

借鉴 CHAOS 的 GORM/SQLite 思路，但用 Python 原生 sqlite3 实现。
"""

from __future__ import annotations

import sqlite3
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path(__file__).parent / "data" / "server.db"

_SCHEMA = '''
CREATE TABLE IF NOT EXISTS agents (
    hostname   TEXT PRIMARY KEY,
    os         TEXT NOT NULL DEFAULT '',
    username   TEXT NOT NULL DEFAULT '',
    arch       TEXT NOT NULL DEFAULT '',
    agent_version TEXT NOT NULL DEFAULT '',
    first_seen TIMESTAMP NOT NULL,
    last_seen  TIMESTAMP NOT NULL,
    online     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS commands (
    id         TEXT PRIMARY KEY,
    hostname   TEXT NOT NULL,
    cmd        TEXT NOT NULL,
    shell      TEXT NOT NULL DEFAULT 'powershell',
    stdout     TEXT NOT NULL DEFAULT '',
    stderr     TEXT NOT NULL DEFAULT '',
    exit_code  INTEGER NOT NULL DEFAULT -1,
    requested_at  TIMESTAMP NOT NULL,
    completed_at  TIMESTAMP,
    status     TEXT NOT NULL DEFAULT 'pending'   -- pending | running | done | error
);

CREATE TABLE IF NOT EXISTS file_transfers (
    id         TEXT PRIMARY KEY,
    hostname   TEXT NOT NULL,
    direction  TEXT NOT NULL,       -- upload | download
    filename   TEXT NOT NULL,
    path       TEXT NOT NULL,
    size       INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_commands_hostname ON commands(hostname);
CREATE INDEX IF NOT EXISTS idx_commands_status  ON commands(status);
'''


class DB:
    """线程安全的 SQLite 封装，仅用于 agents / commands / file_transfers 三张表。"""

    def __init__(self, path: str | Path = DEFAULT_DB_PATH):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ── Agent 注册表 ──

    def register_agent(self, hostname: str, os: str, username: str,
                       arch: str = "", agent_version: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute('''
                INSERT INTO agents (hostname, os, username, arch, agent_version, first_seen, last_seen, online)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(hostname) DO UPDATE SET
                    os = excluded.os,
                    username = excluded.username,
                    arch = excluded.arch,
                    agent_version = excluded.agent_version,
                    last_seen = excluded.last_seen,
                    online = 1
            ''', (hostname, os, username, arch, agent_version, now, now))
            self._conn.commit()

    def set_online(self, hostname: str, online: bool) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                'UPDATE agents SET online = ?, last_seen = ? WHERE hostname = ?',
                (int(online), now, hostname)
            )
            self._conn.commit()

    def get_agent(self, hostname: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                'SELECT * FROM agents WHERE hostname = ?', (hostname,)
            ).fetchone()
        return dict(row) if row else None

    def list_agents(self, online_only: bool = False) -> list[dict]:
        sql = 'SELECT * FROM agents'
        if online_only:
            sql += ' WHERE online = 1'
        sql += ' ORDER BY last_seen DESC'
        with self._lock:
            rows = self._conn.execute(sql).fetchall()
        return [dict(r) for r in rows]

    def get_online_agents(self) -> list[dict]:
        return self.list_agents(online_only=True)

    def mark_all_offline(self) -> None:
        with self._lock:
            self._conn.execute('UPDATE agents SET online = 0')
            self._conn.commit()

    # ── 命令审计 ──

    def log_command(self, cmd_id: str, hostname: str, cmd: str,
                    shell: str = "powershell") -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                'INSERT INTO commands (id, hostname, cmd, shell, requested_at, status) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (cmd_id, hostname, cmd, shell, now, "pending")
            )
            self._conn.commit()

    def update_command_status(self, cmd_id: str, status: str) -> None:
        with self._lock:
            self._conn.execute(
                'UPDATE commands SET status = ? WHERE id = ?', (status, cmd_id)
            )
            self._conn.commit()

    def complete_command(self, cmd_id: str, stdout: str, stderr: str,
                         exit_code: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                'UPDATE commands SET stdout = ?, stderr = ?, exit_code = ?, '
                'completed_at = ?, status = ? WHERE id = ?',
                (stdout, stderr, exit_code, now, "done", cmd_id)
            )
            self._conn.commit()

    def get_command_history(self, hostname: str, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                'SELECT * FROM commands WHERE hostname = ? '
                'ORDER BY requested_at DESC LIMIT ?',
                (hostname, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_pending_commands(self, hostname: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                'SELECT * FROM commands WHERE hostname = ? AND status = ?',
                (hostname, "pending")
            ).fetchall()
        return [dict(r) for r in rows]

    # ── 文件传输记录 ──

    def log_file_transfer(self, transfer_id: str, hostname: str,
                          direction: str, filename: str, path: str,
                          size: int = 0) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                'INSERT INTO file_transfers (id, hostname, direction, filename, '
                'path, size, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (transfer_id, hostname, direction, filename, path, size, now)
            )
            self._conn.commit()

    def complete_file_transfer(self, transfer_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                'UPDATE file_transfers SET completed_at = ? WHERE id = ?',
                (now, transfer_id)
            )
            self._conn.commit()

    # ── 健康检查 ──

    def health(self) -> dict:
        with self._lock:
            agents_total = self._conn.execute('SELECT COUNT(*) FROM agents').fetchone()[0]
            agents_online = self._conn.execute(
                'SELECT COUNT(*) FROM agents WHERE online = 1'
            ).fetchone()[0]
        return {
            "agents_total": agents_total,
            "agents_online": agents_online,
            "status": "healthy",
        }
