// exec — Cross-platform command execution

package exec

import (
	"bytes"
	"context"
	"os/exec"
	"time"

	"hermes-remote-agent/protocol"
)

func HandleExec(id, cmdStr, shell string, timeout int) protocol.Result {
	if timeout <= 0 {
		timeout = 60
	}
	if timeout > 300 {
		timeout = 300
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()

	var c *exec.Cmd
	switch shell {
	case "cmd":
		c = exec.CommandContext(ctx, "cmd.exe", "/C", cmdStr)
	case "bash", "sh":
		c = exec.CommandContext(ctx, "bash", "-c", cmdStr)
	default: // powershell
		c = exec.CommandContext(ctx, "powershell", "-NoProfile", "-NonInteractive",
			"-Command", cmdStr)
	}

	var stdout, stderr bytes.Buffer
	c.Stdout = &stdout
	c.Stderr = &stderr

	err := c.Run()
	exitCode := 0
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			exitCode = -1
		}
	}

	return protocol.Result{
		Type:     protocol.TypeResult,
		ID:       id,
		Stdout:   stdout.String(),
		Stderr:   stderr.String(),
		ExitCode: exitCode,
	}
}
