> Historical project notes. Paths, operational status, badges and test claims below are retained as archival reference and have not all been revalidated. Use the root README and docs/REVIEW.md for this review snapshot.

# Multichain Project Discovery

A multi-stage Python discovery pipeline that collects social observations, classifies projects and tracks launch evidence.

![review](https://img.shields.io/badge/review-private-374151) ![primary](https://img.shields.io/badge/primary-Python-2563EB) [![LinkedIn](https://img.shields.io/badge/LinkedIn-Douglas%20Silva-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/douglas-silva-data-analyst/)

[Overview](#overview) · [Architecture](#architecture) · [Setup](#setup) · [Validation](#validation) · [Roadmap](#roadmap) · [Review notes](docs/REVIEW.md)

## Overview

- Collector, triage, verification and monitoring services have separate responsibilities.
- Chain-address extraction and project scoring enrich observations.
- Messaging services route stage-specific summaries.

**Technology:** Python · Redis Pub/Sub · SQLite WAL · Docker Compose · LLM API adapter · Telegram integrations

**Persistence and data:** Redis routes service messages; SQLite stores projects, social observations and operational state. Supabase integration code is also present.

## Architecture

```text
Social input → collector → classifier/triage → project verification → launch monitoring → configured notifications
```

| Location | Review focus |
| --- | --- |
| [`project-agent/project-agent/agent/analyzer.py`](project-agent/project-agent/agent/analyzer.py) | Source/configuration inspected for scope and structure |
| [`project-agent/project-agent/agent/database.py`](project-agent/project-agent/agent/database.py) | Source/configuration inspected for scope and structure |
| [`project-agent/project-agent/services`](project-agent/project-agent/services) | Source/configuration inspected for scope and structure |
| [`rl-agent`](rl-agent) | Source/configuration inspected for scope and structure |
| [`project-agent/project-agent/docker-compose.yml`](project-agent/project-agent/docker-compose.yml) | Source/configuration inspected for scope and structure |

Internal package and module names are retained where changing them would affect imports or compatibility. This descriptive repository name does not imply a completed package/API migration.

## Setup

Inspect the nested compose and requirements files. Configure credentials locally; empty defaults are intentional after cleanup. Do not start every service merely to inspect the pipeline.

Start from an isolated environment. Use `.env.example` when present and inspect the configuration loader: an example file is not necessarily loaded automatically. Runtime databases, real account sessions and private credentials are not bundled. Live integration prerequisites are separate from local tests.

## Validation

Static parsing checked 111 Python files and 0 strict JSON files. Python syntax errors: 0; JSON errors: 0. No functional test/build result is claimed for this preparation.

Available test scripts are inventoried in [the review notes](docs/REVIEW.md). Choose offline checks before operating any integration.

These results apply to the selected checks on the preparation copy. They do not establish deployment readiness, full coverage, live provider availability or measured performance. CI definitions, when present under `docs/ci-templates/`, are inactive review templates; no remote CI badge is claimed.

## Limits and current status

Multiple local versions remain in this review. Embedded API/JWT/bot fallbacks were removed, but this is not a completed security audit. Known project notes identify oversized batches, cookie handling and routing issues. No service or LLM request was run.

This private snapshot is for code and portfolio review. Generated runtime material and unreviewed binary assets may be excluded. [Review notes](docs/REVIEW.md) record preparation scope, findings and outstanding validation.

## Roadmap

- [ ] Choose one canonical version and compare the alternatives before deletion.
- [ ] Replace cookie/session configuration with explicit local secret loading.
- [ ] Fix documented batch-size and channel-routing problems with offline regressions.

## History and attribution

No recoverable original Git history was verified for this snapshot. Import and preparation commits use their actual current dates; filesystem timestamps are not treated as development dates.

No open-source license is granted by this preparation. A license and attribution review is required before public redistribution.

## Maintainer and feedback

Douglas de Oliveira Silva · [GitHub](https://github.com/qquante) · [LinkedIn](https://www.linkedin.com/in/douglas-silva-data-analyst/)

For this private review, report reproducible issues with a minimal fixture and the exact check output. Keep account data, credentials and generated sensitive reports out of issues and commits. Existing contribution guidelines apply where present.

**Topics:** `python`, `redis`, `sqlite`, `docker-compose`, `applied-ai`, `data-pipeline`, `social-data`
