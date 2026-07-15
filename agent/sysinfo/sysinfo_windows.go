//go:build windows

package sysinfo

import (
	"fmt"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	kernel32 = windows.NewLazySystemDLL("kernel32.dll")
)

func init() {
	osVersionFn = windowsVersion
	cpuPercentFn = func() float64 { return 0 }
	totalMemGBFn = windowsTotalMem
	usedMemGBFn = windowsUsedMem
	totalDiskGBFn = windowsTotalDisk
	usedDiskGBFn = windowsUsedDisk
	uptimeFn = windowsUptime
}

// ── OS Version ──

func windowsVersion() string {
	major, minor, build := windowsRtlGetVersion()
	return fmt.Sprintf("Windows %d.%d (build %d)", major, minor, build)
}

func windowsRtlGetVersion() (uint32, uint32, uint32) {
	ntdll := windows.NewLazySystemDLL("ntdll.dll")
	procRtlGetVersion := ntdll.NewProc("RtlGetVersion")

	type osVersionInfoEx struct {
		OSVersionInfoSize uint32
		MajorVersion      uint32
		MinorVersion      uint32
		BuildNumber       uint32
		PlatformId        uint32
		CSDVersion        [128]uint16
		ServicePackMajor  uint16
		ServicePackMinor  uint16
		SuiteMask         uint16
		ProductType       byte
		Reserved          byte
	}

	info := osVersionInfoEx{OSVersionInfoSize: uint32(unsafe.Sizeof(osVersionInfoEx{}))}
	procRtlGetVersion.Call(uintptr(unsafe.Pointer(&info)))
	return info.MajorVersion, info.MinorVersion, info.BuildNumber
}

// ── Memory ──

type memoryStatusEx struct {
	Length               uint32
	MemoryLoad           uint32
	TotalPhys            uint64
	AvailPhys            uint64
	TotalPageFile        uint64
	AvailPageFile        uint64
	TotalVirtual         uint64
	AvailVirtual         uint64
	AvailExtendedVirtual uint64
}

func windowsTotalMem() float64 {
	proc := kernel32.NewProc("GlobalMemoryStatusEx")
	var m memoryStatusEx
	m.Length = uint32(unsafe.Sizeof(m))
	proc.Call(uintptr(unsafe.Pointer(&m)))
	return float64(m.TotalPhys) / (1024 * 1024 * 1024)
}

func windowsUsedMem() float64 {
	proc := kernel32.NewProc("GlobalMemoryStatusEx")
	var m memoryStatusEx
	m.Length = uint32(unsafe.Sizeof(m))
	proc.Call(uintptr(unsafe.Pointer(&m)))
	return float64(m.TotalPhys-m.AvailPhys) / (1024 * 1024 * 1024)
}

// ── Disk ──

func windowsTotalDisk() float64 {
	var free, total, totalFree uint64
	path, _ := syscall.UTF16PtrFromString("C:\\")
	kernel32.NewProc("GetDiskFreeSpaceExW").Call(
		uintptr(unsafe.Pointer(path)),
		uintptr(unsafe.Pointer(&free)),
		uintptr(unsafe.Pointer(&total)),
		uintptr(unsafe.Pointer(&totalFree)),
	)
	return float64(total) / (1024 * 1024 * 1024)
}

func windowsUsedDisk() float64 {
	var free, total, totalFree uint64
	path, _ := syscall.UTF16PtrFromString("C:\\")
	kernel32.NewProc("GetDiskFreeSpaceExW").Call(
		uintptr(unsafe.Pointer(path)),
		uintptr(unsafe.Pointer(&free)),
		uintptr(unsafe.Pointer(&total)),
		uintptr(unsafe.Pointer(&totalFree)),
	)
	return float64(total-free) / (1024 * 1024 * 1024)
}

// ── Uptime ──

func windowsUptime() int64 {
	proc := kernel32.NewProc("GetTickCount64")
	ret, _, _ := proc.Call()
	return int64(ret) / 1000
}
