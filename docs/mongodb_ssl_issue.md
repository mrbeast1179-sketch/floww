# MongoDB Atlas SSL Issue — 2026-05-18

## Symptoms
- All 3 shards fail SSL handshake: `errno=54 Connection reset by peer`
- TCP connection succeeds (`nc -zv` works)
- SSL handshake fails immediately (0 bytes read)
- Affects all connection methods: srv, direct, tlsInsecure

## Tried
- certifi update
- tlsInsecure flag
- Direct connection string (bypassing SRV)
- Different TLS versions
- All fail with same error

## Likely cause
- Atlas-side SSL certificate rotation or configuration change
- May require IP allowlist update on Atlas dashboard
- Or temporary Atlas service degradation

## Impact
- Cannot retrain SPY v2.0 with GEX features
- Cannot run paper-trade dry-run
- Cannot verify feature quality

## Next steps
1. Check MongoDB Atlas dashboard for alerts
2. Verify IP allowlist includes current IP
3. Try from different network (hotspot)
4. Contact Atlas support if persistent
