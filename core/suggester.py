# core/suggester.py - Pure suggestion logic using Claude
from anthropic import Anthropic
from typing import List, Dict, Any

class SuggestionEngine:
    """
    Pure suggestion generation using Claude.
    Takes content, returns suggestions.
    No knowledge of storage or other components.
    """
    
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
    
    def generate_label_suggestions(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate label suggestions for pages.
        
        Args:
            pages: List of page dictionaries with content and existing labels
            
        Returns:
            List of suggestion dictionaries
        """
        suggestions = []
        
        for page in pages:
            prompt = f"""
            Analyze this Confluence page and suggest appropriate labels.
            
            Title: {page['title']}
            Current labels: {', '.join(page.get('labels', []))}
            Content preview: {page.get('content', '')[:500]}
            
            Suggest 1-3 missing labels that would improve organization.
            Format: For each suggestion, provide the label and confidence (0-1).
            """
            
            response = self.client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=200,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse response and create suggestions
            # (This would need proper parsing logic)
            suggestions.append({
                'page_id': page['id'],
                'text': 'suggested-label',  # Parse from response
                'confidence': 0.8  # Parse from response
            })
        
        return suggestions