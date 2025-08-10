# integrations/confluence_client.py - Pure Confluence API client
import requests
from typing import Dict, List, Any
import json

class ConfluenceClient:
    """
    Pure Confluence API client.
    Only knows how to make API calls to Confluence.
    No business logic, just API communication.
    """
    
    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip('/')
        self.auth = (email, api_token)
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
    
    def get_spaces(self) -> List[Dict[str, Any]]:
        """Fetch all spaces from Confluence."""
        url = f"{self.base_url}/wiki/rest/api/space"
        response = requests.get(url, auth=self.auth, headers=self.headers)
        response.raise_for_status()
        
        data = response.json()
        return data.get('results', [])
    
    def get_pages_with_labels(self, space_key: str) -> List[Dict[str, Any]]:
        """
        Fetch all pages in a space with their labels and parent info.
        
        Returns:
            List of dicts with keys: id, title, parent_id, labels (as JSON string)
        """
        url = f"{self.base_url}/wiki/rest/api/content"
        params = {
            'spaceKey': space_key,
            'type': 'page',
            'expand': 'metadata.labels,ancestors',
            'limit': 500  # Adjust as needed
        }
        
        all_pages = []
        while url:
            response = requests.get(url, auth=self.auth, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            for page in data.get('results', []):
                labels = [label['name'] for label in page.get('metadata', {}).get('labels', {}).get('results', [])]
                
                # Get parent ID (the immediate parent is the last ancestor)
                ancestors = page.get('ancestors', [])
                parent_id = ancestors[-1]['id'] if ancestors else None
                
                all_pages.append({
                    'id': page['id'],
                    'title': page['title'],
                    'parent_id': parent_id,
                    'labels': json.dumps(labels)  # Store as JSON string
                })
            
            # Check for next page
            url = data.get('_links', {}).get('next')
            params = {}  # Clear params for subsequent requests
            
        return all_pages
    
    def get_page_content(self, page_id: str) -> Dict[str, Any]:
        """Fetch the content of a specific page."""
        url = f"{self.base_url}/wiki/rest/api/content/{page_id}"
        params = {'expand': 'body.storage,metadata.labels'}
        
        response = requests.get(url, auth=self.auth, headers=self.headers, params=params)
        response.raise_for_status()
        
        page = response.json()
        return {
            'id': page['id'],
            'title': page['title'],
            'content': page.get('body', {}).get('storage', {}).get('value', ''),
            'labels': [label['name'] for label in page.get('metadata', {}).get('labels', {}).get('results', [])]
        }
    
    def add_label(self, page_id: str, label: str) -> None:
        """Add a label to a page."""
        url = f"{self.base_url}/wiki/rest/api/content/{page_id}/label"
        data = [{"name": label}]
        
        response = requests.post(url, auth=self.auth, headers=self.headers, json=data)
        response.raise_for_status()