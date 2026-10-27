-- Preserve point-in-time strike observations so expiry rollover can be
-- measured across runs instead of overwriting the previous observation.
DROP INDEX IF EXISTS option_strike_observations_expiration_id_strike_key;

ALTER TABLE option_strike_observations
    DROP CONSTRAINT IF EXISTS option_strike_observations_expiration_id_strike_key;

CREATE UNIQUE INDEX IF NOT EXISTS option_strike_observations_expiration_strike_observed_at_key
    ON option_strike_observations (expiration_id, strike, observed_at);

CREATE INDEX IF NOT EXISTS option_strike_observations_expiry_observed_at_idx
    ON option_strike_observations (expiration_id, observed_at DESC);

COMMENT ON INDEX option_strike_observations_expiration_strike_observed_at_key IS
    'Point-in-time option OI/GEX observation identity; preserves history for rollover analysis.';
