#!/usr/bin/env python3
"""
Migration: Add Bandit Experiment Tables and Extend Recommendation Events

This migration adds the complete schema for multi-armed bandit A/B testing:
- experiments: experiment configuration and metadata
- policy_assignments: deterministic user-to-policy assignments
- arm_catalog: stable arm identifiers for algorithms
- policy_states: per-policy state tracking (alpha/beta for Thompson, etc.)
- Extends recommendation_events with experiment tracking fields

Usage:
    python backend/migrate_add_bandit_experiment.py
"""

import sys
import os
from datetime import datetime
import uuid

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from sqlalchemy import text, inspect
from backend.database import engine, SessionLocal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_table_exists(table_name: str) -> bool:
    """Check if a table exists in the database"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def check_column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def check_index_exists(index_name: str) -> bool:
    """Check if an index exists in the database"""
    inspector = inspect(engine)
    indexes = inspector.get_indexes()
    return any(idx['name'] == index_name for idx in indexes)

def run_migration():
    """Execute the bandit experiment migration"""
    
    logger.info("="*60)
    logger.info("BANDIT EXPERIMENT MIGRATION")
    logger.info("="*60)
    
    try:
        db = SessionLocal()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        logger.warning("Skipping bandit migration - database not available")
        return
    
    try:
        # Check if migration already applied
        if check_table_exists('experiments'):
            logger.warning("Migration already applied - experiments table exists")
            return
        
        logger.info("Creating new tables...")
        
        # 1. Create experiments table
        logger.info("Creating experiments table...")
        db.execute(text("""
            CREATE TABLE experiments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(200) NOT NULL,
                start_at TIMESTAMPTZ NOT NULL,
                end_at TIMESTAMPTZ NULL,
                traffic_pct FLOAT NOT NULL DEFAULT 1.0,
                default_policy VARCHAR(20) NOT NULL DEFAULT 'thompson',
                notes TEXT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """))
        
        # 2. Create policy_assignments table
        logger.info("Creating policy_assignments table...")
        
        # Check if users table exists before creating foreign key reference
        if not check_table_exists('users'):
            logger.warning("Users table does not exist. Creating policy_assignments without foreign key constraint.")
            db.execute(text("""
                CREATE TABLE policy_assignments (
                    id SERIAL PRIMARY KEY,
                    experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL,
                    policy VARCHAR(20) NOT NULL,
                    bucket INTEGER NOT NULL CHECK (bucket >= 0 AND bucket <= 99),
                    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(experiment_id, user_id)
                );
            """))
        else:
            db.execute(text("""
                CREATE TABLE policy_assignments (
                    id SERIAL PRIMARY KEY,
                    experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    policy VARCHAR(20) NOT NULL,
                    bucket INTEGER NOT NULL CHECK (bucket >= 0 AND bucket <= 99),
                    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(experiment_id, user_id)
                );
            """))
        
        # 3. Create arm_catalog table
        logger.info("Creating arm_catalog table...")
        db.execute(text("""
            CREATE TABLE arm_catalog (
                arm_id VARCHAR(50) PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                config JSONB NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """))
        
        # 4. Create policy_states table
        logger.info("Creating policy_states table...")
        db.execute(text("""
            CREATE TABLE policy_states (
                id SERIAL PRIMARY KEY,
                policy VARCHAR(20) NOT NULL,
                arm_id VARCHAR(50) NOT NULL,
                context_key VARCHAR(200) NOT NULL DEFAULT 'default',
                count INTEGER NOT NULL DEFAULT 0,
                sum_reward FLOAT NOT NULL DEFAULT 0.0,
                mean_reward FLOAT NOT NULL DEFAULT 0.0,
                alpha FLOAT NOT NULL DEFAULT 1.0,
                beta FLOAT NOT NULL DEFAULT 1.0,
                last_selected_at TIMESTAMPTZ NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(policy, arm_id, context_key)
            );
        """))
        
        # 5. Extend recommendation_events table
        logger.info("Extending recommendation_events table...")
        
        if check_table_exists('recommendation_events'):
            # Check which columns already exist and only add missing ones
            columns_to_add = []
            
            if not check_column_exists('recommendation_events', 'experiment_id'):
                columns_to_add.append("ADD COLUMN experiment_id UUID NULL REFERENCES experiments(id)")
            
            if not check_column_exists('recommendation_events', 'policy'):
                columns_to_add.append("ADD COLUMN policy VARCHAR(20) NULL")
            
            if not check_column_exists('recommendation_events', 'arm_id'):
                columns_to_add.append("ADD COLUMN arm_id VARCHAR(50) NULL")
            
            if not check_column_exists('recommendation_events', 'p_score'):
                columns_to_add.append("ADD COLUMN p_score FLOAT NULL")
            
            if not check_column_exists('recommendation_events', 'latency_ms'):
                columns_to_add.append("ADD COLUMN latency_ms INTEGER NULL")
            
            if not check_column_exists('recommendation_events', 'reward'):
                columns_to_add.append("ADD COLUMN reward FLOAT NULL")
            
            if not check_column_exists('recommendation_events', 'served_at'):
                columns_to_add.append("ADD COLUMN served_at TIMESTAMPTZ NULL")
            
            if columns_to_add:
                alter_sql = f"ALTER TABLE recommendation_events {', '.join(columns_to_add)};"
                db.execute(text(alter_sql))
                logger.info(f"Extended recommendation_events table with {len(columns_to_add)} new columns")
            else:
                logger.info("All bandit columns already exist in recommendation_events table")
        else:
            logger.warning("recommendation_events table does not exist. Skipping extension.")
        
        # 6. Create indexes for performance
        logger.info("Creating indexes...")
        
        # Define all indexes to create
        indexes_to_create = [
            # Experiments indexes
            ("idx_experiments_start_at", "CREATE INDEX idx_experiments_start_at ON experiments(start_at);"),
            ("idx_experiments_end_at", "CREATE INDEX idx_experiments_end_at ON experiments(end_at);"),
            
            # Policy assignments indexes
            ("idx_policy_assignments_experiment_id", "CREATE INDEX idx_policy_assignments_experiment_id ON policy_assignments(experiment_id);"),
            ("idx_policy_assignments_user_id", "CREATE INDEX idx_policy_assignments_user_id ON policy_assignments(user_id);"),
            ("idx_policy_assignments_policy", "CREATE INDEX idx_policy_assignments_policy ON policy_assignments(policy);"),
            
            # Policy states indexes
            ("idx_policy_states_policy_context", "CREATE INDEX idx_policy_states_policy_context ON policy_states(policy, context_key);"),
            ("idx_policy_states_arm_id", "CREATE INDEX idx_policy_states_arm_id ON policy_states(arm_id);"),
            
            # Recommendation events indexes
            ("idx_recommendation_events_experiment_id", "CREATE INDEX idx_recommendation_events_experiment_id ON recommendation_events(experiment_id);"),
            ("idx_recommendation_events_policy", "CREATE INDEX idx_recommendation_events_policy ON recommendation_events(policy);"),
            ("idx_recommendation_events_arm_id", "CREATE INDEX idx_recommendation_events_arm_id ON recommendation_events(arm_id);"),
            ("idx_recommendation_events_served_at", "CREATE INDEX idx_recommendation_events_served_at ON recommendation_events(served_at);")
        ]
        
        # Create indexes only if they don't exist
        indexes_created = 0
        for index_name, create_sql in indexes_to_create:
            if not check_index_exists(index_name):
                try:
                    db.execute(text(create_sql))
                    indexes_created += 1
                    logger.debug(f"Created index: {index_name}")
                except Exception as e:
                    logger.warning(f"Failed to create index {index_name}: {e}")
            else:
                logger.debug(f"Index {index_name} already exists, skipping")
        
        logger.info(f"Created {indexes_created} new indexes")
        
        # 7. Populate arm_catalog with existing algorithms
        logger.info("Populating arm_catalog...")
        arm_catalog_data = [
            ('svd', 'SVD Matrix Factorization', '{"description": "Collaborative filtering via matrix factorization", "type": "collaborative"}'),
            ('embeddings', 'Deep Learning Embeddings', '{"description": "BERT + ResNet embeddings for semantic similarity", "type": "content_based"}'),
            ('graph', 'Knowledge Graph', '{"description": "Graph-based recommendations using movie relationships", "type": "graph"}'),
            ('item_cf', 'Item-based Collaborative Filtering', '{"description": "Item-to-item collaborative filtering", "type": "collaborative"}'),
            ('long_tail', 'Long-tail Discovery', '{"description": "Diversity-focused discovery of underrated gems", "type": "diversity"}'),
            ('serendipity', 'Serendipity Explorer', '{"description": "Unexpected quality recommendations", "type": "serendipity"}'),
            ('hybrid', 'Hybrid Baseline', '{"description": "Traditional hybrid approach (SVD + Item-CF + Content)", "type": "hybrid"}')
        ]
        
        for arm_id, title, config in arm_catalog_data:
            db.execute(text("""
                INSERT INTO arm_catalog (arm_id, title, config) 
                VALUES (:arm_id, :title, :config::jsonb)
                ON CONFLICT (arm_id) DO NOTHING
            """), {"arm_id": arm_id, "title": title, "config": config})
        
        # 8. Backfill existing recommendation_events
        logger.info("Backfilling existing recommendation_events...")
        
        # Count existing events
        result = db.execute(text("SELECT COUNT(*) FROM recommendation_events WHERE experiment_id IS NULL"))
        count = result.scalar()
        logger.info(f"Found {count} existing recommendation_events to backfill")
        
        if count > 0:
            # Set default values for existing events
            db.execute(text("""
                UPDATE recommendation_events 
                SET 
                    policy = CASE 
                        WHEN algorithm LIKE 'bandit_%' THEN 'thompson'
                        WHEN algorithm = 'hybrid' THEN 'hybrid'
                        ELSE 'baseline'
                    END,
                    arm_id = CASE 
                        WHEN algorithm LIKE 'bandit_%' THEN SUBSTRING(algorithm FROM 8)  -- Remove 'bandit_' prefix
                        ELSE algorithm
                    END,
                    p_score = CASE 
                        WHEN algorithm LIKE 'bandit_%' THEN 0.5  -- Default Thompson sampling propensity
                        ELSE 1.0  -- Deterministic baseline
                    END,
                    served_at = created_at
                WHERE experiment_id IS NULL
            """))
            
            logger.info(f"Backfilled {count} recommendation_events with default values")
        
        # Commit all changes
        db.commit()
        
        logger.info("="*60)
        logger.info("MIGRATION COMPLETED SUCCESSFULLY")
        logger.info("="*60)
        
        # Verify tables created
        tables = ['experiments', 'policy_assignments', 'arm_catalog', 'policy_states']
        for table in tables:
            if check_table_exists(table):
                logger.info(f"✓ {table} table created")
            else:
                logger.error(f"✗ {table} table NOT created")
        
        # Verify arm_catalog populated
        result = db.execute(text("SELECT COUNT(*) FROM arm_catalog"))
        arm_count = result.scalar()
        logger.info(f"✓ arm_catalog populated with {arm_count} arms")
        
        # Verify recommendation_events extended
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('recommendation_events')]
        new_columns = ['experiment_id', 'policy', 'arm_id', 'p_score', 'latency_ms', 'reward', 'served_at']
        
        for col in new_columns:
            if col in columns:
                logger.info(f"✓ recommendation_events.{col} column added")
            else:
                logger.error(f"✗ recommendation_events.{col} column NOT added")
        
        logger.info("="*60)
        logger.info("NEXT STEPS:")
        logger.info("1. Verify database schema in your admin tool")
        logger.info("2. Run: python backend/models.py to update ORM models")
        logger.info("3. Test with: python -c 'from backend.models import *; print(\"Models loaded successfully\")'")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
