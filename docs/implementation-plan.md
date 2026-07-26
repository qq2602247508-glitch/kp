# Local COC KP Assistant — Remaining Build Plan

## Global constraints

- Work only in `/Users/inagi/codex/700-AI/local-coc-kp-assistant`.
- Never modify, import, start, or write caches into the existing D&D project.
- Product identity is `local-coc-kp-assistant`; ruleset is `coc7e`.
- Use only `COC_KP_*`, backend `8010`, frontend `5180`, database
  `data/coc_kp.db`, vector collection `coc7_rules`.
- COC7 core v1.2.1 is the default authority. Investigator handbook and
  quickstart are subordinate supplements. Optional modules are disabled by
  default. The 40th anniversary rules stay in a separate legacy namespace.
- Source files are read-only. Never execute spreadsheet macros or external
  links. Never copy source books into Git or expose long copyrighted passages.
- Every rule result carries source pack, source filename, page or section,
  edition, module, era, and checksum provenance.
- State lives in SQLite. AI may only create typed proposals; KP confirmation is
  required before state mutation.
- New behavior follows test-first red/green/refactor. Every task passes the
  domain-isolation scan, backend checks, frontend checks, and fresh migrations
  relevant to its changes.

## Task 1: Deterministic local source ingestion

Build a read-only ingestion pipeline for the registered PDF, DOCX, XLSX, and
XLSM sources. It must:

- validate every file against the source catalog;
- compute file checksums and preserve page/sheet provenance;
- extract page-level text from PDFs with an existing text layer;
- extract paragraphs/tables from DOCX;
- extract workbook/sheet/cell values without executing VBA or external links;
- emit deterministic JSON and Markdown records into ignored
  `data/generated-content/coc7`;
- reject missing, changed, encrypted/unreadable, or unsupported sources with a
  machine-readable report;
- default-enable only COC7 core and the approved P1 supplements;
- provide a CLI with dry-run and full-run modes.

## Task 2: COC-only local RAG index

Build provider-neutral chunking, embedding, Qdrant-local indexing, manifest,
incremental rebuild, and search. It must:

- refuse any corpus or manifest whose product/ruleset namespace is not the COC
  product;
- use stable chunk IDs and deterministic heading/page-aware chunking;
- store source pack, edition, tier, module, era, filename, page/section,
  checksum, and enabled-by-default metadata;
- use installed `bge-m3:latest` without downloading models;
- fail closed on incomplete or mismatched indexes;
- filter legacy and optional packs unless explicitly enabled.

## Task 3: Grounded rules search and answer UI

Expose search and grounded-answer APIs and a real Rules workspace. It must:

- return ranked excerpts with structured page/section citations;
- use installed `qwen3:30b-instruct` without downloads;
- treat source text as untrusted evidence;
- validate citation IDs and abstain on insufficient evidence or invalid model
  output;
- allow source-pack, edition, module, and era filtering;
- show the citation and source location clearly in the UI.

## Task 4: Native case, scene, clue, and timeline state

Implement normalized SQLite models, migrations, CRUD, version conflicts, audit,
and UI for cases, sessions, people, locations, scenes, clues, relationships,
handouts, and timeline events. Keep player-visible text separate from KP truth.
The primary narrative structure is a clue network, never a quest/reward model.

## Task 5: SAN, injury, combat, and chase engines

Implement deterministic, cited COC7 operations and logs for SAN loss/frenzy,
temporary/indefinite insanity, wounds/recovery, combat, weapons, and chases.
Never use AC, d20 initiative, five-foot grids, classes, levels, or challenge
ratings.

## Task 6: AI KP orchestration and proposal confirmation

Implement a fixed read-only tool registry for rules, case context, scenes,
clues, investigators, deterministic checks, and draft generation. All writes
become typed pending proposals. Add KP-private hints, scenario draft parsing,
proposal review, confirmation/rejection, prompt-injection defenses, and audit.

## Task 7: Backup, settings, E2E, and delivery

Add source/model readiness, pack toggles, export/import with strict product and
ruleset validation, consistent database/vector backup, browser E2E for the
critical path, desktop launcher regression, full quality gates, project memory,
and final handoff.
