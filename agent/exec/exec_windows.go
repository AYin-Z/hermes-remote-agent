//go:build windows

package exec

import (
	"encoding/base64"
	"os"
	"os/exec"
	"path/filepath"

	"hermes-remote-agent/protocol"
)

func HandleScreenshot(id string, quality int) protocol.ScreenshotData {
	// TODO: GDI implementation
	return protocol.ScreenshotData{
		Type:   protocol.TypeScreenshotData,
		ID:     id,
		Width:  0,
		Height: 0,
	}
}

func HandleProcesses(id, filter string) protocol.ProcessList {
	out, err := exec.Command("powershell", "-NoProfile", "-Command",
		"Get-Process | Select-Object Id,ProcessName,CPU,@{N='WS';E={[math]::Round($_.WorkingSet64/1MB,1)}} | Sort-Object WS -Descending | Select-Object -First 100 | ConvertTo-Json -Compress",
	).Output()
	if err != nil {
		return protocol.ProcessList{Type: protocol.TypeProcessList, ID: id}
	}

	// Parse JSON... simplified
	_ = out
	return protocol.ProcessList{Type: protocol.TypeProcessList, ID: id}
}

func HandleUpload(id, filename, path, data string, totalChunks, chunkIndex int) protocol.UploadDone {
	if path == "" {
		path = filename
	}
	raw, err := base64.StdEncoding.DecodeString(data)
	if err != nil {
		return protocol.UploadDone{Type: protocol.TypeUploadDone, ID: id, Filename: filename}
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
