"""
Graph Explorer Integration for Phase 2C
Integrates the professional graph-explorer from logpipeline/frontend/
into Streamlit dashboard for superior graph visualization.

Features:
- Blast radius visualization (changed files + affected dependencies)
- Full architecture view with blast overlay
- Search and filtering
- Multiple layouts (Hierarchical, Force-Directed, Concentric, Circle)
- Professional UI with inspector panel
- Responsive design
"""

import json
import logging
import tempfile
from pathlib import Path
from typing import Dict, Optional
import webbrowser
import shutil
import os

logger = logging.getLogger(__name__)


def get_graph_explorer_path() -> Optional[Path]:
    """Get path to graph-explorer files."""
    # Try to find graph-explorer in logpipeline/frontend
    paths_to_try = [
        Path(__file__).resolve().parent.parent.parent.parent / "logpipeline" / "frontend",
        Path(__file__).resolve().parent.parent.parent.parent.parent / "frontend",
        Path.home() / "Desktop" / "finaltest" / "logpipeline" / "frontend",
    ]
    
    for path in paths_to_try:
        if path.exists() and (path / "graph-explorer.html").exists():
            logger.info(f"Found graph-explorer at: {path}")
            return path
    
    logger.warning(f"graph-explorer not found. Tried: {paths_to_try}")
    return None


def generate_graph_explorer_html(
    graph_data: Dict,
    repo_id: str,
    target_sha: str,
    suspicious_files: list = None,
    changed_files: Dict = None
) -> Optional[str]:
    """
    Generate an HTML file using the professional graph-explorer.
    
    Args:
        graph_data: Dict with 'nodes' and 'edges' in Cytoscape format
        repo_id: Repository ID
        target_sha: Target commit SHA
        suspicious_files: List of suspicious files (for highlighting)
        changed_files: Changed files info
    
    Returns:
        HTML string with embedded graph data and explorer UI
    """
    
    if not graph_data or not graph_data.get('nodes'):
        logger.warning("No graph data to generate HTML")
        return None
    
    nodes = graph_data.get('nodes', [])
    edges = graph_data.get('edges', [])
    metadata = graph_data.get('metadata', {})
    
    if not nodes:
        return None
    
    # Convert data to JSON
    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)
    
    sha_display = target_sha[:7] if len(target_sha) >= 7 else target_sha
    
    # Identify changed and suspicious files for highlighting
    suspicious_set = set()
    if suspicious_files:
        for f in suspicious_files:
            path = f.get('path', '')
            if path:
                suspicious_set.add(path)
                suspicious_set.add(Path(path).name)
    
    suspicious_json = json.dumps(list(suspicious_set))
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Code Graph Explorer - {repo_id}@{sha_display}</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
        
        <style>
            :root {{
                --bg-primary: #0f172a;
                --bg-secondary: #1e293b;
                --bg-tertiary: #334155;
                --text-primary: #f1f5f9;
                --text-secondary: #cbd5e1;
                --text-dim: #94a3b8;
                --border-main: #334155;
                --border-subtle: #1e293b;
                --accent: #3b82f6;
                --accent-alt: #06b6d4;
                --font-base: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                --font-mono: 'JetBrains Mono', 'Courier New', monospace;
            }}

            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            html, body {{
                width: 100%;
                height: 100%;
                overflow: hidden;
                background: var(--bg-primary);
            }}

            body {{
                font-family: var(--font-base);
                color: var(--text-primary);
            }}

            .explorer-root {{
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100vh;
            }}

            /* Header */
            .explorer-header {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 0.75rem 1rem;
                background: linear-gradient(135deg, var(--bg-secondary), var(--bg-primary));
                border-bottom: 1px solid var(--border-main);
                height: 56px;
                gap: 1rem;
                flex-shrink: 0;
            }}

            .header-left {{
                display: flex;
                align-items: center;
                gap: 1rem;
                flex: 1;
                min-width: 0;
            }}

            .header-center {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }}

            .header-right {{
                display: flex;
                align-items: center;
                gap: 1rem;
            }}

            .brand-badge {{
                display: flex;
                align-items: center;
                gap: 0.4rem;
                color: var(--text-primary);
                text-decoration: none;
                font-weight: 600;
                font-size: 0.875rem;
                cursor: pointer;
                white-space: nowrap;
            }}

            /* Subbar */
            .explorer-subbar {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 0.6rem 1rem;
                background: var(--bg-secondary);
                border-bottom: 1px solid var(--border-main);
                gap: 1rem;
                height: 44px;
                flex-shrink: 0;
                overflow-x: auto;
            }}

            .search-box-wrap {{
                display: flex;
                align-items: center;
                gap: 0.4rem;
                background: var(--bg-primary);
                border: 1px solid var(--border-main);
                border-radius: 4px;
                padding: 0.4rem 0.6rem;
                flex: 0 0 250px;
            }}

            .search-input {{
                background: none;
                border: none;
                color: var(--text-primary);
                font-size: 0.875rem;
                flex: 1;
                outline: none;
            }}

            .search-input::placeholder {{
                color: var(--text-dim);
            }}

            .subbar-controls {{
                display: flex;
                align-items: center;
                gap: 0.6rem;
                flex-wrap: nowrap;
            }}

            .control-select {{
                background: var(--bg-primary);
                border: 1px solid var(--border-main);
                color: var(--text-primary);
                padding: 0.4rem 0.6rem;
                border-radius: 4px;
                font-size: 0.75rem;
                cursor: pointer;
                white-space: nowrap;
            }}

            .btn-ctrl {{
                background: var(--bg-secondary);
                border: 1px solid var(--border-main);
                color: var(--text-primary);
                padding: 0.4rem 0.6rem;
                border-radius: 4px;
                cursor: pointer;
                font-size: 0.75rem;
                display: flex;
                align-items: center;
                gap: 0.3rem;
                transition: all 0.2s ease;
                white-space: nowrap;
            }}

            .btn-ctrl:hover {{
                background: var(--bg-tertiary);
                border-color: var(--accent);
            }}

            /* Main workspace */
            .explorer-workspace {{
                display: flex;
                flex: 1;
                position: relative;
                overflow: hidden;
                min-height: 0;
            }}

            #cyGraphCanvas {{
                flex: 1;
                background: var(--bg-primary);
                width: 100%;
                height: 100%;
            }}

            /* Canvas controls */
            .canvas-floating-controls {{
                position: absolute;
                bottom: 20px;
                left: 20px;
                display: flex;
                flex-direction: column;
                gap: 0.4rem;
                z-index: 100;
            }}

            /* Canvas legend */
            .canvas-legend {{
                position: absolute;
                bottom: 20px;
                right: 20px;
                background: rgba(30, 41, 59, 0.95);
                border: 1px solid var(--border-main);
                border-radius: 6px;
                padding: 0.8rem;
                font-size: 0.75rem;
                max-width: 200px;
                z-index: 100;
                backdrop-filter: blur(8px);
            }}

            .legend-title {{
                font-weight: 600;
                margin-bottom: 0.6rem;
                color: var(--text-primary);
            }}

            .legend-items {{
                display: flex;
                flex-direction: column;
                gap: 0.4rem;
            }}

            .legend-item {{
                display: flex;
                align-items: center;
                gap: 0.4rem;
                color: var(--text-secondary);
            }}

            .legend-swatch {{
                width: 16px;
                height: 16px;
                border-radius: 2px;
                border: 1px solid var(--border-main);
                flex-shrink: 0;
            }}

            .legend-swatch.file {{
                background: #1e293b;
                border-color: #38bdf8;
            }}

            .legend-swatch.func {{
                background: #0f172a;
                border-color: #818cf8;
            }}

            .legend-swatch.class {{
                background: #0f291e;
                border-color: #34d399;
            }}

            .legend-swatch.changed {{
                background: #78350f;
                border-color: #fda34b;
            }}

            .legend-swatch.affected {{
                background: #7f1d1d;
                border-color: #ff6b6b;
            }}

            /* Side inspector */
            .explorer-inspector {{
                width: 280px;
                background: var(--bg-secondary);
                border-left: 1px solid var(--border-main);
                display: flex;
                flex-direction: column;
                overflow: hidden;
                z-index: 50;
                flex-shrink: 0;
            }}

            .inspector-header {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 0.8rem;
                border-bottom: 1px solid var(--border-main);
                font-size: 0.875rem;
                font-weight: 600;
                flex-shrink: 0;
            }}

            .inspector-body {{
                flex: 1;
                overflow-y: auto;
                padding: 0.8rem;
                font-size: 0.8rem;
                min-height: 0;
            }}

            .inspector-section {{
                margin-bottom: 1rem;
            }}

            .inspector-section-title {{
                font-weight: 600;
                color: var(--accent);
                margin-bottom: 0.4rem;
                font-size: 0.75rem;
                text-transform: uppercase;
            }}

            .inspector-item {{
                display: flex;
                justify-content: space-between;
                padding: 0.3rem 0;
                color: var(--text-secondary);
                border-bottom: 1px solid var(--border-subtle);
                word-break: break-word;
            }}

            .inspector-label {{
                color: var(--text-dim);
                flex-shrink: 0;
            }}

            .inspector-value {{
                color: var(--text-primary);
                font-family: var(--font-mono);
                margin-left: 0.5rem;
                word-break: break-all;
            }}

            /* Spinner */
            .spinner {{
                width: 40px;
                height: 40px;
                border: 3px solid var(--border-main);
                border-top-color: var(--accent);
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
            }}

            @keyframes spin {{
                to {{ transform: rotate(360deg); }}
            }}

            /* Loading overlay */
            .overlay-state {{
                position: absolute;
                inset: 0;
                background: rgba(15, 23, 42, 0.98);
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: 1rem;
                z-index: 200;
                backdrop-filter: blur(4px);
            }}

            .overlay-msg {{
                font-size: 0.95rem;
                font-weight: 500;
            }}

            .overlay-sub {{
                font-size: 0.8rem;
                color: var(--text-dim);
            }}

            /* Scrollbar */
            ::-webkit-scrollbar {{
                width: 8px;
                height: 8px;
            }}

            ::-webkit-scrollbar-track {{
                background: var(--bg-primary);
            }}

            ::-webkit-scrollbar-thumb {{
                background: var(--border-main);
                border-radius: 4px;
            }}

            ::-webkit-scrollbar-thumb:hover {{
                background: var(--border-subtle);
            }}
        </style>
    </head>
    <body>
        <div class="explorer-root">
            <!-- Header -->
            <header class="explorer-header">
                <div class="header-left">
                    <a class="brand-badge" title="Code Graph Explorer">
                        <span>🕸️ Code Graph Explorer</span>
                    </a>
                    <div style="flex: 1;">
                        <span style="font-size: 0.8rem; color: var(--text-dim);">{repo_id}</span>
                        <span style="color: var(--text-dim);">@</span>
                        <span style="font-family: var(--font-mono); color: var(--accent);">{sha_display}</span>
                    </div>
                </div>
                <div class="header-right">
                    <div style="display: flex; gap: 1rem; font-size: 0.8rem;">
                        <div><span style="color: var(--text-dim);">Nodes:</span> <strong style="color: var(--accent);">{metadata.get('total_nodes', len(nodes))}</strong></div>
                        <div><span style="color: var(--text-dim);">Edges:</span> <strong style="color: var(--accent);">{metadata.get('total_edges', len(edges))}</strong></div>
                        <div><span style="color: var(--text-dim);">Suspicious:</span> <strong style="color: #ff6b6b;">{metadata.get('suspicious_files_count', 0)}</strong></div>
                    </div>
                </div>
            </header>

            <!-- Subbar with controls -->
            <div class="explorer-subbar">
                <div class="search-box-wrap">
                    <input type="text" id="graphSearch" class="search-input" placeholder="Search file, function, class..." autocomplete="off">
                </div>
                <div class="subbar-controls">
                    <label for="layoutSelect" style="font-size: 0.75rem; color: var(--text-dim);">Layout:</label>
                    <select id="layoutSelect" class="control-select">
                        <option value="breadthfirst" selected>Hierarchical</option>
                        <option value="cose">Force-Directed</option>
                        <option value="concentric">Concentric</option>
                        <option value="circle">Circle</option>
                    </select>
                    <button id="btnFit" class="btn-ctrl" title="Fit to View">⛶ Fit</button>
                    <button id="btnZoomIn" class="btn-ctrl" title="Zoom In">+ Zoom In</button>
                    <button id="btnZoomOut" class="btn-ctrl" title="Zoom Out">− Zoom Out</button>
                    <button id="btnReset" class="btn-ctrl" title="Reset Layout">↺ Reset</button>
                    <button id="btnToggleInspector" class="btn-ctrl" title="Toggle Inspector">📋 Inspector</button>
                </div>
            </div>

            <!-- Main workspace -->
            <div class="explorer-workspace">
                <div id="cyGraphCanvas"></div>

                <!-- Canvas controls (bottom-left) -->
                <div class="canvas-floating-controls">
                    <button id="floatFit" class="btn-ctrl" title="Fit">⛶</button>
                    <button id="floatZoom" class="btn-ctrl" title="Zoom">🔍</button>
                </div>

                <!-- Canvas legend (bottom-right) -->
                <div class="canvas-legend">
                    <div class="legend-title">Legend</div>
                    <div class="legend-items">
                        <div class="legend-item"><span class="legend-swatch file"></span> File</div>
                        <div class="legend-item"><span class="legend-swatch func"></span> Function</div>
                        <div class="legend-item"><span class="legend-swatch class"></span> Class</div>
                        <div class="legend-item"><span class="legend-swatch changed"></span> Changed</div>
                        <div class="legend-item"><span class="legend-swatch affected"></span> Suspicious</div>
                    </div>
                </div>

                <!-- Side inspector -->
                <aside class="explorer-inspector" id="sideInspector" style="display: none;">
                    <div class="inspector-header">
                        <h3>Node Inspector</h3>
                        <button id="btnCloseInspector" class="btn-ctrl" style="width: 24px; height: 24px;" title="Close">✕</button>
                    </div>
                    <div class="inspector-body" id="inspectorContent">
                        <p style="color: var(--text-dim); text-align: center;">Click a node to see details</p>
                    </div>
                </aside>

                <!-- Loading overlay -->
                <div id="loadingOverlay" class="overlay-state">
                    <div class="spinner"></div>
                    <div class="overlay-msg">Rendering Code Graph...</div>
                </div>
            </div>
        </div>

        <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js"></script>
        <script>
        (function() {{
            console.log('Initializing Professional Graph Explorer...');
            
            let cy = null;
            const nodes = {nodes_json};
            const edges = {edges_json};
            const suspiciousFiles = {suspicious_json};

            // Check if Cytoscape is loaded
            function waitForCytoscape(attempts = 0) {{
                if (typeof cytoscape !== 'undefined') {{
                    initializeGraph();
                }} else if (attempts < 50) {{
                    setTimeout(() => waitForCytoscape(attempts + 1), 100);
                }} else {{
                    console.error('Cytoscape failed to load');
                    document.getElementById('cyGraphCanvas').innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 20px;">Failed to load Cytoscape library</p>';
                    document.getElementById('loadingOverlay').style.display = 'none';
                }}
            }}

            function initializeGraph() {{
                try {{
                    console.log('Cytoscape loaded. Initializing graph...');
                    console.log('Nodes: ' + nodes.length + ', Edges: ' + edges.length);
                    
                    if (nodes.length === 0) {{
                        document.getElementById('cyGraphCanvas').innerHTML = '<p style="color: #94a3b8; text-align: center; padding: 20px;">No nodes to display</p>';
                        document.getElementById('loadingOverlay').style.display = 'none';
                        return;
                    }}

                    // Cytoscape styling
                    const cyStyle = [
                        {{
                            selector: 'node',
                            style: {{
                                'label': 'data(label)',
                                'color': '#f1f5f9',
                                'font-family': 'Inter, sans-serif',
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
                        }}
                    ];

                    console.log('Creating Cytoscape instance...');

                    // Create Cytoscape instance
                    cy = cytoscape({{
                        container: document.getElementById('cyGraphCanvas'),
                        elements: nodes.concat(edges),
                        style: cyStyle,
                        layout: {{
                            name: 'breadthfirst',
                            directed: true,
                            animate: false,
                            spacingFactor: 1.5
                        }},
                        wheelSensitivity: 0.1,
                        maxZoom: 3,
                        minZoom: 0.1
                    }});

                    console.log('Cytoscape instance created');

                    // Highlight suspicious nodes
                    suspiciousFiles.forEach(file => {{
                        const nodeList = cy.elements().filter(el => 
                            el.isNode() && (
                                el.data('label').includes(file) ||
                                (el.data('path') && el.data('path').includes(file)) ||
                                el.data('label') === file
                            )
                        );
                        nodeList.addClass('suspicious');
                    }});

                    // Fit to view and hide loading
                    console.log('Fitting graph to view...');
                    setTimeout(() => {{
                        try {{
                            cy.fit(cy.elements(), 30);
                            cy.animate({{
                                duration: 300
                            }});
                        }} catch(e) {{
                            console.warn('Fit error:', e);
                        }}
                        document.getElementById('loadingOverlay').style.display = 'none';
                        console.log('✓ Graph loaded and ready');
                    }}, 200);

                    // Setup controls
                    document.getElementById('btnFit').addEventListener('click', () => {{
                        cy.fit(cy.elements(), 30);
                    }});

                    document.getElementById('btnZoomIn').addEventListener('click', () => {{
                        cy.zoom(cy.zoom() * 1.2);
                    }});

                    document.getElementById('btnZoomOut').addEventListener('click', () => {{
                        cy.zoom(cy.zoom() / 1.2);
                    }});

                    document.getElementById('floatFit').addEventListener('click', () => {{
                        cy.fit(cy.elements(), 30);
                    }});
                    
                    document.getElementById('btnReset').addEventListener('click', () => {{
                        const layoutName = document.getElementById('layoutSelect').value;
                        const layout = cy.layout({{ name: layoutName, animate: true, animationDuration: 500 }});
                        layout.run();
                    }});

                    document.getElementById('layoutSelect').addEventListener('change', e => {{
                        const layout = cy.layout({{ name: e.target.value, animate: true, animationDuration: 500 }});
                        layout.run();
                    }});

                    // Search
                    document.getElementById('graphSearch').addEventListener('input', e => {{
                        const query = e.target.value.toLowerCase();
                        cy.elements('node').forEach(node => {{
                            const label = (node.data('label') || '').toLowerCase();
                            if (query === '' || label.includes(query)) {{
                                node.removeClass('hidden');
                            }} else {{
                                node.addClass('hidden');
                            }}
                        }});
                    }});

                    // Inspector
                    const inspector = document.getElementById('sideInspector');
                    const inspectorContent = document.getElementById('inspectorContent');
                    const btnToggle = document.getElementById('btnToggleInspector');
                    const btnClose = document.getElementById('btnCloseInspector');

                    btnToggle.addEventListener('click', () => {{
                        const isHidden = inspector.style.display === 'none';
                        inspector.style.display = isHidden ? 'flex' : 'none';
                        if (isHidden) cy.fit(cy.elements(), 30);
                    }});

                    btnClose.addEventListener('click', () => {{
                        inspector.style.display = 'none';
                        cy.fit(cy.elements(), 30);
                    }});

                    cy.on('tap', 'node', evt => {{
                        const node = evt.target;
                        const data = node.data();
                        const indeg = node.indegree();
                        const outdeg = node.outdegree();

                        inspectorContent.innerHTML = `
                            <div class="inspector-section">
                                <div class="inspector-section-title">Node Info</div>
                                <div class="inspector-item">
                                    <span class="inspector-label">Label:</span>
                                    <span class="inspector-value">${{data.label || 'N/A'}}</span>
                                </div>
                                <div class="inspector-item">
                                    <span class="inspector-label">Type:</span>
                                    <span class="inspector-value">${{data.type || 'N/A'}}</span>
                                </div>
                                ${{data.path ? `
                                    <div class="inspector-item">
                                        <span class="inspector-label">Path:</span>
                                        <span class="inspector-value">${{data.path}}</span>
                                    </div>
                                ` : ''}}
                                <div class="inspector-item">
                                    <span class="inspector-label">In-degree:</span>
                                    <span class="inspector-value">${{indeg}}</span>
                                </div>
                                <div class="inspector-item">
                                    <span class="inspector-label">Out-degree:</span>
                                    <span class="inspector-value">${{outdeg}}</span>
                                </div>
                            </div>
                        `;
                        
                        inspector.style.display = 'flex';
                    }});

                }} catch (err) {{
                    console.error('Error:', err);
                    document.getElementById('cyGraphCanvas').innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 20px;">Error rendering graph: ' + err.message + '</p>';
                    document.getElementById('loadingOverlay').style.display = 'none';
                }}
            }}

            // Start waiting for Cytoscape
            waitForCytoscape();
        }})();
        </script>
    </body>
    </html>
    """
    
    return html_content


def save_and_open_graph_explorer(
    graph_data: Dict,
    repo_id: str,
    target_sha: str,
    suspicious_files: list = None,
    changed_files: Dict = None
) -> bool:
    """
    Save graph explorer HTML and open in browser.
    
    Args:
        graph_data: Graph data
        repo_id: Repository ID
        target_sha: Target commit SHA
        suspicious_files: List of suspicious files
        changed_files: Changed files dict
    
    Returns:
        True if successful
    """
    try:
        html_content = generate_graph_explorer_html(
            graph_data,
            repo_id,
            target_sha,
            suspicious_files=suspicious_files,
            changed_files=changed_files
        )
        
        if not html_content:
            logger.error("Failed to generate HTML")
            return False
        
        # Save to temp directory
        temp_dir = Path(tempfile.gettempdir()) / "orc_graph_viewer"
        temp_dir.mkdir(exist_ok=True)
        
        sha_short = target_sha[:7] if len(target_sha) >= 7 else target_sha
        html_file = temp_dir / f"explorer_{repo_id.replace('/', '_')}_{sha_short}.html"
        
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Graph explorer HTML saved to: {html_file}")
        
        # Open in browser
        file_url = html_file.as_uri()
        webbrowser.open(file_url)
        
        logger.info(f"Opened graph explorer in browser: {file_url}")
        return True
    
    except Exception as e:
        logger.error(f"Error saving/opening graph explorer: {e}", exc_info=True)
        return False
