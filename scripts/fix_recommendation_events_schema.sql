-- Add missing bandit experiment columns to recommendation_events table
-- This fixes the "column recommendation_events.policy does not exist" error

-- Check if columns exist and add them if they don't
DO $$
BEGIN
    -- Add experiment_id column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'recommendation_events' AND column_name = 'experiment_id') THEN
        ALTER TABLE recommendation_events ADD COLUMN experiment_id UUID NULL;
        RAISE NOTICE 'Added experiment_id column';
    ELSE
        RAISE NOTICE 'experiment_id column already exists';
    END IF;

    -- Add policy column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'recommendation_events' AND column_name = 'policy') THEN
        ALTER TABLE recommendation_events ADD COLUMN policy VARCHAR(20) NULL;
        RAISE NOTICE 'Added policy column';
    ELSE
        RAISE NOTICE 'policy column already exists';
    END IF;

    -- Add arm_id column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'recommendation_events' AND column_name = 'arm_id') THEN
        ALTER TABLE recommendation_events ADD COLUMN arm_id VARCHAR(50) NULL;
        RAISE NOTICE 'Added arm_id column';
    ELSE
        RAISE NOTICE 'arm_id column already exists';
    END IF;

    -- Add p_score column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'recommendation_events' AND column_name = 'p_score') THEN
        ALTER TABLE recommendation_events ADD COLUMN p_score FLOAT NULL;
        RAISE NOTICE 'Added p_score column';
    ELSE
        RAISE NOTICE 'p_score column already exists';
    END IF;

    -- Add latency_ms column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'recommendation_events' AND column_name = 'latency_ms') THEN
        ALTER TABLE recommendation_events ADD COLUMN latency_ms INTEGER NULL;
        RAISE NOTICE 'Added latency_ms column';
    ELSE
        RAISE NOTICE 'latency_ms column already exists';
    END IF;

    -- Add reward column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'recommendation_events' AND column_name = 'reward') THEN
        ALTER TABLE recommendation_events ADD COLUMN reward FLOAT NULL;
        RAISE NOTICE 'Added reward column';
    ELSE
        RAISE NOTICE 'reward column already exists';
    END IF;

    -- Add served_at column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'recommendation_events' AND column_name = 'served_at') THEN
        ALTER TABLE recommendation_events ADD COLUMN served_at TIMESTAMPTZ NULL;
        RAISE NOTICE 'Added served_at column';
    ELSE
        RAISE NOTICE 'served_at column already exists';
    END IF;
END $$;

-- Create indexes for performance (only if they don't exist)
CREATE INDEX IF NOT EXISTS idx_recommendation_events_experiment_id ON recommendation_events(experiment_id);
CREATE INDEX IF NOT EXISTS idx_recommendation_events_policy ON recommendation_events(policy);
CREATE INDEX IF NOT EXISTS idx_recommendation_events_arm_id ON recommendation_events(arm_id);
CREATE INDEX IF NOT EXISTS idx_recommendation_events_served_at ON recommendation_events(served_at);

-- Verify the columns were added
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'recommendation_events' 
AND column_name IN ('experiment_id', 'policy', 'arm_id', 'p_score', 'latency_ms', 'reward', 'served_at')
ORDER BY column_name;
