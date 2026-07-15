//go:build windows

package exec

import (
	"encoding/base64"
	"encoding/json"
	"image"
	"image/jpeg"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"

	"hermes-remote-agent/protocol"
)

// ── DLL references ──

var (
	user32   = syscall.NewLazyDLL("user32.dll")
	gdi32    = syscall.NewLazyDLL("gdi32.dll")
	kernel32 = syscall.NewLazyDLL("kernel32.dll")

	procGetDC            = user32.NewProc("GetDC")
	procReleaseDC        = user32.NewProc("ReleaseDC")
	procGetSystemMetrics = user32.NewProc("GetSystemMetrics")
	procCreateCompatibleDC = gdi32.NewProc("CreateCompatibleDC")
	procDeleteDC         = gdi32.NewProc("DeleteDC")
	procCreateCompatibleBitmap = gdi32.NewProc("CreateCompatibleBitmap")
	procDeleteObject     = gdi32.NewProc("DeleteObject")
	procSelectObject     = gdi32.NewProc("SelectObject")
	procBitBlt           = gdi32.NewProc("BitBlt")
	procGetDIBits        = gdi32.NewProc("GetDIBits")

	SM_CXSCREEN = 0
	SM_CYSCREEN = 1
	SRCCOPY       = 0x00CC0020
	DIB_RGB_COLORS = 0
	BI_RGB        = 0
)

// ── Screenshot via GDI ──

func HandleScreenshot(id string, quality int) protocol.ScreenshotData {
	if quality <= 0 || quality > 100 {
		quality = 50
	}

	w := int(getSystemMetrics(SM_CXSCREEN))
	h := int(getSystemMetrics(SM_CYSCREEN))

	if w == 0 || h == 0 {
		log.Printf("Screenshot: zero screen size")
		return protocol.ScreenshotData{Type: protocol.TypeScreenshotData, ID: id}
	}

	hdcScreen, _, _ := procGetDC.Call(0)
	if hdcScreen == 0 {
		return protocol.ScreenshotData{Type: protocol.TypeScreenshotData, ID: id}
	}
	defer procReleaseDC.Call(0, hdcScreen)

	hdcMem, _, _ := procCreateCompatibleDC.Call(hdcScreen)
	if hdcMem == 0 {
		return protocol.ScreenshotData{Type: protocol.TypeScreenshotData, ID: id}
	}
	defer procDeleteDC.Call(hdcMem)

	hbmp, _, _ := procCreateCompatibleBitmap.Call(hdcScreen, uintptr(w), uintptr(h))
	if hbmp == 0 {
		return protocol.ScreenshotData{Type: protocol.TypeScreenshotData, ID: id}
	}
	defer procDeleteObject.Call(hbmp)

	oldBmp, _, _ := procSelectObject.Call(hdcMem, hbmp)
	defer procSelectObject.Call(hdcMem, oldBmp)

	procBitBlt.Call(hdcMem, 0, 0, uintptr(w), uintptr(h), hdcScreen, 0, 0, uintptr(SRCCOPY))

	// Get bitmap bits
	header := struct {
		Size        uint32
		Width       int32
		Height      int32
		Planes      uint16
		BitCount    uint16
		Compression uint32
		SizeImage   uint32
		XPelsPerMeter int32
		YPelsPerMeter int32
		ClrUsed     uint32
		ClrImportant uint32
	}{
		Size:        40,
		Width:       int32(w),
		Height:      -int32(h), // top-down
		Planes:      1,
		BitCount:    32,
		Compression: uint32(BI_RGB),
	}

	bmpSize := w * h * 4
	bmpBits := make([]byte, bmpSize)

	procGetDIBits.Call(
		hdcMem, hbmp,
		0, uintptr(h),
		uintptr(unsafe.Pointer(&bmpBits[0])),
		uintptr(unsafe.Pointer(&header)),
		uintptr(DIB_RGB_COLORS),
	)

	// Convert BGRA → RGBA
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	for i := 0; i < w*h; i++ {
		img.Pix[i*4+0] = bmpBits[i*4+2] // R
		img.Pix[i*4+1] = bmpBits[i*4+1] // G
		img.Pix[i*4+2] = bmpBits[i*4+0] // B
		img.Pix[i*4+3] = 255             // A
	}

	// JPEG encode
	var buf strings.Builder
	enc := base64.NewEncoder(base64.StdEncoding, &buf)
	err := jpeg.Encode(enc, img, &jpeg.Options{Quality: quality})
	enc.Close()
	if err != nil {
		log.Printf("Screenshot JPEG error: %v", err)
		return protocol.ScreenshotData{Type: protocol.TypeScreenshotData, ID: id}
	}

	return protocol.ScreenshotData{
		Type:   protocol.TypeScreenshotData,
		ID:     id,
		Data:   buf.String(),
		Width:  w,
		Height: h,
	}
}

func getSystemMetrics(index int) int32 {
	ret, _, _ := procGetSystemMetrics.Call(uintptr(index))
	return int32(ret)
}

// ── Process List via PowerShell ──

type psRawProcess struct {
	ID   int     `json:"Id"`
	Name string  `json:"ProcessName"`
	CPU  float64 `json:"CPU"`
	WS   float64 `json:"WS"`
}

func HandleProcesses(id, filter string) protocol.ProcessList {
	script := `Get-Process | Select-Object -First 100 Id,ProcessName,@{N='CPU';E={[math]::Round($_.CPU,1)}},@{N='WS';E={[math]::Round($_.WorkingSet64/1MB,1)}} | Sort-Object WS -Descending | ConvertTo-Json -Compress`

	cmd := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-Command", script)
	out, err := cmd.Output()
	if err != nil {
		log.Printf("ProcessList: powershell error: %v", err)
		return protocol.ProcessList{Type: protocol.TypeProcessList, ID: id}
	}

	// PowerShell returns an array for multiple, single object for one
	raw := strings.TrimSpace(string(out))
	if raw == "" {
		return protocol.ProcessList{Type: protocol.TypeProcessList, ID: id}
	}

	var rawProcs []psRawProcess

	// Try array first
	if strings.HasPrefix(raw, "[") {
		if err := json.Unmarshal([]byte(raw), &rawProcs); err != nil {
			log.Printf("ProcessList: JSON array parse error: %v", err)
			return protocol.ProcessList{Type: protocol.TypeProcessList, ID: id}
		}
	} else {
		// Single object
		var single psRawProcess
		if err := json.Unmarshal([]byte(raw), &single); err != nil {
			log.Printf("ProcessList: JSON single parse error: %v", err)
			return protocol.ProcessList{Type: protocol.TypeProcessList, ID: id}
		}
		rawProcs = []psRawProcess{single}
	}

	var procs []protocol.ProcessInfo
	for _, rp := range rawProcs {
		if filter != "" && !strings.Contains(strings.ToLower(rp.Name), strings.ToLower(filter)) {
			continue
		}
		procs = append(procs, protocol.ProcessInfo{
			PID:       rp.ID,
			Name:      rp.Name,
			CPUPercent: rp.CPU,
			MemoryMB:  rp.WS,
		})
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
		return protocol.UploadDone{Type: protocol.TypeUploadDone, ID: id, Filename: filename}
	}
	dir := filepath.Dir(path)
	if dir != "" {
		os.MkdirAll(dir, 0755)
	}
	if err := os.WriteFile(path, raw, 0644); err != nil {
		log.Printf("Upload: write error: %v", err)
		return protocol.UploadDone{Type: protocol.TypeUploadDone, ID: id, Filename: filename, Path: path}
	}
	return protocol.UploadDone{
		Type:     protocol.TypeUploadDone,
		ID:       id,
		Filename: filename,
		Path:     path,
		Size:     len(raw),
	}
}
