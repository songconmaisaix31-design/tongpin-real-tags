from __future__ import annotations

import re
from functools import wraps
from uuid import uuid4

from flask import current_app, flash, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db, is_integrity_error, utcnow
from .users import ValidationError


EVENT_PENDING_STATUS = "pending_review"
EVENT_APPROVED_STATUS = "recruiting"
EVENT_REJECTED_STATUS = "rejected"
REPORT_PENDING_STATUS = "pending"
REPORT_DECISIONS = ("resolved", "dismissed")


def create_admin(email: str, password: str, display_name: str) -> str:
    email = email.strip().lower()
    display_name = display_name.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValidationError("请输入有效的管理员邮箱。")
    if len(password) < 12:
        raise ValidationError("管理员密码至少需要 12 位。")
    if not 2 <= len(display_name) <= 40:
        raise ValidationError("管理员显示名需为 2–40 个字符。")
    admin_id = f"admin_{uuid4().hex[:12]}"
    try:
        get_db().execute(
            """INSERT INTO admins (id, email, password_hash, display_name, is_active, created_at)
               VALUES (?, ?, ?, ?, 1, ?)""",
            (admin_id, email, generate_password_hash(password), display_name, utcnow()),
        )
        get_db().commit()
    except Exception as error:
        if is_integrity_error(error):
            raise ValidationError("该管理员邮箱已存在。") from error
        raise
    return admin_id


def get_admin(admin_id: str) -> dict | None:
    row = get_db().execute(
        "SELECT id, email, display_name, is_active, created_at FROM admins WHERE id = ?",
        (admin_id,),
    ).fetchone()
    if row is None or (row["id"] == "admin_demo" and not current_app.config["DEMO_MODE"]):
        return None
    return dict(row)


def current_admin() -> dict | None:
    admin_id = session.get("admin_id")
    admin = get_admin(admin_id) if admin_id else None
    if admin_id and (not admin or not admin["is_active"]):
        session.pop("admin_id", None)
        return None
    return admin


def authenticate_admin(email: str, password: str) -> dict:
    row = get_db().execute(
        "SELECT id, email, display_name, is_active, created_at, password_hash FROM admins WHERE email = ?",
        (email.strip().lower(),),
    ).fetchone()
    if (
        row is None
        or (row["id"] == "admin_demo" and not current_app.config["DEMO_MODE"])
        or not row["is_active"]
        or not check_password_hash(row["password_hash"], password)
    ):
        raise ValidationError("管理员邮箱或密码错误。")
    return {key: row[key] for key in ("id", "email", "display_name", "is_active", "created_at")}


def set_current_admin(admin_id: str) -> None:
    admin = get_admin(admin_id)
    if not admin or not admin["is_active"]:
        raise ValidationError("管理员账户不可用。")
    session.clear()
    session["admin_id"] = admin_id


def clear_current_admin() -> None:
    session.pop("admin_id", None)


def admin_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_admin() is None:
            flash("请使用管理员账户登录。", "error")
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)

    return wrapped


def _require_active_admin(admin_id: str) -> dict:
    admin = get_admin(admin_id)
    if not admin or not admin["is_active"]:
        raise ValidationError("管理员账户不可用。")
    return admin


def _audit(db, admin_id: str, action: str, target_type: str, target_id: str,
           old_status: str | None, new_status: str, note: str | None) -> None:
    db.execute(
        """INSERT INTO admin_audit_logs
           (admin_id, action, target_type, target_id, old_status, new_status, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (admin_id, action, target_type, target_id, old_status, new_status, note or None, utcnow()),
    )


def list_pending_events() -> list[dict]:
    rows = get_db().execute(
        """SELECT e.id, e.title, e.description, e.poi_name, e.poi_address, e.start_at,
                  e.signup_deadline, e.min_size, e.max_size, e.status, e.created_at,
                  u.anonymous_alias AS host_alias, u.email AS host_email
           FROM events e
           LEFT JOIN users u ON e.host_type = 'user' AND u.id = e.host_id
           WHERE e.status = ?
           ORDER BY e.created_at""",
        (EVENT_PENDING_STATUS,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_event_for_review(event_id: str) -> dict | None:
    row = get_db().execute(
        """SELECT e.id, e.host_type, e.title, e.description, e.poi_name, e.poi_address,
                  e.start_at, e.signup_deadline, e.min_size, e.max_size, e.budget_level,
                  e.pay_type, e.gender_policy, e.signup_mode, e.required_tags_json,
                  e.status, e.created_at, u.anonymous_alias AS host_alias,
                  u.email AS host_email, er.rejection_reason, er.reviewed_at,
                  a.display_name AS reviewed_by_name
           FROM events e
           LEFT JOIN users u ON e.host_type = 'user' AND u.id = e.host_id
           LEFT JOIN event_reviews er ON er.event_id = e.id
           LEFT JOIN admins a ON a.id = er.reviewed_by
           WHERE e.id = ?""",
        (event_id,),
    ).fetchone()
    return dict(row) if row else None


def review_event(event_id: str, admin_id: str, decision: str, rejection_reason: str = "") -> str:
    _require_active_admin(admin_id)
    if decision not in ("approve", "reject"):
        raise ValidationError("无效的活动审核决定。")
    reason = rejection_reason.strip()
    if decision == "reject" and not reason:
        raise ValidationError("拒绝活动时必须填写原因。")
    if len(reason) > 500:
        raise ValidationError("审核原因不能超过 500 个字符。")

    db = get_db()
    event = db.execute(
        "SELECT id, host_type, status, created_at FROM events WHERE id = ?", (event_id,)
    ).fetchone()
    if event is None:
        raise ValidationError("活动不存在。")
    if event["host_type"] != "user" or event["status"] != EVENT_PENDING_STATUS:
        raise ValidationError("该活动当前不在待审核状态。")

    event_status = EVENT_APPROVED_STATUS if decision == "approve" else EVENT_REJECTED_STATUS
    review_status = "approved" if decision == "approve" else "rejected"
    reviewed_at = utcnow()
    with db:
        changed = db.execute(
            "UPDATE events SET status = ? WHERE id = ? AND status = ?",
            (event_status, event_id, EVENT_PENDING_STATUS),
        )
        if changed.rowcount != 1:
            raise ValidationError("活动状态已变化，请刷新后重试。")
        db.execute(
            """INSERT INTO event_reviews
               (event_id, status, submitted_at, reviewed_by, rejection_reason, reviewed_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(event_id) DO UPDATE SET
                   status = excluded.status,
                   reviewed_by = excluded.reviewed_by,
                   rejection_reason = excluded.rejection_reason,
                   reviewed_at = excluded.reviewed_at""",
            (event_id, review_status, event["created_at"], admin_id, reason or None, reviewed_at),
        )
        _audit(
            db, admin_id, f"event_{review_status}", "event", event_id,
            EVENT_PENDING_STATUS, event_status, reason or None,
        )
    return event_status


_REPORT_SELECT = """SELECT r.id, r.subject_type, r.subject_id, r.reason, r.status,
                            r.handling_note, r.handled_at, r.created_at,
                            u.anonymous_alias AS reporter_alias, u.email AS reporter_email,
                            COALESCE(e.title, c.id, r.subject_id) AS subject_label,
                            a.display_name AS handled_by_name
                     FROM reports r
                     JOIN users u ON u.id = r.reporter_id
                     LEFT JOIN events e ON r.subject_type = 'event' AND e.id = r.subject_id
                     LEFT JOIN conversations c ON r.subject_type = 'conversation' AND c.id = r.subject_id
                     LEFT JOIN admins a ON a.id = r.handled_by"""


def list_reports(status: str = REPORT_PENDING_STATUS) -> list[dict]:
    if status not in (REPORT_PENDING_STATUS, *REPORT_DECISIONS):
        raise ValidationError("无效的举报状态。")
    rows = get_db().execute(
        f"{_REPORT_SELECT} WHERE r.status = ? ORDER BY r.created_at", (status,)
    ).fetchall()
    return [dict(row) for row in rows]


def list_registered_users(query: str = "") -> list[dict]:
    """Return the limited account fields needed for the administrator's read-only view."""
    query = query.strip()[:80]
    conditions = ""
    params: tuple[str, ...] = ()
    if query:
        conditions = "WHERE u.email LIKE ? OR u.anonymous_alias LIKE ? OR u.city LIKE ?"
        like_query = f"%{query}%"
        params = (like_query, like_query, like_query)
    rows = get_db().execute(
        f"""SELECT u.email, u.anonymous_alias, u.city, u.phone_verified, u.is_demo, u.created_at,
                   COUNT(CASE WHEN ec.status = 'connected' THEN 1 END) AS authorized_source_count
            FROM users u
            LEFT JOIN external_connections ec ON ec.user_id = u.id
            {conditions}
            GROUP BY u.id, u.email, u.anonymous_alias, u.city, u.phone_verified, u.is_demo, u.created_at
            ORDER BY u.created_at DESC, u.email""",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def get_report_for_review(report_id: str) -> dict | None:
    row = get_db().execute(f"{_REPORT_SELECT} WHERE r.id = ?", (report_id,)).fetchone()
    return dict(row) if row else None


def review_report(report_id: str, admin_id: str, decision: str, note: str = "") -> str:
    _require_active_admin(admin_id)
    if decision not in REPORT_DECISIONS:
        raise ValidationError("无效的举报处理决定。")
    note = note.strip()
    if len(note) > 500:
        raise ValidationError("处理备注不能超过 500 个字符。")

    db = get_db()
    report = db.execute("SELECT status FROM reports WHERE id = ?", (report_id,)).fetchone()
    if report is None:
        raise ValidationError("举报不存在。")
    if report["status"] != REPORT_PENDING_STATUS:
        raise ValidationError("该举报已经处理。")

    handled_at = utcnow()
    with db:
        changed = db.execute(
            """UPDATE reports
               SET status = ?, handled_by = ?, handling_note = ?, handled_at = ?
               WHERE id = ? AND status = ?""",
            (decision, admin_id, note or None, handled_at, report_id, REPORT_PENDING_STATUS),
        )
        if changed.rowcount != 1:
            raise ValidationError("举报状态已变化，请刷新后重试。")
        _audit(
            db, admin_id, f"report_{decision}", "report", report_id,
            REPORT_PENDING_STATUS, decision, note or None,
        )
    return decision


def recent_audit_logs(limit: int = 20) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    rows = get_db().execute(
        """SELECT l.action, l.target_type, l.target_id, l.old_status, l.new_status,
                  l.note, l.created_at, a.display_name AS admin_name
           FROM admin_audit_logs l JOIN admins a ON a.id = l.admin_id
           ORDER BY l.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
