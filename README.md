# Multichain Project Discovery

A multi-stage Python discovery pipeline that collects social observations, classifies projects and tracks launch evidence.

## Features

- Collector, triage, verification and monitoring services have separate responsibilities.
- Chain-address extraction and project scoring enrich observations.
- Messaging services route stage-specific summaries.

## Stack

Python · Redis Pub/Sub · SQLite WAL · Docker Compose · LLM API adapter · Telegram integrations

Redis routes service messages; SQLite stores projects, social observations and operational state. Supabase integration code is also present.

## Getting started

Inspect the nested compose and requirements files. Configure credentials locally; empty defaults are intentional after cleanup. Do not start every service merely to inspect the pipeline.

## How it works

```text
Social input → collector → classifier/triage → project verification → launch monitoring → configured notifications
```

## Current limitations

Multiple local versions remain in this review. Embedded API/JWT/bot fallbacks were removed, but this is not a completed security audit. Known project notes identify oversized batches, cookie handling and routing issues. No service or LLM request was run.

## Tests

```console
python -m unittest discover -s tests -v
```

These checks use offline fixtures or controlled backends.

## License

No open-source license has been granted. Redistribution terms remain to be defined.

## Documentation

The pipeline overview and flow reference are maintained in [the main service README](project-agent/project-agent/README.md) and [flow guide](project-agent/project-agent/README_FLOW.md). The alternate service tree shares these guides; duplicate copies are omitted.
