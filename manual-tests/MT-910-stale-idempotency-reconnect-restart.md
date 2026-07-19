# MT-910: Stale State, Idempotency, Reconnect, and Restart

## Cases
1. **Stale state version**: Submit request with outdated state_version → expect STALE_STATE_VERSION
2. **Idempotent retry**: Submit same request twice → second returns original result
3. **Idempotent key collision**: Different payload with same key → rejected
4. **Reconnect**: Disconnect SSE, reconnect → replay from last event ID
5. **Restart**: Restart backend → state survives in database
