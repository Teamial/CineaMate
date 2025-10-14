#!/usr/bin/env python3
"""
Test script using psycopg2 to verify recommendation_events table columns
"""

import os
import sys
import logging

# Configure logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import psycopg2
except ImportError:
    try:
        import psycopg2_binary as psycopg2
    except ImportError:
        logger.error("Neither psycopg2 nor psycopg2_binary is available")
        sys.exit(1)
from urllib.parse import urlparse

def get_db_connection():
    """Get database connection using psycopg2"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL not found in environment")
        return None
    
    try:
        # Parse the database URL
        parsed = urlparse(database_url)
        
        # Extract connection parameters
        conn_params = {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path[1:],  # Remove leading slash
            'user': parsed.username,
            'password': parsed.password
        }
        
        # Create connection
        conn = psycopg2.connect(**conn_params)
        return conn
        
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return None

def test_recommendation_events_columns():
    """Test if all required columns exist in recommendation_events table"""
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        logger.info("🔍 Testing recommendation_events table columns using psycopg2...")
        
        # Get all columns in the table
        cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'recommendation_events' 
            ORDER BY column_name
        """)
        
        columns = cursor.fetchall()
        column_names = [col[0] for col in columns]
        
        # Required columns for bandit experiments
        required_columns = [
            'experiment_id', 'policy', 'arm_id', 'p_score', 
            'latency_ms', 'reward', 'served_at'
        ]
        
        missing_columns = []
        existing_columns = []
        
        for col in required_columns:
            if col in column_names:
                existing_columns.append(col)
                logger.info(f"✅ Column {col} exists")
            else:
                missing_columns.append(col)
                logger.error(f"❌ Column {col} missing")
        
        logger.info(f"📊 Summary: {len(existing_columns)}/{len(required_columns)} columns exist")
        
        if missing_columns:
            logger.error(f"❌ Missing columns: {missing_columns}")
            return False
        else:
            logger.info("✅ All required columns exist!")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error testing columns: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    success = test_recommendation_events_columns()
    sys.exit(0 if success else 1)
