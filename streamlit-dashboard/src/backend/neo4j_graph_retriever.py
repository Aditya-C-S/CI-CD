"""
Neo4j Graph Retriever for Phase 2C
Retrieves code graph data from Neo4j and converts it to Cytoscape.js format.
"""

import logging
from typing import Dict, List, Optional, Set
from pathlib import Path
import sys
import os

logger = logging.getLogger(__name__)

# Add graph-doc-gen to path
_graph_doc_gen_path = Path(__file__).resolve().parent.parent.parent.parent / "graph-doc-gen-main" / "database"
if _graph_doc_gen_path.exists() and str(_graph_doc_gen_path) not in sys.path:
    sys.path.insert(0, str(_graph_doc_gen_path))

try:
    from neo4j_client import Neo4jClient
    _neo4j_available = True
except ImportError as e:
    logger.warning(f"Neo4j client not available: {e}")
    _neo4j_available = False
    Neo4jClient = None


class Neo4jGraphRetriever:
    """Retrieves code graph from Neo4j and formats for Cytoscape.js visualization."""
    
    def __init__(self):
        """Initialize Neo4j client."""
        self.client = None
        
        if not _neo4j_available:
            logger.warning("Neo4j client library not available")
            return
        
        try:
            self.client = Neo4jClient()
            logger.info("Neo4j client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j client: {e}", exc_info=True)
            self.client = None
    
    def retrieve_graph(
        self,
        repo_id: str,
        target_sha: str = None,
        changed_files: Dict = None,
        suspicious_files: List[Dict] = None,
        max_nodes: int = 500
    ) -> Optional[Dict]:
        """
        Retrieve code graph from Neo4j and convert to Cytoscape format.
        
        Args:
            repo_id: Repository identity (e.g., "owner/repo")
            target_sha: Target commit SHA for verification (optional)
            changed_files: Dict of changed files from ORC (added, modified, deleted, renamed)
            suspicious_files: List of suspicious files from ORC with centrality scores
            max_nodes: Maximum nodes to retrieve (for visualization clarity)
        
        Returns:
            Dict with 'nodes' and 'edges' for Cytoscape, or None if retrieval fails
        """
        if not self.client:
            logger.error("Neo4j client not initialized")
            return None
        
        try:
            logger.info(f"Retrieving graph for repository: {repo_id}")
            
            # Retrieve all nodes and edges for the repository
            nodes = self._retrieve_nodes(repo_id, max_nodes)
            logger.info(f"Retrieved {len(nodes)} nodes")
            
            if not nodes:
                logger.warning(f"No graph nodes found for repository {repo_id}")
                return None
            
            edges = self._retrieve_edges(repo_id, nodes)
            logger.info(f"Retrieved {len(edges)} edges")
            
            # Build highlight sets from ORC results
            changed_file_set = self._build_changed_files_set(changed_files)
            suspicious_file_set = self._build_suspicious_files_set(suspicious_files)
            logger.info(f"Suspicious files to highlight: {len(suspicious_file_set)}")
            
            # Convert to Cytoscape format
            cytoscape_nodes = self._convert_nodes_to_cytoscape(
                nodes,
                changed_files=changed_file_set,
                suspicious_files=suspicious_file_set
            )
            cytoscape_edges = self._convert_edges_to_cytoscape(edges)
            
            metadata = {
                'repo_id': repo_id,
                'total_nodes': len(cytoscape_nodes),
                'total_edges': len(cytoscape_edges),
                'changed_files_count': len(changed_file_set),
                'suspicious_files_count': len(suspicious_file_set)
            }
            logger.info(f"Graph conversion complete: {metadata}")
            
            return {
                'nodes': cytoscape_nodes,
                'edges': cytoscape_edges,
                'metadata': metadata
            }
        
        except Exception as e:
            logger.error(f"Failed to retrieve graph from Neo4j: {e}", exc_info=True)
            return None
    
    def _retrieve_nodes(self, repo_id: str, max_nodes: int = 500) -> List[Dict]:
        """
        Retrieve all nodes from Neo4j for the given repository.
        
        Returns list of node dicts with properties.
        """
        if not self.client:
            return []
        
        try:
            with self.client.session() as session:
                query = """
                MATCH (n {repo_id: $repo_id})
                WHERE n:File OR n:Class OR n:Function OR n:Module
                RETURN 
                    id(n) AS node_id,
                    labels(n) AS labels,
                    n.id AS id,
                    n.name AS name,
                    n.path AS path,
                    n.file_path AS file_path,
                    n.rel_path AS rel_path,
                    properties(n) AS properties
                LIMIT $limit
                """
                
                logger.info(f"Executing node query for repo: {repo_id}, limit: {max_nodes}")
                result = session.run(query, repo_id=repo_id, limit=max_nodes)
                nodes = []
                
                for record in result:
                    node = {
                        'node_id': record['node_id'],
                        'labels': record['labels'] or [],
                        'id': record['id'],
                        'name': record['name'],
                        'path': record['path'],
                        'file_path': record['file_path'],
                        'rel_path': record['rel_path'],
                        'properties': record['properties'] or {}
                    }
                    nodes.append(node)
                
                logger.info(f"Retrieved {len(nodes)} nodes from Neo4j for {repo_id}")
                return nodes
        
        except Exception as e:
            logger.error(f"Error retrieving nodes from Neo4j: {e}", exc_info=True)
            return []
    
    def _retrieve_edges(self, repo_id: str, nodes: List[Dict]) -> List[Dict]:
        """
        Retrieve all relationships between nodes.
        
        Returns list of edge dicts with source, target, and type.
        """
        if not self.client or not nodes:
            return []
        
        try:
            # Extract node IDs for edge query
            node_ids = [n['node_id'] for n in nodes]
            
            with self.client.session() as session:
                query = """
                MATCH (a {repo_id: $repo_id})-[r]->(b {repo_id: $repo_id})
                WHERE id(a) IN $node_ids AND id(b) IN $node_ids
                RETURN 
                    id(a) AS from_id,
                    id(b) AS to_id,
                    type(r) AS rel_type,
                    properties(r) AS rel_properties
                """
                
                result = session.run(query, repo_id=repo_id, node_ids=node_ids)
                edges = []
                
                for record in result:
                    edge = {
                        'from_id': record['from_id'],
                        'to_id': record['to_id'],
                        'type': record['rel_type'],
                        'properties': record['rel_properties'] or {}
                    }
                    edges.append(edge)
                
                logger.info(f"Retrieved {len(edges)} edges from Neo4j for {repo_id}")
                return edges
        
        except Exception as e:
            logger.error(f"Error retrieving edges from Neo4j: {e}")
            return []
    
    def _build_changed_files_set(self, changed_files: Dict) -> Set[str]:
        """Build set of changed file names/paths for highlighting."""
        changed_set = set()
        
        if not changed_files:
            return changed_set
        
        # Extract file names from changed_files dict
        for category in ['added', 'modified', 'deleted', 'renamed']:
            count = changed_files.get(category, 0)
            # Note: changed_files only contains counts, not actual file names
            # We'll need to match by examining Neo4j node names instead
        
        return changed_set
    
    def _build_suspicious_files_set(self, suspicious_files: List[Dict]) -> Set[str]:
        """Build set of suspicious file paths for highlighting."""
        suspicious_set = set()
        
        if not suspicious_files:
            return suspicious_set
        
        for file_info in suspicious_files:
            file_path = file_info.get('path', '')
            if file_path:
                suspicious_set.add(file_path)
                # Also add just the filename in case paths don't match exactly
                suspicious_set.add(Path(file_path).name)
        
        return suspicious_set
    
    def _convert_nodes_to_cytoscape(
        self,
        nodes: List[Dict],
        changed_files: Set[str] = None,
        suspicious_files: Set[str] = None
    ) -> List[Dict]:
        """Convert Neo4j nodes to Cytoscape.js format."""
        if changed_files is None:
            changed_files = set()
        if suspicious_files is None:
            suspicious_files = set()
        
        cytoscape_nodes = []
        
        for node in nodes:
            # Determine node label (readable name)
            label = (
                node.get('name') or
                node.get('rel_path') or
                node.get('file_path') or
                node.get('path') or
                node.get('id') or
                'Unknown'
            )
            
            # Determine node type for styling
            node_type = node.get('labels', [None])[0] if node.get('labels') else 'Unknown'
            
            # Check if file is suspicious or changed
            is_suspicious = label in suspicious_files or node.get('rel_path', '') in suspicious_files
            is_changed = label in changed_files
            
            # Determine node color/class
            if is_suspicious:
                node_class = 'suspicious'
                color = '#ff6b6b'  # Red for suspicious
            elif is_changed:
                node_class = 'changed'
                color = '#ffa94d'  # Orange for changed
            else:
                node_class = 'default'
                color = '#4c6ef5'  # Blue for default
            
            cytoscape_node = {
                'data': {
                    'id': f"node_{node['node_id']}",
                    'label': label,
                    'type': node_type,
                    'path': node.get('rel_path') or node.get('path'),
                    'properties': node.get('properties', {})
                },
                'classes': node_class,
                'style': {
                    'background-color': color
                }
            }
            
            cytoscape_nodes.append(cytoscape_node)
        
        return cytoscape_nodes
    
    def _convert_edges_to_cytoscape(self, edges: List[Dict]) -> List[Dict]:
        """Convert Neo4j relationships to Cytoscape.js format."""
        cytoscape_edges = []
        
        for edge in edges:
            cytoscape_edge = {
                'data': {
                    'source': f"node_{edge['from_id']}",
                    'target': f"node_{edge['to_id']}",
                    'label': edge.get('type', 'UNKNOWN'),
                    'type': edge.get('type', 'UNKNOWN'),
                    'properties': edge.get('properties', {})
                },
                'classes': edge.get('type', 'default').lower()
            }
            
            cytoscape_edges.append(cytoscape_edge)
        
        return cytoscape_edges
    
    def close(self):
        """Close Neo4j connection."""
        if self.client:
            try:
                self.client.close()
            except Exception as e:
                logger.error(f"Error closing Neo4j client: {e}")
