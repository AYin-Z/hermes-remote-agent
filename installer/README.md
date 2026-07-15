# Windows 安装包制作

## 前置条件

在 **Windows** 上安装 [NSIS](https://nsis.sourceforge.io/Download)：

```powershell
winget install NSIS.NSIS
```

## 构建步骤

### 1. 交叉编译 Agent

在 Linux/macOS 上：

```bash
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 \
  go build -ldflags="-s -w" -o build/agent.exe ./agent
```

### 2. 制作安装包

把 `build/agent.exe` 复制到 `installer/` 目录，然后：

```powershell
makensis /DSERVER_URL=wss://your-server.example.com/ws /DAUTH_TOKEN=your-secret-token hermes-agent.nsi
```

输出：`hermes-agent-setup.exe` （约 6-7 MB）

## 安装包行为

双击运行 → 自动完成：

1. 安装 `agent.exe` 到 `C:\Program Files\HermesRemoteAgent\`
2. 注册为 Windows 服务 (`HermesRemoteAgent`)，开机自启
3. 配置崩溃自动重启（失败后 5s/10s/30s 重试）
4. 立即启动服务

## 静默安装（批量部署）

```powershell
hermes-agent-setup.exe /S /D=C:\Program Files\HermesRemoteAgent
```

## 卸载

```
控制面板 → 程序和功能 → Hermes Remote Agent → 卸载
```

或命令行：

```powershell
sc stop HermesRemoteAgent
sc delete HermesRemoteAgent
del /f "C:\Program Files\HermesRemoteAgent\agent.exe"
```

## 调试

查看 Agent 日志（以服务运行时，日志写入 Windows Event Log）：

```powershell
Get-EventLog -LogName Application -Source HermesRemoteAgent -Newest 20
```

或前台测试模式：

```powershell
agent.exe -server wss://your-server.com/ws -token xxx -console
```
