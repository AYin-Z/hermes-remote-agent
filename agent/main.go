// Hermes Remote Agent — Windows/Linux/macOS agent
//
// Build: go build -ldflags "-X main.ServerURL=wss://... -X main.AuthToken=xxx"
// Cross: GOOS=windows GOARCH=amd64 go build -o agent.exe

package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"runtime"
	"syscall"

	"hermes-remote-agent/protocol"
	"hermes-remote-agent/ws"
	"hermes-remote-agent/exec"
	"hermes-remote-agent/sysinfo"
)

// ── ldflags 注入 ──

var (
	ServerURL = "ws://127.0.0.1:8085/ws"
	AuthToken = ""
	AgentName = ""
)

var (
	flagServer = flag.String("server", ServerURL, "WebSocket server URL")
	flagToken  = flag.String("token", AuthToken, "Auth token")
	flagName   = flag.String("name", AgentName, "Agent hostname")
)

func main() {
	flag.Parse()
	log.SetFlags(log.LstdFlags | log.Lshortfile)

	hostname := *flagName
	if hostname == "" {
		h, _ := os.Hostname()
		hostname = h
	}

	info := protocol.AgentInfo{
		Hostname:     hostname,
		OS:           runtime.GOOS,
		Arch:         runtime.GOARCH,
		AgentVersion: "1.0.0",
		Username:     sysinfo.Username(),
	}

	log.Printf("Agent %s (%s/%s) → %s", info.Hostname, info.OS, info.Arch, *flagServer)

	// 注册命令处理器
	client := ws.NewClient(ws.Config{
		ServerURL: *flagServer,
		Token:     *flagToken,
		AgentInfo: info,
		Handlers: ws.MessageHandlers{
			Exec:       exec.HandleExec,
			Screenshot: exec.HandleScreenshot,  // will be replaced by screen on Windows
			Processes:  exec.HandleProcesses,
			SysInfoFn:  sysinfo.Collect,
			UploadFn:   exec.HandleUpload,
		},
	})

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-sigCh
		log.Println("Shutting down...")
		client.Close()
		os.Exit(0)
	}()

	if err := client.Connect(); err != nil {
		log.Fatalf("Connect failed: %v", err)
	}

	select {}
}
