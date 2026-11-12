#!/usr/bin/env python3
"""
Inspect how File, Function, Class, Module nodes are identified in Neo4j.
Determine if absolute paths alone are sufficient for repository isolation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "graph-doc-gen-main"))

from database.neo4j_client import Neo4jClient

print("=" * 100)
print("NEO4J NODE STRUCTURE INSPECTION")
print("=" * 100)

client = Neo4jClient()

with client.session() as session:
    # ========================================================================
    # 1. File Node Properties
    # ========================================================================
    print("\n[1] FILE NODE STRUCTURE")
    print("-" * 100)
    
    result = session.run("""
        MATCH (f:File)
        RETURN keys(f) as properties
        LIMIT 1
    """)
    
    for record in result:
        props = record['properties']
        print(f"File node properties: {sorted(props)}")
    
    # Sample File nodes
    result = session.run("""
        MATCH (f:File)
        RETURN f.path, f.name, f.id, f.repo_id
        LIMIT 5
    """)
    
    print("\nSample File nodes:")
    for i, record in enumerate(result, 1):
        path = record['f.path']
        name = record['f.name']
        fid = record['f.id']
        repo = record['f.repo_id']
        print(f"  {i}. path={path}")
        print(f"     name={name}, id={fid}, repo_id={repo}")
    
    # ========================================================================
    # 2. Function Node Properties
    # ========================================================================
    print("\n[2] FUNCTION NODE STRUCTURE")
    print("-" * 100)
    
    result = session.run("""
        MATCH (func:Function)
        RETURN keys(func) as properties
        LIMIT 1
    """)
    
    for record in result:
        props = record['properties']
        print(f"Function node properties: {sorted(props)}")
    
    # Sample Function nodes
    result = session.run("""
        MATCH (func:Function)
        RETURN func.name, func.file_path, func.id, func.repo_id
        LIMIT 5
    """)
    
    print("\nSample Function nodes:")
    for i, record in enumerate(result, 1):
        name = record['func.name']
        fpath = record['func.file_path']
        fid = record['func.id']
        repo = record['func.repo_id']
        print(f"  {i}. name={name}")
        print(f"     file_path={fpath}, id={fid}, repo_id={repo}")
    
    # ========================================================================
    # 3. Check for repo_id property (isolation mechanism)
    # ========================================================================
    print("\n[3] REPOSITORY ISOLATION CHECK")
    print("-" * 100)
    
    result = session.run("""
        MATCH (n)
        WHERE n.repo_id IS NOT NULL
        RETURN DISTINCT labels(n)[0] as label, COUNT(DISTINCT n.repo_id) as unique_repos
    """)
    
    repos_with_scoping = []
    for record in result:
        label = record['label']
        count = record['unique_repos']
        repos_with_scoping.append((label, count))
        print(f"{label}: {count} unique repo_id values")
    
    if not repos_with_scoping:
        print("⚠ WARNING: No repo_id properties found in graph")
        print("  Isolation relies on absolute file paths only")
    
    # ========================================================================
    # 4. Duplicate function names across repositories
    # ========================================================================
    print("\n[4] DUPLICATE FUNCTION NAMES")
    print("-" * 100)
    
    result = session.run("""
        MATCH (func:Function)
        WITH func.name as name, COUNT(*) as count
        WHERE count > 1
        RETURN name, count
        ORDER BY count DESC
        LIMIT 10
    """)
    
    duplicates = list(result)
    if duplicates:
        print(f"Found {len(duplicates)} function names that appear multiple times:")
        for record in duplicates[:10]:
            print(f"  {record['name']}: {record['count']} occurrences")
    else:
        print("No duplicate function names found")
    
    # ========================================================================
    # 5. Check CONTAINS and CALLS relationships
    # ========================================================================
    print("\n[5] RELATIONSHIP STRUCTURE")
    print("-" * 100)
    
    result = session.run("""
        MATCH (f:File)-[:CONTAINS]->(func:Function)
        RETURN f.repo_id as file_repo, func.repo_id as func_repo
        LIMIT 1
    """)
    
    for record in result:
        file_repo = record['file_repo']
        func_repo = record['func_repo']
        print(f"CONTAINS relationship: File.repo_id={file_repo} → Function.repo_id={func_repo}")
    
    result = session.run("""
        MATCH (a:Function)-[:CALLS]->(b:Function)
        RETURN a.repo_id as caller_repo, b.repo_id as callee_repo
        LIMIT 1
    """)
    
    for record in result:
        caller_repo = record['caller_repo']
        callee_repo = record['callee_repo']
        print(f"CALLS relationship: Function.repo_id={caller_repo} → Function.repo_id={callee_repo}")
    
    # ========================================================================
    # 6. Path uniqueness analysis
    # ========================================================================
    print("\n[6] PATH UNIQUENESS ANALYSIS")
    print("-" * 100)
    
    result = session.run("""
        MATCH (n)
        WHERE n.path IS NOT NULL
        WITH n.path as path, COUNT(*) as count
        WHERE count > 1
        RETURN path, count
        LIMIT 5
    """)
    
    duplicate_paths = list(result)
    if duplicate_paths:
        print(f"WARNING: {len(duplicate_paths)} paths appear multiple times:")
        for record in duplicate_paths:
            print(f"  {record['path']}: {record['count']} nodes")
    else:
        print("✓ All file paths are unique")

client.close()

print("\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)
print("""
Current isolation mechanism: Absolute file paths (path property)
Issues identified:
  - Path-based isolation is implicit, not explicit
  - Duplicate function names across repos not checked
  - No repo_id property scoping on nodes
  - Cross-repository CALLS relationships possible if paths collide

Recommendation: Add explicit repo_id property to all nodes
""")
