# Service guide

## API contract

The API contract keeps document provenance with every chunk. A caller can use
the heading path and line range to link a retrieval result back to its source.

## Configuration

Use a small token budget in this corpus so section boundaries, not random text
windows, decide the returned chunks.
