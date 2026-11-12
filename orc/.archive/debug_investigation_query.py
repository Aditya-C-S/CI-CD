#!/usr/bin/env python3
"""
Debug the investigation query to understand why it returns 0 results
when we know CALLS relationships exist.
"""

import sys
from pathlib import Path
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'

GRAPH_DOC_GEN_ROOT = Path(__file__).parent.parent / "graph-doc-gen-main"
sys.path.insert(0, str(GRAPH_DOC_GEN_ROOT))

from database.neo4j_client import Neo4jClient

print("=" * 100)
print("DEBUG INVESTIGATION QUERY")
print("=" * 100)

client = Neo4jClient()

# Test repository paths
test_file_a = r"C:\Users\DHRUVH~1\AppData\Local\Temp\e2e_test_4sp6q4pr\file_a.py"
test_file_b = r"C:\Users\DHRUVH~1\AppData\Local\Temp\e2e_test_4sp6q4pr\file_b.py"

with client.session() as session:
    # Test 1: Find File nodes by pattern
    print("\n[TEST 1] Find File nodes...")
    result = session.run("MATCH (f:File) WHERE f.path CONTAINS $pattern RETURN f.path, f.name", pattern="e2e_test_4sp6q4pr")
    files_found = 0
    for rec in result:
        print(f"  {rec['f.name']}: {rec['f.path']}")
        files_found += 1
    print(f"  Found: {files_found}")
    
    # Test 2: Run query with exact paths
    print("\n[TEST 2] Run investigation query with exact paths...")
    query = """
        MATCH (changed_file:File) WHERE changed_file.path IN $changed_paths
        OPTIONAL MATCH (changed_file)-[:CONTAINS]->(changed_sym)
        OPTIONAL MATCH (changed_sym)-[:CALLS]->(callee)
        OPTIONAL MATCH (caller)-[:CALLS]->(changed_sym)
        WITH DISTINCT 
            CASE 
                WHEN callee IS NOT NULL THEN callee.file_path
                WHEN caller IS NOT NULL THEN caller.file_path
                ELSE NULL
            END AS connected_path,
            CASE 
                WHEN callee IS NOT NULL THEN callee
                WHEN caller IS NOT NULL THEN caller
                ELSE NULL
            END AS symbol_node
        WHERE connected_path IS NOT NULL
          AND NOT (connected_path IN $changed_paths)
        WITH DISTINCT connected_path, symbol_node
        OPTIONAL MATCH (symbol_node)-[:CALLS]->(outgoing)
        OPTIONAL MATCH (incoming)-[:CALLS]->(symbol_node)
        RETURN connected_path,
               count(DISTINCT outgoing) AS out_degree,
               count(DISTINCT incoming) AS in_degree
    """
    
    changed_paths = [test_file_a]
    print(f"  Changed files: {changed_paths}")
    
    result = session.run(query, changed_paths=changed_paths)
    
    rows = list(result)
    print(f"  Results: {len(rows)} rows")
    for row in rows:
        print(f"    - {row['connected_path']} (in:{row['in_degree']}, out:{row['out_degree']})")
    
    # Test 3: Manual query - find the relationship manually
    print("\n[TEST 3] Manual relationship check...")
    result = session.run("""
        MATCH (f:File) WHERE f.path = $path RETURN f.path, id(f) as fid
    """, path=test_file_a)
    
    file_a_id = None
    for rec in result:
        file_a_id = rec['fid']
        print(f"  file_a id: {file_a_id}")
    
    if file_a_id:
        # Find functions in file_a
        result = session.run("""
            MATCH (f)-[:CONTAINS]->(func)
            WHERE id(f) = $file_id
            RETURN func.name, id(func) as fid
        """, file_id=file_a_id)
        
        print(f"  Functions in file_a:")
        for rec in result:
            func_id = rec['fid']
            func_name = rec['func.name']
            print(f"    {func_name} (id={func_id})")
            
            # Find what it calls
            result2 = session.run("""
                MATCH (f)-[:CALLS]->(other)
                WHERE id(f) = $func_id
                RETURN other.name, other.file_path
            """, func_id=func_id)
            
            for rec2 in result2:
                print(f"      -> {rec2['other.name']} (file={rec2['other.file_path']})")
    
    # Test 4: What if we use CONTAINS properly?
    print("\n[TEST 4] Test with CONTAINS pattern...")
    result = session.run("""
        MATCH (changed_file:File) WHERE changed_file.path = $path
        OPTIONAL MATCH (changed_file)-[:CONTAINS]->(changed_sym)
        OPTIONAL MATCH (changed_sym)-[:CALLS]->(callee)
        OPTIONAL MATCH (caller)-[:CALLS]->(changed_sym)
        RETURN changed_file.path, changed_sym.name, callee.name, callee.file_path, caller.name
    """, path=test_file_a)
    
    for rec in result:
        print(f"  File: {rec['changed_file.path']}")
        print(f"    Defined: {rec['changed_sym.name']}")
        print(f"    Calls: {rec['callee.name']} @ {rec['callee.file_path']}")
        print(f"    Called by: {rec['caller.name']}")

client.close()

print("\n" + "=" * 100)
print("INSIGHTS")
print("=" * 100)
