from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from flask import current_app

from ..constants import EVENT_TAGS, POIS
from ..db import get_db, utcnow
from .matching import event_match_score, event_required_tags
from .users import ValidationError, get_user

EVENT_STATUSES = {
    "draft": "草稿",
    "pending_review": "待平台审核",
    "recruiting": "报名中",
    "formed": "已成团",
    "ongoing": "进行中",
    "ended": "已结束",
    "cancelled": "已取消",
    "rejected": "审核未通过",
}

# Server-only coordinates for the public restaurant whitelist.
# User coordinates are used only while handling the current request.
POI_LOCATIONS = {
    "poi_001": {"city": "北京", "lat": 39.914525, "lng": 116.402873},
    "poi_002": {"city": "北京", "lat": 39.941174, "lng": 116.419240},
    "poi_003": {"city": "北京", "lat": 39.886721, "lng": 116.363329},
    "poi_004": {"city": "北京", "lat": 39.927286, "lng": 116.413522},
    "poi_005": {"city": "北京", "lat": 39.871734, "lng": 116.405566},
    "poi_006": {"city": "北京", "lat": 39.899292, "lng": 116.385072},
    "poi_007": {"city": "北京", "lat": 39.932207, "lng": 116.367609},
    "poi_008": {"city": "北京", "lat": 39.914089, "lng": 116.412053},
}
DEFAULT_RADIUS_KM = 5.0
MAX_RADIUS_KM = 50.0
MAX_LOCATION_ACCURACY_M = 100_000.0


def _decode_event(row) -> dict | None:
    if row is None:
        return None
    event = dict(row)
    event["required_tags"] = json.loads(event.pop("required_tags_json"))
    event["merchant_benefit"] = json.loads(event.pop("merchant_benefit_json")) if event["merchant_benefit_json"] else None
    event["status_label"] = EVENT_STATUSES[event["status"]]
    return event


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValidationError("请填写有效的活动时间。") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    return parsed


def _event_members(event_id: str, status: str | None = None) -> list[dict]:
    query = """SELECT em.*, u.gender FROM event_members em JOIN users u ON u.id = em.user_id
               WHERE em.event_id = ?"""
    params: list[str] = [event_id]
    if status:
        query += " AND em.membership_status = ?"
        params.append(status)
    return [dict(row) for row in get_db().execute(query, params).fetchall()]


def _review_token(event_id: str, user_id: str) -> str:
    key = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    digest = hmac.new(key, f"{event_id}\0{user_id}".encode("utf-8"), hashlib.sha256).digest()[:18]
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _event_summary(event: dict, user_id: str) -> dict:
    approved_members = _event_members(event["id"], "approved")
    genders = {"male": 0, "female": 0, "undisclosed": 0}
    for member in approved_members:
        genders[member["gender"]] += 1
    score = event_match_score(user_id, event["required_tags"])
    event.update(score)
    event["approved_count"] = len(approved_members)
    event["gender_counts"] = genders
    event["is_merchant"] = event["host_type"] == "merchant"
    event["required_tag_labels"] = [EVENT_TAGS[tag] for tag in event["required_tags"]]
    event["start_at_display"] = _parse_datetime(event["start_at"]).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    event.pop("host_id", None)
    return event


def parse_nearby_query(args) -> dict:
    """Validate request-scoped coordinates without persisting them."""
    lat_text = (args.get("lat") or "").strip()
    lng_text = (args.get("lng") or "").strip()
    accuracy_text = (args.get("accuracy") or "").strip()
    radius_text = (args.get("radius") or str(DEFAULT_RADIUS_KM)).strip()
    if bool(lat_text) != bool(lng_text):
        raise ValidationError("定位参数不完整，请重新获取当前位置。")
    try:
        radius_km = float(radius_text)
    except ValueError as error:
        raise ValidationError("附近半径必须是有效数字。") from error
    if not math.isfinite(radius_km) or not 0 < radius_km <= MAX_RADIUS_KM:
        raise ValidationError(f"附近半径须大于 0 且不超过 {int(MAX_RADIUS_KM)} km。")
    if not lat_text:
        return {"active": False, "radius_km": radius_km}
    try:
        lat, lng = float(lat_text), float(lng_text)
    except ValueError as error:
        raise ValidationError("当前位置的经纬度无效，请重新定位。") from error
    if not math.isfinite(lat) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
        raise ValidationError("当前位置超出有效经纬度范围，请重新定位。")
    location = {
        "active": True,
        "lat": lat,
        "lng": lng,
        # Four decimals keep the request useful for nearby filtering without claiming a precise address.
        "lat_param": f"{lat:.4f}",
        "lng_param": f"{lng:.4f}",
        "radius_km": radius_km,
    }
    if accuracy_text:
        try:
            accuracy_m = float(accuracy_text)
        except ValueError as error:
            raise ValidationError("浏览器定位精度无效，请重新定位。") from error
        if not math.isfinite(accuracy_m) or not 0 <= accuracy_m <= MAX_LOCATION_ACCURACY_M:
            raise ValidationError("浏览器定位精度超出有效范围，请重新定位。")
        location["accuracy_m"] = round(accuracy_m)
        location["accuracy_param"] = str(round(accuracy_m))

    poi_id, poi = min(
        POI_LOCATIONS.items(),
        key=lambda item: haversine_km(lat, lng, item[1]["lat"], item[1]["lng"]),
    )
    location["nearest_poi"] = {
        "id": poi_id,
        "name": POIS[poi_id]["name"],
        "distance_km": round(haversine_km(lat, lng, poi["lat"], poi["lng"]), 1),
    }
    return location


def haversine_km(lat_a: float, lng_a: float, lat_b: float, lng_b: float) -> float:
    """Return great-circle distance in kilometres."""
    lat_a_rad, lat_b_rad = math.radians(lat_a), math.radians(lat_b)
    lat_delta = math.radians(lat_b - lat_a)
    lng_delta = math.radians(lng_b - lng_a)
    haversine = math.sin(lat_delta / 2) ** 2 + math.cos(lat_a_rad) * math.cos(lat_b_rad) * math.sin(lng_delta / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, haversine)))


def list_events(user_id: str, args) -> list[dict]:
    nearby = parse_nearby_query(args)
    rows = get_db().execute("SELECT * FROM events WHERE status IN ('recruiting', 'formed', 'ongoing')").fetchall()
    events = [_event_summary(_decode_event(row), user_id) for row in rows]
    tag = args.get("tag")
    budget = args.get("budget")
    benefit = args.get("benefit")
    city = args.get("city")
    if tag in EVENT_TAGS:
        events = [event for event in events if tag in event["required_tags"]]
    if budget in ("under_50", "50-100", "100-200", "200_plus"):
        events = [event for event in events if event["budget_level"] == budget]
    if benefit == "yes":
        events = [event for event in events if event["merchant_benefit"]]
    if city:
        events = [event for event in events if POI_LOCATIONS.get(event["poi_id"], {}).get("city") == city]
    if nearby["active"]:
        for event in events:
            poi = POI_LOCATIONS.get(event["poi_id"])
            event["distance_km"] = (
                haversine_km(nearby["lat"], nearby["lng"], poi["lat"], poi["lng"]) if poi else None
            )
        events = [
            event for event in events
            if event["distance_km"] is not None and event["distance_km"] <= nearby["radius_km"]
        ]
    sort = args.get("sort", "match")
    if sort == "time":
        events.sort(key=lambda item: item["start_at"])
    elif sort == "distance" and nearby["active"]:
        events.sort(key=lambda item: (item["distance_km"], item["start_at"]))
    else:
        events.sort(key=lambda item: item["raw_score"], reverse=True)
    for event in events:
        event.pop("raw_score", None)
        if "distance_km" in event:
            event["distance_km"] = round(event["distance_km"], 1)
    return events


def get_event(event_id: str, user_id: str | None = None) -> dict | None:
    event = _decode_event(get_db().execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone())
    if event is None:
        return None
    if user_id:
        is_host = event["host_type"] == "user" and event["host_id"] == user_id
        if event["status"] in ("pending_review", "rejected") and not is_host:
            return None
        _event_summary(event, user_id)
        member = get_db().execute(
            """SELECT role, membership_status, match_score, common_tag_count, checked_in, joined_at
               FROM event_members WHERE event_id = ? AND user_id = ?""",
            (event_id, user_id),
        ).fetchone()
        event["viewer_membership"] = dict(member) if member else None
        event["is_host"] = is_host
        event["group_conversation_id"] = _group_conversation_id(event_id)
        event.pop("raw_score", None)
        event.pop("host_id", None)
    return event


def _form_values(form) -> dict:
    tags = form.getlist("required_tags")
    if not 1 <= len(tags) <= 5 or any(tag not in EVENT_TAGS for tag in tags):
        raise ValidationError("请选择 1–5 个有效的目标标签。")
    title = form.get("title", "").strip()
    description = form.get("description", "").strip()
    poi_id = form.get("poi_id")
    if not 2 <= len(title) <= 60:
        raise ValidationError("活动主题需为 2–60 个字符。")
    if len(description) > 200:
        raise ValidationError("活动介绍不能超过 200 个字符。")
    if poi_id not in POIS:
        raise ValidationError("地点必须从已验证餐厅中选择。")
    start_at = _parse_datetime(form.get("start_at", ""))
    if start_at.minute not in (0, 30) or start_at.second:
        raise ValidationError("活动时间需精确到 30 分钟。")
    if start_at <= datetime.now(timezone.utc):
        raise ValidationError("活动时间必须在未来。")
    try:
        min_size, max_size = int(form.get("min_size", "3")), int(form.get("max_size", ""))
    except ValueError as error:
        raise ValidationError("请填写人数限制。") from error
    if not (3 <= min_size <= max_size <= 10):
        raise ValidationError("人数须满足 3 ≤ 成团下限 ≤ 人数上限 ≤ 10。")
    deadline_text = form.get("signup_deadline", "").strip()
    deadline = _parse_datetime(deadline_text) if deadline_text else start_at - timedelta(hours=2)
    if not datetime.now(timezone.utc) < deadline < start_at:
        raise ValidationError("报名截止时间需晚于当前时间且早于活动开始时间。")
    budget = form.get("budget_level")
    pay_type = form.get("pay_type")
    gender_policy = form.get("gender_policy")
    signup_mode = form.get("signup_mode")
    if budget not in ("under_50", "50-100", "100-200", "200_plus"):
        raise ValidationError("请选择人均预算。")
    if pay_type not in ("AA", "host_pays", "separate") or gender_policy not in ("any", "balanced", "same_gender"):
        raise ValidationError("费用方式或性别构成偏好无效。")
    if signup_mode not in ("first_come", "review"):
        raise ValidationError("报名方式无效。")
    return {
        "title": title, "description": description, "poi_id": poi_id, "start_at": start_at.isoformat(),
        "signup_deadline": deadline.isoformat(), "min_size": min_size, "max_size": max_size,
        "required_tags": tags, "budget_level": budget, "pay_type": pay_type,
        "gender_policy": gender_policy, "signup_mode": signup_mode,
    }


def create_user_event(user_id: str, form) -> str:
    host = get_user(user_id)
    if host is None:
        raise ValidationError("发起人账户不存在。")
    if not host["phone_verified"]:
        raise ValidationError("发起线下饭局前需完成手机号验证。")
    values = _form_values(form)
    poi = POIS[values["poi_id"]]
    event_id = f"event_{uuid4().hex[:12]}"
    db = get_db()
    db.execute(
        """INSERT INTO events (
            id, host_type, host_id, title, poi_id, poi_name, poi_address, start_at, signup_deadline,
            min_size, max_size, budget_level, pay_type, required_tags_json, gender_policy, signup_mode,
            status, description, merchant_benefit_json, created_at
        ) VALUES (?, 'user', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, NULL, ?)""",
        (event_id, user_id, values["title"], values["poi_id"], poi["name"], poi["address"], values["start_at"],
         values["signup_deadline"], values["min_size"], values["max_size"], values["budget_level"], values["pay_type"],
         json.dumps(values["required_tags"], ensure_ascii=False), values["gender_policy"], values["signup_mode"],
         values["description"], utcnow()),
    )
    db.execute(
        """INSERT INTO event_members (event_id, user_id, role, membership_status, match_score, common_tag_count, joined_at)
           VALUES (?, ?, 'host', 'approved', 100, ?, ?)""",
        (event_id, user_id, len(values["required_tags"]), utcnow()),
    )
    db.commit()
    return event_id


def _event_overlap(event: dict, user_id: str) -> bool:
    candidate_start = _parse_datetime(event["start_at"])
    candidate_end = candidate_start + timedelta(hours=3)
    rows = get_db().execute(
        """SELECT e.* FROM events e JOIN event_members em ON em.event_id = e.id
           WHERE em.user_id = ? AND em.membership_status IN ('approved', 'pending')
             AND e.status IN ('recruiting', 'formed', 'ongoing') AND e.id != ?""",
        (user_id, event["id"]),
    ).fetchall()
    for row in rows:
        other_start = _parse_datetime(row["start_at"])
        if candidate_start < other_start + timedelta(hours=3) and other_start < candidate_end:
            return True
    return False


def signup_for_event(event_id: str, user_id: str) -> str:
    event = get_event(event_id, user_id)
    if event is None:
        raise ValidationError("活动不存在。")
    if event["status"] != "recruiting":
        raise ValidationError("此活动当前不接受报名。")
    if _parse_datetime(event["signup_deadline"]) <= datetime.now(timezone.utc):
        raise ValidationError("此活动报名已截止。")
    if event["approved_count"] >= event["max_size"]:
        raise ValidationError("活动人数已满。")
    if event["viewer_membership"]:
        raise ValidationError("你已报名此活动。")
    if _event_overlap(event, user_id):
        raise ValidationError("该时段与已报名活动冲突。")
    score = event_match_score(user_id, event["required_tags"])
    membership_status = "pending" if event["signup_mode"] == "review" else "approved"
    db = get_db()
    result = db.execute(
        """INSERT INTO event_members (event_id, user_id, role, membership_status, match_score, common_tag_count, joined_at)
           SELECT ?, ?, 'member', ?, ?, ?, ?
           WHERE ? != 'approved'
              OR (SELECT COUNT(*) FROM event_members
                  WHERE event_id = ? AND membership_status = 'approved')
                 < (SELECT max_size FROM events WHERE id = ?)""",
        (
            event_id,
            user_id,
            membership_status,
            score["display_score"],
            score["common_tag_count"],
            utcnow(),
            membership_status,
            event_id,
            event_id,
        ),
    )
    if not result.rowcount:
        db.rollback()
        raise ValidationError("活动人数已满。")
    db.commit()
    return membership_status


def review_applicants(event_id: str, host_id: str) -> list[dict]:
    event = get_event(event_id, host_id)
    if (
        not event
        or not event["is_host"]
        or event["signup_mode"] != "review"
        or event["status"] != "recruiting"
    ):
        raise ValidationError("无权审核此活动的报名。")
    rows = get_db().execute(
        """SELECT user_id, match_score, common_tag_count, joined_at FROM event_members
           WHERE event_id = ? AND membership_status = 'pending' ORDER BY joined_at""", (event_id,)
    ).fetchall()
    # The host receives an opaque action reference, never a profile id.
    return [
        {
            "review_token": _review_token(event_id, row["user_id"]),
            "match_score": row["match_score"],
            "common_tag_count": row["common_tag_count"],
            "joined_at": row["joined_at"],
        }
        for row in rows
    ]


def review_signup(event_id: str, host_id: str, applicant_id: str, approve: bool) -> None:
    event = get_event(event_id, host_id)
    if (
        not event
        or not event["is_host"]
        or event["signup_mode"] != "review"
        or event["status"] != "recruiting"
    ):
        raise ValidationError("无权审核此活动的报名。")
    if _parse_datetime(event["signup_deadline"]) <= datetime.now(timezone.utc):
        raise ValidationError("此活动报名已截止。")
    pending = get_db().execute(
        """SELECT user_id FROM event_members
           WHERE event_id = ? AND membership_status = 'pending'""",
        (event_id,),
    ).fetchall()
    resolved_id = next(
        (
            row["user_id"]
            for row in pending
            if hmac.compare_digest(applicant_id, row["user_id"])
            or hmac.compare_digest(applicant_id, _review_token(event_id, row["user_id"]))
        ),
        None,
    )
    if resolved_id is None:
        raise ValidationError("没有可处理的报名申请。")
    if approve:
        approved_count = get_db().execute(
            """SELECT COUNT(*) AS count FROM event_members
               WHERE event_id = ? AND membership_status = 'approved'""",
            (event_id,),
        ).fetchone()["count"]
        if approved_count >= event["max_size"]:
            raise ValidationError("活动人数已满，不能继续通过申请。")
    status = "approved" if approve else "rejected"
    db = get_db()
    result = db.execute(
        """UPDATE event_members SET membership_status = ?
           WHERE event_id = ? AND user_id = ? AND membership_status = 'pending'
             AND (? = 0 OR
                  (SELECT COUNT(*) FROM event_members
                   WHERE event_id = ? AND membership_status = 'approved')
                  < (SELECT max_size FROM events WHERE id = ?))""",
        (status, event_id, resolved_id, int(approve), event_id, event_id),
    )
    if not result.rowcount:
        if approve:
            still_pending = db.execute(
                """SELECT 1 FROM event_members
                   WHERE event_id = ? AND user_id = ? AND membership_status = 'pending'""",
                (event_id, resolved_id),
            ).fetchone()
            if still_pending:
                db.rollback()
                raise ValidationError("活动人数已满，不能继续通过申请。")
        db.rollback()
        raise ValidationError("没有可处理的报名申请。")
    db.commit()


def cancel_event(event_id: str, host_id: str) -> None:
    event = get_event(event_id, host_id)
    if not event or not event["is_host"]:
        raise ValidationError("只有发起人可以取消该活动。")
    if event["status"] not in ("draft", "recruiting"):
        raise ValidationError("当前状态不能取消活动。")
    db = get_db()
    db.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (event_id,))
    db.execute(
        """UPDATE event_members SET membership_status = 'rejected'
           WHERE event_id = ? AND membership_status = 'pending'""",
        (event_id,),
    )
    db.execute("UPDATE event_coupons SET status = 'invalid' WHERE event_id = ?", (event_id,))
    db.commit()


def _group_conversation_id(event_id: str) -> str | None:
    row = get_db().execute("SELECT id FROM conversations WHERE event_id = ? AND type = 'event_group'", (event_id,)).fetchone()
    return row["id"] if row else None


def _form_group(event: dict) -> None:
    db = get_db()
    if _group_conversation_id(event["id"]):
        return
    members = _event_members(event["id"], "approved")
    if not (3 <= len(members) <= event["max_size"] <= 10):
        raise ValidationError("活动成员数量不符合 3–10 人成团边界。")
    conversation_id = f"group_{uuid4().hex[:12]}"
    db.execute(
        "INSERT INTO conversations (id, type, event_id, created_at) VALUES (?, 'event_group', ?, ?)",
        (conversation_id, event["id"], utcnow()),
    )
    aliases = ("银杏", "星云", "海盐", "青柠", "云杉", "琥珀", "月桂", "鲸歌", "栖木", "微光")
    for index, member in enumerate(members):
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, group_alias, joined_at) VALUES (?, ?, ?, ?)",
            (conversation_id, member["user_id"], aliases[index], utcnow()),
        )
    body = f"饭局已成团｜{event['start_at']}｜{event['poi_name']}（{event['poi_address']}）"
    db.execute(
        "INSERT INTO messages (conversation_id, sender_id, message_type, content, metadata_json, created_at) VALUES (?, NULL, 'system_card', ?, '{}', ?)",
        (conversation_id, body, utcnow()),
    )
    if event["merchant_benefit"]:
        for member in members:
            code = f"{event['id'][-4:].upper()}-{member['user_id'][-4:].upper()}"
            db.execute(
                """INSERT INTO event_coupons (id, event_id, user_id, benefit_json, redeem_code, status, issued_at)
                   VALUES (?, ?, ?, ?, ?, 'issued', ?)""",
                (f"coupon_{uuid4().hex[:12]}", event["id"], member["user_id"],
                 json.dumps(event["merchant_benefit"], ensure_ascii=False), code, utcnow()),
            )
        db.execute(
            "INSERT INTO messages (conversation_id, sender_id, message_type, content, metadata_json, created_at) VALUES (?, NULL, 'system_card', ?, '{}', ?)",
            (conversation_id, f"商家权益已发放：{event['merchant_benefit']['label']}。核销码仅在本次饭局时段和门店有效。", utcnow()),
        )


def refresh_event_statuses(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    db = get_db()
    changed = 0
    wrote = False
    rows = db.execute("SELECT * FROM events WHERE status IN ('recruiting', 'formed', 'ongoing', 'ended')").fetchall()
    for row in rows:
        event = _decode_event(row)
        start = _parse_datetime(event["start_at"])
        deadline = _parse_datetime(event["signup_deadline"])
        if event["status"] == "recruiting" and deadline <= now:
            count = len(_event_members(event["id"], "approved"))
            if 3 <= event["min_size"] <= count <= event["max_size"] <= 10:
                db.execute("UPDATE events SET status = 'formed' WHERE id = ?", (event["id"],))
                event["status"] = "formed"
                _form_group(event)
            else:
                db.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (event["id"],))
                event["status"] = "cancelled"
            db.execute(
                """UPDATE event_members SET membership_status = 'rejected'
                   WHERE event_id = ? AND membership_status = 'pending'""",
                (event["id"],),
            )
            changed += 1
            wrote = True
        if event["status"] == "formed" and start <= now:
            db.execute("UPDATE events SET status = 'ongoing' WHERE id = ?", (event["id"],))
            event["status"] = "ongoing"
            changed += 1
            wrote = True
        if event["status"] in ("formed", "ongoing") and start + timedelta(hours=3) <= now:
            db.execute("UPDATE events SET status = 'ended' WHERE id = ?", (event["id"],))
            event["status"] = "ended"
            changed += 1
            wrote = True
        if start + timedelta(days=7) <= now:
            archived = db.execute(
                "UPDATE conversations SET archived_at = ? WHERE event_id = ? AND archived_at IS NULL",
                (utcnow(), event["id"]),
            )
            wrote = wrote or bool(archived.rowcount)
    if wrote:
        db.commit()
    return changed


def demo_settle_event(event_id: str, user_id: str) -> str:
    if not current_app.config["DEMO_MODE"]:
        raise ValidationError("演示快捷操作只在 DEMO_MODE 中可用。")
    event = get_event(event_id, user_id)
    if not event or not event["is_host"]:
        raise ValidationError("只有发起人可以执行演示结算。")
    if event["status"] != "recruiting":
        raise ValidationError("只有报名中的活动可演示结算。")
    approved = len(_event_members(event_id, "approved"))
    db = get_db()
    if 3 <= event["min_size"] <= approved <= event["max_size"] <= 10:
        db.execute("UPDATE events SET status = 'formed' WHERE id = ?", (event_id,))
        event["status"] = "formed"
        _form_group(event)
        result = "formed"
    else:
        db.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (event_id,))
        result = "cancelled"
    db.execute(
        """UPDATE event_members SET membership_status = 'rejected'
           WHERE event_id = ? AND membership_status = 'pending'""",
        (event_id,),
    )
    db.commit()
    return result


def viewer_coupon(event_id: str, user_id: str) -> dict | None:
    row = get_db().execute(
        "SELECT * FROM event_coupons WHERE event_id = ? AND user_id = ? ORDER BY issued_at DESC LIMIT 1", (event_id, user_id)
    ).fetchone()
    if not row:
        return None
    coupon = dict(row)
    coupon["benefit"] = json.loads(coupon.pop("benefit_json"))
    return coupon


def redeem_coupon(event_id: str, user_id: str, redeem_code: str) -> None:
    coupon = viewer_coupon(event_id, user_id)
    if not coupon or coupon["status"] != "issued" or coupon["redeem_code"] != redeem_code:
        raise ValidationError("核销码无效或已使用。")
    get_db().execute("UPDATE event_coupons SET status = 'redeemed', redeemed_at = ? WHERE id = ?", (utcnow(), coupon["id"]))
    get_db().commit()
