def initialize(sql):
    sql.exec(
        "CREATE TABLE IF NOT EXISTS nonces "
        "(nonce_hash TEXT PRIMARY KEY, expires_at_ms INTEGER NOT NULL)"
    )
    sql.exec("CREATE INDEX IF NOT EXISTS nonces_expiry ON nonces(expires_at_ms)")


def reserve(sql, nonce_hash, expires_at_ms, now_ms):
    # No await between these synchronous SQL calls: Durable Object storage
    # groups the writes atomically and cannot interleave another request.
    sql.exec("DELETE FROM nonces WHERE expires_at_ms <= ?", now_ms)
    rows = sql.exec(
        "INSERT OR IGNORE INTO nonces (nonce_hash, expires_at_ms) "
        "VALUES (?, ?) RETURNING nonce_hash",
        nonce_hash,
        expires_at_ms,
    ).toArray()
    return len(rows) == 1
