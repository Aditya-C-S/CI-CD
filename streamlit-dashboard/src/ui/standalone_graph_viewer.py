"""
Standalone Graph Viewer for Phase 2C
Uses the professional graph-explorer from logpipeline/frontend/ for viewing code graphs.
This provides a much better visualization with:
- Blast radius analysis (changed file + affected dependencies)
- Full architecture view
- Interactive search and filtering
- Multiple layout algorithms
- Professional UI/UX
"""

import json
import logging
import tempfile
from pathlib import Path
from typing import Dict, Optional
import webbrowser
import shutil

logger = logging.getLogger(__name__)


def generate_standalone_graph_html(graph_data: Dict, repo_id: str, target_sha: str) -> str:
    """
    Generate a standalone HTML file for graph visualization.
    
    Args:
        graph_data: Dict with 'nodes' and 'edges' in Cytoscape format
        repo_id: Repository identifier
        target_sha: Target commit SHA
    
    Returns:
        Path to generated HTML file
    """
    if not graph_data or not graph_data.get('nodes'):
        logger.warning("No graph data to generate HTML")
        return None
    
    nodes = graph_data.get('nodes', [])
    edges = graph_data.get('edges', [])
    metadata = graph_data.get('metadata', {})
    
    # Convert to JSON strings
    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)
    
    sha_display = target_sha[:7] if len(target_sha) >= 7 else target_sha
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Code Graph - {repo_id}@{sha_display}</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Inter', 'Segoe UI', Roboto, -apple-system, BlinkMacSystemFont, sans-serif;
                background: #0f172a;
                color: #f1f5f9;
                overflow: hidden;
                height: 100vh;
            }}
            
            #header {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border-bottom: 1px solid #334155;
                padding: 12px 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                height: 60px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
                z-index: 100;
            }}
            
            #title {{
                font-size: 16px;
                font-weight: 600;
                color: #f1f5f9;
            }}
            
            #subtitle {{
                font-size: 12px;
                color: #94a3b8;
                margin-top: 2px;
            }}
            
            #controls {{
                display: flex;
                gap: 10px;
                align-items: center;
            }}
            
            .control-group {{
                display: flex;
                gap: 8px;
                align-items: center;
                padding: 0 12px;
                border-right: 1px solid #334155;
            }}
            
            .control-group:last-child {{
                border-right: none;
            }}
            
            button {{
                background: #1e293b;
                color: #f1f5f9;
                border: 1px solid #475569;
                padding: 6px 12px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
                font-weight: 500;
                transition: all 0.2s ease;
            }}
            
            button:hover {{
                background: #334155;
                border-color: #64748b;
            }}
            
            button.active {{
                background: #3b82f6;
                border-color: #60a5fa;
            }}
            
            select {{
                background: #1e293b;
                color: #f1f5f9;
                border: 1px solid #475569;
                padding: 4px 8px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
            }}
            
            #container {{
                display: flex;
                height: calc(100vh - 60px);
                gap: 0;
            }}
            
            #cy {{
                flex: 1;
                background: #0f172a;
                border-right: 1px solid #334155;
                position: relative;
            }}
            
            #sidebar {{
                width: 300px;
                background: #1e293b;
                border-left: 1px solid #334155;
                overflow-y: auto;
                padding: 16px;
                display: flex;
                flex-direction: column;
                gap: 16px;
            }}
            
            .sidebar-section {{
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 12px;
            }}
            
            .section-title {{
                font-size: 13px;
                font-weight: 600;
                color: #f1f5f9;
                margin-bottom: 8px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            
            .stat {{
                display: flex;
                justify-content: space-between;
                padding: 6px 0;
                border-bottom: 1px solid #334155;
                font-size: 12px;
            }}
            
            .stat:last-child {{
                border-bottom: none;
            }}
            
            .stat-label {{
                color: #94a3b8;
            }}
            
            .stat-value {{
                color: #38bdf8;
                font-weight: 600;
            }}
            
            .legend-item {{
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 8px 0;
                font-size: 12px;
                color: #e2e8f0;
            }}
            
            .legend-color {{
                width: 20px;
                height: 20px;
                border-radius: 3px;
                border: 1px solid #475569;
                flex-shrink: 0;
            }}
            
            .node-details {{
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 10px;
                font-size: 11px;
                word-break: break-all;
                max-height: 200px;
                overflow-y: auto;
            }}
            
            .node-details-label {{
                font-weight: 600;
                color: #38bdf8;
                margin-top: 6px;
                margin-bottom: 2px;
            }}
            
            .node-details-value {{
                color: #cbd5e1;
                word-break: break-word;
            }}
            
            #loading {{
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                font-size: 14px;
                color: #94a3b8;
                background: rgba(15, 23, 42, 0.95);
                padding: 30px 50px;
                border-radius: 8px;
                z-index: 1000;
                text-align: center;
            }}
            
            .spinner {{
                width: 24px;
                height: 24px;
                border: 2px solid #334155;
                border-top-color: #38bdf8;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
                margin: 0 auto 10px;
            }}
            
            @keyframes spin {{
                to {{ transform: rotate(360deg); }}
            }}
            
            #tip {{
                position: absolute;
                bottom: 10px;
                left: 10px;
                font-size: 11px;
                color: #64748b;
                background: rgba(30, 41, 59, 0.8);
                padding: 6px 10px;
                border-radius: 4px;
                z-index: 10;
            }}
            
            /* Scrollbar styling */
            ::-webkit-scrollbar {{
                width: 8px;
                height: 8px;
            }}
            
            ::-webkit-scrollbar-track {{
                background: #0f172a;
            }}
            
            ::-webkit-scrollbar-thumb {{
                background: #334155;
                border-radius: 4px;
            }}
            
            ::-webkit-scrollbar-thumb:hover {{
                background: #475569;
            }}
        </style>
    </head>
    <body>
        <div id="header">
            <div>
                <div id="title">📊 Code Graph Viewer</div>
                <div id="subtitle">{repo_id} @ {sha_display}</div>
            </div>
            <div id="controls">
                <div class="control-group">
                    <button id="btn-fit" title="Fit graph to view">🔍 Fit</button>
                    <button id="btn-center" title="Center graph">⊕ Center</button>
                </div>
                <div class="control-group">
                    <label for="layout-select" style="font-size: 12px; color: #94a3b8;">Layout:</label>
                    <select id="layout-select">
                        <option value="breadthfirst">Hierarchical</option>
                        <option value="grid">Grid</option>
                        <option value="circle">Circle</option>
                        <option value="random">Random</option>
                    </select>
                </div>
                <div class="control-group">
                    <button id="btn-legend" title="Toggle legend" class="active">📖 Legend</button>
                    <button id="btn-fullscreen" title="Toggle fullscreen">⛶ Fullscreen</button>
                </div>
            </div>
        </div>
        
        <div id="container">
            <div id="cy"></div>
            
            <div id="sidebar">
                <div class="sidebar-section">
                    <div class="section-title">📊 Statistics</div>
                    <div class="stat">
                        <span class="stat-label">Total Nodes:</span>
                        <span class="stat-value">{metadata.get('total_nodes', len(nodes))}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Relationships:</span>
                        <span class="stat-value">{metadata.get('total_edges', len(edges))}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Suspicious:</span>
                        <span class="stat-value">{metadata.get('suspicious_files_count', 0)}</span>
                    </div>
                </div>
                
                <div class="sidebar-section">
                    <div class="section-title">🎨 Legend</div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #1e293b; border-color: #38bdf8;"></div>
                        <span>File</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #0f172a; border-color: #818cf8;"></div>
                        <span>Function</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #0f291e; border-color: #34d399;"></div>
                        <span>Class</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #7f1d1d; border-color: #ff6b6b;"></div>
                        <span>Suspicious</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #78350f; border-color: #fda34b;"></div>
                        <span>Changed</span>
                    </div>
                </div>
                
                <div class="sidebar-section">
                    <div class="section-title">🔗 Edges</div>
                    <div class="legend-item">
                        <div style="width: 20px; height: 2px; background: #818cf8;"></div>
                        <span>CALLS</span>
                    </div>
                    <div class="legend-item">
                        <div style="width: 20px; height: 2px; background: #64748b; border-top: 1px dashed;"></div>
                        <span>CONTAINS</span>
                    </div>
                    <div class="legend-item">
                        <div style="width: 20px; height: 2px; background: #34d399; border-top: 1px dotted;"></div>
                        <span>IMPORTS</span>
                    </div>
                </div>
                
                <div class="sidebar-section" id="selected-node-panel" style="display: none;">
                    <div class="section-title">✋ Selected Node</div>
                    <div id="node-details-content" class="node-details"></div>
                </div>
                
                <div class="sidebar-section" id="search-panel">
                    <div class="section-title">🔍 Search Nodes</div>
                    <input 
                        type="text" 
                        id="search-input" 
                        placeholder="Type to search..." 
                        style="width: 100%; padding: 6px 8px; background: #0f172a; border: 1px solid #334155; color: #f1f5f9; border-radius: 4px; font-size: 12px;"
                    />
                </div>
            </div>
        </div>
        
        <div id="loading">
            <div class="spinner"></div>
            <div>Loading graph...</div>
        </div>
        
        <div id="tip">
            💡 Drag nodes • Scroll to zoom • Double-click background to deselect
        </div>
        
        <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js"></script>
        <script>
        (function() {{
            console.log('Initializing Standalone Graph Viewer...');
            
            let cy = null;
            let currentLayout = null;
            
            setTimeout(function() {{
                if (typeof cytoscape === 'undefined') {{
                    document.getElementById('cy').innerHTML = '<p style="text-align:center;padding:20px;color:#ff6b6b;">Cytoscape library failed to load</p>';
                    document.getElementById('loading').style.display = 'none';
                    return;
                }}
                
                try {{
                    const nodes = {nodes_json};
                    const edges = {edges_json};
                    
                    console.log('Nodes: ' + nodes.length + ', Edges: ' + edges.length);
                    
                    if (nodes.length === 0) {{
                        document.getElementById('cy').innerHTML = '<p style="text-align:center;padding:20px;color:#94a3b8;">No nodes to display</p>';
                        document.getElementById('loading').style.display = 'none';
                        return;
                    }}
                    
                    // Neo4j Explorer Style
                    const cyStyle = [
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
                    
                    // Create Cytoscape instance
                    cy = cytoscape({{
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
                        motionBlur: false,
                        maxZoom: 3,
                        minZoom: 0.1
                    }});
                    
                    // Store layout reference
                    currentLayout = cy.layout({{ name: 'breadthfirst' }});
                    
                    // Fit and hide loading
                    setTimeout(function() {{
                        try {{
                            cy.fit(cy.elements(), 30);
                        }} catch(e) {{
                            console.warn('Fit error:', e);
                        }}
                        document.getElementById('loading').style.display = 'none';
                        console.log('✓ Graph rendered successfully');
                    }}, 300);
                    
                    // Node selection
                    cy.on('tap', 'node', function(evt) {{
                        const node = evt.target;
                        const nodeData = node.data();
                        
                        // Show selected node panel
                        const panel = document.getElementById('selected-node-panel');
                        const content = document.getElementById('node-details-content');
                        
                        content.innerHTML = `
                            <div class="node-details-label">Label:</div>
                            <div class="node-details-value">${{nodeData.label}}</div>
                            
                            <div class="node-details-label">Type:</div>
                            <div class="node-details-value">${{nodeData.type}}</div>
                            
                            ${{nodeData.path ? `
                                <div class="node-details-label">Path:</div>
                                <div class="node-details-value">${{nodeData.path}}</div>
                            ` : ''}}
                            
                            <div class="node-details-label">Degree:</div>
                            <div class="node-details-value">In: ${{node.indegree()}}, Out: ${{node.outdegree()}}</div>
                        `;
                        
                        panel.style.display = 'block';
                    }});
                    
                    // Deselect on background double-click
                    cy.on('dblclick', function(evt) {{
                        if (evt.target === cy) {{
                            cy.elements().unselect();
                            document.getElementById('selected-node-panel').style.display = 'none';
                        }}
                    }});
                    
                    // Control buttons
                    document.getElementById('btn-fit').addEventListener('click', function() {{
                        cy.fit(cy.elements(), 30);
                    }});
                    
                    document.getElementById('btn-center').addEventListener('click', function() {{
                        cy.center();
                    }});
                    
                    document.getElementById('btn-fullscreen').addEventListener('click', function() {{
                        const elem = document.getElementById('cy');
                        if (!document.fullscreenElement) {{
                            elem.requestFullscreen().catch(console.error);
                        }} else {{
                            document.exitFullscreen();
                        }}
                    }});
                    
                    // Layout selector
                    document.getElementById('layout-select').addEventListener('change', function(e) {{
                        const layoutName = e.target.value;
                        
                        if (currentLayout) {{
                            currentLayout.stop();
                        }}
                        
                        currentLayout = cy.layout({{ name: layoutName, animate: true, animationDuration: 500 }});
                        currentLayout.run();
                    }});
                    
                    // Search
                    document.getElementById('search-input').addEventListener('input', function(e) {{
                        const query = e.target.value.toLowerCase();
                        
                        cy.elements('node').forEach(function(node) {{
                            const label = node.data('label').toLowerCase();
                            if (query === '' || label.includes(query)) {{
                                node.removeClass('hidden');
                            }} else {{
                                node.addClass('hidden');
                            }}
                        }});
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
    
    return html_content


def save_and_open_graph(graph_data: Dict, repo_id: str, target_sha: str) -> bool:
    """
    Generate graph HTML, save to temp file, and open in browser.
    
    Args:
        graph_data: Graph data dict
        repo_id: Repository ID
        target_sha: Target commit SHA
    
    Returns:
        True if successful, False otherwise
    """
    try:
        html_content = generate_standalone_graph_html(graph_data, repo_id, target_sha)
        
        if not html_content:
            logger.error("Failed to generate HTML")
            return False
        
        # Save to temp file
        temp_dir = Path(tempfile.gettempdir()) / "orc_graph_viewer"
        temp_dir.mkdir(exist_ok=True)
        
        sha_short = target_sha[:7] if len(target_sha) >= 7 else target_sha
        html_file = temp_dir / f"graph_{repo_id.replace('/', '_')}_{sha_short}.html"
        
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Graph HTML saved to: {html_file}")
        
        # Open in browser
        file_url = html_file.as_uri()
        webbrowser.open(file_url)
        
        logger.info(f"Opened graph in browser: {file_url}")
        return True
    
    except Exception as e:
        logger.error(f"Error saving/opening graph: {e}", exc_info=True)
        return False
