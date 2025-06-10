-- Migration: Rename position_type to position_status and change entry_time/exit_time to entry_date/exit_date
ALTER TABLE positions RENAME COLUMN position_type TO position_status;
ALTER TABLE positions RENAME COLUMN entry_time TO entry_date;
ALTER TABLE positions RENAME COLUMN exit_time TO exit_date;
-- Update unique constraint if present
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'unique_ticker_platform_positiontype' AND table_name = 'positions'
    ) THEN
        ALTER TABLE positions DROP CONSTRAINT unique_ticker_platform_positiontype;
    END IF;
END $$;
ALTER TABLE positions ADD CONSTRAINT unique_ticker_platform_status UNIQUE (ticker, platform_id, position_status);
