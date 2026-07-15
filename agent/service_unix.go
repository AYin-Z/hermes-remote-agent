//go:build !windows

package main

func isWindowsService() bool {
	return false
}

// stub — never called on non-Windows
func runServiceMain() {}
