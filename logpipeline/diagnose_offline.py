#!/usr/bin/env python3
"""
Diagnostic script to capture EXACT error when Neo4j goes OFFLINE.
Run this if you see OFFLINE status to get the full error message.
"""

import sys
import os
import traceback
from pathlib import Path

# Setup paths exactly as main.py does
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_ROOT = _PROJECT_ROOT / "src"

sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_SRC_ROOT))

# Load environment exactly as main.py does
from dotenv import load_dotenv

_GRAPH_GEN_ROOT = _PROJECT_ROOT.parent / "graph-doc-gen-main"
print(f"[ENV] Loading from: {_GRAPH_GEN_ROOT / '.env'}")

if (_GRAPH_GEN_ROOT / ".env").exists():
    result = load_dotenv(str(_GRAPH_GEN_ROOT / ".env"))
    print(f"[ENV] Loaded graph-doc-gen/.env: {result}")
else:
    print(f"[ENV] ERROR: {_GRAPH_GEN_ROOT / '.env'} not found!")

result = load_dotenv(str(_PROJECT_ROOT / ".env"), override=False)
print(f"[ENV] Loaded logpipeline/.env: {result}")

# Check what we got
print("\n[ENV] Variables loaded:")
for var in ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE"]:
    value = os.getenv(var)
    if value:
        # Mask password
        if "PASSWORD" in var:
            print(f"  {var}: {'*' * len(value)}")
        else:
            print(f"  {var}: {value}")
    else:
        print(f"  {var}: NOT SET ❌")

print("\n[IMPORT] Importing Neo4jClient...")
try:
    # Add graph-doc-gen-main to path
    _GRAPH_GEN_ROOT = _PROJECT_ROOT.parent / "graph-doc-gen-main"
    if str(_GRAPH_GEN_ROOT) not in sys.path:
        sys.path.insert(0, str(_GRAPH_GEN_ROOT))
    
    from database.neo4j_client import Neo4jClient
    print("[IMPORT] Success!")
except Exception as e:
    print(f"[IMPORT] Failed: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n[TEST] Creating Neo4jClient...")
try:
    client = Neo4jClient()
    print("[TEST] Client created!")
except Exception as e:
    print(f"[TEST] Failed to create client: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n[TEST] Verifying connectivity...")
try:
    client.driver.verify_connectivity()
    print("[TEST] Connectivity verified!")
except Exception as e:
    print(f"[TEST] Connectivity failed: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n[TEST] Running Neo4j query...")
try:
    with client.session() as session:
        result = session.run("MATCH (n) RETURN count(n) as count").single()
        print(f"[TEST] Query succeeded! Node count: {result['count']}")
except Exception as e:
    print(f"[TEST] Query failed: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*70)
print("✓ ALL TESTS PASSED - Neo4j is working correctly!")
print("="*70)
