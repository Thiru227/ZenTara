#!/usr/bin/env bash
# ── Render Build Script ─────────────────────────
# Runs during every deploy on Render

set -o errexit  # Exit on error

echo "🧘 ZenTara Build Starting..."

# 1. Upgrade pip
pip install --upgrade pip

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create upload and RAG directories
mkdir -p uploads
mkdir -p rag/collections

echo "🧘 ZenTara Build Complete!"
