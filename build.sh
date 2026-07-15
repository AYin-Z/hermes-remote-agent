#!/bin/bash
# Build Hermes Remote Agent for all platforms
# Usage: ./build.sh [SERVER_URL] [AUTH_TOKEN]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$SCRIPT_DIR/agent"
BUILD_DIR="$SCRIPT_DIR/build"
INSTALLER_DIR="$SCRIPT_DIR/installer"

SERVER_URL="${1:-ws://127.0.0.1:8085/ws}"
AUTH_TOKEN="${2:-}"

echo "=== Building Hermes Remote Agent ==="
echo "  Server: $SERVER_URL"
echo "  Token: ${AUTH_TOKEN:0:8}..."
echo ""

# Build flags
LDFLAGS="-s -w -X main.ServerURL=$SERVER_URL"
if [ -n "$AUTH_TOKEN" ]; then
	LDFLAGS="$LDFLAGS -X main.AuthToken=$AUTH_TOKEN"
fi

mkdir -p "$BUILD_DIR"

# Windows (primary target)
echo "► Building windows/amd64..."
cd "$AGENT_DIR"
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 \
	go build -ldflags="$LDFLAGS" -o "$BUILD_DIR/agent.exe" .
echo "  $BUILD_DIR/agent.exe ($(du -h "$BUILD_DIR/agent.exe" | cut -f1))"

# Linux (for testing)
echo "► Building linux/amd64..."
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 \
	go build -ldflags="$LDFLAGS" -o "$BUILD_DIR/agent_linux" .
echo "  $BUILD_DIR/agent_linux ($(du -h "$BUILD_DIR/agent_linux" | cut -f1))"

# Copy to installer dir
cp "$BUILD_DIR/agent.exe" "$INSTALLER_DIR/agent.exe"

echo ""
echo "=== Build complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit installer/hermes-agent.nsi SERVER_URL/AUTH_TOKEN if needed"
echo "  2. On Windows: makensis installer/hermes-agent.nsi"
echo "  3. Distribute: hermes-agent-setup.exe"
