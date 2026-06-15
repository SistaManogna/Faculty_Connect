#!/bin/bash
# Faculty Connect – startup script
# Run this file to launch the app: bash run.sh

set -e

cd "$(dirname "$0")"

echo "🔧 Installing dependencies..."
pip3 install -r requirements.txt -q 2>/dev/null || \
  pip install -r requirements.txt -q 2>/dev/null || true

echo "🚀 Starting Faculty Connect on http://127.0.0.1:5000"
echo "   Press Ctrl+C to stop."
echo ""
python3 app.py
