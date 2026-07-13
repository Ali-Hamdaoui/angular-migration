# Checkpoints

Owns checkpoint metadata and safe resume boundaries.

Checkpoints must be state-bound, workspace-integrity-bound, and policy-bound.
This module must not bypass the transition service, resume from unsafe partial
work, execute commands, or modify artifacts.