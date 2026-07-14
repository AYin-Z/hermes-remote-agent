"""
消息协议定义 — Agent ↔ Server 之间的 12 种 JSON 消息类型。

方向标记:
  A→S: Agent 发给 Server
  S→A: Server 发给 Agent
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class MsgType(StrEnum):
    # ── 握手 ──
    REGISTER = "register"          # A→S: 注册 + 主机信息
    REGISTERED = "registered"       # S→A: 注册成功确认
    REGISTER_ERROR = "register_error"  # S→A: 注册失败（token 错误等）

    # ── 心跳 ──
    PING = "ping"                   # A→S: 心跳
    PONG = "pong"                   # S→A: 心跳回复

    # ── 命令执行 ──
    EXEC = "exec"                   # S→A: 执行命令
    RESULT = "result"               # A→S: 命令结果

    # ── 文件传输 ──
    UPLOAD = "upload"               # S→A: 推送文件到 Agent
    UPLOAD_PROGRESS = "upload_progress"   # A→S: 接收进度
    UPLOAD_DONE = "upload_done"        # A→S: 文件接收完成
    DOWNLOAD_REQUEST = "download_request"   # A→S: 请求发起下载 (agent → server)
    DOWNLOAD_START = "download_start"     # S→A: 通知 Agent 准备接收文件
    DOWNLOAD_DATA = "download_data"     # S→A: 文件数据块

    # ── 截图 ──
    SCREENSHOT = "screenshot"       # S→A: 截图请求
    SCREENSHOT_DATA = "screenshot_data"     # A→S: JPEG Base64

    # ── 进程管理 ──
    PROCESSES = "processes"         # S→A: 请求进程列表
    PROCESS_LIST = "process_list"       # A→S: 返回进程列表

    # ── 系统信息 ──
    SYSINFO = "sysinfo"             # S→A: 请求系统信息
    SYSINFO_DATA = "sysinfo_data"        # A→S: 返回系统信息

    # ── 错误 ──
    ERROR = "error"                  # A→S 或 S→A: 操作失败


# ── 消息基类 ──

@dataclass
class Message:
    """所有消息的基类。id 用于请求-响应匹配。"""
    type: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str | bytes) -> dict:
        return json.loads(raw)


# ── 握手 ──

@dataclass
class Register(Message):
    """A→S: Agent 启动时的注册包"""
    type: str = MsgType.REGISTER
    hostname: str = ""
    os: str = ""
    username: str = ""
    arch: str = ""
    agent_version: str = ""
    token: str = ""


@dataclass
class Registered(Message):
    """S→A: 注册成功"""
    type: str = MsgType.REGISTERED


@dataclass
class RegisterError(Message):
    """S→A: 注册失败"""
    type: str = MsgType.REGISTER_ERROR
    reason: str = ""


# ── 心跳 ──

@dataclass
class Ping(Message):
    """A→S: 心跳"""
    type: str = MsgType.PING


@dataclass
class Pong(Message):
    """S→A: 心跳回复"""
    type: str = MsgType.PONG


# ── 命令执行 ──

@dataclass
class Exec(Message):
    """S→A: 执行命令"""
    type: str = MsgType.EXEC
    cmd: str = ""
    shell: str = "powershell"  # powershell | cmd | bash
    timeout: int = 60


@dataclass
class Result(Message):
    """A→S: 命令执行结果"""
    type: str = MsgType.RESULT
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


# ── 文件传输 ──

@dataclass
class Upload(Message):
    """S→A: 推送文件到 Agent"""
    type: str = MsgType.UPLOAD
    filename: str = ""
    path: str = ""          # 目标绝对路径
    data: str = ""          # Base64 编码的文件内容
    total_chunks: int = 1
    chunk_index: int = 0


@dataclass
class UploadProgress(Message):
    """A→S: 接收进度"""
    type: str = MsgType.UPLOAD_PROGRESS
    filename: str = ""
    received_bytes: int = 0
    total_bytes: int = 0


@dataclass
class UploadDone(Message):
    """A→S: 文件接收完成"""
    type: str = MsgType.UPLOAD_DONE
    filename: str = ""
    path: str = ""
    size: int = 0


@dataclass
class DownloadRequest(Message):
    """A→S: Agent 请求从 Server 下载文件
    注：这是 Server→Agent 推送下载文件的启动信号。
    实际设计：Server 主动下发 download_start 给 Agent。
    此类型保留用于扩展：Agent 端请求从 Server 拉取某个已知文件。
    """
    type: str = MsgType.DOWNLOAD_REQUEST
    path: str = ""


@dataclass
class DownloadStart(Message):
    """S→A: 通知 Agent 准备接收文件"""
    type: str = MsgType.DOWNLOAD_START
    filename: str = ""
    total_chunks: int = 0


@dataclass
class DownloadData(Message):
    """S→A: 文件数据块"""
    type: str = MsgType.DOWNLOAD_DATA
    filename: str = ""
    data: str = ""          # Base64 编码的数据块
    chunk_index: int = 0
    total_chunks: int = 0
    is_last: bool = False


# ── 截图 ──

@dataclass
class Screenshot(Message):
    """S→A: 截图请求"""
    type: str = MsgType.SCREENSHOT
    quality: int = 70       # JPEG 质量 1-100


@dataclass
class ScreenshotData(Message):
    """A→S: JPEG Base64 截图"""
    type: str = MsgType.SCREENSHOT_DATA
    data: str = ""          # Base64 JPEG
    width: int = 0
    height: int = 0


# ── 进程管理 ──

@dataclass
class Processes(Message):
    """S→A: 请求进程列表"""
    type: str = MsgType.PROCESSES
    filter: str = ""         # 可选的进程名过滤


@dataclass
class ProcessInfo:
    pid: int = 0
    name: str = ""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0


@dataclass
class ProcessList(Message):
    """A→S: 返回进程列表"""
    type: str = MsgType.PROCESS_LIST
    processes: list[ProcessInfo] = field(default_factory=list)

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, ensure_ascii=False)


# ── 系统信息 ──

@dataclass
class SysInfo(Message):
    """S→A: 请求系统信息"""
    type: str = MsgType.SYSINFO


@dataclass
class SysInfoData(Message):
    """A→S: 系统信息"""
    type: str = MsgType.SYSINFO_DATA
    hostname: str = ""
    os_name: str = ""
    os_version: str = ""
    arch: str = ""
    cpu_cores: int = 0
    cpu_percent: float = 0.0
    total_memory_gb: float = 0.0
    used_memory_gb: float = 0.0
    total_disk_gb: float = 0.0
    used_disk_gb: float = 0.0
    uptime_seconds: int = 0


# ── 错误 ──

@dataclass
class Error(Message):
    """操作失败"""
    type: str = MsgType.ERROR
    request_id: str = ""       # 对应原始请求的 id
    message: str = ""


# ── 消息解析器 ──

_TYPE_MAP: dict[str, type[Message]] = {
    MsgType.REGISTER: Register,
    MsgType.REGISTERED: Registered,
    MsgType.REGISTER_ERROR: RegisterError,
    MsgType.PING: Ping,
    MsgType.PONG: Pong,
    MsgType.EXEC: Exec,
    MsgType.RESULT: Result,
    MsgType.UPLOAD: Upload,
    MsgType.UPLOAD_PROGRESS: UploadProgress,
    MsgType.UPLOAD_DONE: UploadDone,
    MsgType.DOWNLOAD_REQUEST: DownloadRequest,
    MsgType.DOWNLOAD_START: DownloadStart,
    MsgType.DOWNLOAD_DATA: DownloadData,
    MsgType.SCREENSHOT: Screenshot,
    MsgType.SCREENSHOT_DATA: ScreenshotData,
    MsgType.PROCESSES: Processes,
    MsgType.PROCESS_LIST: ProcessList,
    MsgType.SYSINFO: SysInfo,
    MsgType.SYSINFO_DATA: SysInfoData,
    MsgType.ERROR: Error,
}


def parse(raw: str | bytes) -> Message:
    """将收到的 JSON 字符串反序列化为对应的 Message 子类。"""
    d = json.loads(raw)
    msg_type = d.get("type", "")
    cls = _TYPE_MAP.get(msg_type)
    if cls is None:
        return Error(type=MsgType.ERROR, message=f"Unknown message type: {msg_type}")
    # 过滤掉 dataclass 不认识的 key
    valid_fields = {f.name for f in field_iterator(cls)}
    filtered = {k: v for k, v in d.items() if k in valid_fields}
    return cls(**filtered)


def field_iterator(cls: type) -> list:
    """兼容 Python 3.10 - 3.13 的 fields() 调用"""
    import dataclasses
    return list(dataclasses.fields(cls))


def register_from(msg: Message) -> Register:
    """从 Message 基类提取 Register 字段，绕过类型检查。"""
    d = json.loads(msg.to_json())
    return Register(**{k: v for k, v in d.items()
                       if k in {f.name for f in field_iterator(Register)}})
