# Delivery

Owns final publication checks, delivery manifests, conflict policy, temporary
publication directories, and atomic `migrated-app` rename behavior where
supported.

Delivery must occur only after the final assurance and delivery gates pass. It
must not expose failed, cancelled, or incomplete work as final output, overwrite
existing output without policy, or mutate the original source.