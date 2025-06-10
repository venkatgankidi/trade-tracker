-- Migration: Update option_trades status constraint to include 'close'
ALTER TABLE option_trades
    DROP CONSTRAINT IF EXISTS option_trades_status_check;
ALTER TABLE option_trades
    ADD CONSTRAINT option_trades_status_check CHECK (
        status::text = ANY (ARRAY['open'::character varying, 'expired'::character varying, 'exercised'::character varying, 'close'::character varying]::text[])
    );
