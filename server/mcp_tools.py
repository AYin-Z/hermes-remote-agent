"""
MCP 工具定义 — Hermes 可调用的远程机器控制工具。

工具列表:
  agent.list              列出所有已注册机器
  agent.exec              执行命令
  agent.upload             上传文件
  agent.screenshot         截图
  agent.processes          进程列表
  agent.sysinfo            系统信息
  agent.history            命令历史
"""

from __future__ import annotations

import base64
import uuid
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from protocol import (
    Exec, Upload, Screenshot, Processes, SysInfo,
    Result, ScreenshotData, ProcessList, SysInfoData,
    UploadDone, DownloadStart, DownloadData,
)
from ws_hub import Hub
from db import DB

logger = logging.getLogger("mcp_tools")

mcp = FastMCP("hermes-remote-agent", log_level="WARNING")


def bind(hub: Hub, db: DB) -> None:
    """将 hub 和 db 注入到 tool 函数中。"""
    mcp._hub = hub  # type: ignore[attr-defined]
    mcp._db = db  # type: ignore[attr-defined]


# ── agent.list ──

@mcp.tool()
async def agent_list(online_only: bool = True) -> str:
    """列出已注册的远程机器。

    Args:
        online_only: True=仅在线机器, False=全部历史机器

    Returns:
        机器列表，含 hostname / OS / username / 在线状态 / 最后在线时间
    """
    db: DB = mcp._db  # type: ignore
    hub: Hub = mcp._hub  # type: ignore

    agents = db.list_agents(online_only=online_only)
    # 用 ws_hub 的实时在线状态覆盖 DB
    for a in agents:
        a["online"] = hub.is_online(a["hostname"])

    if not agents:
        return "没有已注册的机器。"

    lines = []
    for a in agents:
        status = "🟢" if a["online"] else "🔴"
        lines.append(
            f"{status} **{a['hostname']}** — {a['os']} — "
            f"用户: {a['username']} — 最后在线: {a['last_seen'][:19] if a['last_seen'] else '未知'}"
        )
    return "\n".join(lines)


# ── agent.exec ──

@mcp.tool()
async def agent_exec(hostname: str, cmd: str,
                     shell: str = "powershell",
                     timeout: int = 60) -> str:
    """在远程 Windows 机器上执行命令并返回结果。

    Args:
        hostname: 目标机器名（通过 agent.list 查看）
        cmd: 要执行的命令
        shell: 命令解释器 (powershell / cmd)
        timeout: 超时秒数 (默认 60，最大 300)

    Returns:
        stdout / stderr / exit_code
    """
    hub: Hub = mcp._hub  # type: ignore
    db: DB = mcp._db  # type: ignore

    if not hub.is_online(hostname):
        return f"错误：机器 '{hostname}' 不在线。"

    msg = Exec(cmd=cmd, shell=shell, timeout=min(timeout, 300))

    # 记录审计
    db.log_command(msg.id, hostname, cmd, shell)

    try:
        result: Result = await hub.send(hostname, msg, timeout=timeout + 10)
        if result.exit_code == 0:
            return result.stdout or "(命令执行成功，无输出)"
        else:
            return (
                f"exit_code={result.exit_code}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )
    except TimeoutError:
        return f"错误：命令执行超时（{timeout}s）"
    except ConnectionError as e:
        return f"错误：{e}"


# ── agent.upload ──

@mcp.tool()
async def agent_upload(hostname: str, local_path: str,
                       remote_path: str) -> str:
    """上传文件到远程机器。

    Args:
        hostname: 目标机器名
        local_path: 本地文件路径（在 ayinserver 上）
        remote_path: 远程目标路径（绝对路径，如 C:\\Users\\user\\Desktop\\file.exe）

    限制：单文件 ≤ 50MB，超过会自动分块。
    """
    hub: Hub = mcp._hub  # type: ignore
    db: DB = mcp._db  # type: ignore

    if not hub.is_online(hostname):
        return f"错误：机器 '{hostname}' 不在线。"

    path = Path(local_path)
    if not path.exists():
        return f"错误：本地文件不存在: {local_path}"
    if not path.is_file():
        return f"错误：路径不是文件: {local_path}"

    data = path.read_bytes()
    file_size = len(data)

    if file_size > 50 * 1024 * 1024:
        return f"错误：文件过大（{file_size / 1024 / 1024:.1f}MB > 50MB 限制）"

    b64_data = base64.b64encode(data).decode()

    transfer_id = uuid.uuid4().hex[:8]
    db.log_file_transfer(transfer_id, hostname, "upload",
                         path.name, remote_path, file_size)

    msg = Upload(
        filename=path.name,
        path=remote_path,
        data=b64_data,
        total_chunks=1,
        chunk_index=0,
    )

    result: UploadDone = await hub.send(hostname, msg, timeout=120)
    db.complete_file_transfer(transfer_id)
    return (
        f"✅ 上传完成: '{path.name}' ({file_size:,} bytes)\n"
        f"   目标: {result.path}"
    )


# ── agent.screenshot ──

@mcp.tool()
async def agent_screenshot(hostname: str) -> str:
    """对远程机器截图。

    Args:
        hostname: 目标机器名

    Returns:
        截图保存路径（在 ayinserver 上），以及分辨率信息。
    """
    hub: Hub = mcp._hub  # type: ignore

    if not hub.is_online(hostname):
        return f"错误：机器 '{hostname}' 不在线。"

    msg = Screenshot()
    result: ScreenshotData = await hub.send(hostname, msg, timeout=30)

    # 保存截图到本地
    out_dir = Path("/tmp/hermes-screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = out_dir / f"{hostname}_{msg.id}.jpg"
    fname.write_bytes(base64.b64decode(result.data))

    return (
        f"📸 截图已保存: {fname}\n"
        f"   分辨率: {result.width}x{result.height}"
    )


# ── agent.processes ──

@mcp.tool()
async def agent_processes(hostname: str,
                          filter: str = "") -> str:
    """获取远程机器的进程列表。

    Args:
        hostname: 目标机器名
        filter: 可选的进程名过滤（模糊匹配）

    Returns:
        进程列表 (PID / 名称 / CPU% / 内存)
    """
    hub: Hub = mcp._hub  # type: ignore

    if not hub.is_online(hostname):
        return f"错误：机器 '{hostname}' 不在线。"

    msg = Processes(filter=filter)
    result: ProcessList = await hub.send(hostname, msg, timeout=15)

    if not result.processes:
        return f"（{hostname} 上未找到进程" + (f"，过滤条件: '{filter}')" if filter else "）")

    lines = [f"**{hostname} 进程列表**："]
    for p in sorted(result.processes, key=lambda x: -x.memory_mb)[:30]:
        lines.append(
            f"  PID {p.pid:>6}  {p.name:<30}  "
            f"CPU {p.cpu_percent:>5.1f}%  MEM {p.memory_mb:>8.1f} MB"
        )
    if len(result.processes) > 30:
        lines.append(f"  ... 还有 {len(result.processes) - 30} 个进程未显示")
    return "\n".join(lines)


# ── agent.sysinfo ──

@mcp.tool()
async def agent_sysinfo(hostname: str) -> str:
    """获取远程机器的系统信息。

    Args:
        hostname: 目标机器名

    Returns:
        OS / CPU / 内存 / 磁盘 / 运行时间
    """
    hub: Hub = mcp._hub  # type: ignore

    if not hub.is_online(hostname):
        return f"错误：机器 '{hostname}' 不在线。"

    msg = SysInfo()
    result: SysInfoData = await hub.send(hostname, msg, timeout=15)

    uptime_h = result.uptime_seconds / 3600
    uptime_str = f"{int(uptime_h)}h {int((uptime_h % 1) * 60)}m"

    return (
        f"**{result.hostname}** — {result.os_name} {result.os_version}\n"
        f"  架构: {result.arch}  |  CPU: {result.cpu_cores} 核 ({result.cpu_percent:.1f}%)\n"
        f"  内存: {result.used_memory_gb:.1f}/{result.total_memory_gb:.1f} GB\n"
        f"  磁盘: {result.used_disk_gb:.1f}/{result.total_disk_gb:.1f} GB\n"
        f"  运行时间: {uptime_str}"
    )


# ── agent.history ──

@mcp.tool()
async def agent_history(hostname: str, limit: int = 20) -> str:
    """查看远程机器的命令执行历史（审计日志）。

    Args:
        hostname: 目标机器名
        limit: 返回最近 N 条记录 (默认 20)
    """
    db: DB = mcp._db  # type: ignore
    records = db.get_command_history(hostname, limit=min(limit, 100))

    if not records:
        return f"机器 '{hostname}' 没有命令执行记录。"

    lines = [f"**{hostname} 命令历史**（最近 {len(records)} 条）："]
    for r in records:
        status_icon = "✅" if r["exit_code"] == 0 else "❌" if r["exit_code"] > 0 else "⏳"
        lines.append(
            f"  {status_icon} {r['requested_at'][:19] if r['requested_at'] else '?'}  "
            f"exit={r['exit_code']}  {r['cmd'][:80]}"
        )
    return "\n".join(lines)
