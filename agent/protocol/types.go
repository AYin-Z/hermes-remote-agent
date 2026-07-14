// protocol — Agent ↔ Server message types (Go port of server/protocol.py)

package protocol

// ── Type constants ──

const (
	TypeRegister       = "register"
	TypeRegistered     = "registered"
	TypeRegisterError  = "register_error"
	TypePing           = "ping"
	TypePong           = "pong"
	TypeExec           = "exec"
	TypeResult         = "result"
	TypeUpload         = "upload"
	TypeUploadDone     = "upload_done"
	TypeDownloadStart  = "download_start"
	TypeDownloadData   = "download_data"
	TypeScreenshot     = "screenshot"
	TypeScreenshotData = "screenshot_data"
	TypeProcesses      = "processes"
	TypeProcessList    = "process_list"
	TypeSysInfo        = "sysinfo"
	TypeSysInfoData    = "sysinfo_data"
	TypeError          = "error"
)

// ── Agent registration data ──

type AgentInfo struct {
	Hostname     string `json:"hostname"`
	OS           string `json:"os"`
	Arch         string `json:"arch"`
	AgentVersion string `json:"agent_version"`
	Username     string `json:"username"`
}

// ── Message structs ──

type Register struct {
	Type   string `json:"type"`
	Token  string `json:"token"`
	AgentInfo
}

type BaseMsg struct {
	Type string `json:"type"`
	ID   string `json:"id,omitempty"`
}

type Exec struct {
	Type    string `json:"type"`
	ID      string `json:"id"`
	Cmd     string `json:"cmd"`
	Shell   string `json:"shell"`
	Timeout int    `json:"timeout"`
}

type Result struct {
	Type     string `json:"type"`
	ID       string `json:"id"`
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	ExitCode int    `json:"exit_code"`
}

type Upload struct {
	Type        string `json:"type"`
	ID          string `json:"id"`
	Filename    string `json:"filename"`
	Path        string `json:"path"`
	Data        string `json:"data"`
	TotalChunks int    `json:"total_chunks"`
	ChunkIndex  int    `json:"chunk_index"`
}

type UploadDone struct {
	Type     string `json:"type"`
	ID       string `json:"id"`
	Filename string `json:"filename"`
	Path     string `json:"path"`
	Size     int    `json:"size"`
}

type DownloadStart struct {
	Type        string `json:"type"`
	ID          string `json:"id"`
	Filename    string `json:"filename"`
	TotalChunks int    `json:"total_chunks"`
}

type DownloadData struct {
	Type        string `json:"type"`
	ID          string `json:"id"`
	Filename    string `json:"filename"`
	Data        string `json:"data"`
	ChunkIndex  int    `json:"chunk_index"`
	TotalChunks int    `json:"total_chunks"`
	IsLast      bool   `json:"is_last"`
}

type Screenshot struct {
	Type    string `json:"type"`
	ID      string `json:"id"`
	Quality int    `json:"quality"`
}

type ScreenshotData struct {
	Type   string `json:"type"`
	ID     string `json:"id"`
	Data   string `json:"data"`
	Width  int    `json:"width"`
	Height int    `json:"height"`
}

type Processes struct {
	Type   string `json:"type"`
	ID     string `json:"id"`
	Filter string `json:"filter"`
}

type ProcessInfo struct {
	PID       int     `json:"pid"`
	Name      string  `json:"name"`
	CPUPercent float64 `json:"cpu_percent"`
	MemoryMB  float64 `json:"memory_mb"`
}

type ProcessList struct {
	Type      string        `json:"type"`
	ID        string        `json:"id"`
	Processes []ProcessInfo `json:"processes"`
}

type SysInfoMsg struct {
	Type string `json:"type"`
	ID   string `json:"id"`
}

type SysInfoData struct {
	Type           string  `json:"type"`
	ID             string  `json:"id"`
	Hostname       string  `json:"hostname"`
	OSName         string  `json:"os_name"`
	OSVersion      string  `json:"os_version"`
	Arch           string  `json:"arch"`
	CPUCores       int     `json:"cpu_cores"`
	CPUPercent     float64 `json:"cpu_percent"`
	TotalMemoryGB  float64 `json:"total_memory_gb"`
	UsedMemoryGB   float64 `json:"used_memory_gb"`
	TotalDiskGB    float64 `json:"total_disk_gb"`
	UsedDiskGB     float64 `json:"used_disk_gb"`
	UptimeSeconds  int64   `json:"uptime_seconds"`
}

type Error struct {
	Type      string `json:"type"`
	ID        string `json:"id"`
	RequestID string `json:"request_id"`
	Message   string `json:"message"`
}

// NewRegister creates a register message.
func NewRegister(info AgentInfo, token string) Register {
	return Register{
		Type:      TypeRegister,
		Token:     token,
		AgentInfo: info,
	}
}

// NewResult creates a result message.
func NewResult(id string, stdout, stderr string, exitCode int) Result {
	return Result{
		Type:     TypeResult,
		ID:       id,
		Stdout:   stdout,
		Stderr:   stderr,
		ExitCode: exitCode,
	}
}
