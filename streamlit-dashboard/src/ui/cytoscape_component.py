"""
Cytoscape.js Visualization Component for Phase 2C
Renders interactive code graphs inside Streamlit using Cytoscape.js with Neo4j Explorer styling.
"""

import streamlit as st
import json
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def render_cytoscape_graph(graph_data: Dict, height: int = 600):
    """
    Render an interactive Cytoscape.js graph inside Streamlit.
    Uses Cytoscape.js from CDN with styling from Neo4j explorer.
    
    Args:
        graph_data: Dict with 'nodes' and 'edges' in Cytoscape format
        height: Height of graph container in pixels
    """
    if not graph_data or not graph_data.get('nodes'):
        st.warning("No graph data to display")
        return
    
    try:
        nodes = graph_data.get('nodes', [])
        edges = graph_data.get('edges', [])
        metadata = graph_data.get('metadata', {})
        
        if len(nodes) == 0:
            st.warning("Graph has no nodes to display")
            return
        
        # Display metadata
        st.markdown("**Graph Statistics:**")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Nodes", metadata.get('total_nodes', len(nodes)))
        with col2:
            st.metric("Relationships", metadata.get('total_edges', len(edges)))
        with col3:
            st.metric("Suspicious Files", metadata.get('suspicious_files_count', 0))
        
        st.divider()
        
        # Render graph using Cytoscape HTML
        html_content = _generate_cytoscape_html(nodes, edges, height)
        
        if html_content:
            st.components.v1.html(html_content, height=height + 100, scrolling=True)
        else:
            st.error("Failed to generate Cytoscape HTML")
            return
        
        st.divider()
        
        # Display legend
        _render_graph_legend()
        
        # Display node/edge details on selection
        _render_graph_info_panel(nodes, edges)
    
    except Exception as e:
        logger.error(f"Error rendering Cytoscape graph: {e}", exc_info=True)
        st.error(f"Failed to render graph: {str(e)}")


def _generate_cytoscape_html(nodes: list, edges: list, height: int = 600) -> str:
    """
    Generate HTML/JavaScript code for Cytoscape.js visualization.
    Uses Neo4j Explorer styling (breadthfirst layout, proper node/edge colors).
    
    Args:
        nodes: List of nodes in Cytoscape format
        edges: List of edges in Cytoscape format
        height: Height of graph container
    
    Returns:
        HTML string containing complete Cytoscape visualization
    """
    
    if not nodes:
        return ""
    
    # Convert nodes and edges to JSON for embedding
    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <style>
            body {{
                margin: 0;
                padding: 0;
                font-family: 'Inter', 'Segoe UI', Roboto, sans-serif;
                background: #0f172a;
            }}
            #cy {{
                width: 100%;
                height: {height}px;
                border: 1px solid #334155;
                border-radius: 8px;
                background: #0f172a;
            }}
            #loading {{
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                font-size: 14px;
                color: #94a3b8;
                background: rgba(15, 23, 42, 0.9);
                padding: 20px 40px;
                border-radius: 8px;
                z-index: 100;
            }}
            .spinner {{
                width: 20px;
                height: 20px;
                border: 2px solid #334155;
                border-top-color: #38bdf8;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
                margin: 0 auto 10px;
            }}
            @keyframes spin {{
                to {{ transform: rotate(360deg); }}
            }}
        </style>
    </head>
    <body>
        <div id="cy"></div>
        <div id="loading">
            <div class="spinner"></div>
            <div>Loading graph...</div>
        </div>
        
        <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js"></script>
        <script>
        (function() {{
            console.log('Initializing Cytoscape with Neo4j Explorer Style...');
            
            // Wait a bit for Cytoscape to load
            setTimeout(function() {{
                if (typeof cytoscape === 'undefined') {{
                    console.error('Cytoscape not loaded');
                    document.getElementById('cy').innerHTML = '<p style="text-align:center;padding:20px;color:#ff6b6b;">Cytoscape library failed to load</p>';
                    return;
                }}
                
                var nodes = {nodes_json};
                var edges = {edges_json};
                
                console.log('Nodes: ' + nodes.length + ', Edges: ' + edges.length);
                
                if (nodes.length === 0) {{
                    document.getElementById('cy').innerHTML = '<p style="text-align:center;padding:20px;color:#94a3b8;">No nodes to display</p>';
                    return;
                }}
                
                try {{
                    // Neo4j Explorer Style Configuration
                    var cyStyle = [
                        {{
                            selector: 'node',
                            style: {{
                                'label': 'data(label)',
                                'color': '#f1f5f9',
                                'font-family': 'Inter, Segoe UI, sans-serif',
                                'font-size': '11px',
                                'font-weight': '500',
                                'text-valign': 'center',
                                'text-halign': 'center',
                                'text-outline-color': '#06090e',
                                'text-outline-width': '1px',
                                'background-color': '#1e293b',
                                'border-color': '#38bdf8',
                                'border-width': '2px',
                                'width': '60px',
                                'height': '60px'
                            }}
                        }},
                        {{
                            selector: 'node[type="File"]',
                            style: {{
                                'shape': 'roundrectangle',
                                'background-color': '#1e293b',
                                'border-color': '#38bdf8',
                                'width': '80px',
                                'height': '35px'
                            }}
                        }},
                        {{
                            selector: 'node[type="Function"]',
                            style: {{
                                'shape': 'ellipse',
                                'background-color': '#0f172a',
                                'border-color': '#818cf8',
                                'width': '45px',
                                'height': '45px'
                            }}
                        }},
                        {{
                            selector: 'node[type="Class"]',
                            style: {{
                                'shape': 'diamond',
                                'background-color': '#0f291e',
                                'border-color': '#34d399',
                                'width': '50px',
                                'height': '50px'
                            }}
                        }},
                        {{
                            selector: 'node.suspicious',
                            style: {{
                                'background-color': '#7f1d1d',
                                'border-color': '#ff6b6b',
                                'border-width': '3px'
                            }}
                        }},
                        {{
                            selector: 'node.changed',
                            style: {{
                                'background-color': '#78350f',
                                'border-color': '#fda34b',
                                'border-width': '2px'
                            }}
                        }},
                        {{
                            selector: 'node:selected',
                            style: {{
                                'background-color': '#1e40af',
                                'border-color': '#60a5fa',
                                'border-width': '3px'
                            }}
                        }},
                        {{
                            selector: 'edge',
                            style: {{
                                'line-color': '#475569',
                                'target-arrow-color': '#475569',
                                'target-arrow-shape': 'triangle',
                                'width': '1.5px',
                                'label': 'data(label)',
                                'font-size': '9px',
                                'color': '#94a3b8',
                                'text-background-color': '#0f172a',
                                'text-background-padding': '2px',
                                'text-background-opacity': '0.9',
                                'curve-style': 'bezier'
                            }}
                        }},
                        {{
                            selector: 'edge.calls',
                            style: {{
                                'line-color': '#818cf8',
                                'target-arrow-color': '#818cf8',
                                'line-style': 'solid'
                            }}
                        }},
                        {{
                            selector: 'edge.contains',
                            style: {{
                                'line-color': '#64748b',
                                'target-arrow-color': '#64748b',
                                'line-style': 'dashed'
                            }}
                        }},
                        {{
                            selector: 'edge.imports',
                            style: {{
                                'line-color': '#34d399',
                                'target-arrow-color': '#34d399',
                                'line-style': 'dotted'
                            }}
                        }},
                        {{
                            selector: 'edge:selected',
                            style: {{
                                'line-color': '#60a5fa',
                                'target-arrow-color': '#60a5fa',
                                'width': '2.5px'
                            }}
                        }}
                    ];
                    
                    var cy = cytoscape({{
                        container: document.getElementById('cy'),
                        elements: nodes.concat(edges),
                        style: cyStyle,
                        layout: {{
                            name: 'breadthfirst',
                            directed: true,
                            animate: true,
                            animationDuration: 500,
                            animationEasing: 'ease-in-out',
                            spacingFactor: 1.5
                        }},
                        wheelSensitivity: 0.1,
                        motionBlur: false
                    }});
                    
                    // Fit viewport and hide loading
                    setTimeout(function() {{
                        try {{
                            cy.fit(cy.elements(), 30);
                        }} catch(e) {{
                            console.warn('Fit error:', e);
                        }}
                        document.getElementById('loading').style.display = 'none';
                        console.log('✓ Graph rendered successfully');
                    }}, 300);
                    
                    // Interactivity
                    cy.on('tap', 'node', function(evt) {{
                        console.log('Selected node:', evt.target.data().label);
                    }});
                    
                    cy.on('tap', 'edge', function(evt) {{
                        console.log('Selected edge:', evt.target.data().type);
                    }});
                    
                }} catch (err) {{
                    console.error('Cytoscape error:', err);
                    document.getElementById('cy').innerHTML = '<p style="text-align:center;padding:20px;color:#ff6b6b;">Error: ' + err.message + '</p>';
                    document.getElementById('loading').style.display = 'none';
                }}
            }}, 100);
        }})();
        </script>
    </body>
    </html>
    """
    
    return html


def _render_graph_legend():
    """Render legend explaining node and edge colors."""
    with st.expander("📖 Graph Legend", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Node Types:**")
            st.markdown("- 📄 **File** — Rounded rectangle (cyan border)")
            st.markdown("- 🔵 **Function** — Ellipse (purple border)")
            st.markdown("- 💎 **Class** — Diamond (green border)")
        
        with col2:
            st.markdown("**Relationship Types:**")
            st.markdown("- ─→ **CALLS** — Function calls (solid purple)")
            st.markdown("- ┈→ **CONTAINS** — Structural (dashed gray)")
            st.markdown("- ⋯→ **IMPORTS** — External module (dotted green)")
        
        st.markdown("**Node Highlighting:**")
        st.markdown("- 🔴 **Red border** — Suspicious file (high centrality)")
        st.markdown("- 🟠 **Orange border** — Changed in commit")


def _render_graph_info_panel(nodes: list, edges: list):
    """Render panel showing details of selected nodes and edges."""
    
    with st.expander("ℹ️ Node & Edge Details", expanded=False):
        st.markdown("**Node Information:**")
        
        col1, col2 = st.columns(2)
        with col1:
            node_list = [n.get('data', {}).get('label', 'Unknown') for n in nodes[:20]]
            if node_list:
                selected_node_label = st.selectbox(
                    "Select a node to inspect:",
                    node_list,
                    key="node_selector"
                )
                
                # Find and display selected node details
                for node in nodes:
                    if node.get('data', {}).get('label') == selected_node_label:
                        node_data = node.get('data', {})
                        st.markdown(f"**Label:** {node_data.get('label', 'N/A')}")
                        st.markdown(f"**Type:** {node_data.get('type', 'N/A')}")
                        if node_data.get('path'):
                            st.markdown(f"**Path:** `{node_data.get('path')}`")
                        if node_data.get('properties'):
                            with st.expander("Properties"):
                                st.json(node_data.get('properties'))
                        break
            else:
                st.info("No nodes to inspect")
        
        with col2:
            st.markdown("**Edge Information:**")
            
            edge_labels = [e.get('data', {}).get('label', 'Unknown') for e in edges[:20]]
            if edge_labels:
                unique_labels = list(set(edge_labels))
                selected_edge_label = st.selectbox(
                    "Select a relationship type:",
                    unique_labels,
                    key="edge_selector"
                )
                
                # Count edges of this type
                edge_count = sum(1 for e in edges if e.get('data', {}).get('label') == selected_edge_label)
                st.markdown(f"**Type:** {selected_edge_label}")
                st.markdown(f"**Count:** {edge_count} relationships")
            else:
                st.info("No edges in graph")
