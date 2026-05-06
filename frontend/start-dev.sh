#!/bin/bash
set -e

IMS_DIR="/home/akbar-ali/DEVOPS/projects/ims"
FRONTEND_DIR="$IMS_DIR/frontend"

echo "=========================================="
echo "IMS React Frontend Development Server"
echo "=========================================="
echo ""
echo "Directory: $FRONTEND_DIR"
echo "Starting dev server..."
echo ""

# Navigate and start
cd "$FRONTEND_DIR"

# Check if npm is available
if ! command -v npm &> /dev/null; then
    echo "ERROR: npm is not installed"
    exit 1
fi

# Start the dev server
npm run dev -- --host 0.0.0.0

