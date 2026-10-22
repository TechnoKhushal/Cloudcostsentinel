from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from ..models.cost import CostAnomaly
from ..models.decision import DeciderResponseTrace
from ..models.approval import ApprovalItem
from ..models.report import BedrockReport


class ApprovalConflictError(Exception):
    """Raised when an approval that is already reviewed attempts another transition."""
    pass


class DatabaseRepository:
    def __init__(self, db_path: str = "backend/data/sentinel.db"):
        self.db_path = db_path
        dir_name = os.path.dirname(self.db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        self._init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _init_tables(self) -> None:
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS anomalies (
                    anomaly_id TEXT PRIMARY KEY,
                    scenario_id TEXT,
                    scenario_name TEXT,
                    service TEXT,
                    environment TEXT,
                    criticality TEXT,
                    data_json TEXT,
                    detected_at TEXT
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id TEXT PRIMARY KEY,
                    anomaly_id TEXT,
                    action TEXT,
                    confidence REAL,
                    provider TEXT,
                    model_id TEXT,
                    latency_ms REAL,
                    is_fallback INTEGER,
                    trace_json TEXT,
                    timestamp TEXT
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    decision_id TEXT,
                    anomaly_id TEXT,
                    service TEXT,
                    environment TEXT,
                    suggested_action TEXT,
                    estimated_monthly_savings REAL,
                    status TEXT,
                    reviewed_by TEXT,
                    reviewed_at TEXT,
                    notes TEXT,
                    created_at TEXT,
                    is_simulated INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY,
                    anomaly_id TEXT,
                    decision_id TEXT,
                    title TEXT,
                    report_json TEXT,
                    provider TEXT,
                    model_id TEXT,
                    generated_at TEXT
                );
            """)

            # Safe automated schema migration: verify is_simulated in approvals
            cursor = conn.execute("PRAGMA table_info(approvals)")
            columns = [col["name"] for col in cursor.fetchall()]
            if "is_simulated" not in columns:
                conn.execute("ALTER TABLE approvals ADD COLUMN is_simulated INTEGER DEFAULT 1")

    def save_anomaly(self, anomaly: CostAnomaly) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO anomalies (anomaly_id, scenario_id, scenario_name, service, environment, criticality, data_json, detected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    anomaly.anomaly_id,
                    anomaly.scenario_id,
                    anomaly.scenario_name,
                    anomaly.service,
                    anomaly.environment,
                    anomaly.criticality,
                    anomaly.model_dump_json(),
                    anomaly.detected_at,
                ),
            )

    def save_decision_trace(self, anomaly_id: str, trace: DeciderResponseTrace) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO decisions (decision_id, anomaly_id, action, confidence, provider, model_id, latency_ms, is_fallback, trace_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.decision_id,
                    anomaly_id,
                    trace.action,
                    trace.confidence,
                    trace.provider,
                    trace.model_id,
                    trace.latency_ms,
                    1 if trace.is_fallback else 0,
                    trace.model_dump_json(),
                    trace.timestamp,
                ),
            )

    def save_approval(self, approval: ApprovalItem) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO approvals (id, decision_id, anomaly_id, service, environment, suggested_action, estimated_monthly_savings, status, reviewed_by, reviewed_at, notes, created_at, is_simulated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval.id,
                    approval.decision_id,
                    approval.anomaly_id,
                    approval.service,
                    approval.environment,
                    approval.suggested_action,
                    approval.estimated_monthly_savings,
                    approval.status,
                    approval.reviewed_by,
                    approval.reviewed_at,
                    approval.notes,
                    approval.created_at,
                    1 if approval.is_simulated else 0,
                ),
            )

    def save_report(self, report: BedrockReport) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO reports (report_id, anomaly_id, decision_id, title, report_json, provider, model_id, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.report_id,
                    report.anomaly_id,
                    report.decision_id,
                    report.title,
                    report.model_dump_json(),
                    report.provider,
                    report.model_id,
                    report.generated_at,
                ),
            )

    def get_recent_decisions(self, limit: int = 20) -> List[DeciderResponseTrace]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT trace_json FROM decisions ORDER BY timestamp DESC LIMIT ?", (limit,)
            )
            rows = cursor.fetchall()
            return [DeciderResponseTrace.model_validate_json(row["trace_json"]) for row in rows]

    def get_approvals(self, status: Optional[str] = None) -> List[ApprovalItem]:
        with self._get_connection() as conn:
            if status:
                cursor = conn.execute(
                    "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC", (status,)
                )
            else:
                cursor = conn.execute("SELECT * FROM approvals ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [
                ApprovalItem(
                    id=row["id"],
                    decision_id=row["decision_id"],
                    anomaly_id=row["anomaly_id"],
                    service=row["service"],
                    environment=row["environment"],
                    suggested_action=row["suggested_action"],
                    estimated_monthly_savings=row["estimated_monthly_savings"],
                    status=row["status"],
                    reviewed_by=row["reviewed_by"],
                    reviewed_at=row["reviewed_at"],
                    notes=row["notes"],
                    created_at=row["created_at"],
                    is_simulated=bool(row["is_simulated"]) if "is_simulated" in row.keys() and row["is_simulated"] is not None else True,
                )
                for row in rows
            ]

    def update_approval_status(
        self, approval_id: str, status: str, reviewed_by: str, notes: Optional[str] = None
    ) -> Optional[ApprovalItem]:
        """Atomically update an approval status from pending to approved/rejected.

        Enforces single-transition idempotency: raises ApprovalConflictError if already reviewed.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            # First fetch current record to verify existence and check for replay
            cursor = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
            current = cursor.fetchone()
            if not current:
                return None

            if current["status"] != "pending":
                raise ApprovalConflictError(
                    f"Approval item '{approval_id}' was already reviewed with status '{current['status']}' "
                    f"by {current['reviewed_by']} at {current['reviewed_at']}."
                )

            conn.execute(
                """
                UPDATE approvals
                SET status = ?, reviewed_by = ?, reviewed_at = ?, notes = ?
                WHERE id = ? AND status = 'pending'
                """,
                (status, reviewed_by, now_str, notes, approval_id),
            )
            cursor = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ApprovalItem(
                id=row["id"],
                decision_id=row["decision_id"],
                anomaly_id=row["anomaly_id"],
                service=row["service"],
                environment=row["environment"],
                suggested_action=row["suggested_action"],
                estimated_monthly_savings=row["estimated_monthly_savings"],
                status=row["status"],
                reviewed_by=row["reviewed_by"],
                reviewed_at=row["reviewed_at"],
                notes=row["notes"],
                created_at=row["created_at"],
                is_simulated=bool(row["is_simulated"]) if "is_simulated" in row.keys() and row["is_simulated"] is not None else True,
            )

    def get_latest_report_for_anomaly(self, anomaly_id: str) -> Optional[BedrockReport]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT report_json FROM reports WHERE anomaly_id = ? ORDER BY generated_at DESC LIMIT 1",
                (anomaly_id,),
            )
            row = cursor.fetchone()
            if row:
                return BedrockReport.model_validate_json(row["report_json"])
            return None
