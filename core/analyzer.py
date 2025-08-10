# core/analyzer.py - Pure analysis logic
import json
from typing import List, Dict, Any, Tuple

class ClusterAnalyzer:
    """
    Pure analysis functions.
    Takes data, returns analysis results.
    No knowledge of where data comes from or goes.
    """
    
    def find_clusters(self, pages_data: List[Tuple], cluster_label: str) -> List[Dict[str, Any]]:
        """
        Find clusters based on a specific label.
        
        Args:
            pages_data: List of tuples (id, title, labels_json)
            cluster_label: The label that identifies cluster directories
            
        Returns:
            List of cluster dictionaries
        """
        clusters = []
        
        for page_id, title, labels_json in pages_data:
            labels = json.loads(labels_json) if labels_json else []
            
            if cluster_label in labels:
                clusters.append({
                    'id': page_id,
                    'title': title,
                    'labels': labels
                })
        
        return clusters
    
    def find_orphans(self, pages_data: List[Tuple], clusters: List[Dict]) -> List[str]:
        """
        Find pages that don't belong to any cluster.
        
        Args:
            pages_data: All pages
            clusters: Identified clusters
            
        Returns:
            List of orphan page IDs
        """
        cluster_ids = {c['id'] for c in clusters}
        orphans = []
        
        for page_id, _, _ in pages_data:
            if page_id not in cluster_ids:
                # More logic would go here to check membership
                orphans.append(page_id)
        
        return orphans
    
    def analyze_label_patterns(self, pages_data: List[Tuple]) -> Dict[str, int]:
        """
        Analyze label usage patterns.
        
        Returns:
            Dictionary of label -> count
        """
        label_counts = {}
        
        for _, _, labels_json in pages_data:
            labels = json.loads(labels_json) if labels_json else []
            for label in labels:
                label_counts[label] = label_counts.get(label, 0) + 1
        
        return label_counts