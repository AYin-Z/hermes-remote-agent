// sysinfo — System information, platform-specific parts loaded via build tags

package sysinfo

import (
	"os"
	"runtime"

	"hermes-remote-agent/protocol"
)

// Platform-specific functions — assigned in sysinfo_linux.go / sysinfo_windows.go

var (
	osVersionFn     func() string  = func() string { return runtime.GOOS }
	cpuPercentFn    func() float64 = func() float64 { return 0 }
	totalMemGBFn    func() float64 = func() float64 { return 0 }
	usedMemGBFn     func() float64 = func() float64 { return 0 }
	totalDiskGBFn   func() float64 = func() float64 { return 0 }
	usedDiskGBFn    func() float64 = func() float64 { return 0 }
	uptimeFn         func() int64  = func() int64 { return 0 }
)

func Username() string {
	if u := os.Getenv("USER"); u != "" {
		return u
	}
	if u := os.Getenv("USERNAME"); u != "" {
		return u
	}
	return "unknown"
}

func Collect(id string) protocol.SysInfoData {
	hostname, _ := os.Hostname()

	return protocol.SysInfoData{
		Type:          protocol.TypeSysInfoData,
		ID:            id,
		Hostname:      hostname,
		OSName:        runtime.GOOS,
		OSVersion:     osVersionFn(),
		Arch:          runtime.GOARCH,
		CPUCores:      runtime.NumCPU(),
		CPUPercent:    cpuPercentFn(),
		TotalMemoryGB: totalMemGBFn(),
		UsedMemoryGB:  usedMemGBFn(),
		TotalDiskGB:   totalDiskGBFn(),
		UsedDiskGB:    usedDiskGBFn(),
		UptimeSeconds: uptimeFn(),
	}
}
