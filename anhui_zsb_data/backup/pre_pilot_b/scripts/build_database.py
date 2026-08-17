#!/usr/bin/env python3
"""Build a constraint-backed SQLite database from canonical CSV exports."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from common import DB_DIR, NORMALIZED_DIR, ensure_directories, read_csv

DB_PATH = DB_DIR / "anhui_zsb.sqlite"


def null(value: str):
    return None if value == "" else value


def number(value: str):
    if value == "":
        return None
    return float(value) if "." in value else int(value)


def boolean(value: str):
    if value == "":
        return None
    return 1 if value.lower() == "true" else 0


def execute_many(connection: sqlite3.Connection, sql: str, rows: list[tuple]) -> None:
    if rows:
        connection.executemany(sql, rows)


def build_database(path: Path = DB_PATH) -> Path:
    ensure_directories()
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE schema_metadata (
            metadata_key TEXT PRIMARY KEY,
            metadata_value TEXT NOT NULL
        );

        CREATE TABLE institutions (
            institution_id TEXT PRIMARY KEY,
            institution_name_std TEXT NOT NULL UNIQUE,
            institution_name_raw TEXT NOT NULL,
            institution_type TEXT,
            institution_role TEXT,
            city TEXT,
            official_code TEXT,
            official_url TEXT,
            address TEXT,
            address_source_id TEXT,
            address_source_locator TEXT
        );

        CREATE TABLE source_sites (
            source_site_id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            organization_name TEXT NOT NULL,
            site_name TEXT NOT NULL,
            base_url TEXT NOT NULL,
            source_level TEXT NOT NULL
        );

        CREATE TABLE source_documents (
            source_document_id TEXT PRIMARY KEY,
            source_site_id TEXT NOT NULL REFERENCES source_sites(source_site_id),
            year INTEGER NOT NULL,
            school_id TEXT NOT NULL REFERENCES institutions(institution_id),
            document_type TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            publish_date TEXT,
            retrieved_at TEXT,
            source_level TEXT NOT NULL,
            status TEXT NOT NULL,
            primary_asset_id TEXT,
            notes TEXT
        );

        CREATE TABLE source_assets (
            asset_id TEXT PRIMARY KEY,
            source_document_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
            local_path TEXT NOT NULL UNIQUE,
            file_name TEXT NOT NULL,
            original_file_name TEXT,
            asset_type TEXT NOT NULL,
            mime_type TEXT,
            file_size INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            retrieved_at TEXT,
            parent_asset_id TEXT REFERENCES source_assets(asset_id),
            parser_name TEXT,
            parser_version TEXT,
            generated_at TEXT
        );

        CREATE TABLE program_years (
            program_year_id TEXT PRIMARY KEY,
            year INTEGER NOT NULL,
            admission_school_id TEXT NOT NULL REFERENCES institutions(institution_id),
            undergraduate_major_id TEXT NOT NULL,
            major_name_raw TEXT NOT NULL,
            major_name_std TEXT NOT NULL,
            admission_track_raw TEXT NOT NULL,
            admission_track_code TEXT NOT NULL,
            study_years INTEGER NOT NULL,
            source_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
            source_locator TEXT NOT NULL,
            UNIQUE(year, admission_school_id, major_name_std)
        );

        CREATE TABLE program_offerings (
            offering_id TEXT PRIMARY KEY,
            program_year_id TEXT NOT NULL REFERENCES program_years(program_year_id),
            year INTEGER NOT NULL,
            training_type TEXT NOT NULL,
            training_institution_id TEXT NOT NULL REFERENCES institutions(institution_id),
            training_institution_name TEXT NOT NULL,
            training_campus TEXT,
            training_campus_status TEXT NOT NULL,
            training_address TEXT,
            tuition_value REAL,
            study_years INTEGER NOT NULL,
            remarks_source_raw TEXT,
            training_type_is_derived INTEGER NOT NULL,
            training_type_derivation_method TEXT,
            source_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
            source_locator TEXT NOT NULL,
            UNIQUE(program_year_id, training_type, training_institution_id, training_campus)
        );

        CREATE TABLE enrollment_plans (
            enrollment_plan_id TEXT PRIMARY KEY,
            offering_id TEXT NOT NULL REFERENCES program_offerings(offering_id),
            plan_type TEXT NOT NULL,
            plan_value REAL,
            value_status TEXT NOT NULL,
            plan_version TEXT NOT NULL,
            announcement_date TEXT,
            is_derived INTEGER NOT NULL,
            derivation_method TEXT,
            raw_value TEXT,
            source_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
            source_locator TEXT NOT NULL,
            UNIQUE(offering_id, plan_type, plan_version)
        );

        CREATE TABLE exam_subjects (
            exam_subject_id TEXT PRIMARY KEY,
            program_year_id TEXT NOT NULL REFERENCES program_years(program_year_id),
            year INTEGER NOT NULL,
            subject_slot TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            subject_name_raw TEXT NOT NULL,
            subject_name_std TEXT NOT NULL,
            score_max REAL NOT NULL,
            exam_duration_minutes INTEGER,
            exam_method TEXT,
            source_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
            source_locator TEXT NOT NULL,
            UNIQUE(program_year_id, subject_slot)
        );

        CREATE TABLE exam_sessions (
            exam_session_id TEXT PRIMARY KEY,
            program_year_id TEXT NOT NULL REFERENCES program_years(program_year_id),
            year INTEGER NOT NULL,
            session_type TEXT NOT NULL,
            subject_slots_json TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            exam_date TEXT,
            start_time TEXT,
            end_time TEXT,
            exam_site_raw TEXT,
            exam_site_status TEXT NOT NULL,
            source_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
            source_locator TEXT NOT NULL,
            UNIQUE(program_year_id, session_type)
        );

        CREATE TABLE major_eligibility (
            eligibility_id TEXT PRIMARY KEY,
            program_year_id TEXT NOT NULL REFERENCES program_years(program_year_id),
            year INTEGER NOT NULL,
            undergraduate_major_raw TEXT NOT NULL,
            undergraduate_major_std TEXT NOT NULL,
            allowed_major_categories_raw TEXT NOT NULL,
            allowed_major_categories_std TEXT NOT NULL,
            restriction_raw_text TEXT NOT NULL,
            source_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
            source_locator TEXT NOT NULL,
            UNIQUE(program_year_id)
        );

        CREATE TABLE eligibility_rule_sets (
            eligibility_rule_set_id TEXT PRIMARY KEY,
            program_year_id TEXT NOT NULL REFERENCES program_years(program_year_id),
            year INTEGER NOT NULL,
            raw_text TEXT NOT NULL,
            source_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
            source_locator TEXT NOT NULL,
            UNIQUE(program_year_id)
        );

        CREATE TABLE eligibility_rule_items (
            eligibility_rule_item_id TEXT PRIMARY KEY,
            eligibility_rule_set_id TEXT NOT NULL REFERENCES eligibility_rule_sets(eligibility_rule_set_id),
            ordinal INTEGER NOT NULL,
            scope_type TEXT NOT NULL,
            include_or_exclude TEXT NOT NULL,
            category_code TEXT,
            category_name_raw TEXT NOT NULL,
            major_code TEXT,
            major_name_raw TEXT,
            condition_raw TEXT,
            UNIQUE(eligibility_rule_set_id, ordinal)
        );

        CREATE TABLE admission_scores (
            admission_score_id TEXT PRIMARY KEY,
            offering_id TEXT NOT NULL REFERENCES program_offerings(offering_id),
            year INTEGER NOT NULL,
            candidate_category TEXT NOT NULL,
            admission_round TEXT NOT NULL,
            score_metric TEXT NOT NULL,
            score_basis TEXT NOT NULL,
            score_max REAL,
            score_value_numeric REAL,
            score_raw TEXT,
            value_status TEXT NOT NULL,
            threshold_detail_json TEXT,
            assessment_name TEXT,
            notes_source_raw TEXT,
            is_official_direct INTEGER NOT NULL,
            is_derived INTEGER NOT NULL,
            derivation_method TEXT,
            source_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
            source_locator TEXT NOT NULL,
            UNIQUE(offering_id, candidate_category, score_metric, admission_round)
        );

        CREATE TABLE admission_rules (
            rule_id TEXT PRIMARY KEY,
            year INTEGER NOT NULL,
            school_id TEXT NOT NULL REFERENCES institutions(institution_id),
            rule_type TEXT NOT NULL,
            rule_scope TEXT,
            rule_raw_text TEXT NOT NULL,
            rule_structured_json TEXT,
            source_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
            source_locator TEXT NOT NULL,
            UNIQUE(year, school_id, rule_type, rule_scope)
        );


        CREATE TABLE fact_sources (
            fact_source_id TEXT PRIMARY KEY,
            table_name TEXT NOT NULL,
            record_id TEXT NOT NULL,
            source_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
            relation_type TEXT NOT NULL,
            source_locator TEXT NOT NULL,
            UNIQUE(table_name, record_id, source_id, relation_type)
        );
        """
    )

    connection.executemany(
        "INSERT INTO schema_metadata VALUES (?,?)",
        [("schema_version", "0.3.0"), ("canonical_source", "normalized CSV exports")],
    )

    rows = read_csv(NORMALIZED_DIR / "institutions.csv")
    columns = ["institution_id","institution_name_std","institution_name_raw","institution_type","institution_role","city","official_code","official_url","address","address_source_id","address_source_locator"]
    execute_many(connection, "INSERT INTO institutions VALUES (?,?,?,?,?,?,?,?,?,?,?)", [tuple(null(row[key]) for key in columns) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "source_sites.csv")
    execute_many(connection, "INSERT INTO source_sites VALUES (?,?,?,?,?,?)", [tuple(null(row[key]) for key in row) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "source_documents.csv")
    columns = ["source_document_id","source_site_id","year","school_id","document_type","title","url","publish_date","retrieved_at","source_level","status","primary_asset_id","notes"]
    execute_many(connection, "INSERT INTO source_documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [tuple(number(row[key]) if key == "year" else null(row[key]) for key in columns) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "source_assets.csv")
    columns = ["asset_id","source_document_id","local_path","file_name","original_file_name","asset_type","mime_type","file_size","sha256","retrieved_at","parent_asset_id","parser_name","parser_version","generated_at"]
    # Insert parents before children.
    rows.sort(key=lambda row: bool(row["parent_asset_id"]))
    execute_many(connection, "INSERT INTO source_assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [tuple(number(row[key]) if key == "file_size" else null(row[key]) for key in columns) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "program_years.csv")
    columns = ["program_year_id","year","admission_school_id","undergraduate_major_id","major_name_raw","major_name_std","admission_track_raw","admission_track_code","study_years","source_id","source_locator"]
    execute_many(connection, "INSERT INTO program_years VALUES (?,?,?,?,?,?,?,?,?,?,?)", [tuple(number(row[key]) if key in {"year","study_years"} else null(row[key]) for key in columns) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "program_offerings.csv")
    columns = ["offering_id","program_year_id","year","training_type","training_institution_id","training_institution_name","training_campus","training_campus_status","training_address","tuition_value","study_years","remarks_source_raw","training_type_is_derived","training_type_derivation_method","source_id","source_locator"]
    execute_many(connection, "INSERT INTO program_offerings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [tuple(number(row[key]) if key in {"year","tuition_value","study_years"} else boolean(row[key]) if key == "training_type_is_derived" else null(row[key]) for key in columns) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "enrollment_plans.csv")
    columns = ["enrollment_plan_id","offering_id","plan_type","plan_value","value_status","plan_version","announcement_date","is_derived","derivation_method","raw_value","source_id","source_locator"]
    execute_many(connection, "INSERT INTO enrollment_plans VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [tuple(number(row[key]) if key == "plan_value" else boolean(row[key]) if key == "is_derived" else null(row[key]) for key in columns) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "exam_subjects.csv")
    columns = ["exam_subject_id","program_year_id","year","subject_slot","subject_id","subject_name_raw","subject_name_std","score_max","exam_duration_minutes","exam_method","source_id","source_locator"]
    execute_many(connection, "INSERT INTO exam_subjects VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [tuple(number(row[key]) if key in {"year","score_max","exam_duration_minutes"} else null(row[key]) for key in columns) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "exam_sessions.csv")
    columns = ["exam_session_id","program_year_id","year","session_type","subject_slots_json","duration_minutes","exam_date","start_time","end_time","exam_site_raw","exam_site_status","source_id","source_locator"]
    execute_many(connection, "INSERT INTO exam_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [tuple(number(row[key]) if key in {"year","duration_minutes"} else null(row[key]) for key in columns) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "major_eligibility.csv")
    columns = ["eligibility_id","program_year_id","year","undergraduate_major_raw","undergraduate_major_std","allowed_major_categories_raw","allowed_major_categories_std","restriction_raw_text","source_id","source_locator"]
    execute_many(connection, "INSERT INTO major_eligibility VALUES (?,?,?,?,?,?,?,?,?,?)", [tuple(number(row[key]) if key == "year" else null(row[key]) for key in columns) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "eligibility_rule_sets.csv")
    columns = ["eligibility_rule_set_id","program_year_id","year","raw_text","source_id","source_locator"]
    execute_many(connection, "INSERT INTO eligibility_rule_sets VALUES (?,?,?,?,?,?)", [tuple(number(row[key]) if key == "year" else null(row[key]) for key in columns) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "eligibility_rule_items.csv")
    columns = ["eligibility_rule_item_id","eligibility_rule_set_id","ordinal","scope_type","include_or_exclude","category_code","category_name_raw","major_code","major_name_raw","condition_raw"]
    execute_many(connection, "INSERT INTO eligibility_rule_items VALUES (?,?,?,?,?,?,?,?,?,?)", [tuple(number(row[key]) if key == "ordinal" else null(row[key]) for key in columns) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "admission_scores.csv")
    columns = ["admission_score_id","offering_id","year","candidate_category","admission_round","score_metric","score_basis","score_max","score_value_numeric","score_raw","value_status","threshold_detail_json","assessment_name","notes_source_raw","is_official_direct","is_derived","derivation_method","source_id","source_locator"]
    execute_many(connection, "INSERT INTO admission_scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [tuple(number(row[key]) if key in {"year","score_max","score_value_numeric"} else boolean(row[key]) if key in {"is_official_direct","is_derived"} else null(row[key]) for key in columns) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "admission_rules.csv")
    columns = ["rule_id","year","school_id","rule_type","rule_scope","rule_raw_text","rule_structured_json","source_id","source_locator"]
    execute_many(connection, "INSERT INTO admission_rules VALUES (?,?,?,?,?,?,?,?,?)", [tuple(number(row[key]) if key == "year" else null(row[key]) for key in columns) for row in rows])

    rows = read_csv(NORMALIZED_DIR / "fact_sources.csv")
    columns = ["fact_source_id","table_name","record_id","source_id","relation_type","source_locator"]
    execute_many(connection, "INSERT INTO fact_sources VALUES (?,?,?,?,?,?)", [tuple(null(row[key]) for key in columns) for row in rows])

    connection.executescript(
        """
        CREATE INDEX idx_program_year_major ON program_years(year, major_name_std);
        CREATE INDEX idx_offering_program ON program_offerings(program_year_id);
        CREATE INDEX idx_plan_offering ON enrollment_plans(offering_id);
        CREATE INDEX idx_score_offering ON admission_scores(offering_id);
        CREATE INDEX idx_fact_source_record ON fact_sources(table_name, record_id);

        CREATE VIEW v_program_offerings AS
        SELECT
            po.offering_id,
            py.year,
            py.major_name_std,
            py.admission_track_code,
            po.training_type,
            po.training_institution_name,
            po.tuition_value
        FROM program_offerings po
        JOIN program_years py ON py.program_year_id = po.program_year_id;

        CREATE VIEW v_published_admission_scores AS
        SELECT
            s.*,
            py.major_name_std,
            po.training_institution_name
        FROM admission_scores s
        JOIN program_offerings po ON po.offering_id = s.offering_id
        JOIN program_years py ON py.program_year_id = po.program_year_id
        WHERE s.value_status = 'published_value';
        """
    )
    violations = list(connection.execute("PRAGMA foreign_key_check"))
    if violations:
        raise RuntimeError(f"SQLite foreign-key violations: {violations[:5]}")
    connection.execute("PRAGMA user_version = 300")
    connection.commit()
    connection.close()
    return path


def main() -> int:
    path = build_database()
    print(f"SQLite database built: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
