#!/usr/bin/env python3
"""
Simple migration script that uses the existing SQLAlchemy engine
Adds missing bandit experiment columns to recommendation_events table
"""

import os
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_recommendation_events():
    """Add missing bandit experiment columns to recommendation_events table"""
    
    try:
        # Import the existing database engine
        from database import engine
        from sqlalchemy import text
        
        logger.info("🔧 Migrating recommendation_events table using existing SQLAlchemy engine...")
        
        with engine.connect() as conn:
            # List of columns to add with their types
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
                # Check if column exists
                result = conn.execute(text(f"""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'recommendation_events' 
                    AND column_name = '{column_name}'
                """))
                
                if result.fetchone() is None:
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
            
            logger.info(f"✅ Migration completed! Added {added_count} columns.")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error during migration: {e}")
        return False

if __name__ == "__main__":
    success = migrate_recommendation_events()
    sys.exit(0 if success else 1)
