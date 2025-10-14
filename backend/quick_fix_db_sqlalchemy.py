#!/usr/bin/env python3
"""
Quick database schema fix for recommendation_events table
Adds missing bandit experiment columns
"""

import os
import sys
import logging
from sqlalchemy import create_engine, text, inspect

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_column_exists(engine, table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def fix_recommendation_events_schema():
    """Add missing columns to recommendation_events table"""
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL not found in environment")
        return False
    
    try:
        # Create engine
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            logger.info("🔧 Checking recommendation_events table schema...")
            
            # List of columns to add
            columns_to_add = [
                ("experiment_id", "UUID NULL"),
                ("policy", "VARCHAR(20) NULL"),
                ("arm_id", "VARCHAR(50) NULL"),
                ("p_score", "FLOAT NULL"),
                ("latency_ms", "INTEGER NULL"),
                ("reward", "FLOAT NULL"),
                ("served_at", "TIMESTAMPTZ NULL")
            ]
            
            added_count = 0
            
            for column_name, column_type in columns_to_add:
                if not check_column_exists(engine, 'recommendation_events', column_name):
                    # Column doesn't exist, add it
                    alter_sql = f"ALTER TABLE recommendation_events ADD COLUMN {column_name} {column_type}"
                    conn.execute(text(alter_sql))
                    logger.info(f"✅ Added column: {column_name}")
                    added_count += 1
                else:
                    logger.info(f"ℹ️  Column {column_name} already exists")
            
            # Create indexes if they don't exist
            indexes_to_create = [
                ("idx_recommendation_events_experiment_id", "CREATE INDEX IF NOT EXISTS idx_recommendation_events_experiment_id ON recommendation_events(experiment_id)"),
                ("idx_recommendation_events_policy", "CREATE INDEX IF NOT EXISTS idx_recommendation_events_policy ON recommendation_events(policy)"),
                ("idx_recommendation_events_arm_id", "CREATE INDEX IF NOT EXISTS idx_recommendation_events_arm_id ON recommendation_events(arm_id)"),
                ("idx_recommendation_events_served_at", "CREATE INDEX IF NOT EXISTS idx_recommendation_events_served_at ON recommendation_events(served_at)")
            ]
            
            for index_name, create_sql in indexes_to_create:
                try:
                    conn.execute(text(create_sql))
                    logger.info(f"✅ Created index: {index_name}")
                except Exception as e:
                    logger.warning(f"⚠️  Index {index_name} may already exist: {e}")
            
            # Commit changes
            conn.commit()
            
            logger.info(f"✅ Schema fix completed! Added {added_count} columns.")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error fixing schema: {e}")
        return False

if __name__ == "__main__":
    success = fix_recommendation_events_schema()
    sys.exit(0 if success else 1)
