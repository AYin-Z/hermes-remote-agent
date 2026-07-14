# Hermes Remote Agent

让 [Hermes Agent](https://hermesagent.org.cn) 全权控制远程 Windows 机器。

## 架构

```
Windows Agent (Go) ──WSS──> Server (Python) <── CLI ── Hermes
```

## 组件

| 组件 | 语言 | 说明 |
|------|------|------|
| `agent/` | Go | Windows 服务，WebSocket 客户端 |
| `server/` | Python | asyncio WebSocket 中枢 |
| `cli/` | Python | Hermes 端命令行工具 |
| `installer/` | NSIS | Windows 一键安装包 |

## 特性

- 单一 exe，~8MB
- 注册为 Windows 服务，开机自启
- 断线自动重连
- 命令执行 / 文件传输 / 实时屏幕
