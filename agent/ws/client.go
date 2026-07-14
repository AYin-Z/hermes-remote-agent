// ws — WebSocket client with auto-reconnect and heartbeat

package ws

import (
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/url"
	"sync"
	"time"

	"hermes-remote-agent/protocol"

	"github.com/gorilla/websocket"
)

// ── Config ──

type Config struct {
	ServerURL string
	Token     string
	AgentInfo protocol.AgentInfo
	Handlers  MessageHandlers
}

// MessageHandlers defines callback functions for each server command type.
type MessageHandlers struct {
	Exec       func(id, cmd, shell string, timeout int) protocol.Result
	Screenshot func(id string, quality int) protocol.ScreenshotData
	Processes  func(id, filter string) protocol.ProcessList
	SysInfoFn  func(id string) protocol.SysInfoData
	UploadFn   func(id, filename, path, data string, totalChunks, chunkIndex int) protocol.UploadDone
}

// ── Client ──

type Client struct {
	cfg    Config
	conn   *websocket.Conn
	mu     sync.Mutex
	closed bool
	done   chan struct{}
}

func NewClient(cfg Config) *Client {
	return &Client{
		cfg:  cfg,
		done: make(chan struct{}),
	}
}

func (c *Client) Connect() error {
	backoff := 2 * time.Second
	maxBackoff := 5 * time.Minute

	for {
		if c.closed {
			return fmt.Errorf("client closed")
		}

		err := c.connectOnce()
		if err == nil {
			backoff = 2 * time.Second // reset
			// After disconnect, loop back with backoff
			c.mu.Lock()
			conn := c.conn
			c.conn = nil
			c.mu.Unlock()
			if conn != nil {
				conn.Close()
			}
			log.Printf("Disconnected, reconnecting in %v...", backoff)
		} else {
			log.Printf("Connection failed: %v (retry in %v)", err, backoff)
		}

		select {
		case <-c.done:
			return nil
		case <-time.After(backoff):
		}

		backoff = time.Duration(math.Min(float64(backoff*2), float64(maxBackoff)))
	}
}

func (c *Client) connectOnce() error {
	u, err := url.Parse(c.cfg.ServerURL)
	if err != nil {
		return fmt.Errorf("invalid server URL: %w", err)
	}

	conn, _, err := websocket.DefaultDialer.Dial(u.String(), nil)
	if err != nil {
		return fmt.Errorf("dial: %w", err)
	}

	c.mu.Lock()
	c.conn = conn
	c.mu.Unlock()

	// Register
	reg := protocol.NewRegister(c.cfg.AgentInfo, c.cfg.Token)
	if err := conn.WriteJSON(reg); err != nil {
		return fmt.Errorf("register: %w", err)
	}

	var resp map[string]interface{}
	if err := conn.ReadJSON(&resp); err != nil {
		return fmt.Errorf("read register response: %w", err)
	}

	if t, _ := resp["type"].(string); t != protocol.TypeRegistered {
		reason, _ := resp["reason"].(string)
		conn.Close()
		return fmt.Errorf("register rejected: %s", reason)
	}

	log.Println("Registered with server")

	// Heartbeat
	go c.heartbeat(conn)

	// Message loop
	return c.readLoop(conn)
}

func (c *Client) heartbeat(conn *websocket.Conn) {
	ticker := time.NewTicker(15 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		c.mu.Lock()
		if c.closed || c.conn != conn {
			c.mu.Unlock()
			return
		}
		c.mu.Unlock()

		conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
		if err := conn.WriteJSON(map[string]string{"type": protocol.TypePing}); err != nil {
			return
		}
	}
}

func (c *Client) readLoop(conn *websocket.Conn) error {
	for {
		var raw json.RawMessage
		if err := conn.ReadJSON(&raw); err != nil {
			return err
		}

		// Parse type
		var base protocol.BaseMsg
		if err := json.Unmarshal(raw, &base); err != nil {
			log.Printf("Bad message: %v", err)
			continue
		}

		switch base.Type {
		case protocol.TypePong:
			// alive

		case protocol.TypeExec:
			var msg protocol.Exec
			json.Unmarshal(raw, &msg)
			if c.cfg.Handlers.Exec != nil {
				go func() {
					result := c.cfg.Handlers.Exec(msg.ID, msg.Cmd, msg.Shell, msg.Timeout)
					c.sendJSON(result)
				}()
			}

		case protocol.TypeScreenshot:
			var msg protocol.Screenshot
			json.Unmarshal(raw, &msg)
			if c.cfg.Handlers.Screenshot != nil {
				go func() {
					data := c.cfg.Handlers.Screenshot(msg.ID, msg.Quality)
					c.sendJSON(data)
				}()
			}

		case protocol.TypeSysInfo:
			var msg protocol.SysInfoMsg
			json.Unmarshal(raw, &msg)
			if c.cfg.Handlers.SysInfoFn != nil {
				go func() {
					data := c.cfg.Handlers.SysInfoFn(msg.ID)
					c.sendJSON(data)
				}()
			}

		case protocol.TypeProcesses:
			var msg protocol.Processes
			json.Unmarshal(raw, &msg)
			if c.cfg.Handlers.Processes != nil {
				go func() {
					data := c.cfg.Handlers.Processes(msg.ID, msg.Filter)
					c.sendJSON(data)
				}()
			}

		case protocol.TypeUpload:
			var msg protocol.Upload
			json.Unmarshal(raw, &msg)
			if c.cfg.Handlers.UploadFn != nil {
				go func() {
					data := c.cfg.Handlers.UploadFn(msg.ID, msg.Filename, msg.Path, msg.Data, msg.TotalChunks, msg.ChunkIndex)
					c.sendJSON(data)
				}()
			}

		default:
			log.Printf("Unknown message type: %s", base.Type)
		}
	}
}

func (c *Client) sendJSON(v interface{}) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.conn != nil {
		c.conn.SetWriteDeadline(time.Now().Add(30 * time.Second))
		c.conn.WriteJSON(v)
	}
}

func (c *Client) Close() {
	c.mu.Lock()
	c.closed = true
	if c.conn != nil {
		c.conn.Close()
	}
	c.mu.Unlock()
	close(c.done)
}
