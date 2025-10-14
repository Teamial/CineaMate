#!/usr/bin/env python3
"""
Quick fix for recommendation_events table schema
Adds missing bandit experiment columns
"""

import os
import sys
from sqlalchemy import create_engine, text

def fix_schema():
    """Add missing columns to recommendation_events table"""
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found in environment")
        return False
    
    try:
        # Create engine
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            print("🔧 Adding missing columns to recommendation_events table...")
            
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
                    print(f"✅ Added column: {column_name}")
                    added_count += 1
                else:
                    print(f"ℹ️  Column {column_name} already exists")
            
            # Create indexes
            indexes_to_create = [
                ("idx_recommendation_events_experiment_id", "CREATE INDEX IF NOT EXISTS idx_recommendation_events_experiment_id ON recommendation_events(experiment_id)"),
                ("idx_recommendation_events_policy", "CREATE INDEX IF NOT EXISTS idx_recommendation_events_policy ON recommendation_events(policy)"),
                ("idx_recommendation_events_arm_id", "CREATE INDEX IF NOT EXISTS idx_recommendation_events_arm_id ON recommendation_events(arm_id)"),
                ("idx_recommendation_events_served_at", "CREATE INDEX IF NOT EXISTS idx_recommendation_events_served_at ON recommendation_events(served_at)")
            ]
            
            for index_name, create_sql in indexes_to_create:
                try:
                    conn.execute(text(create_sql))
                    print(f"✅ Created index: {index_name}")
                except Exception as e:
                    print(f"⚠️  Index {index_name} may already exist: {e}")
            
            # Commit changes
            conn.commit()
            
            print(f"\n✅ Schema fix completed! Added {added_count} columns.")
            return True
            
    except Exception as e:
        print(f"❌ Error fixing schema: {e}")
        return False

if __name__ == "__main__":
    success = fix_schema()
    sys.exit(0 if success else 1)
