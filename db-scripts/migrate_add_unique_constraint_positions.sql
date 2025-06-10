-- Add a unique constraint to ensure only one position per ticker/platform/position_type (open or closed) exists
ALTER TABLE positions
ADD CONSTRAINT unique_ticker_platform_positiontype UNIQUE (ticker, platform_id, position_type);
