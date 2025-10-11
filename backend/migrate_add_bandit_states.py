#!/usr/bin/env python3
"""
Add bandit_states table to database for Thompson Sampling
Creates:
- bandit_states: Store alpha/beta parameters for multi-armed bandit algorithm selection
"""
import os
import sys
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv

load_dotenv()

def add_bandit_states_table():
    """Add bandit_states table for Thompson Sampling"""
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        sys.exit(1)
    
    # Fix for SQLAlchemy 1.4+: replace postgres:// with postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
        print("ℹ️  Converted postgres:// to postgresql:// for SQLAlchemy 1.4+")
    
    print("🎰 Adding bandit_states table for Thompson Sampling...")
    print(f"Database: {database_url.split('@')[1] if '@' in database_url else 'localhost'}\n")
    
    engine = create_engine(database_url)
    inspector = inspect(engine)
    
    try:
        with engine.connect() as conn:
            # Create bandit_states table
            if 'bandit_states' not in inspector.get_table_names():
                print("📊 Creating bandit_states table...")
                conn.execute(text("""
                    CREATE TABLE bandit_states (
                        id SERIAL PRIMARY KEY,
                        context_key VARCHAR(200) NOT NULL,
                        algorithm VARCHAR(50) NOT NULL,
                        
                        alpha FLOAT DEFAULT 1.0 NOT NULL,
                        beta FLOAT DEFAULT 1.0 NOT NULL,
                        
                        total_pulls INTEGER DEFAULT 0,
                        total_successes INTEGER DEFAULT 0,
                        total_failures INTEGER DEFAULT 0,
                        
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                    )
                """))
                
                # Add indexes for efficient lookups
                conn.execute(text("CREATE INDEX idx_bandit_context ON bandit_states(context_key)"))
                conn.execute(text("CREATE INDEX idx_bandit_algo ON bandit_states(algorithm)"))
                conn.execute(text("CREATE UNIQUE INDEX idx_bandit_context_algo ON bandit_states(context_key, algorithm)"))
                
                conn.commit()
                print("✅ Created bandit_states table with indexes")
            else:
                print("ℹ️  bandit_states table already exists")
            
            print("\n✨ Migration completed successfully!")
            print("\nNext steps:")
            print("1. Restart your API server")
            print("2. The bandit selector will automatically start learning")
            print("3. Monitor performance with: python backend/ml/monitoring_alerts.py")
            
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    add_bandit_states_table()

