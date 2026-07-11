# Delivery

Owns final publication checks, delivery manifests, conflict policy, temporary
publication directories, and atomic `migrated-app` rename behavior where
supported.

Delivery must occur only after the final assurance and delivery gates pass. It
must not expose failed, cancelled, or incomplete work as final output, overwrite
existing output without policy, or mutate the original source.

Canonical Sprint 0 publication path:

```text
{target}/migrated-app/
```

`DeliveryService` copies workspace output into a temporary sibling directory and
renames it into `migrated-app`. The default conflict policy fails when output
already exists; replacement must be requested explicitly. Failed, cancelling,
cancelled, and diagnostic-hold runs return a blocked delivery manifest and do
not create final output.
