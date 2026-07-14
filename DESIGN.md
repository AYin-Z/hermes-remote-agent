# Hermes Remote Agent — 技术规划

## 参考项目分析

| 维度 | Spark (Go) | CHAOS (Go) | 我们采纳 |
|------|-----------|-----------|---------|
| Agent 编译 | 源码编译，配置外置 | **Payload Generator 编译时嵌入** | ✅ CHAOS |
| 通信协议 | WebSocket 明文 | WebSocket | ✅ WSS + Token |
| 服务注册 | Windows 服务 | 无 | ✅ Spark |
| Server 持久化 | 无状态 | **GORM SQLite** | ✅ CHAOS |
| HTTP 框架 | 自研 | **Gin** | N/A（Python FastAPI） |
| 管理界面 | Web Dashboard | Web Panel | ❌ 替换为 MCP |
| 命令执行 | ✅ | ✅ | ✅ 两者参考 |
| 文件传输 | ✅ | ✅ | ✅ 两者参考 |
| 截图 | ✅ | ✅ | ✅ Spark |
| 进程管理 | ✅ | ✅ | ✅ |
| 认证 | 无 | JWT | ✅ Pre-shared Token |

---

## 最终架构

```
┌──────────────────────────────────────────────────────────┐
│                    Hermes (我)                            │
│  agent.list / agent.exec / agent.upload / agent.download │
│  agent.screenshot / agent.processes                      │
└────────────┬─────────────────────────────────────────────┘
             │ MCP (Streamable HTTP)
             ▼
┌─────────────────────────────────────────────────────────┐
│              Server (Python — ayinserver)                 │
│  FastAPI + MCP Server + WebSocket Hub                    │
│  ┌──────────────────────────────────────────────────┐   │
│  │ WebSocket Hub (管理 N 个 Agent 连接)              │   │
│  │  ├─ DELL-PC (zhangsan) — ws 连接 #1              │   │
│  │  ├─ LAPTOP-X1 (lisi)   — ws 连接 #2              │   │
│  │  └─ ...                                          │   │
│  ├──────────────────────────────────────────────────┤   │
│  │ SQLite (机器注册表 + 命令历史 + 审计日志)          │   │
│  └──────────────────────────────────────────────────┘   │
└────────────┬────────────────────────────────────────────┘
             │ WSS (Cloudflare Tunnel)
             ▼
┌─────────────────────────────────────────────────────────┐
│              Agent (Go — Windows)                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │ 编译时嵌入: server_url, token, agent_id          │   │
│  │ 运行时启动: WebSocket 连接 + 注册包              │   │
│  │ Windows 服务: 开机自启, 断线重连                 │   │
│  ├──────────────────────────────────────────────────┤   │
│  │ 命令执行: cmd / powershell                       │   │
│  │ 文件传输: 分块上传/下载 + 进度                    │   │
│  │ 屏幕截图: GDI → JPEG → Base64                    │   │
│  │ 进程管理: list / kill                            │   │
│  │ 系统信息: CPU/内存/磁盘/网络                      │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 组件详细设计

### 1. Agent（Go，编译为单一 exe）

**借鉴 CHAOS：编译时嵌入配置**
```go
// 由 go build -ldflags 注入
var (
    ServerURL  = "wss://agent.ayinserver.xin/ws"
    AuthToken  = ""   // 预共享密钥
    AgentID    = ""   // 机器标识（hostname 或自定义）
)
```

**借鉴 Spark：WebSocket 协议**
```json
// Agent → Server（注册）
{"type": "register", "hostname": "DELL-PC", "os": "Windows 11 Pro",
 "username": "zhangsan", "token": "xxx"}

// Server → Agent（命令）
{"type": "exec", "cmd": "dir C:\\Users", "id": "req-001"}

// Agent → Server（结果）
{"type": "result", "id": "req-001", "stdout": "...", "stderr": "...",
 "exit_code": 0}

// Agent → Server（心跳）
{"type": "ping"}
// Server → Agent
{"type": "pong"}
```

**模块清单（参照 Spark + CHAOS）**：
- `ws/client.go` — WebSocket 连接 + 重连
- `exec/exec.go` — PowerShell/cmd 执行
- `file/file.go` — 分块传输（64KB 块）
- `screen/screen.go` — Windows GDI 截图
- `sysinfo/sysinfo.go` — 系统信息采集
- `service/service.go` — Windows 服务注册
- `main.go` — 入口，连接 → 注册 → 等待命令

### 2. Server（Python，FastAPI + MCP）

```python
# 核心结构
class WsHub:
    """借鉴 Spark 的 Hub 模式"""
    agents: dict[str, WebSocket]  # hostname → ws

    async def register(self, ws, agent_info)
    async def send_command(self, hostname, cmd) -> Result
    async def heartbeat_check(self)  # 借鉴 Spark 的心跳

class McpTools:
    """Hermes 可见的工具"""
    async def agent_list() -> list[Agent]
    async def agent_exec(hostname, cmd) -> ExecResult
    async def agent_upload(hostname, local_path, remote_path)
    async def agent_download(hostname, remote_path)
    async def agent_screenshot(hostname) -> Image
    async def agent_processes(hostname) -> list[Process]
```

**借鉴 CHAOS：SQLite 持久化**
```sql
-- 机器注册表
CREATE TABLE agents (
    hostname TEXT PRIMARY KEY,
    username TEXT,
    os TEXT,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    online BOOLEAN
);

-- 命令历史
CREATE TABLE commands (
    id TEXT PRIMARY KEY,
    hostname TEXT,
    cmd TEXT,
    result TEXT,
    executed_at TIMESTAMP
);
```

### 3. CLI（Python）

```bash
agent-ctl list                          # 列出在线机器
agent-ctl exec DELL-PC "Get-Process"   # 执行命令
agent-ctl upload DELL-PC ./setup.exe C:\Users\user\Desktop\
agent-ctl download DELL-PC C:\report.txt ./
agent-ctl screenshot DELL-PC            # 截图保存
agent-ctl processes DELL-PC             # 进程列表
```

底层走 MCP 协议，与 Hermes 调用同一套工具。

### 4. 安装包（NSIS）

- 嵌入 Agent exe + 配置写入脚本
- UAC 提权 → 注册 Windows 服务
- 服务启动 → 自动连接 Server → 注册
- 桌面快捷方式用于手动启停/卸载

---

## 协议总结：Agent ↔ Server 消息类型

| 方向 | 类型 | 用途 |
|------|------|------|
| Agent→Server | `register` | 注册 + 传输主机信息 |
| Agent→Server | `ping` | 心跳（15s 间隔） |
| Server→Agent | `pong` | 心跳回复 |
| Server→Agent | `exec` | 执行命令 |
| Agent→Server | `result` | 返回命令结果 |
| Server→Agent | `upload` | 推送文件到 Agent |
| Agent→Server | `upload_progress` / `upload_done` | 上传进度 |
| Agent→Server | `download` | 请求下载文件 |
| Server→Agent | `download_data` | 文件数据块 |
| Server→Agent | `screenshot` | 截图请求 |
| Agent→Server | `screenshot_data` | JPEG Base64 返回 |
| Server→Agent | `processes` | 请求进程列表 |
| Agent→Server | `process_list` | 返回进程列表 |

---

## 安全设计

| 层面 | 措施 |
|------|------|
| 传输 | WSS（Cloudflare TLS 加密 + Tunnel 认证） |
| 认证 | 编译时嵌入 Token，Server 验证 |
| 操作审计 | SQLite 记录全部命令 + 执行人 |
| 卸载 | Windows 服务可正常停止/删除，无需特殊清理 |

---

## 文件结构

```
hermes-remote-agent/
├── agent/
│   ├── main.go              # 入口
│   ├── ws/
│   │   └── client.go        # WebSocket 客户端
│   ├── exec/
│   │   └── exec.go          # 命令执行
│   ├── file/
│   │   └── file.go          # 文件传输
│   ├── screen/
│   │   └── screen.go        # 截图
│   ├── sysinfo/
│   │   └── sysinfo.go        # 系统信息
│   ├── service/
│   │   └── service.go        # Windows 服务
│   └── go.mod
├── server/
│   ├── main.py               # FastAPI + MCP 入口
│   ├── ws_hub.py             # WebSocket Hub
│   ├── mcp_tools.py          # MCP 工具定义
│   ├── db.py                 # SQLite 持久化
│   ├── protocol.py           # 消息类型定义
│   └── requirements.txt
├── cli/
│   ├── agent_ctl.py          # CLI 入口
│   └── mcp_client.py         # MCP 客户端
├── installer/
│   └── setup.nsi             # NSIS 安装脚本
├── scripts/
│   └── build-agent.sh        # Go 交叉编译 + ldflags 注入
└── README.md
```
