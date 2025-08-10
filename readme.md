# Confluence Organizer

A Flask-based tool to help organize Confluence spaces by managing labels across pages using a directory/cluster structure.

## Features

- **Cluster Detection**: Identifies directory pages marked with a configurable label (default: `directory-pages`)
- **Automatic Page Grouping**: Groups child pages under their parent directories
- **Label Suggestions**: Suggests missing labels for pages based on their directory's labels
- **Bulk Application**: Apply multiple label suggestions with one click
- **Caching**: Reduces API calls by caching Confluence data locally

## Prerequisites

- Python 3.7+
- Confluence account with API access
- Confluence API token
- Claude API key (optional, for AI-powered suggestions)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/confluencehelper.git
cd confluencehelper
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `config.yaml` file based on the example:
```yaml
confluence:
  url: "https://your-domain.atlassian.net"
  email: "your-email@example.com"
  api_token: "your-confluence-api-token"

claude:
  api_key: "your-claude-api-key"  # Optional for now

database:
  path: "confluence_organizer.db"

analysis:
  cluster_label: "directory-pages"  # Label that identifies directory pages

app:
  debug: true
  port: 7000
  secret_key: "your-secret-key-here"
```

## Getting API Tokens

### Confluence API Token
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Give it a name and copy the token

### Claude API Key (Optional)
1. Go to https://console.anthropic.com/
2. Navigate to API keys section
3. Create and copy your key

## Usage

1. Start the application:
```bash
python app.py
```

2. Open your browser to `http://localhost:7000`

3. Workflow:
   - Select a Confluence space
   - View clusters (directory pages)
   - Click on a cluster to see its pages
   - Generate label suggestions
   - Review and apply suggestions

## Project Structure

```
confluencehelper/
├── app.py                      # Main Flask application
├── config.yaml                 # Configuration (not in git)
├── requirements.txt            # Python dependencies
├── core/                       # Business logic
│   ├── analyzer.py            # Cluster analysis
│   └── suggester.py           # Suggestion generation
├── integrations/              # External integrations
│   ├── confluence_client.py  # Confluence API
│   └── db_manager.py         # Database abstraction
├── templates/                 # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── space.html
│   ├── cluster.html
│   └── help.html
└── static/                    # CSS and JavaScript
    ├── css/style.css
    └── js/main.js
```

## How It Works

1. **Directory Structure**: Pages are organized under directory pages (marked with a special label)
2. **Cluster Membership**: A page belongs to the cluster it sits under hierarchically
3. **Label Suggestions**: Currently suggests labels from the directory; AI analysis coming soon
4. **No Overlaps**: Each page belongs to exactly one cluster, preventing conflicts

## Configuration

Edit `config.yaml` to customize:
- `cluster_label`: The label that identifies directory pages (default: "directory-pages")
- `port`: The port to run the Flask app on
- `debug`: Set to false for production

## Troubleshooting

- **No clusters found**: Ensure your directory pages have the configured label
- **Missing pages**: Only direct children are included in clusters
- **API errors**: Check your API token has appropriate permissions

## Future Enhancements

- AI-powered content analysis for smarter label suggestions
- Support for nested clusters
- Label taxonomy optimization
- Orphan page detection and management
- Bulk operations across multiple clusters

## License

[Your chosen license]

## Contributing

Pull requests are welcome! Please ensure:
- Code follows existing patterns
- Components remain properly isolated
- Database changes include migrations
- New features include documentation