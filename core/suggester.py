# core/suggester.py - Pure suggestion logic using Claude
from anthropic import Anthropic
from typing import List, Dict, Any
import json
import re

class SuggestionEngine:
    """
    Pure suggestion generation using Claude.
    Takes content, returns suggestions.
    No knowledge of storage or other components.
    """
    
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
    
    def generate_label_suggestions(self, page: Dict[str, Any], all_labels_in_space: List[str], cluster_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate label suggestions for a single page using Claude.
        
        Args:
            page: Dictionary with 'id', 'title', 'content', 'labels'
            all_labels_in_space: List of all labels used in the space (for consistency)
            cluster_info: Dictionary with 'title' and 'labels' of the cluster/directory
            
        Returns:
            List of suggestion dictionaries with 'label', 'confidence', 'reason'
        """
        
        # Remove HTML tags from content for cleaner analysis
        content_text = re.sub('<[^<]+?>', '', page.get('content', ''))[:3000]  # Limit to 3000 chars
        
        prompt = f"""Analyze this Confluence page and suggest appropriate labels.

Page Title: {page['title']}
Current Labels: {', '.join(page.get('labels', [])) if page.get('labels') else 'None'}
Page Content:
{content_text}

Context:
- This page is in the "{cluster_info.get('title', 'Unknown')}" cluster/directory
- The directory has these labels: {', '.join(cluster_info.get('labels', []))}
- Other labels used in this space include: {', '.join(all_labels_in_space[:30])}  # Show first 30

Task: Suggest 1-5 labels that would help organize this page better.

Rules:
1. Prefer existing labels from the space when appropriate (for consistency)
2. Suggest new labels only if no existing ones fit well
3. Labels should be lowercase with hyphens (e.g., "project-planning", "technical-docs")
4. Focus on what the page is ABOUT, not just copying directory labels
5. Each suggestion needs a confidence score (0.0-1.0) and brief reason

Output format (JSON):
[
  {{"label": "example-label", "confidence": 0.85, "reason": "Page discusses X extensively"}},
  {{"label": "another-label", "confidence": 0.7, "reason": "Related to Y topics"}}
]
Only suggest labels that are NOT already on the page.
Return only the JSON array, no other text."""

        try:
            response = self.client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=500,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Extract JSON from response
            response_text = response.content[0].text
            
            # Try to parse the JSON
            try:
                suggestions_raw = json.loads(response_text)
            except json.JSONDecodeError:
                # If direct parsing fails, try to extract JSON from the response
                json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
                if json_match:
                    suggestions_raw = json.loads(json_match.group())
                else:
                    print(f"Could not parse Claude response: {response_text}")
                    return []
            
            # Filter out labels that the page already has
            existing_labels = [label.lower() for label in page.get('labels', [])]
            suggestions = []
            
            for suggestion in suggestions_raw:
                if suggestion['label'].lower() not in existing_labels:
                    suggestions.append({
                        'label': suggestion['label'],
                        'confidence': float(suggestion['confidence']),
                        'reason': suggestion['reason']
                    })
            
            return suggestions
            
        except Exception as e:
            print(f"Error generating suggestions for page {page.get('title', 'Unknown')}: {str(e)}")
            return []
    
    def generate_batch_suggestions(self, pages: List[Dict[str, Any]], all_labels_in_space: List[str], cluster_info: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Generate suggestions for multiple pages.
        
        Returns:
            Dictionary mapping page_id to list of suggestions
        """
        results = {}
        
        for page in pages:
            suggestions = self.generate_label_suggestions(page, all_labels_in_space, cluster_info)
            if suggestions:
                results[page['id']] = suggestions
        
        return results