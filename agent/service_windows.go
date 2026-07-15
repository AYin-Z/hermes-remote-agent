//go:build windows

package main

import (
	"log"
	"os"
	"os/signal"
	"runtime"
	"syscall"

	"golang.org/x/sys/windows/svc"

	"hermes-remote-agent/exec"
	"hermes-remote-agent/protocol"
	"hermes-remote-agent/sysinfo"
	"hermes-remote-agent/ws"
)

func isWindowsService() bool {
	isSvc, err := svc.IsWindowsService()
	if err != nil {
		return false
	}
	return isSvc
}

// ── Service implementation ──

type agentService struct{}

func (s *agentService) Execute(args []string, r <-chan svc.ChangeRequest, status chan<- svc.Status) (bool, uint32) {
	const cmdsAccepted = svc.AcceptStop | svc.AcceptShutdown

	status <- svc.Status{State: svc.StartPending}

	stopCh := make(chan struct{})
	go runAgent(stopCh)

	status <- svc.Status{State: svc.Running, Accepts: cmdsAccepted}

	for c := range r {
		switch c.Cmd {
		case svc.Interrogate:
			status <- c.CurrentStatus
		case svc.Stop, svc.Shutdown:
			status <- svc.Status{State: svc.StopPending}
			close(stopCh)
			return false, 0
		default:
			log.Printf("Unexpected service control request #%d", c.Cmd)
		}
	}
	return false, 0
}

func runServiceMain() {
	err := svc.Run("HermesRemoteAgent", &agentService{})
	if err != nil {
		log.Fatalf("Service failed: %v", err)
	}
}

// ── Agent runner (shared) ──

func runAgent(stopCh chan struct{}) {
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

	log.Printf("Agent %s (%s/%s) → %s [SERVICE]", info.Hostname, info.OS, info.Arch, *flagServer)

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
		select {
		case <-sigCh:
		case <-stopCh:
		}
		log.Println("Agent shutting down...")
		client.Close()
	}()

	if err := client.Connect(); err != nil {
		log.Printf("Agent connect failed: %v", err)
	}
}
