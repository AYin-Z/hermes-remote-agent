//go:build linux

package sysinfo

import (
	"bufio"
	"os"
	"strconv"
	"strings"
	"syscall"
)

func init() {
	osVersionFn = linuxVersion
	cpuPercentFn = linuxCPUPercent
	totalMemGBFn = linuxTotalMem
	usedMemGBFn = linuxUsedMem
	totalDiskGBFn = linuxTotalDisk
	usedDiskGBFn = linuxUsedDisk
	uptimeFn = linuxUptime
}

func linuxVersion() string {
	data, _ := os.ReadFile("/proc/version")
	return strings.TrimSpace(string(data))
}

func linuxCPUPercent() float64 {
	f, err := os.Open("/proc/stat")
	if err != nil {
		return 0
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	if !scanner.Scan() {
		return 0
	}
	fields := strings.Fields(scanner.Text())
	if len(fields) < 5 {
		return 0
	}
	var total, idle int64
	for i := 1; i < len(fields); i++ {
		v, _ := strconv.ParseInt(fields[i], 10, 64)
		total += v
		if i == 4 {
			idle = v
		}
	}
	if total == 0 {
		return 0
	}
	return float64(total-idle) / float64(total) * 100
}

func linuxTotalMem() float64 {
	return float64(sysinfoTotal()*4096) / (1024 * 1024 * 1024)
}

func linuxUsedMem() float64 {
	total := sysinfoTotal()
	free := sysinfoFree()
	return float64((total-free)*4096) / (1024 * 1024 * 1024)
}

func sysinfoTotal() uint64 {
	var si syscall.Sysinfo_t
	syscall.Sysinfo(&si)
	return si.Totalram >> 12
}

func sysinfoFree() uint64 {
	var si syscall.Sysinfo_t
	syscall.Sysinfo(&si)
	return (si.Freeram + si.Bufferram) >> 12
}

func linuxTotalDisk() float64 { return 0 }
func linuxUsedDisk() float64  { return 0 }

func linuxUptime() int64 {
	data, _ := os.ReadFile("/proc/uptime")
	fields := strings.Fields(string(data))
	if len(fields) > 0 {
		v, _ := strconv.ParseFloat(fields[0], 64)
		return int64(v)
	}
	return 0
}
