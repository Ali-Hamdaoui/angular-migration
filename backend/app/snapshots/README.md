# Snapshot Service

S1-F07 owns snapshot creation. When implemented, it may write only to the registered alias:

```text
<resolved-output-root>/.migration-factory/runs/<run-id>/source-snapshot/
```
