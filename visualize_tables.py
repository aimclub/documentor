"""
Script to visualize HTML tables from structure.json file.
Creates an HTML file with all tables rendered.
"""

import json
from pathlib import Path

def visualize_tables(json_path: Path, output_path: Path = None):
    """
    Extract and visualize HTML tables from structure.json.
    
    Args:
        json_path: Path to structure.json file
        output_path: Path to output HTML file (default: tables_visualization.html in same directory)
    """
    # Load JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Find all tables
    tables = [e for e in data.get('elements', []) if e.get('type') == 'TABLE']
    
    print(f"Found {len(tables)} tables in the document")
    
    # Create output path
    if output_path is None:
        output_path = json_path.parent / "tables_visualization.html"
    
    # Generate HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HTML Tables Visualization - {json_path.stem}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        .table-container {{
            background: white;
            margin: 20px 0;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .table-info {{
            background: #e8f5e9;
            padding: 10px;
            margin-bottom: 15px;
            border-radius: 4px;
            font-size: 14px;
        }}
        .table-info strong {{
            color: #2e7d32;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
            font-size: 14px;
        }}
        th {{
            background-color: #4CAF50;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: bold;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        tr:hover {{
            background-color: #f1f8e9;
        }}
        .empty-table {{
            color: #999;
            font-style: italic;
            padding: 20px;
            text-align: center;
        }}
        .stats {{
            background: #fff3cd;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <h1>HTML Tables Visualization</h1>
    <div class="stats">
        <strong>Document:</strong> {data.get('source', 'N/A')}<br>
        <strong>Format:</strong> {data.get('format', 'N/A')}<br>
        <strong>Total Tables Found:</strong> {len(tables)}
    </div>
"""
    
    for i, table in enumerate(tables, 1):
        table_id = table.get('id', f'unknown_{i}')
        page_num = table.get('page_num', 'N/A')
        bbox = table.get('bbox', [])
        html_content_table = table.get('content', '')
        
        # Get full content - check if there's a separate table file
        table_dir = json_path.parent / "tables"
        if table_dir.exists():
            # Try to load from separate table file
            table_file = table_dir / f"table_{i}.json"
            if table_file.exists():
                try:
                    with open(table_file, 'r', encoding='utf-8') as tf:
                        table_data = json.load(tf)
                        html_content_table = table_data.get('html', '') or html_content_table
                except Exception as e:
                    print(f"Warning: Could not load table file {table_file}: {e}")
        
        # If still empty, try metadata
        if not html_content_table or not html_content_table.strip():
            metadata = table.get('metadata', {})
            html_content_table = metadata.get('table_html', '') or html_content_table
        
        # If still empty, use preview (truncated)
        if not html_content_table or not html_content_table.strip():
            html_content_table = table.get('content_preview', '')
        
        html_content += f"""
    <div class="table-container">
        <div class="table-info">
            <strong>Table {i}</strong> | 
            ID: {table_id} | 
            Page: {page_num} | 
            BBox: {bbox} |
            HTML Length: {len(html_content_table)} chars
        </div>
"""
        
        if html_content_table and html_content_table.strip():
            # Insert the HTML table directly
            html_content += html_content_table
        else:
            html_content += '<div class="empty-table">(Table content is empty)</div>'
        
        html_content += """
    </div>
"""
    
    html_content += """
</body>
</html>
"""
    
    # Save HTML file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Visualization saved to: {output_path}")
    print(f"Open the file in your browser to view the tables")
    
    return output_path

if __name__ == "__main__":
    import sys
    
    json_path = Path("experiments/pdf_text_extraction/results/pdf/2507.06920v1/structure.json")
    
    if len(sys.argv) > 1:
        json_path = Path(sys.argv[1])
    
    if not json_path.exists():
        print(f"Error: File not found: {json_path}")
        sys.exit(1)
    
    output_path = visualize_tables(json_path)
    print(f"\nSuccessfully created visualization: {output_path}")
