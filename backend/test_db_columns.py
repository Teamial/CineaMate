#!/usr/bin/env python3
"""
Test script to verify recommendation_events table columns
"""

import os
import sys
import logging
from sqlalchemy import create_engine, text, inspect

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_recommendation_events_columns():
    """Test if all required columns exist in recommendation_events table"""
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL not found in environment")
        return False
    
    try:
        # Create engine
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            logger.info("🔍 Testing recommendation_events table columns...")
            
            # Get all columns in the table
            inspector = inspect(engine)
            columns = [col['name'] for col in inspector.get_columns('recommendation_events')]
            
            # Required columns for bandit experiments
            required_columns = [
                'experiment_id', 'policy', 'arm_id', 'p_score', 
                'latency_ms', 'reward', 'served_at'
            ]
            
            missing_columns = []
            existing_columns = []
            
            for col in required_columns:
                if col in columns:
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

if __name__ == "__main__":
    success = test_recommendation_events_columns()
    sys.exit(0 if success else 1)
