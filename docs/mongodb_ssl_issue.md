# MongoDB Atlas SSL Issue — Update 2026-05-18

## Status: Persistent SSL failure

Even OpenSSL (`s_client`) fails with errno=54 (Connection reset by peer).
The server sends RST immediately after TCP handshake.
This is NOT a Python or certifi issue — it's server-side.

## Possible causes
1. IP allowlist changed on Atlas dashboard
2. Cluster TLS certificate rotation
3. Atlas service degradation
4. Network policy change

## What works
- TCP connection: `nc -zv` succeeds
- DNS resolution: SRV records resolve correctly
- Ping: host responds to ICMP

## What fails
- SSL handshake: immediate RST from server
- All Python MongoDB connection methods
- OpenSSL s_client

## Action needed
1. Check MongoDB Atlas dashboard for alerts
2. Verify IP allowlist includes current IP
3. Check if cluster needs TLS reconfiguration
4. Try from different network (hotspot/VPN)
