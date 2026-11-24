-- =============================================================================
-- transfer_positions.sql
--
-- Move OPEN positions (stocks/ETFs, long & short) and OPEN option trades from one
-- platform to another, WITHOUT disturbing historical (closed) records, realized
-- P&L, or tax calculations. Pure PostgreSQL - run it in your hosted database's
-- SQL console (Supabase / Neon / RDS / psql ...), no Python needed.
--
-- HOW IT WORKS
--   1. Replays the source platform's trades with FIFO (same rules as
--      sync_positions_from_trades() in db/db_utils.py) to find the open lots.
--   2. Open lot from a trade that was never sold      -> trade re-pointed to target.
--   3. Open lot from a PARTIALLY sold trade           -> trade shrunk to the sold
--      quantity (stays on source, so closed P&L is identical) and a new trade for
--      the unsold remainder is created on target with the ORIGINAL date and price
--      (holding period + cost basis preserved).
--   4. Open option_trades (status='open') are re-pointed to target. Closed/expired
--      ones stay put. option_trade_legs follow automatically (keyed by trade id).
--   5. The `positions` table is updated for the affected open lots only.
--      Closed position rows are never touched.
--   6. Optional cash transfer (cash_flows rows + platforms.cash_available).
--   7. Integrity checks run inside the transaction and abort it on any mismatch.
--
-- SAFETY
--   * The whole script is ONE transaction and ends with ROLLBACK by default (dry run).
--     Review the result grid, then change the last statement to COMMIT and re-run.
--   * Take a backup first (e.g. your provider's snapshot or pg_dump).
--   * Run it in a single session/script execution (temp tables are used).
--
-- STEP 1: edit the CONFIG block below.  STEP 2: run whole script (dry run).
-- STEP 3: if the output looks right, replace ROLLBACK with COMMIT at the bottom.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- CONFIG  (edit these values only)
-- -----------------------------------------------------------------------------
CREATE TEMP TABLE xfer_params ON COMMIT DROP AS
SELECT s.id   AS source_id,
       s.name AS source_name,
       t.id   AS target_id,
       t.name AS target_name,
       cfg.tickers,
       cfg.cash,
       cfg.force,
       cfg.allow_oversell
FROM (
    SELECT
        'WEBULL'::text  AS source_name,   -- platform to move FROM (platforms.name, case-insensitive)
        'ROBINHOOD'::text     AS target_name,   -- platform to move TO
        ARRAY['VOO','QQQ','MSFT','MELI','BULL','VXF','VXUS','INTU','SOFI','GLDM']::text[] AS tickers,  -- NULL = all open holdings
        0::numeric         AS cash,          -- cash to move between the platforms (0 = none)
        true              AS force,         -- true = skip the "target has later sells" safety stop
        true               AS allow_oversell -- true = ignore sells that exceed what was ever bought (app does the same); they are listed as NOTE rows in the result
) cfg
JOIN platforms s ON upper(btrim(s.name)) = upper(btrim(cfg.source_name))
JOIN platforms t ON upper(btrim(t.name)) = upper(btrim(cfg.target_name));

-- -----------------------------------------------------------------------------
-- Normalized source-platform trades (in scope)
-- kind = 'open'  : Long buy  / Short sell   (creates a lot)
-- kind = 'close' : Long sell / Short buy    (consumes lots FIFO)
-- -----------------------------------------------------------------------------
CREATE TEMP TABLE xfer_trades ON COMMIT DROP AS
SELECT n.*,
       CASE WHEN (n.dir = 'Long'  AND n.ttype = 'buy')
              OR (n.dir = 'Short' AND n.ttype = 'sell') THEN 'open' ELSE 'close' END AS kind
FROM (
    SELECT tr.id, tr.ticker, tr.price, round(tr.quantity, 6) AS quantity, tr.date,
           lower(btrim(tr.trade_type))                          AS ttype,
           initcap(btrim(coalesce(tr.direction, 'Long')))       AS dir
    FROM trades tr, xfer_params p
    WHERE tr.platform_id = p.source_id
      AND (p.tickers IS NULL OR tr.ticker = ANY (SELECT upper(btrim(x)) FROM unnest(p.tickers) x))
      AND tr.quantity <> 0
) n
WHERE n.ttype IN ('buy', 'sell');

-- -----------------------------------------------------------------------------
-- FIFO open lots: earliest opening trades are consumed first by closing trades,
-- so a lot survives if (cumulative opened qty) > (effective closed qty).
--
-- Like sync_positions_from_trades(), a closing trade larger than what is open at that
-- moment (e.g. fractional-share rounding) only consumes what exists; the excess is
-- ignored. With S = running (open - close) sum, the ignored excess in total is
-- GREATEST(0, -MIN(S)) (reflected random walk), so effective closed = closed - excess.
-- -----------------------------------------------------------------------------
CREATE TEMP TABLE xfer_lots ON COMMIT DROP AS
WITH running AS (
    SELECT ticker, dir,
           SUM(CASE WHEN kind = 'open' THEN quantity ELSE -quantity END)
               OVER (PARTITION BY ticker, dir ORDER BY date, id) AS s
    FROM xfer_trades
),
excess AS (
    SELECT ticker, dir, GREATEST(0, -MIN(s)) AS ignored_qty
    FROM running GROUP BY ticker, dir
),
closed AS (
    SELECT t.ticker, t.dir,
           SUM(t.quantity) - COALESCE(MAX(e.ignored_qty), 0) AS closed_qty
    FROM xfer_trades t
    LEFT JOIN excess e ON e.ticker = t.ticker AND e.dir = t.dir
    WHERE t.kind = 'close'
    GROUP BY t.ticker, t.dir
),
opened AS (
    SELECT x.*, SUM(x.quantity) OVER (PARTITION BY x.ticker, x.dir ORDER BY x.date, x.id) AS cum_end
    FROM xfer_trades x WHERE x.kind = 'open'
)
SELECT o.id        AS trade_id,
       o.ticker,
       o.dir,
       o.price,
       o.date,
       o.quantity  AS original_qty,
       LEAST(o.quantity, o.cum_end - COALESCE(c.closed_qty, 0)) AS remaining
FROM opened o
LEFT JOIN closed c ON c.ticker = o.ticker AND c.dir = o.dir
WHERE o.cum_end - COALESCE(c.closed_qty, 0) > 0.000001;

-- Sells/covers that exceeded what was open (ignored by the app's FIFO too)
CREATE TEMP TABLE xfer_excess ON COMMIT DROP AS
SELECT ticker, dir, GREATEST(0, -MIN(s)) AS ignored_qty
FROM (
    SELECT ticker, dir,
           SUM(CASE WHEN kind = 'open' THEN quantity ELSE -quantity END)
               OVER (PARTITION BY ticker, dir ORDER BY date, id) AS s
    FROM xfer_trades
) r
GROUP BY ticker, dir
HAVING MIN(s) < -0.000001;

-- Open options to move
CREATE TEMP TABLE xfer_opts ON COMMIT DROP AS
SELECT ot.id, ot.ticker, ot.strategy, ot.quantity, ot.trade_date, ot.option_open_price
FROM option_trades ot, xfer_params p
WHERE ot.platform_id = p.source_id
  AND ot.status = 'open'
  AND (p.tickers IS NULL OR ot.ticker = ANY (SELECT upper(btrim(x)) FROM unnest(p.tickers) x));

-- Pre-flight snapshots for integrity verification
CREATE TEMP TABLE xfer_snap_net ON COMMIT DROP AS
SELECT ticker,
       initcap(btrim(coalesce(direction, 'Long'))) AS dir,
       SUM(CASE WHEN (initcap(btrim(coalesce(direction,'Long'))) = 'Long'  AND lower(btrim(trade_type)) = 'buy')
                  OR (initcap(btrim(coalesce(direction,'Long'))) = 'Short' AND lower(btrim(trade_type)) = 'sell')
                THEN quantity ELSE -quantity END) AS net_qty
FROM trades
GROUP BY ticker, initcap(btrim(coalesce(direction, 'Long')));

CREATE TEMP TABLE xfer_snap_closed ON COMMIT DROP AS
SELECT platform_id, COUNT(*) AS n, COALESCE(SUM(profit_loss), 0) AS pl
FROM positions
WHERE position_status = 'close'
GROUP BY platform_id;

-- -----------------------------------------------------------------------------
-- EXECUTION + CHECKS
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    v_src      int;
    v_tgt      int;
    v_src_name text;
    v_tgt_name text;
    v_tickers  text[];
    v_cash     numeric;
    v_force    boolean;
    v_allow_oversell boolean;
    v_bad      record;
    v_n        int;
    v_list     text;
    v_full     int;
    v_split    int;
    v_opts     int;
    v_trades_before int;
    v_trades_after  int;
BEGIN
    SELECT source_id, target_id, source_name, target_name, tickers, cash, force, allow_oversell
      INTO v_src, v_tgt, v_src_name, v_tgt_name, v_tickers, v_cash, v_force, v_allow_oversell
      FROM xfer_params;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Source or target platform name not found in platforms table. Check CONFIG.';
    END IF;
    IF v_src = v_tgt THEN
        RAISE EXCEPTION 'Source and target platform are the same.';
    END IF;
    IF v_cash < 0 THEN
        RAISE EXCEPTION 'cash must be >= 0.';
    END IF;

    -- Guard 1: sells/covers larger than what was ever open. The app's FIFO ignores the
    -- excess, and so does this script (lots match the Positions page). Usually caused by
    -- shares that arrived from another broker without a buy trade, or a split. Set
    -- allow_oversell=false in CONFIG to make this a hard stop instead.
    IF NOT v_allow_oversell THEN
        SELECT ticker, dir, ignored_qty INTO v_bad
        FROM xfer_excess WHERE ignored_qty > 1 LIMIT 1;
        IF FOUND THEN
            RAISE EXCEPTION 'Source trades for % (%) sell/cover % more than were ever open. Likely missing buy trades - fix the data first.',
                v_bad.ticker, v_bad.dir, v_bad.ignored_qty;
        END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM xfer_lots) AND NOT EXISTS (SELECT 1 FROM xfer_opts) AND v_cash = 0 THEN
        RAISE EXCEPTION 'Nothing to transfer: no open lots, no open options and no cash.';
    END IF;

    -- Guard 2: would any moved lot get consumed by an EXISTING sell/cover on the target?
    -- Target FIFO is ordered by date, so a moved lot dated before some target sells can be
    -- matched by them (instead of the target's own lots), changing the target's historical
    -- P&L the next time positions are re-synced. We merge the moved lots into the target's
    -- trade list per (ticker, direction) and check whether the effective closed quantity
    -- (closed - ignored excess) reaches into the moved lot, i.e. > opened qty dated before it.
    WITH merged AS (
        SELECT t.ticker, initcap(btrim(coalesce(t.direction, 'Long'))) AS dir, t.id, t.date,
               round(t.quantity, 6) AS quantity, lower(btrim(t.trade_type)) AS ttype, false AS moved
        FROM trades t
        WHERE t.platform_id = v_tgt AND t.quantity <> 0
          AND EXISTS (SELECT 1 FROM xfer_lots l
                      WHERE l.ticker = t.ticker
                        AND l.dir = initcap(btrim(coalesce(t.direction, 'Long'))))
        UNION ALL
        SELECT l.ticker, l.dir, l.trade_id, l.date, l.remaining,
               CASE WHEN l.dir = 'Long' THEN 'buy' ELSE 'sell' END, true
        FROM xfer_lots l
    ),
    m2 AS (
        SELECT m.*,
               CASE WHEN (m.dir = 'Long' AND m.ttype = 'buy') OR (m.dir = 'Short' AND m.ttype = 'sell')
                    THEN 'open' ELSE 'close' END AS kind
        FROM merged m WHERE m.ttype IN ('buy', 'sell')
    ),
    run AS (
        SELECT m2.*,
               SUM(CASE WHEN kind = 'open' THEN quantity ELSE -quantity END)
                   OVER (PARTITION BY ticker, dir ORDER BY date, id) AS s,
               SUM(CASE WHEN kind = 'open' THEN quantity ELSE 0 END)
                   OVER (PARTITION BY ticker, dir ORDER BY date, id
                         ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS open_before
        FROM m2
    ),
    agg AS (
        SELECT ticker, dir,
               SUM(CASE WHEN kind = 'close' THEN quantity ELSE 0 END) - GREATEST(0, -MIN(s)) AS c_eff
        FROM run GROUP BY ticker, dir
    )
    SELECT COUNT(*), string_agg(DISTINCT r.ticker, ', ' ORDER BY r.ticker)
      INTO v_n, v_list
    FROM run r
    JOIN agg a ON a.ticker = r.ticker AND a.dir = r.dir
    WHERE r.moved AND a.c_eff > COALESCE(r.open_before, 0) + 0.000001;

    IF v_n > 0 AND NOT v_force THEN
        RAISE EXCEPTION '% transferred lot(s) would be consumed by existing sells on % (tickers: %), changing its historical P&L. Move other tickers only (set tickers in CONFIG), or set force=true if intended.',
            v_n, v_tgt_name, v_list;
    END IF;

    SELECT COUNT(*) INTO v_trades_before FROM trades;

    -- 1) Create the target-side trade for the unsold remainder of PARTIALLY sold trades
    INSERT INTO trades (ticker, platform_id, price, quantity, date, trade_type, direction)
    SELECT tr.ticker, v_tgt, tr.price, l.remaining, tr.date, tr.trade_type, tr.direction
    FROM xfer_lots l
    JOIN trades tr ON tr.id = l.trade_id
    WHERE l.remaining < l.original_qty;
    GET DIAGNOSTICS v_split = ROW_COUNT;

    -- 2) Shrink the original trade to the quantity that was actually sold (stays on source)
    UPDATE trades tr
       SET quantity = l.original_qty - l.remaining
      FROM xfer_lots l
     WHERE tr.id = l.trade_id
       AND l.remaining < l.original_qty;

    -- 3) Entirely unsold trades move as-is
    UPDATE trades tr
       SET platform_id = v_tgt
      FROM xfer_lots l
     WHERE tr.id = l.trade_id
       AND l.remaining = l.original_qty;
    GET DIAGNOSTICS v_full = ROW_COUNT;

    -- 4) Open options (legs follow via option_trade_id)
    UPDATE option_trades ot
       SET platform_id = v_tgt
      FROM xfer_opts o
     WHERE ot.id = o.id;
    GET DIAGNOSTICS v_opts = ROW_COUNT;

    -- 5) positions table: replace OPEN rows for the moved scope; closed rows untouched
    DELETE FROM positions
     WHERE platform_id = v_src
       AND position_status = 'open'
       AND (v_tickers IS NULL OR ticker = ANY (SELECT upper(btrim(x)) FROM unnest(v_tickers) x));

    INSERT INTO positions (ticker, trade_type, position_status, entry_price, quantity,
                           entry_date, platform_id, profit_loss, direction)
    SELECT l.ticker, NULL, 'open', l.price, l.remaining, l.date, v_tgt, NULL, l.dir
    FROM xfer_lots l;

    -- 6) Optional cash transfer
    IF v_cash > 0 THEN
        INSERT INTO cash_flows (platform_id, flow_type, amount, flow_date, notes)
        VALUES (v_src, 'withdrawal', v_cash, CURRENT_DATE, 'Transfer to ' || v_tgt_name),
               (v_tgt, 'deposit',    v_cash, CURRENT_DATE, 'Transfer from ' || v_src_name);
        UPDATE platforms SET cash_available = COALESCE(cash_available, 0) - v_cash WHERE id = v_src;
        UPDATE platforms SET cash_available = COALESCE(cash_available, 0) + v_cash WHERE id = v_tgt;
    END IF;

    -- ------------------------- INTEGRITY CHECKS -------------------------------
    -- (a) trade row accounting: only the split inserts add rows
    SELECT COUNT(*) INTO v_trades_after FROM trades;
    IF v_trades_after <> v_trades_before + v_split THEN
        RAISE EXCEPTION 'Integrity check failed: unexpected trade row count change (% -> %).', v_trades_before, v_trades_after;
    END IF;

    -- (b) net shares per ticker/direction across ALL platforms unchanged
    SELECT COALESCE(a.ticker, b.ticker) AS ticker, COALESCE(a.dir, b.dir) AS dir,
           COALESCE(a.net_qty, 0) AS before_qty, COALESCE(b.net_qty, 0) AS after_qty
      INTO v_bad
    FROM xfer_snap_net a
    FULL JOIN (
        SELECT ticker,
               initcap(btrim(coalesce(direction, 'Long'))) AS dir,
               SUM(CASE WHEN (initcap(btrim(coalesce(direction,'Long'))) = 'Long'  AND lower(btrim(trade_type)) = 'buy')
                          OR (initcap(btrim(coalesce(direction,'Long'))) = 'Short' AND lower(btrim(trade_type)) = 'sell')
                        THEN quantity ELSE -quantity END) AS net_qty
        FROM trades
        GROUP BY ticker, initcap(btrim(coalesce(direction, 'Long')))
    ) b ON a.ticker = b.ticker AND a.dir = b.dir
    WHERE abs(COALESCE(a.net_qty, 0) - COALESCE(b.net_qty, 0)) > 0.0001
    LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION 'Integrity check failed: net shares for % (%) changed from % to %.',
            v_bad.ticker, v_bad.dir, v_bad.before_qty, v_bad.after_qty;
    END IF;

    -- (c) closed position history (count + realized P&L) unchanged on every platform
    SELECT COALESCE(a.platform_id, b.platform_id) AS platform_id INTO v_bad
    FROM xfer_snap_closed a
    FULL JOIN (
        SELECT platform_id, COUNT(*) AS n, COALESCE(SUM(profit_loss), 0) AS pl
        FROM positions WHERE position_status = 'close' GROUP BY platform_id
    ) b ON a.platform_id = b.platform_id
    WHERE COALESCE(a.n, 0) <> COALESCE(b.n, 0)
       OR abs(COALESCE(a.pl, 0) - COALESCE(b.pl, 0)) > 0.005
    LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION 'Integrity check failed: closed position history changed for platform id %.', v_bad.platform_id;
    END IF;

    -- (d) every moved lot now exists on target with identical date/price
    IF EXISTS (
        SELECT 1 FROM xfer_lots l
        WHERE NOT EXISTS (
            SELECT 1 FROM trades t
            WHERE t.platform_id = v_tgt AND t.ticker = l.ticker
              AND t.date = l.date AND t.price = l.price
              AND round(t.quantity, 6) >= l.remaining
        )
    ) THEN
        RAISE EXCEPTION 'Integrity check failed: a transferred lot is missing on target platform.';
    END IF;

    RAISE NOTICE 'OK: % trade(s) re-pointed, % trade(s) split, % open option(s) moved, % -> %.',
        v_full, v_split, v_opts, v_src_name, v_tgt_name;
END
$$;

-- -----------------------------------------------------------------------------
-- RESULT: everything this run moved (shown before you commit)
-- -----------------------------------------------------------------------------
SELECT 'STOCK'        AS asset,
       l.ticker,
       l.dir          AS direction_or_strategy,
       l.remaining    AS quantity,
       l.date         AS entry_date,
       l.price        AS cost_basis_or_premium,
       CASE WHEN l.remaining = l.original_qty
            THEN 'reassigned trade #' || l.trade_id
            ELSE 'split trade #' || l.trade_id || ' (kept ' || (l.original_qty - l.remaining) || ' on source)'
       END            AS action
FROM xfer_lots l
UNION ALL
SELECT 'OPTION', o.ticker, o.strategy, o.quantity::numeric, o.trade_date, o.option_open_price,
       'reassigned option trade #' || o.id
FROM xfer_opts o
UNION ALL
SELECT 'NOTE', e.ticker, e.dir, e.ignored_qty, NULL::date, NULL::numeric,
       'sells/covers exceeded buys by ' || e.ignored_qty || ' - ignored (same as app); nothing moved for this excess'
FROM xfer_excess e
ORDER BY 1, 2, 5;

-- -----------------------------------------------------------------------------
-- DRY RUN by default. When the result above is what you expect, change the next
-- line to  COMMIT;  and run the whole script again.
-- -----------------------------------------------------------------------------
ROLLBACK;
--COMMIT;

-- After COMMIT: reload the Streamlit app. Optionally open "Positions" and click
-- "Sync Positions from Trades" - it should leave everything unchanged.
