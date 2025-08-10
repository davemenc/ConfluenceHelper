# app.py - Main Flask application
from flask import Flask, render_template, request, redirect, url_for, flash
import yaml
import json
from datetime import datetime

# Import our isolated components
from integrations.confluence_client import ConfluenceClient
from integrations.db_manager import DatabaseManager
from core.analyzer import ClusterAnalyzer
from core.suggester import SuggestionEngine

app = Flask(__name__)

# Load configuration
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

app.secret_key = config['app']['secret_key']

# Initialize components (each knows nothing about the others)
db = DatabaseManager(config['database']['path'])
confluence = ConfluenceClient(
    config['confluence']['url'],
    config['confluence']['email'],
    config['confluence']['api_token']
)
analyzer = ClusterAnalyzer()
suggester = SuggestionEngine(config['claude']['api_key'])

@app.route('/')
def index():
    """Home page - list spaces"""
    # Check cache first
    spaces_data = db.execute_query("SELECT key, name, last_indexed FROM spaces")
    
    if not spaces_data:
        # Fetch from Confluence
        spaces = confluence.get_spaces()
        # Store in cache
        for space in spaces:
            db.execute_query(
                "INSERT OR REPLACE INTO spaces (key, name, last_indexed) VALUES (?, ?, ?)",
                (space['key'], space['name'], datetime.now().isoformat())
            )
        spaces_data = db.execute_query("SELECT key, name, last_indexed FROM spaces")
    
    return render_template('index.html', spaces=spaces_data)

@app.route('/space/<space_key>')
def view_space(space_key):
    """Show clusters in a space"""
    # Get pages from cache or fetch
    pages_data = db.execute_query(
        "SELECT id, title, labels_json FROM pages WHERE space_key = ?",
        (space_key,)
    )
    
    if not pages_data:
        # Fetch and cache
        pages = confluence.get_pages_with_labels(space_key)
        for page in pages:
            db.execute_query(
                "INSERT OR REPLACE INTO pages (id, space_key, title, parent_id, labels_json) VALUES (?, ?, ?, ?, ?)",
                (page['id'], space_key, page['title'], page.get('parent_id'), page['labels'])
            )
        pages_data = db.execute_query(
            "SELECT id, title, labels_json FROM pages WHERE space_key = ?",
            (space_key,)
        )
    
    # Find clusters (pages with directory_page label)
    clusters = analyzer.find_clusters(pages_data, config['analysis']['cluster_label'])
    
    return render_template('space.html', 
                         space_key=space_key, 
                         clusters=clusters,
                         cluster_label=config['analysis']['cluster_label'])

@app.route('/space/<space_key>/reindex')
def reindex_space(space_key):
    """Force reindex of a space"""
    # Clear cache for this space
    db.execute_query("DELETE FROM pages WHERE space_key = ?", (space_key,))
    flash(f'Space {space_key} will be reindexed')
    return redirect(url_for('view_space', space_key=space_key))

@app.route('/help')
def help_page():
    """Display help documentation"""
    return render_template('help.html', config=config)

@app.route('/cluster/<cluster_id>')
def view_cluster(cluster_id):
    """Show cluster details and suggestions"""
    # Get the cluster page info
    cluster_page = db.execute_query(
        "SELECT id, title, space_key, labels_json FROM pages WHERE id = ?",
        (cluster_id,)
    )
    
    if not cluster_page:
        flash('Cluster not found')
        return redirect(url_for('index'))
    
    # Parse cluster info
    cluster_id, cluster_title, space_key, labels_json = cluster_page[0]
    import json
    cluster_labels = json.loads(labels_json) if labels_json else []
    
    # Get all pages in the space to find members
    all_pages = db.execute_query(
        "SELECT id, title, parent_id, labels_json FROM pages WHERE space_key = ?",
        (space_key,)
    )
    
    # Find pages that belong to this cluster
    # A page belongs to a cluster if and only if it's a direct child of the directory page
    member_pages = []
    for page_id, title, parent_id, page_labels_json in all_pages:
        if page_id == cluster_id:
            continue  # Skip the directory page itself
        
        # ONLY include if it's a direct child
        if parent_id == cluster_id:
            page_labels = json.loads(page_labels_json) if page_labels_json else []
            member_pages.append({
                'id': page_id,
                'title': title,
                'labels': page_labels
            })
    
    # Get existing suggestions from database
    suggestions = db.execute_query(
        """SELECT s.id, s.page_id, p.title, s.suggestion_text, s.confidence_score, s.status
           FROM suggestions s
           JOIN pages p ON s.page_id = p.id
           WHERE s.cluster_id = ? AND s.status = 'pending'""",
        (cluster_id,)
    )
    
    # Format suggestions for template
    formatted_suggestions = []
    for sug_id, page_id, page_title, label, confidence, status in suggestions:
        formatted_suggestions.append({
            'id': sug_id,
            'page_id': page_id,
            'page_title': page_title,
            'label': label,
            'confidence': confidence,
            'reason': 'Based on content analysis'  # We'll improve this later
        })
    
    return render_template('cluster.html',
                         cluster_id=cluster_id,
                         cluster_title=cluster_title,
                         space_key=space_key,
                         cluster_labels=cluster_labels,
                         member_pages=member_pages,
                         suggestions=formatted_suggestions,
                         config=config)

@app.route('/cluster/<cluster_id>/generate-suggestions')
def generate_suggestions(cluster_id):
    """Generate new suggestions for a cluster"""
    space_key = request.args.get('space_key')
    
    # Clear old suggestions
    db.execute_query(
        "DELETE FROM suggestions WHERE cluster_id = ?",
        (cluster_id,)
    )
    
    # Get cluster info
    cluster_page = db.execute_query(
        "SELECT labels_json FROM pages WHERE id = ?",
        (cluster_id,)
    )
    
    if not cluster_page:
        flash('Cluster not found')
        return redirect(url_for('view_space', space_key=space_key))
    
    import json
    cluster_labels = json.loads(cluster_page[0][0]) if cluster_page[0][0] else []
    directory_labels = [l for l in cluster_labels if l != config['analysis']['cluster_label']]
    
    # Get member pages
    all_pages = db.execute_query(
        "SELECT id, title, parent_id, labels_json FROM pages WHERE space_key = ?",
        (space_key,)
    )
    
    member_pages = []
    for page_id, title, parent_id, page_labels_json in all_pages:
        if page_id == cluster_id:
            continue
            
        page_labels = json.loads(page_labels_json) if page_labels_json else []
        
        # Check if page is a child of the directory
        is_child = (parent_id == cluster_id)
        
        # Check if page shares any labels with the directory
        shares_labels = any(label in page_labels for label in directory_labels)
        
        # Include page if it's either a child OR shares labels
        if is_child or shares_labels:
            member_pages.append({
                'id': page_id,
                'title': title,
                'labels': page_labels
            })
    
    # For now, let's create some simple suggestions
    # (We'll integrate Claude properly later)
    for page in member_pages:
        # Simple rule: suggest directory labels that the page doesn't have
        for label in directory_labels:
            if label not in page['labels']:
                db.execute_query(
                    """INSERT INTO suggestions 
                       (cluster_id, page_id, type, suggestion_text, confidence_score, status, created_date) 
                       VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (cluster_id, page['id'], 'label', label, 0.75, 'pending')
                )
    
    flash(f'Generated suggestions for {len(member_pages)} pages')
    return redirect(url_for('view_cluster', cluster_id=cluster_id))

@app.route('/apply-suggestions', methods=['POST'])
def apply_suggestions():
    """Apply selected suggestions"""
    selected = request.form.getlist('suggestion_ids')
    cluster_id = request.form.get('cluster_id')
    space_key = request.form.get('space_key')
    
    success_count = 0
    error_count = 0
    
    for suggestion_id in selected:
        try:
            # Get suggestion details
            suggestion_data = db.execute_query(
                """SELECT s.page_id, s.suggestion_text, s.type 
                   FROM suggestions s 
                   WHERE s.id = ?""",
                (suggestion_id,)
            )
            
            if suggestion_data:
                page_id, suggestion_text, suggestion_type = suggestion_data[0]
                
                if suggestion_type == 'label':
                    # Apply the label via Confluence API
                    confluence.add_label(page_id, suggestion_text)
                    
                    # Mark as applied in database
                    db.execute_query(
                        "UPDATE suggestions SET status = 'applied', applied_date = datetime('now') WHERE id = ?",
                        (suggestion_id,)
                    )
                    
                    # Also update the cached page labels
                    db.execute_query(
                        """UPDATE pages 
                           SET labels_json = (
                               SELECT json_insert(
                                   COALESCE(labels_json, '[]'), 
                                   '$[#]', 
                                   ?
                               )
                               FROM pages 
                               WHERE id = ?
                           )
                           WHERE id = ?""",
                        (suggestion_text, page_id, page_id)
                    )
                    
                    success_count += 1
        except Exception as e:
            print(f"Error applying suggestion {suggestion_id}: {str(e)}")
            error_count += 1
    
    if success_count > 0:
        flash(f'Successfully applied {success_count} suggestion(s)', 'success')
    if error_count > 0:
        flash(f'Failed to apply {error_count} suggestion(s)', 'error')
    
    return redirect(url_for('view_cluster', cluster_id=cluster_id))

def init_database():
    """Initialize database tables"""
    db.execute_query("""
        CREATE TABLE IF NOT EXISTS spaces (
            key TEXT PRIMARY KEY,
            name TEXT,
            last_indexed TEXT
        )
    """)
    
    db.execute_query("""
        CREATE TABLE IF NOT EXISTS pages (
            id TEXT PRIMARY KEY,
            space_key TEXT,
            title TEXT,
            parent_id TEXT,
            labels_json TEXT,
            last_fetched TEXT
        )
    """)
    
    db.execute_query("""
        CREATE TABLE IF NOT EXISTS clusters (
            id INTEGER PRIMARY KEY,
            space_key TEXT,
            directory_page_id TEXT,
            name TEXT
        )
    """)
    
    db.execute_query("""
        CREATE TABLE IF NOT EXISTS cluster_members (
            cluster_id INTEGER,
            page_id TEXT
        )
    """)
    
    db.execute_query("""
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY,
            cluster_id INTEGER,
            page_id TEXT,
            type TEXT,
            suggestion_text TEXT,
            confidence_score REAL,
            status TEXT,
            created_date TEXT DEFAULT CURRENT_TIMESTAMP,
            applied_date TEXT
        )
    """)

if __name__ == '__main__':
    init_database()
    app.run(debug=config['app']['debug'], port=config['app']['port'])