CREATE TABLE IF NOT EXISTS jobs (
    id uuid PRIMARY KEY,
    filename text NOT NULL,
    document bytea,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'queued', 'completed', 'failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at timestamptz NOT NULL DEFAULT now(),
    result text,
    error text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jobs_pending_idx ON jobs (available_at, created_at)
    WHERE status = 'pending';
