# integrations/db_manager.py - Pure database abstraction
import sqlite3
from typing import List, Tuple, Any

class DatabaseManager:
    """
    Pure database abstraction layer.
    Only knows how to execute SQL and return results.
    No application logic, no table knowledge, just SQL execution.
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def execute_query(self, query: str, params: Tuple = ()) -> List[Tuple[Any, ...]]:
        """
        Execute a SQL query and return results.
        
        Args:
            query: Raw SQL string
            params: Parameters for parameterized queries (if the DB supports it)
        
        Returns:
            List of tuples containing query results
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(query, params)
            
            # If it's a SELECT query, fetch results
            if query.strip().upper().startswith('SELECT'):
                results = cursor.fetchall()
            else:
                # For INSERT/UPDATE/DELETE, commit and return empty
                conn.commit()
                results = []
                
            return results
            
        finally:
            conn.close()
    
    def execute_many(self, query: str, params_list: List[Tuple]) -> None:
        """
        Execute the same query multiple times with different parameters.
        
        Args:
            query: Raw SQL string
            params_list: List of parameter tuples
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.executemany(query, params_list)
            conn.commit()
        finally:
            conn.close()