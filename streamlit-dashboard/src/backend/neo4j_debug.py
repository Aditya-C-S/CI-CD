"""
Debug utility for Neo4j connection testing.
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add graph-doc-gen to path
_graph_doc_gen_path = Path(__file__).resolve().parent.parent.parent.parent / "graph-doc-gen-main" / "database"
if _graph_doc_gen_path.exists() and str(_graph_doc_gen_path) not in sys.path:
    sys.path.insert(0, str(_graph_doc_gen_path))


def test_neo4j_connection():
    """Test Neo4j connection and return connection status."""
    try:
        from neo4j_client import Neo4jClient
        
        print("Attempting to connect to Neo4j...")
        client = Neo4jClient()
        
        with client.session() as session:
            # Simple test query
            result = session.run("RETURN 1 as test")
            record = result.single()
            
            if record:
                print("✅ Neo4j connection successful!")
                return True
            else:
                print("❌ Neo4j connection returned no response")
                return False
    
    except Exception as e:
        print(f"❌ Neo4j connection failed: {e}")
        return False


def count_repositories_in_neo4j():
    """Count unique repositories in Neo4j."""
    try:
        from neo4j_client import Neo4jClient
        
        client = Neo4jClient()
        
        with client.session() as session:
            result = session.run(
                "MATCH (n) RETURN DISTINCT n.repo_id as repo_id, count(*) as count LIMIT 10"
            )
            
            print("\nRepositories in Neo4j:")
            for record in result:
                repo = record.get('repo_id')
                count = record.get('count')
                print(f"  - {repo}: {count} nodes")
            
            return True
    
    except Exception as e:
        print(f"Error querying repositories: {e}")
        return False


def test_graph_retrieval(repo_id: str):
    """Test graph retrieval for a specific repository."""
    try:
        from neo4j_client import Neo4jClient
        
        print(f"\nRetrieving graph for {repo_id}...")
        client = Neo4jClient()
        
        with client.session() as session:
            # Count nodes
            node_result = session.run(
                "MATCH (n {repo_id: $repo_id}) RETURN count(n) as count",
                repo_id=repo_id
            )
            node_count = node_result.single()['count']
            print(f"  Nodes: {node_count}")
            
            # Count edges
            edge_result = session.run(
                "MATCH (a {repo_id: $repo_id})-[r]-(b {repo_id: $repo_id}) RETURN count(r) as count",
                repo_id=repo_id
            )
            edge_count = edge_result.single()['count']
            print(f"  Edges: {edge_count}")
            
            if node_count > 0 and edge_count > 0:
                print(f"✅ Graph data found for {repo_id}")
                return True
            else:
                print(f"⚠️ No graph data found for {repo_id}")
                return False
    
    except Exception as e:
        print(f"Error retrieving graph: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("Neo4j Connection Debug")
    print("=" * 50)
    
    # Test connection
    if test_neo4j_connection():
        # List repositories
        count_repositories_in_neo4j()
        
        # Test specific repo if provided
        repo = input("\nEnter repository ID to test (or press Enter to skip): ").strip()
        if repo:
            test_graph_retrieval(repo)
    
    print("\n" + "=" * 50)
