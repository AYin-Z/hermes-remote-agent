// Hermes Remote Agent — Windows/Linux/macOS agent
//
// Build: go build -ldflags "-X main.ServerURL=wss://... -X main.AuthToken=xxx"
// Cross: GOOS=windows GOARCH=amd64 go build -o agent.exe
//
// On Windows, runs as console app or Windows service (auto-detect).

package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"runtime"
	"syscall"

	"hermes-remote-agent/exec"
	"hermes-remote-agent/protocol"
	"hermes-remote-agent/sysinfo"
	"hermes-remote-agent/ws"
)

// ── ldflags 注入 ──

var (
	ServerURL = "ws://127.0.0.1:8085/ws"
	AuthToken = ""
	AgentName = ""
)

var (
	flagServer  = flag.String("server", ServerURL, "WebSocket server URL")
	flagToken   = flag.String("token", AuthToken, "Auth token")
	flagName    = flag.String("name", AgentName, "Agent hostname (default: system hostname)")
	flagConsole = flag.Bool("console", false, "Force console mode (don't run as service)")
)

func main() {
	flag.Parse()
	log.SetFlags(log.LstdFlags | log.Lshortfile)

	// Windows: detect service mode
	if isWindowsService() && !*flagConsole {
		runServiceMain()
		return
	}

	// Console mode
	runConsoleAgent()
}

func runConsoleAgent() {
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

	client := ws.NewClient(ws.Config{
		ServerURL: *flagServer,
		Token:     *flagToken,
		AgentInfo: info,
		Handlers: ws.MessageHandlers{
			Exec:       exec.HandleExec,
			Screenshot: exec.HandleScreenshot,
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
