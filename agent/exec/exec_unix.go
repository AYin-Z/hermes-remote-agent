//go:build !windows

package exec

import (
	"bytes"
	"encoding/base64"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"hermes-remote-agent/protocol"
)

func HandleScreenshot(id string, quality int) protocol.ScreenshotData {
	return protocol.ScreenshotData{
		Type:   protocol.TypeScreenshotData,
		ID:     id,
		Width:  0,
		Height: 0,
	}
}

func HandleProcesses(id, filter string) protocol.ProcessList {
	entries, _ := os.ReadDir("/proc")
	var procs []protocol.ProcessInfo

	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		var pid int
		if _, err := fmt.Sscanf(e.Name(), "%d", &pid); err != nil {
			continue
		}
		comm, err := os.ReadFile(fmt.Sprintf("/proc/%d/comm", pid))
		if err != nil {
			continue
		}
		name := string(bytes.TrimSpace(comm))
		if filter != "" && !strings.Contains(name, filter) {
			continue
		}
		procs = append(procs, protocol.ProcessInfo{
			PID:  pid,
			Name: name,
		})
		if len(procs) >= 200 {
			break
		}
	}

	return protocol.ProcessList{
		Type:      protocol.TypeProcessList,
		ID:        id,
		Processes: procs,
	}
}

func HandleUpload(id, filename, path, data string, totalChunks, chunkIndex int) protocol.UploadDone {
	if path == "" {
		path = filename
	}
	raw, err := base64.StdEncoding.DecodeString(data)
	if err != nil {
		return protocol.UploadDone{
			Type:     protocol.TypeUploadDone,
			ID:       id,
			Filename: filename,
			Path:     path,
		}
	}
	dir := filepath.Dir(path)
	if dir != "" {
		os.MkdirAll(dir, 0755)
	}
	os.WriteFile(path, raw, 0644)
	return protocol.UploadDone{
		Type:     protocol.TypeUploadDone,
		ID:       id,
		Filename: filename,
		Path:     path,
		Size:     len(raw),
	}
}
