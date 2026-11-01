-- =============================================================================
-- AutoDoctor AI - unified diagnostic database schema (SQLite)
-- =============================================================================
-- Design rules
--  * A DTC code alone is NEVER a unique key. Identity is
--    (code, standard, context) where context can be generic, manufacturer,
--    ECU or vehicle variant.
--  * Every fact is attached to at least one provenance claim (provenance_claims)
--    which in turn points at an immutable source record (source_records).
--  * Conflicting statements are stored side by side and flagged; nothing is
--    silently overwritten because another source disagrees.
--  * Derived values (risk level, canonical definition) carry an explicit rule id.
-- =============================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- 1. Source registry, versions, raw records
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS data_sources (
    id                       INTEGER PRIMARY KEY,
    slug                     TEXT    NOT NULL UNIQUE,
    name                     TEXT    NOT NULL,
    repo_url                 TEXT    NOT NULL,
    code_license             TEXT,
    data_license             TEXT,
    data_license_url         TEXT,
    contents_license         TEXT,
    attribution_required     INTEGER NOT NULL DEFAULT 1 CHECK (attribution_required IN (0, 1)),
    share_alike              INTEGER NOT NULL DEFAULT 0 CHECK (share_alike IN (0, 1)),
    redistribution_allowed   INTEGER CHECK (redistribution_allowed IN (0, 1)),
    commercial_use_allowed   INTEGER CHECK (commercial_use_allowed IN (0, 1)),
    legal_review_status      TEXT    NOT NULL DEFAULT 'pending'
                             CHECK (legal_review_status IN ('pending', 'approved', 'rejected')),
    lineage_group            TEXT,
    homepage                 TEXT,
    notes                    TEXT,
    created_at               TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS data_versions (
    id            INTEGER PRIMARY KEY,
    source_id     INTEGER NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    version_label TEXT,
    commit_sha    TEXT    NOT NULL,
    retrieved_at  TEXT    NOT NULL,
    file_count    INTEGER NOT NULL DEFAULT 0,
    record_count  INTEGER NOT NULL DEFAULT 0,
    content_hash  TEXT    NOT NULL,
    UNIQUE (source_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS source_files (
    id              INTEGER PRIMARY KEY,
    data_version_id INTEGER NOT NULL REFERENCES data_versions(id) ON DELETE CASCADE,
    path            TEXT    NOT NULL,
    sha256          TEXT    NOT NULL,
    size_bytes      INTEGER NOT NULL,
    record_count    INTEGER NOT NULL DEFAULT 0,
    record_type     TEXT,
    UNIQUE (data_version_id, path)
);

-- Immutable upstream record. raw_json is optional: the full payload always lives
-- in the raw JSONL archive (raw_archive_path) so the distributable DB stays small.
CREATE TABLE IF NOT EXISTS source_records (
    id                INTEGER PRIMARY KEY,
    source_file_id    INTEGER NOT NULL REFERENCES source_files(id) ON DELETE CASCADE,
    source_record_id  TEXT    NOT NULL,
    record_type       TEXT    NOT NULL,
    raw_hash          TEXT    NOT NULL,
    raw_archive_path  TEXT    NOT NULL,
    raw_json          TEXT,
    ingested_at       TEXT    NOT NULL,
    UNIQUE (source_file_id, source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_source_records_hash ON source_records(raw_hash);

-- ---------------------------------------------------------------------------
-- 2. Vehicles, ECUs, parameters
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS manufacturers (
    id         INTEGER PRIMARY KEY,
    slug       TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL UNIQUE,
    country    TEXT,
    notes      TEXT
);

CREATE TABLE IF NOT EXISTS vehicles (
    id              INTEGER PRIMARY KEY,
    manufacturer_id INTEGER NOT NULL REFERENCES manufacturers(id),
    model           TEXT NOT NULL,
    generation      TEXT,
    year_start      INTEGER,
    year_end        INTEGER,
    description     TEXT,
    UNIQUE (manufacturer_id, model, generation)
);

CREATE TABLE IF NOT EXISTS vehicle_variants (
    id           INTEGER PRIMARY KEY,
    vehicle_id   INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    year_start   INTEGER,
    year_end     INTEGER,
    engine_code  TEXT,
    power_kw     REAL,
    notes        TEXT,
    UNIQUE (vehicle_id, name)
);

CREATE TABLE IF NOT EXISTS ecus (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,   -- e.g. "Continental EMS2101", "Toyota 7E0"
    vendor          TEXT,
    model           TEXT,
    variant         TEXT,
    ecu_type        TEXT,
    protocol        TEXT,
    notes           TEXT
);

-- OBDb-style addressing information: which CAN header a vehicle uses per ECU type.
CREATE TABLE IF NOT EXISTS vehicle_ecu_links (
    id                 INTEGER PRIMARY KEY,
    vehicle_variant_id INTEGER NOT NULL REFERENCES vehicle_variants(id) ON DELETE CASCADE,
    ecu_id             INTEGER REFERENCES ecus(id),
    header             TEXT,
    ecu_type           TEXT,
    UNIQUE (vehicle_variant_id, header, ecu_type)
);

-- Mode 01/09 PIDs (generic) and Mode 21/22 parameters (vehicle specific).
CREATE TABLE IF NOT EXISTS pids (
    id            INTEGER PRIMARY KEY,
    mode          TEXT    NOT NULL,
    pid           TEXT    NOT NULL,
    scope         TEXT    NOT NULL DEFAULT 'generic' CHECK (scope IN ('generic', 'vehicle')),
    bytes         INTEGER,
    unit          TEXT,
    formula       TEXT,
    range_min     REAL,
    range_max     REAL,
    signal_id     TEXT,
    path          TEXT,
    fmt_json      TEXT,
    UNIQUE (mode, pid, scope, signal_id)
);

CREATE TABLE IF NOT EXISTS pid_texts (
    id       INTEGER PRIMARY KEY,
    pid_id   INTEGER NOT NULL REFERENCES pids(id) ON DELETE CASCADE,
    language TEXT    NOT NULL,
    name     TEXT    NOT NULL,
    UNIQUE (pid_id, language)
);

-- ---------------------------------------------------------------------------
-- 3. DTC identity and content
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS dtc_codes (
    id                       INTEGER PRIMARY KEY,
    code                     TEXT    NOT NULL,
    standard                 TEXT    NOT NULL DEFAULT 'unknown',
    protocol                 TEXT,
    context_type             TEXT    NOT NULL
                             CHECK (context_type IN ('generic', 'manufacturer', 'ecu', 'vehicle_variant')),
    context_key              TEXT    NOT NULL UNIQUE,
    manufacturer_id          INTEGER REFERENCES manufacturers(id),
    ecu_id                   INTEGER REFERENCES ecus(id),
    vehicle_variant_id       INTEGER REFERENCES vehicle_variants(id),
    category                 TEXT,
    system                   TEXT,
    subsystem                TEXT,
    severity_source          TEXT,
    first_seen_version_id    INTEGER REFERENCES data_versions(id),
    created_at               TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dtc_codes_code ON dtc_codes(code);
CREATE INDEX IF NOT EXISTS idx_dtc_codes_context ON dtc_codes(context_type, manufacturer_id);

-- One row per distinct statement. Identical text coming from two sources collapses
-- into one row with two provenance claims; different text yields two rows, one of
-- which is canonical and both of which are marked in conflicts.
CREATE TABLE IF NOT EXISTS dtc_definitions (
    id                   INTEGER PRIMARY KEY,
    dtc_code_id          INTEGER NOT NULL REFERENCES dtc_codes(id) ON DELETE CASCADE,
    language             TEXT    NOT NULL,
    title                TEXT,
    description          TEXT,
    content_hash         TEXT    NOT NULL,
    is_canonical         INTEGER NOT NULL DEFAULT 0 CHECK (is_canonical IN (0, 1)),
    verification_status  TEXT    NOT NULL DEFAULT 'source_reported'
                         CHECK (verification_status IN
                                ('verified', 'source_reported', 'conflicting', 'unverified')),
    confidence           REAL,
    is_translated        INTEGER NOT NULL DEFAULT 0,
    translation_reviewed INTEGER NOT NULL DEFAULT 0,
    UNIQUE (dtc_code_id, language, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_defs_lang ON dtc_definitions(language, is_canonical);

CREATE TABLE IF NOT EXISTS dtc_causes (
    id                  INTEGER PRIMARY KEY,
    dtc_code_id         INTEGER NOT NULL REFERENCES dtc_codes(id) ON DELETE CASCADE,
    cause_key           TEXT    NOT NULL,
    likelihood          TEXT CHECK (likelihood IN ('low', 'medium', 'high')),
    verification_status TEXT    NOT NULL DEFAULT 'source_reported',
    UNIQUE (dtc_code_id, cause_key)
);

CREATE TABLE IF NOT EXISTS dtc_cause_texts (
    id       INTEGER PRIMARY KEY,
    cause_id INTEGER NOT NULL REFERENCES dtc_causes(id) ON DELETE CASCADE,
    language TEXT    NOT NULL,
    label    TEXT    NOT NULL,
    UNIQUE (cause_id, language)
);

CREATE TABLE IF NOT EXISTS dtc_symptoms (
    id                  INTEGER PRIMARY KEY,
    dtc_code_id         INTEGER NOT NULL REFERENCES dtc_codes(id) ON DELETE CASCADE,
    symptom_key         TEXT    NOT NULL,
    verification_status TEXT    NOT NULL DEFAULT 'source_reported',
    UNIQUE (dtc_code_id, symptom_key)
);

CREATE TABLE IF NOT EXISTS dtc_symptom_texts (
    id         INTEGER PRIMARY KEY,
    symptom_id INTEGER NOT NULL REFERENCES dtc_symptoms(id) ON DELETE CASCADE,
    language   TEXT    NOT NULL,
    text       TEXT    NOT NULL,
    UNIQUE (symptom_id, language)
);

-- Verification / inspection procedures. A DTC is a hypothesis, never a verdict,
-- so tests are first class citizens.
CREATE TABLE IF NOT EXISTS dtc_tests (
    id                  INTEGER PRIMARY KEY,
    dtc_code_id         INTEGER NOT NULL REFERENCES dtc_codes(id) ON DELETE CASCADE,
    test_key            TEXT    NOT NULL,
    kind                TEXT    NOT NULL DEFAULT 'check'
                        CHECK (kind IN ('check', 'measurement', 'freeze_frame', 'drive_cycle',
                                        'resistance', 'voltage', 'visual', 'other')),
    expected            TEXT,
    requires_tool       TEXT,
    sequence            INTEGER,
    verification_status TEXT    NOT NULL DEFAULT 'source_reported',
    UNIQUE (dtc_code_id, test_key)
);

CREATE TABLE IF NOT EXISTS dtc_test_texts (
    id       INTEGER PRIMARY KEY,
    test_id  INTEGER NOT NULL REFERENCES dtc_tests(id) ON DELETE CASCADE,
    language TEXT    NOT NULL,
    text     TEXT    NOT NULL,
    UNIQUE (test_id, language)
);

CREATE TABLE IF NOT EXISTS dtc_repairs (
    id                  INTEGER PRIMARY KEY,
    dtc_code_id         INTEGER NOT NULL REFERENCES dtc_codes(id) ON DELETE CASCADE,
    repair_key          TEXT    NOT NULL,
    difficulty          TEXT    CHECK (difficulty IN ('easy', 'medium', 'hard', 'shop_only')),
    diy_possible        INTEGER CHECK (diy_possible IN (0, 1)),
    cost_min            REAL,
    cost_max            REAL,
    currency            TEXT,
    hours_min           REAL,
    hours_max           REAL,
    verification_status TEXT    NOT NULL DEFAULT 'source_reported',
    UNIQUE (dtc_code_id, repair_key)
);

CREATE TABLE IF NOT EXISTS dtc_repair_texts (
    id        INTEGER PRIMARY KEY,
    repair_id INTEGER NOT NULL REFERENCES dtc_repairs(id) ON DELETE CASCADE,
    language  TEXT    NOT NULL,
    text      TEXT    NOT NULL,
    UNIQUE (repair_id, language)
);

CREATE TABLE IF NOT EXISTS dtc_related_codes (
    id                 INTEGER PRIMARY KEY,
    dtc_code_id        INTEGER NOT NULL REFERENCES dtc_codes(id) ON DELETE CASCADE,
    related_code       TEXT    NOT NULL,
    relation_type      TEXT    NOT NULL DEFAULT 'related',
    related_dtc_code_id INTEGER REFERENCES dtc_codes(id),
    UNIQUE (dtc_code_id, related_code, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_related_code ON dtc_related_codes(related_code);

CREATE TABLE IF NOT EXISTS dtc_components (
    id            INTEGER PRIMARY KEY,
    dtc_code_id   INTEGER NOT NULL REFERENCES dtc_codes(id) ON DELETE CASCADE,
    component_key TEXT    NOT NULL,
    UNIQUE (dtc_code_id, component_key)
);

CREATE TABLE IF NOT EXISTS dtc_component_texts (
    id            INTEGER PRIMARY KEY,
    component_id  INTEGER NOT NULL REFERENCES dtc_components(id) ON DELETE CASCADE,
    language      TEXT    NOT NULL,
    label         TEXT    NOT NULL,
    UNIQUE (component_id, language)
);

-- Upstream evidence for a statement: the TSBs, regulation texts and PDFs a
-- source cites for its own claim. Kept per code because that is how sources
-- publish them, and because a reviewer needs them to trust a definition.
CREATE TABLE IF NOT EXISTS dtc_evidence_sources (
    id          INTEGER PRIMARY KEY,
    dtc_code_id INTEGER NOT NULL REFERENCES dtc_codes(id) ON DELETE CASCADE,
    url         TEXT    NOT NULL,
    kind        TEXT    NOT NULL DEFAULT 'source'
                CHECK (kind IN ('source', 'reference', 'documentation')),
    label       TEXT,
    UNIQUE (dtc_code_id, url)
);
CREATE INDEX IF NOT EXISTS idx_evidence_code ON dtc_evidence_sources(dtc_code_id);

CREATE TABLE IF NOT EXISTS dtc_flags (
    dtc_code_id        INTEGER PRIMARY KEY REFERENCES dtc_codes(id) ON DELETE CASCADE,
    mil                INTEGER CHECK (mil IN (0, 1)),
    emissions_relevant INTEGER CHECK (emissions_relevant IN (0, 1)),
    drive_cycle_required INTEGER CHECK (drive_cycle_required IN (0, 1)),
    limp_mode_possible INTEGER CHECK (limp_mode_possible IN (0, 1)),
    risk_level         TEXT CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    risk_rule_id       TEXT,
    risk_basis_json    TEXT
);

-- ---------------------------------------------------------------------------
-- 4. Provenance, conflicts, validation, duplicates
-- ---------------------------------------------------------------------------

-- One row per (entity attribute, source record). verification_status here is the
-- per-claim status; the entity level status is an aggregate.
CREATE TABLE IF NOT EXISTS provenance_claims (
    id                 INTEGER PRIMARY KEY,
    entity_type        TEXT    NOT NULL,
    entity_id          INTEGER NOT NULL,
    attribute          TEXT    NOT NULL,
    source_id          INTEGER NOT NULL REFERENCES data_sources(id),
    data_version_id    INTEGER NOT NULL REFERENCES data_versions(id),
    source_record_id   INTEGER REFERENCES source_records(id),
    value_hash         TEXT,
    extraction_method  TEXT    NOT NULL DEFAULT 'connector',
    is_derived         INTEGER NOT NULL DEFAULT 0,
    is_translated      INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT   NOT NULL DEFAULT 'source_reported'
                       CHECK (verification_status IN
                              ('verified', 'source_reported', 'conflicting', 'unverified')),
    extracted_at       TEXT    NOT NULL,
    notes              TEXT,
    UNIQUE (entity_type, entity_id, attribute, source_record_id, extraction_method)
);
CREATE INDEX IF NOT EXISTS idx_claims_entity ON provenance_claims(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_claims_source ON provenance_claims(source_id, data_version_id);

CREATE TABLE IF NOT EXISTS conflicts (
    id              INTEGER PRIMARY KEY,
    -- stable identity of the disagreement, independent of database ids, so a
    -- human decision can be re-applied to the next build (see data/reviews)
    fingerprint     TEXT,
    conflict_type   TEXT    NOT NULL,
    entity_type     TEXT    NOT NULL,
    entity_id       INTEGER NOT NULL,
    dtc_code_id     INTEGER REFERENCES dtc_codes(id),
    code            TEXT,
    context_key     TEXT,
    attribute       TEXT,
    summary         TEXT    NOT NULL,
    similarity      REAL,
    status          TEXT    NOT NULL DEFAULT 'needs_review'
                    CHECK (status IN ('needs_review', 'resolved', 'accepted_difference')),
    resolution_note TEXT,
    created_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conflicts_status ON conflicts(status, conflict_type);
CREATE INDEX IF NOT EXISTS idx_conflicts_fingerprint ON conflicts(fingerprint);

CREATE TABLE IF NOT EXISTS conflict_evidence (
    id           INTEGER PRIMARY KEY,
    conflict_id  INTEGER NOT NULL REFERENCES conflicts(id) ON DELETE CASCADE,
    claim_id     INTEGER REFERENCES provenance_claims(id),
    source_slug  TEXT    NOT NULL,
    value_text   TEXT
);

CREATE TABLE IF NOT EXISTS validation_results (
    id          INTEGER PRIMARY KEY,
    entity_type TEXT    NOT NULL,
    entity_id   INTEGER,
    entity_key  TEXT,
    rule_id     TEXT    NOT NULL,
    severity    TEXT    NOT NULL CHECK (severity IN ('error', 'warning', 'info')),
    passed      INTEGER NOT NULL CHECK (passed IN (0, 1)),
    message     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_validation_rule ON validation_results(rule_id, passed);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id                 INTEGER PRIMARY KEY,
    group_key          TEXT    NOT NULL,
    match_type         TEXT    NOT NULL,
    reason             TEXT    NOT NULL,
    member_count       INTEGER NOT NULL,
    canonical_entity   TEXT,
    canonical_entity_id INTEGER,
    created_at         TEXT    NOT NULL,
    UNIQUE (group_key, match_type)
);

CREATE TABLE IF NOT EXISTS duplicate_members (
    id          INTEGER PRIMARY KEY,
    group_id    INTEGER NOT NULL REFERENCES duplicate_groups(id) ON DELETE CASCADE,
    entity_type TEXT    NOT NULL,           -- source_record | dtc_code_context
    entity_ref  TEXT    NOT NULL,           -- "slug:source_record_id" or context_key
    entity_id   INTEGER,                    -- resolved id when available
    similarity  REAL,
    reason      TEXT,
    UNIQUE (group_id, entity_type, entity_ref)
);

-- ---------------------------------------------------------------------------
-- 5. Releases
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS db_versions (
    id               INTEGER PRIMARY KEY,
    version          TEXT    NOT NULL UNIQUE,
    -- licence boundary of the build: 'private' (internal) or 'public'
    -- (only sources whose data licence and legal review allow redistribution)
    source_set       TEXT    NOT NULL DEFAULT 'private'
                     CHECK (source_set IN ('private', 'public')),
    built_at         TEXT    NOT NULL,
    git_commit       TEXT,
    schema_version   TEXT    NOT NULL DEFAULT '1',
    sources_json     TEXT    NOT NULL,
    counts_json      TEXT    NOT NULL,
    validation_json  TEXT    NOT NULL,
    sha256           TEXT,
    export_path      TEXT,
    test_status      TEXT    NOT NULL DEFAULT 'pending'
                     CHECK (test_status IN ('pending', 'passed', 'failed')),
    published_at     TEXT,
    notes            TEXT
);

-- Translations that were not provided by an upstream source must be traceable to
-- a human translator/reviewer. The engine never fabricates translations.
CREATE TABLE IF NOT EXISTS translations (
    id              INTEGER PRIMARY KEY,
    dtc_code_id     INTEGER NOT NULL REFERENCES dtc_codes(id) ON DELETE CASCADE,
    language        TEXT    NOT NULL,
    title           TEXT,
    description     TEXT,
    translator      TEXT,
    reviewer        TEXT,
    source_url      TEXT,
    reviewed        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    UNIQUE (dtc_code_id, language)
);

-- ---------------------------------------------------------------------------
-- 6. Convenience views for the Flutter client
-- ---------------------------------------------------------------------------

DROP VIEW IF EXISTS v_dtc_lookup;
CREATE VIEW v_dtc_lookup AS
SELECT
    c.code,
    c.id                AS dtc_code_id,
    c.standard,
    c.protocol,
    c.context_type,
    c.context_key,
    c.category,
    m.name              AS manufacturer,
    e.name              AS ecu,
    d.language,
    d.title,
    d.description,
    d.is_canonical,
    d.verification_status,
    d.confidence
FROM dtc_codes c
JOIN dtc_definitions d ON d.dtc_code_id = c.id
LEFT JOIN manufacturers m ON m.id = c.manufacturer_id
LEFT JOIN ecus e ON e.id = c.ecu_id;

DROP VIEW IF EXISTS v_dtc_summary;
CREATE VIEW v_dtc_summary AS
SELECT
    c.id                AS dtc_code_id,
    c.code,
    c.context_type,
    m.name              AS manufacturer,
    (SELECT title FROM dtc_definitions d
      WHERE d.dtc_code_id = c.id AND d.language = 'en' AND d.is_canonical = 1 LIMIT 1) AS title_en,
    (SELECT title FROM dtc_definitions d
      WHERE d.dtc_code_id = c.id AND d.language = 'ar' AND d.is_canonical = 1 LIMIT 1) AS title_ar,
    (SELECT COUNT(*) FROM dtc_causes x WHERE x.dtc_code_id = c.id)     AS cause_count,
    (SELECT COUNT(*) FROM dtc_symptoms x WHERE x.dtc_code_id = c.id)   AS symptom_count,
    (SELECT COUNT(*) FROM dtc_tests x WHERE x.dtc_code_id = c.id)      AS test_count,
    (SELECT COUNT(*) FROM dtc_repairs x WHERE x.dtc_code_id = c.id)    AS repair_count,
    (SELECT COUNT(DISTINCT p.source_id) FROM provenance_claims p
      WHERE p.entity_type = 'dtc_code' AND p.entity_id = c.id)         AS source_count,
    f.risk_level,
    f.mil,
    f.emissions_relevant
FROM dtc_codes c
LEFT JOIN manufacturers m ON m.id = c.manufacturer_id
LEFT JOIN dtc_flags f ON f.dtc_code_id = c.id;
