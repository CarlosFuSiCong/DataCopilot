# Observation

This layer owns runtime signals and dataset inspection tools.

Current modules:

- `risk_rules`: step-level warning and error rules.
- `observations`: separate read-only dataset observation tools.

Future work:

- Convert validation failures, empty results, execution errors, and schema changes into Agent decision signals.
