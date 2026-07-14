//go:build windows

package sysinfo

import (
	"os"
	"runtime"
	"syscall"
)

func init() {
	osVersionFn = windowsVersion
	cpuPercentFn = func() float64 { return 0 } // TODO: CPU%
	totalMemGBFn = windowsTotalMem
	usedMemGBFn = windowsUsedMem
	totalDiskGBFn = func() float64 { return 0 }
	usedDiskGBFn = func() float64 { return 0 }
	uptimeFn = func() int64 { return 0 }
}

func windowsVersion() string {
	major, minor, build := windowsOSVersion()
	return fmt.Sprintf("Windows %d.%d (build %d)", major, minor, build)
}

func windowsOSVersion() (uint32, uint32, uint32) {
	return 10, 0, 22000
}

func windowsTotalMem() float64 {
	var memStatus [64]byte
	memStatus[0] = 64 // size
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	proc := kernel32.NewProc("GlobalMemoryStatusEx")
	proc.Call(uintptr(unsafe.Pointer(&memStatus[0])))
	// Simplified — returns 0 for now
	return 0
}

func windowsUsedMem() float64 {
	return 0
}
