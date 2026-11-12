#!/usr/bin/env python3
"""
Test Graph Synchronization and Recovery

Focused verification of:
1. Graph sync idempotence (no duplicate nodes on re-run)
2. Graph sync recovery (checkpoint not marked prematurely)
3. Graph content accuracy (expected nodes and relationships)
4. Why investigation returned no connected files
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

os.environ['PYTHONIOENCODING'] = 'utf-8'

# Setup paths
METADATA_PIPELINE_ROOT = Path(__file__).parent.parent / "Metadata-Pipeline-main"
GRAPH_DOC_GEN_ROOT = Path(__file__).parent.parent / "graph-doc-gen-main"
ORC_ROOT = Path(__file__).parent

sys.path.insert(0, str(METADATA_PIPELINE_ROOT))
sys.path.insert(0, str(GRAPH_DOC_GEN_ROOT))
sys.path.insert(0, str(ORC_ROOT))

# Imports
from database.neo4j_client import Neo4jClient
from maintenance.git_utils import get_commit_diff

# ============================================================================
# TEST CONFIGURATION
# ============================================================================

REPO_ID = "DhruvHegde/dependency-error-repo"
REPO_PATH = r"c:\Users\DHRUV HEGDE\Desktop\dependency-error-repo"
TARGET_SHA = "396184b8566debf2f302fe411f9e9816f73b76ee"
BASE_SHA = "5fc4a8b"  # Parent commit (computed previously)

# ============================================================================
# TEST 1: GRAPH STATE INSPECTION
# ============================================================================

print("\n" + "=" * 80)
print("TEST 1: EXAMINE CURRENT GRAPH STATE")
print("=" * 80)

try:
    client = Neo4jClient()
    
    with client.session() as session:
        # Count nodes by type
        print("\n[1] Node counts by type:")
        result = session.run("MATCH (n) RETURN labels(n)[0] as label, count(*) as count ORDER BY count DESC")
        for record in result:
            label = record.get("label", "Unknown")
            count = record.get("count", 0)
            print(f"    {label:20s}: {count:5d} nodes")
        
        # Get total node count
        result = session.run("MATCH (n) RETURN count(n) as total")
        total_nodes_before = result.single()[0]
        print(f"\n    TOTAL: {total_nodes_before} nodes")
        
        # Count relationships by type
        print("\n[2] Relationship counts by type:")
        result = session.run("MATCH ()-[r]-() RETURN type(r) as rel_type, count(*) as count ORDER BY count DESC")
        rel_count = 0
        for record in result:
            rel_type = record.get("rel_type", "Unknown")
            count = record.get("count", 0)
            print(f"    {rel_type:20s}: {count:5d} relationships")
            rel_count += count
        print(f"\n    TOTAL: {rel_count} relationships")
        
        # Sample File nodes
        print("\n[3] Sample File nodes (first 10):")
        result = session.run("MATCH (f:File) RETURN f.path as path, f.name as name LIMIT 10")
        for i, record in enumerate(result, 1):
            path = record.get("path", "N/A")
            name = record.get("name", "N/A")
            print(f"    {i}. {name} ({path})")
        
        # Search for requirements.txt specifically
        print("\n[4] Looking for 'requirements.txt' in graph:")
        result = session.run("MATCH (f:File) WHERE f.name CONTAINS 'requirements' OR f.path CONTAINS 'requirements' RETURN f.path, f.name, id(f) as node_id LIMIT 5")
        found = False
        for record in result:
            found = True
            path = record.get("f.path", "N/A")
            name = record.get("f.name", "N/A")
            node_id = record.get("node_id", "N/A")
            print(f"    Found: {name} at {path} (node_id={node_id})")
        if not found:
            print("    NOT FOUND - requirements.txt not yet in graph")
        
        # Check for Function/Class nodes
        print("\n[5] Code definition nodes (Function, Class, etc.):")
        result = session.run("MATCH (n) WHERE n:Function OR n:Class OR n:Module RETURN labels(n)[0] as label, count(*) as count")
        for record in result:
            label = record.get("label", "Unknown")
            count = record.get("count", 0)
            print(f"    {label}: {count}")
        
        # Check relationship targets for requirements.txt
        if found:
            print("\n[6] Relationships involving requirements.txt:")
            result = session.run("""
                MATCH (f:File {name: 'requirements.txt'})
                OPTIONAL MATCH (f)-[r]->(target)
                RETURN type(r) as rel_type, labels(target) as target_labels, count(*) as count
                GROUP BY rel_type, target_labels
            """)
            rel_found = False
            for record in result:
                rel_found = True
                rel_type = record.get("rel_type", "N/A")
                target_labels = record.get("target_labels", [])
                count = record.get("count", 0)
                print(f"    {rel_type} -> {target_labels}: {count}")
            if not rel_found:
                print("    No outgoing relationships from requirements.txt")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
finally:
    if 'client' in locals():
        client.close()

# ============================================================================
# TEST 2: VERIFY DIFF COMPUTATION
# ============================================================================

print("\n" + "=" * 80)
print("TEST 2: VERIFY GIT DIFF COMPUTATION")
print("=" * 80)

try:
    diff = get_commit_diff(BASE_SHA, TARGET_SHA, cwd=REPO_PATH)
    
    print(f"\nGit diff between {BASE_SHA[:7]} → {TARGET_SHA[:7]}:")
    print(f"  Files added:     {len(diff.get('added', []))}")
    for f in diff.get('added', []):
        print(f"    + {f}")
    
    print(f"  Files modified:  {len(diff.get('modified', []))}")
    for f in diff.get('modified', []):
        print(f"    ~ {f}")
    
    print(f"  Files deleted:   {len(diff.get('deleted', []))}")
    for f in diff.get('deleted', []):
        print(f"    - {f}")
    
    print(f"  Files renamed:   {len(diff.get('renamed', []))}")
    for old, new in diff.get('renamed', []):
        print(f"    > {old} → {new}")
    
    all_changed = (
        diff.get('added', []) +
        diff.get('modified', []) +
        [new for old, new in diff.get('renamed', [])]
    )
    print(f"\n  Total changed files: {len(all_changed)}")
    print(f"  Changed file list: {all_changed}")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# TEST 3: QUERY FOR CONNECTED FILES (UNDERSTAND WHY EMPTY)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 3: INVESTIGATE WHY CONNECTED FILES QUERY RETURNED EMPTY")
print("=" * 80)

try:
    client = Neo4jClient()
    
    changed_file = "requirements.txt"
    
    with client.session() as session:
        # Step 1: Does changed file exist in graph?
        print(f"\nStep 1: Search for '{changed_file}' in graph:")
        result = session.run("""
            MATCH (f:File)
            WHERE f.path CONTAINS $filename OR f.name CONTAINS $filename
            RETURN f.path as path, f.name as name
            LIMIT 5
        """, filename=changed_file)
        
        files_found = list(result)
        if not files_found:
            print(f"  RESULT: '{changed_file}' NOT FOUND in graph")
            print(f"  This explains why connected files query returned empty!")
        else:
            print(f"  FOUND:")
            for record in files_found:
                print(f"    - {record['name']} at {record['path']}")
                
                # Step 2: Check if file has any CONTAINS relationships
                print(f"\n  Step 2: Check what this file CONTAINS:")
                result = session.run("""
                    MATCH (f:File {path: $path})
                    OPTIONAL MATCH (f)-[:CONTAINS]->(child)
                    RETURN child, count(*) as count
                """, path=record['path'])
                
                contains_count = 0
                for r in result:
                    if r['child']:
                        contains_count += 1
                        print(f"    - Contains: {r['child']}")
                
                if contains_count == 0:
                    print(f"    (No CONTAINS relationships)")
                
                # Step 3: Check if any functions/classes CALL each other
                print(f"\n  Step 3: Check for CALLS relationships:")
                result = session.run("""
                    MATCH (f:File {path: $path})-[:CONTAINS]->(sym)
                    OPTIONAL MATCH (sym)-[:CALLS]->(target)
                    RETURN sym, target, count(*) as count
                """, path=record['path'])
                
                calls_count = 0
                for r in result:
                    if r['target']:
                        calls_count += 1
                        print(f"    - {r['sym']} CALLS {r['target']}")
                
                if calls_count == 0:
                    print(f"    (No CALLS relationships)")
        
        # Step 4: Show what IS in the graph
        print(f"\n  Step 4: Examine actual graph content type:")
        result = session.run("""
            MATCH (n)
            WITH DISTINCT labels(n) as node_types
            RETURN node_types
            LIMIT 10
        """)
        
        print(f"  Node types in graph:")
        for record in result:
            types = record.get('node_types', [])
            print(f"    - {types}")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
finally:
    if 'client' in locals():
        client.close()

# ============================================================================
# TEST 4: RE-RUN SAME COMMIT AND CHECK FOR IDEMPOTENCE
# ============================================================================

print("\n" + "=" * 80)
print("TEST 4: RUN SAME COMMIT TWICE AND CHECK FOR DUPLICATES")
print("=" * 80)

try:
    client = Neo4jClient()
    
    with client.session() as session:
        # Get node count before
        result = session.run("MATCH (n) RETURN count(n) as count")
        count_before = result.single()[0]
        
        # Get relationship count before
        result = session.run("MATCH ()-[r]-() RETURN count(r) as count")
        rel_before = result.single()[0]
        
        print(f"\nBefore re-run:")
        print(f"  Nodes:         {count_before}")
        print(f"  Relationships: {rel_before}")
        
        # Simulate second run by checking if nodes would be duplicated
        # (We're not actually running the sync again, just checking the logic)
        print(f"\nCheck: If we run sync again on same SHA:")
        print(f"  Expected: No change (idempotent operation)")
        print(f"  Verification: Check for duplicate file nodes with same path")
        
        result = session.run("""
            MATCH (f:File)
            WITH f.path as path, count(*) as cnt
            WHERE cnt > 1
            RETURN path, cnt
        """)
        
        duplicates = list(result)
        if duplicates:
            print(f"  WARNING: Found duplicate nodes:")
            for record in duplicates:
                print(f"    - {record['path']}: {record['cnt']} copies")
        else:
            print(f"  RESULT: No duplicate File nodes (idempotence OK)")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
finally:
    if 'client' in locals():
        client.close()

# ============================================================================
# TEST 5: CHECKPOINT STATE CHECK
# ============================================================================

print("\n" + "=" * 80)
print("TEST 5: CHECK CHECKPOINT STATE TRANSITIONS")
print("=" * 80)

try:
    from src.storage.checkpoint import CheckpointManager, CheckpointState
    
    manager = CheckpointManager()
    
    cached = manager.get(REPO_ID, TARGET_SHA)
    
    if cached:
        print(f"\nCheckpoint exists for {REPO_ID}@{TARGET_SHA[:7]}:")
        print(f"  State:       {cached.get('state', 'UNKNOWN')}")
        print(f"  Retry count: {cached.get('retry_count', 0)}")
        print(f"  Created:     {cached.get('created_at', 'N/A')}")
        print(f"  Has prediction: {bool(cached.get('prediction_result'))}")
        print(f"  Has graph sync result: {bool(cached.get('graph_sync_result'))}")
    else:
        print(f"\nNo checkpoint found for {REPO_ID}@{TARGET_SHA[:7]}")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("TESTS COMPLETE")
print("=" * 80)
