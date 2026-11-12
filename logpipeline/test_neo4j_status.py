#!/usr/bin/env python3
"""
Test Neo4j status directly without Uvicorn.
Run this to check if Neo4j connectivity works.
"""

import sys
from pathlib import Path

# Setup paths exactly as main.py does
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_ROOT = _PROJECT_ROOT / "src"

sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_SRC_ROOT))

# Load environment exactly as main.py does
from dotenv import load_dotenv

_GRAPH_GEN_ROOT = _PROJECT_ROOT.parent / "graph-doc-gen-main"
print(f"Loading environment from: {_GRAPH_GEN_ROOT / '.env'}")

if (_GRAPH_GEN_ROOT / ".env").exists():
    result = load_dotenv(str(_GRAPH_GEN_ROOT / ".env"))
    print(f"  Result: {result}")
else:
    print(f"  ERROR: File not found!")

result = load_dotenv(str(_PROJECT_ROOT / ".env"), override=False)
print(f"Loading local overrides from: {_PROJECT_ROOT / '.env'}")
print(f"  Result: {result}")
print()

# Check environment
import os
print("Environment variables:")
for var in ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE"]:
    value = os.getenv(var)
    print(f"  {var}: {'SET' if value else 'NOT SET'}")
print()

# Get and test the service
print("Importing MetadataService...")
from src.prediction.metadata_service import MetadataService

service = MetadataService.get_instance()
print("Getting graph status...")

result = service.get_graph_status()

print()
print("=" * 70)
print("RESULT:")
print("=" * 70)
print(f"Status:       {result['status']}")
print(f"Connected:    {result['connected']}")
print(f"Database:     {result.get('database', 'N/A')}")
print(f"Version:      {result.get('version', 'N/A')}")
print(f"Edition:      {result.get('edition', 'N/A')}")
print(f"Node Count:   {result.get('node_count', 0)}")
print(f"Edge Count:   {result.get('edge_count', 0)}")
print(f"Repositories: {', '.join(result.get('repositories', []))}")
print()

if result['status'] == 'ONLINE':
    print("SUCCESS: Neo4j is online and connected!")
else:
    print(f"FAILED: {result.get('message', 'Unknown error')}")
