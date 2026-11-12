#!/usr/bin/env python3
"""
Analyze graph structure to understand what relationships exist between our test files.
"""

import sys
from pathlib import Path
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'

GRAPH_DOC_GEN_ROOT = Path(__file__).parent.parent / "graph-doc-gen-main"
sys.path.insert(0, str(GRAPH_DOC_GEN_ROOT))

from database.neo4j_client import Neo4jClient

print("=" * 100)
print("GRAPH STRUCTURE ANALYSIS")
print("=" * 100)

client = Neo4jClient()

with client.session() as session:
    # Find our test files
    print("\n[1] Finding our test files...")
    result = session.run("""
        MATCH (f:File)
        WHERE f.path CONTAINS 'e2e_test'
        RETURN f.path as path, f.name as name, id(f) as id
        ORDER BY f.name
    """)
    
    test_files = {}
    for record in result:
        path = record['path']
        name = record['name']
        fid = record['id']
        test_files[name] = {'path': path, 'id': fid}
        print(f"  {name}: {path} (id={fid})")
    
    # Look for Functions in each file
    print("\n[2] Functions defined in our test files...")
    for fname, fdata in test_files.items():
        fid = fdata['id']
        result = session.run("""
            MATCH (f)-->(func:Function)
            WHERE id(f) = $file_id
            RETURN func.name as name, func.file_path as file_path, id(func) as id
        """, file_id=fid)
        
        funcs = list(result)
        if funcs:
            print(f"\n  {fname}:")
            for func_rec in funcs:
                print(f"    - {func_rec['name']} (file_path={func_rec['file_path']}, id={func_rec['id']})")
        else:
            print(f"\n  {fname}: NO FUNCTIONS FOUND")
    
    # Look for any CALLS relationships between our test files
    print("\n[3] CALLS relationships between test files...")
    result = session.run("""
        MATCH (file_a:File)-[:CONTAINS]->(func_a:Function)-[:CALLS]->(func_b:Function)<-[:CONTAINS]-(file_b:File)
        WHERE file_a.path CONTAINS 'e2e_test' AND file_b.path CONTAINS 'e2e_test'
        RETURN file_a.name as file_a, func_a.name as func_a, func_b.name as func_b, file_b.name as file_b
    """)
    
    calls = list(result)
    if calls:
        for call_rec in calls:
            print(f"  {call_rec['file_a']}({call_rec['func_a']}) -> {call_rec['file_b']}({call_rec['func_b']})")
    else:
        print("  NO CALLS RELATIONSHIPS FOUND between test files")
    
    # Look at all relationship types
    print("\n[4] All relationship types in graph...")
    result = session.run("""
        MATCH ()-[r]->()
        RETURN DISTINCT type(r) as rel_type, count(*) as count
        ORDER BY count DESC
    """)
    
    for rec in result:
        print(f"  {rec['rel_type']:15s}: {rec['count']:5d}")
    
    # Check if there's any IMPORT relationship
    print("\n[5] Looking for IMPORT relationships...")
    result = session.run("""
        MATCH (f:File)-->(sym)--[:IMPORT|IMPORTS]->(other)
        WHERE f.path CONTAINS 'e2e_test'
        RETURN f.name as file, sym.name as symbol, other.name as imported
        LIMIT 10
    """)
    
    imports = list(result)
    if imports:
        for imp_rec in imports:
            print(f"  {imp_rec['file']}.{imp_rec['symbol']} imports {imp_rec['imported']}")
    else:
        print("  NO IMPORT relationships")
    
    # Inspect node properties
    print("\n[6] Function node structure (sample)...")
    result = session.run("""
        MATCH (func:Function)
        WHERE func.file_path CONTAINS 'e2e_test'
        RETURN func.name, func.file_path, keys(func) as properties
        LIMIT 5
    """)
    
    for rec in result:
        print(f"\n  Function: {rec['func.name']}")
        print(f"    file_path: {rec['func.file_path']}")
        print(f"    All properties: {rec['properties']}")

client.close()

print("\n" + "=" * 100)
print("CONCLUSION")
print("=" * 100)
print("""
Check the output above to determine:
1. Are Functions being extracted from our test files?
2. Are CALLS relationships being created?
3. What relationship types exist?
4. Are there IMPORT relationships instead?

This will inform whether the graph-doc-gen parser limitation or
the investigation query is the issue.
""")
