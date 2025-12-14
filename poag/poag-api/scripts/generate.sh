#!/usr/bin/env bash
# Generate Python client and FastAPI server using Fern
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Generating POAG API client and server with Fern..."
echo ""

# Clean previous generated code
rm -rf generated/

# Run Fern generation
cd fern
fern generate --group all --log-level info

echo ""
echo "✓ Generated code written to:"
echo "  - generated/client-py/   (Python SDK)"
echo "  - generated/server/      (FastAPI server stubs)"
echo ""
echo "Run tests with: pytest tests/ -v"
