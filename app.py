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

import logging

# Set up logging to file
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('debug.log'),
        logging.StreamHandler()  # Also print to console
    ]
)
logger = logging.getLogger(__name__)

# Then in generate_suggestions, replace print statements with:
# logger.info("message here")
# For example:
# logger.info(f"Starting suggestion generation for cluster {cluster_id}")
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
                         cluster_label=config['analysis']['cluster_label'],
                         config=config)

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
        """SELECT s.id, s.page_id, p.title, s.suggestion_text, s.confidence_score, s.status, s.created_date
           FROM suggestions s
           JOIN pages p ON s.page_id = p.id
           WHERE s.cluster_id = ? AND s.status = 'pending'
           ORDER BY p.title,s.confidence_score DESC""",
        (cluster_id,)
    )
    
    # Format suggestions for template
    formatted_suggestions = []
    for sug_id, page_id, page_title, label, confidence, status, created_date in suggestions:
        # Try to get a reason from the created_date field (we'll improve this later)
        reason = f"Based on AI analysis of page content"
        if confidence >= 0.8:
            reason = "High relevance to page content"
        elif confidence >= 0.6:
            reason = "Moderate relevance to page content"
        else:
            reason = "Possible relevance to page content"
            
        formatted_suggestions.append({
            'id': sug_id,
            'page_id': page_id,
            'page_title': page_title,
            'label': label,
            'confidence': confidence,
            'reason': reason
        })
    
    return render_template('cluster.html',
                         cluster_id=cluster_id,
                         cluster_title=cluster_title,
                         space_key=space_key,
                         cluster_labels=cluster_labels,
                         member_pages=member_pages,
                         suggestions=formatted_suggestions,
                         config=config)

""" START GENERATE SUGGESTIONS"""
@app.route('/cluster/<cluster_id>/generate-suggestions')
def generate_suggestions(cluster_id):
    """Generate new suggestions for a cluster using Claude"""
    print("\n" + "="*60)
    print("GENERATE_SUGGESTIONS FUNCTION CALLED!")
    print(f"Cluster ID: {cluster_id}")
    print("="*60)
    
    space_key = request.args.get('space_key')
    print(f"Space key: {space_key}")
    
    # Clear old suggestions
    print("Clearing old suggestions...")
    db.execute_query(
        "DELETE FROM suggestions WHERE cluster_id = ?",
        (cluster_id,)
    )
    print("Old suggestions cleared")
    
    # Get cluster info
    print(f"Fetching cluster info for ID: {cluster_id}")
    cluster_page = db.execute_query(
        "SELECT title, labels_json FROM pages WHERE id = ?",
        (cluster_id,)
    )
    print(f"Cluster query returned: {len(cluster_page)} results")
    
    if not cluster_page:
        print("ERROR: Cluster not found in database!")
        flash('Cluster not found')
        return redirect(url_for('view_space', space_key=space_key))
    
    cluster_title, cluster_labels_json = cluster_page[0]
    cluster_labels = json.loads(cluster_labels_json) if cluster_labels_json else []
    print(f"Cluster title: {cluster_title}")
    print(f"Cluster labels: {cluster_labels}")
    
    # Get all labels used in the space (for consistency)
    print("Getting all labels in space...")
    all_pages_in_space = db.execute_query(
        "SELECT labels_json FROM pages WHERE space_key = ?",
        (space_key,)
    )
    
    all_labels = set()
    for labels_json, in all_pages_in_space:
        if labels_json:
            labels = json.loads(labels_json)
            all_labels.update(labels)
    
    all_labels_list = sorted(list(all_labels))
    print(f"Found {len(all_labels_list)} unique labels in space")
    
    # Get member pages (direct children only)
    print("Getting member pages...")
    member_pages = db.execute_query(
        "SELECT id, title, parent_id, labels_json FROM pages WHERE space_key = ? AND parent_id = ?",
        (space_key, cluster_id)
    )
    print(f"Found {len(member_pages)} member pages")
    
    if len(member_pages) == 0:
        print("WARNING: No member pages found!")
        flash('No pages found in this cluster', 'warning')
        return redirect(url_for('view_cluster', cluster_id=cluster_id))
    
    # Check if Claude API key is configured
    claude_key = config.get('claude', {}).get('api_key', '')
    if not claude_key or claude_key == 'your-claude-api-key-here':
        print("ERROR: Claude API key not configured or still has placeholder value!")
        flash('Claude API key not configured. Please add it to config.yaml', 'error')
        return redirect(url_for('view_cluster', cluster_id=cluster_id))
    
    print(f"Claude API key found: {claude_key[:10]}...")
    
    # Prepare cluster info for AI
    cluster_info = {
        'title': cluster_title,
        'labels': [l for l in cluster_labels if l != config['analysis']['cluster_label']]
    }
    
    suggestions_generated = 0
    pages_processed = 0
    errors = []
    
    print(f"\nStarting to process pages ...")
    
    for page_id, title, parent_id, page_labels_json in member_pages:  # Process all pages
        pages_processed += 1
        page_labels = json.loads(page_labels_json) if page_labels_json else []
        print(f"\n--- Processing page {pages_processed}/{ len(member_pages)}: {title}")
        print(f"    Page ID: {page_id}")
        print(f"    Current labels: {page_labels}")
        
        # Fetch full page content for AI analysis
        try:
            print(f"    Fetching content from Confluence...")
            page_content = confluence.get_page_content(page_id)
            content_length = len(page_content.get('content', ''))
            print(f"    Got {content_length} characters of content")
            
            if content_length == 0:
                print(f"    WARNING: No content found for this page!")
                continue
            
            # Prepare page data for AI
            page_data = {
                'id': page_id,
                'title': title,
                'content': page_content.get('content', ''),
                'labels': page_labels
            }
            
            # Get AI suggestions
            print(f"    Calling Claude for suggestions...")
            print(f"    Using suggester: {suggester}")
            
            suggestions = suggester.generate_label_suggestions(
                page_data, 
                all_labels_list, 
                cluster_info
            )
            
            print(f"    Claude returned {len(suggestions)} suggestions:")
            for s in suggestions:
                print(f"      - {s['label']} (confidence: {s['confidence']})")
            
            # Store suggestions in database
            for suggestion in suggestions:
                print(f"    Storing suggestion: {suggestion['label']}")
                db.execute_query(
                    """INSERT INTO suggestions 
                       (cluster_id, page_id, type, suggestion_text, confidence_score, status, created_date) 
                       VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (cluster_id, page_id, 'label', suggestion['label'], suggestion['confidence'], 'pending')
                )
                suggestions_generated += 1
                
        except Exception as e:
            error_msg = f"ERROR processing page {title}: {str(e)}"
            print(f"    {error_msg}")
            print(f"    Exception type: {type(e)}")
            import traceback
            print(f"    Traceback: {traceback.format_exc()}")
            errors.append(error_msg)
    
    print(f"\n{'='*60}")
    print(f"SUMMARY: Generated {suggestions_generated} suggestions for {pages_processed} pages")
    print(f"Errors: {len(errors)}")
    print(f"{'='*60}\n")
    
    if errors:
        for error in errors[:3]:  # Show first 3 errors
            flash(error, 'warning')
    
    if suggestions_generated > 0:
        flash(f'Generated {suggestions_generated} AI-powered suggestions for {pages_processed} pages ', 'success')
    else:
        flash(f'No suggestions generated. Check console for debug output. Processed {pages_processed} pages.', 'warning')
    
    return redirect(url_for('view_cluster', cluster_id=cluster_id))


""" END  GENERATE SUGGESTIONS"""
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