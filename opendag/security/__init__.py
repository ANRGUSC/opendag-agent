"""Security layer (P3): per-agent Ed25519 identities, signed task envelopes,
hash-chained tamper-evident audit logs, capability manifests, and the
``opendag verify`` CLI.

Beyond audit, the roadmap includes privacy-preserving *partitioned
execution*: sharding data — or model weights — across executors so that
pieces are transferred only at computation time and assembled transiently,
with the task graph (and Wayline's peer-to-peer, scheduler-visible data
plane) deciding which piece is where, when. No single node, and no
single-point adversary, ever holds the complete dataset or model; audit
envelopes then prove it. Scenario A's site-pinned raw data is the first,
simplest instance of the pattern.

Not yet implemented; design in the project plan and docs/SECURITY.md (to
come)."""
