"""
WebSocket Hub — 管理所有 Agent 连接。

借鉴 Spark 的 Hub 模式：一个中心结构维护所有 WebSocket 连接，
支持按 hostname 路由命令、心跳检测、断线清理。

消息流转：
  收到消息 → parse → 如果是注册/心跳，Hub 自己处理；
             → 如果是 result/screenshot 等响应，回调 pending_futures。
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Callable, Awaitable

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from protocol import (
    parse, register_from, MsgType,
    Message, Register, Registered, RegisterError,
    Ping, Pong, Result, ScreenshotData, ProcessList,
    SysInfoData, UploadDone,
)
from db import DB

logger = logging.getLogger("ws_hub")

# 心跳间隔 (Agent 侧发 ping，Server 侧只回复 pong)
HEARTBEAT_TIMEOUT = 60  # 超过 60s 未收到 ping，标记离线


class Hub:
    """WebSocket 连接中枢。单例。"""

    def __init__(self, db: DB, token: str = "", heartbeat_timeout: int = HEARTBEAT_TIMEOUT):
        self.db = db
        self.token = token
        self.heartbeat_timeout = heartbeat_timeout

        # hostname → WebSocket
        self._connections: dict[str, WebSocket] = {}
        # hostname → 最后心跳时间
        self._last_ping: dict[str, datetime] = {}
        # hostname → 已注册状态
        self._registered: set[str] = set()

        # 消息回调 (用于 MCP 工具等待 agent 响应)
        # key: msg_id → asyncio.Future
        self._pending: dict[str, asyncio.Future] = {}

        self._heartbeat_task: asyncio.Task | None = None

    # ── 连接生命周期 ──

    async def handle(self, ws: WebSocket) -> None:
        """主入口：一个 Agent 连接的全部生命周期。"""
        hostname = "unknown"
        try:
            await ws.accept()
            raw = await ws.receive_text()
            msg = parse(raw)

            if msg.type != MsgType.REGISTER:
                await ws.send_text(RegisterError(reason="First message must be register").to_json())
                await ws.close()
                return

            # 验证 token
            reg = register_from(msg)
            if self.token and reg.token != self.token:
                logger.warning(f"Agent {reg.hostname} token mismatch")
                await ws.send_text(RegisterError(reason="Invalid token").to_json())
                await ws.close()
                return

            hostname = reg.hostname.strip() or reg.username.strip() or "unknown"

            # 处理重连：关掉旧连接
            if hostname in self._connections:
                old_ws = self._connections[hostname]
                try:
                    if old_ws.client_state == WebSocketState.CONNECTED:
                        await old_ws.close()
                except Exception:
                    pass

            # 注册
            self._connections[hostname] = ws
            self._last_ping[hostname] = datetime.now(timezone.utc)
            self._registered.add(hostname)

            self.db.register_agent(
                hostname=hostname,
                os=reg.os,
                username=reg.username,
                arch=getattr(reg, 'arch', ''),
                agent_version=getattr(reg, 'agent_version', ''),
            )
            logger.info(f"Agent registered: {hostname} ({reg.os}, {reg.username})")

            await ws.send_text(Registered().to_json())

            # 消息循环
            async for raw in ws.iter_text():
                try:
                    msg = parse(raw)
                    await self._dispatch(hostname, msg)
                except Exception as e:
                    logger.error(f"Error dispatching message from {hostname}: {e}")
                    traceback.print_exc()

        except WebSocketDisconnect:
            logger.info(f"Agent {hostname} disconnected")
        except Exception as e:
            logger.error(f"Agent {hostname} error: {e}")
            traceback.print_exc()
        finally:
            # 清理
            if hostname in self._connections:
                del self._connections[hostname]
            if hostname in self._last_ping:
                del self._last_ping[hostname]
            self._registered.discard(hostname)
            self.db.set_online(hostname, False)

            # 取消该 hostname 的所有 pending futures
            to_cancel = [
                mid for mid, fut in self._pending.items()
                if not fut.done()
            ]
            for mid in to_cancel:
                self._pending[mid].set_exception(
                    ConnectionError(f"Agent {hostname} disconnected")
                )
                del self._pending[mid]

            logger.info(f"Agent {hostname} cleaned up ({len(self._connections)} remaining)")

    # ── 消息分发 ──

    async def _dispatch(self, hostname: str, msg: Message) -> None:
        self._last_ping[hostname] = datetime.now(timezone.utc)

        if msg.type == MsgType.PING:
            # 回复 pong
            ws = self._connections.get(hostname)
            if ws:
                await ws.send_text(Pong(id=msg.id).to_json())

        elif msg.type == MsgType.RESULT:
            self.db.complete_command(
                cmd_id=msg.id,
                stdout=getattr(msg, 'stdout', ''),
                stderr=getattr(msg, 'stderr', ''),
                exit_code=getattr(msg, 'exit_code', -1),
            )
            if msg.id in self._pending:
                self._pending[msg.id].set_result(msg)

        elif msg.type == MsgType.SCREENSHOT_DATA:
            if msg.id in self._pending:
                self._pending[msg.id].set_result(msg)

        elif msg.type == MsgType.PROCESS_LIST:
            if msg.id in self._pending:
                self._pending[msg.id].set_result(msg)

        elif msg.type == MsgType.SYSINFO_DATA:
            if msg.id in self._pending:
                self._pending[msg.id].set_result(msg)

        elif msg.type == MsgType.UPLOAD_DONE:
            if msg.id in self._pending:
                self._pending[msg.id].set_result(msg)

        elif msg.type == MsgType.ERROR:
            if msg.id in self._pending:
                self._pending[msg.id].set_exception(RuntimeError(
                    getattr(msg, 'message', 'Agent error')
                ))

    # ── 发送命令到 Agent ──

    async def send(self, hostname: str, msg: Message,
                   timeout: float = 120.0) -> Message:
        """发送消息并等待响应。用于 exec/screenshot/processes 等请求-响应模式。"""
        if hostname not in self._connections:
            raise ConnectionError(f"Agent '{hostname}' not connected")

        ws = self._connections[hostname]
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending[msg.id] = future

        try:
            await ws.send_text(msg.to_json())
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg.id, None)
            raise TimeoutError(f"Agent '{hostname}' did not respond within {timeout}s")
        except Exception:
            self._pending.pop(msg.id, None)
            raise

    async def send_no_wait(self, hostname: str, msg: Message) -> None:
        """发送消息，不等待响应。用于 upload 等流水线操作。"""
        if hostname not in self._connections:
            raise ConnectionError(f"Agent '{hostname}' not connected")
        ws = self._connections[hostname]
        await ws.send_text(msg.to_json())

    # ── 心跳检测 ──

    async def start_heartbeat(self) -> None:
        """启动后台心跳检测任务。Server 启动时调用一次。"""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Heartbeat monitor started")

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            now = datetime.now(timezone.utc)
            offline = []
            for hostname, last in list(self._last_ping.items()):
                if (now - last).total_seconds() > self.heartbeat_timeout:
                    offline.append(hostname)
            for hostname in offline:
                logger.warning(f"Agent {hostname} heartbeat timeout, marking offline")
                self._registered.discard(hostname)
                self.db.set_online(hostname, False)
                ws = self._connections.pop(hostname, None)
                self._last_ping.pop(hostname, None)
                if ws:
                    try:
                        await ws.close()
                    except Exception:
                        pass

    # ── 查询 ──

    @property
    def online_count(self) -> int:
        return len(self._connections)

    @property
    def online_hostnames(self) -> list[str]:
        return list(self._connections.keys())

    def is_online(self, hostname: str) -> bool:
        return hostname in self._connections
