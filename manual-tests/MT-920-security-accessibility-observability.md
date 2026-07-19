# MT-920: Security, Accessibility, Observability

## Cases
1. **Authorization**: Unauthorized actor cannot run S3-F10 through S3-F14 operations
2. **Input validation**: Malformed input returns stable machine-readable error
3. **Path traversal**: Artifact IDs with path traversal characters are rejected
4. **Observability**: All operations emit metrics, events, and logs
5. **Secret redaction**: Logs do not contain secrets or tokens
