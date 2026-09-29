from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime
from uuid import uuid4

from flask import current_app

from ..db import get_db, utcnow
from .ai_fallback import AiFallbackFailure, ai_fallback_available, complete_ai_reply
from .matching import calculate_match, is_hard_filter_match
from .users import ValidationError, get_user, matching_tags, profile_tags


TASK_CARDS = {
    "学习": [
        "说出你最近最想学的一项新技能，并约定一个 10 分钟的开始动作。",
        "分享一次你坚持最久的学习习惯，以及它为什么没有中断。",
        "用三个词描述一个你想去深入了解的领域。",
        "给对方推荐一个你正在使用的学习工具。",
        "假如只能保留一门正在学习的知识，你会选什么？",
        "各自说一个最近纠正过的错误认知。",
    ],
    "运动": [
        "讲一次让你想继续运动下去的瞬间。",
        "设计一场 30 分钟、零器械的双人运动挑战。",
        "你最愿意和搭子一起完成哪项运动？",
        "说出你的运动前仪式感。",
        "分享一首最适合运动时听的歌。",
        "互相猜猜对方更偏晨练还是夜练，然后公布答案。",
    ],
    "生活": [
        "用一道食物形容最近的生活状态，并解释原因。",
        "分享一个你会反复去的小店或城市角落。",
        "如果明天完全不用工作，你会如何安排 24 小时？",
        "说说最近让你小小开心的一件事。",
        "各自列出一个想戒掉和一个想保留的小习惯。",
        "给对方出一道你觉得很有代表性的生活选择题。",
    ],
    "脑洞": [
        "如果可以瞬移到任何地方吃晚餐，你会选哪里？",
        "给彼此的匿名代号编一个超能力设定。",
        "如果你们要共同做一档播客，第一期主题是什么？",
        "只用三样东西，如何度过一个没有网络的周末？",
        "为你们的聊天取一个电影片名。",
        "假如一天有 30 小时，你会把多出的 6 小时花在哪里？",
    ],
    "价值观": [
        "你认为一段舒服的关系最重要的一条规则是什么？",
        "讲一件别人给过你、你一直记得的善意。",
        "你更在意被理解，还是被支持？为什么？",
        "如果只能带走一种成长能力，你会带走什么？",
        "你如何判断一件事值得长期投入？",
        "分享一个你希望未来的自己仍然保持的特质。",
    ],
}
DICE_TOPICS = {
    1: "最近一次让你觉得“今天值了”的小事是什么？",
    2: "你想和搭子一起养成什么习惯？",
    3: "如果周末只选一个活动，你会选什么？",
    4: "分享一部想二刷的电影或一本书。",
    5: "你最想把哪项技能点亮到专业级？",
    6: "说一个朋友经常误解你的地方。",
}


def _members(conversation_id: str) -> list[dict]:
    rows = get_db().execute(
        """SELECT cm.user_id, cm.group_alias, u.anonymous_alias, u.city, u.birth_year, u.interests_json, u.is_demo
           FROM conversation_members cm JOIN users u ON u.id = cm.user_id
           WHERE cm.conversation_id = ? ORDER BY cm.joined_at""", (conversation_id,)
    ).fetchall()
    members = []
    for row in rows:
        member = dict(row)
        member["interests"] = json.loads(member.pop("interests_json"))
        members.append(member)
    return members


def _conversation_row(conversation_id: str):
    return get_db().execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()


def is_ai_fallback_conversation(conversation_id: str) -> bool:
    row = _conversation_row(conversation_id)
    return bool(row and row["counterpart_type"] == "ai")


def _ensure_member(conversation_id: str, user_id: str):
    if not get_db().execute(
        "SELECT 1 FROM conversation_members WHERE conversation_id = ? AND user_id = ?", (conversation_id, user_id)
    ).fetchone():
        raise ValidationError("你不是此会话成员。")


def _is_direct_blocked(conversation_id: str) -> bool:
    row = _conversation_row(conversation_id)
    if not row or row["type"] != "direct" or row["counterpart_type"] == "ai":
        return False
    member_ids = [member["user_id"] for member in _members(conversation_id)]
    if len(member_ids) != 2:
        return False
    left_id, right_id = member_ids
    return bool(
        get_db().execute(
            """SELECT 1 FROM blocks
               WHERE (blocker_id = ? AND blocked_id = ?)
                  OR (blocker_id = ? AND blocked_id = ?)
               LIMIT 1""",
            (left_id, right_id, right_id, left_id),
        ).fetchone()
    )


def _is_cross_pool_direct(conversation_id: str) -> bool:
    row = _conversation_row(conversation_id)
    if not row or row["type"] != "direct" or row["counterpart_type"] == "ai":
        return False
    members = _members(conversation_id)
    return len(members) == 2 and bool(members[0]["is_demo"]) != bool(members[1]["is_demo"])


def _ensure_interactive(conversation_id: str, user_id: str):
    _ensure_member(conversation_id, user_id)
    conversation = _conversation_row(conversation_id)
    if conversation["archived_at"]:
        raise ValidationError("该会话已归档，不能继续互动。")
    if conversation["counterpart_type"] == "ai" and not ai_fallback_available():
        raise ValidationError("AI 候场服务当前未启用，这段历史会话暂时只能查看。")
    if _is_cross_pool_direct(conversation_id):
        raise ValidationError("该历史会话已停用，不能继续互动。")
    if _is_direct_blocked(conversation_id):
        raise ValidationError("这段会话已停止联系，不能继续互动。")
    return conversation


def _insert_system(
    conversation_id: str,
    content: str,
    metadata: dict | None = None,
    *,
    sender_id: str | None = None,
) -> None:
    get_db().execute(
        """INSERT INTO messages (conversation_id, sender_id, message_type, content, metadata_json, created_at)
           VALUES (?, ?, 'system_card', ?, ?, ?)""",
        (conversation_id, sender_id, content, json.dumps(metadata or {}, ensure_ascii=False), utcnow()),
    )


def start_ai_fallback_conversation(user_id: str) -> str:
    """Create one clearly labeled, single-member AI standby conversation."""
    if not get_user(user_id) or not ai_fallback_available():
        raise ValidationError("AI 候场服务当前不可用。")
    conversation_id = f"ai_{hashlib.sha256(f'ai:{user_id}'.encode()).hexdigest()[:20]}"
    db = get_db()
    created = db.execute(
        """INSERT OR IGNORE INTO conversations
           (id, type, counterpart_type, event_id, created_at)
           VALUES (?, 'direct', 'ai', NULL, ?)""",
        (conversation_id, utcnow()),
    ).rowcount
    db.execute(
        """INSERT OR IGNORE INTO conversation_members
           (conversation_id, user_id, group_alias, joined_at)
           VALUES (?, ?, NULL, ?)""",
        (conversation_id, user_id, utcnow()),
    )
    if created:
        _insert_system(
            conversation_id,
            "当前没有符合硬性条件的真人候选。这里是明确标注的 AI 候场互动，不是真人匹配。",
            {"kind": "ai_fallback_started"},
        )
    db.commit()
    return conversation_id


def start_direct_conversation(viewer_id: str, candidate_id: str) -> str:
    viewer, candidate = get_user(viewer_id), get_user(candidate_id)
    if (
        viewer_id == candidate_id
        or not viewer
        or not candidate
        or bool(viewer["is_demo"]) != bool(candidate["is_demo"])
        or not is_hard_filter_match(viewer, candidate)
    ):
        raise ValidationError("该匿名匹配已不可用。")
    if get_db().execute(
        "SELECT 1 FROM blocks WHERE (blocker_id = ? AND blocked_id = ?) OR (blocker_id = ? AND blocked_id = ?)",
        (viewer_id, candidate_id, candidate_id, viewer_id),
    ).fetchone():
        raise ValidationError("该会话不可建立。")
    existing = get_db().execute(
        """SELECT c.id FROM conversations c
           JOIN conversation_members a ON a.conversation_id = c.id AND a.user_id = ?
           JOIN conversation_members b ON b.conversation_id = c.id AND b.user_id = ?
           WHERE c.type = 'direct' LIMIT 1""", (viewer_id, candidate_id),
    ).fetchone()
    if existing:
        return existing["id"]

    pair_key = ":".join(sorted((viewer_id, candidate_id)))
    conversation_id = f"direct_{hashlib.sha256(pair_key.encode()).hexdigest()[:20]}"
    db = get_db()
    created = db.execute(
        "INSERT OR IGNORE INTO conversations (id, type, event_id, created_at) VALUES (?, 'direct', NULL, ?)",
        (conversation_id, utcnow()),
    ).rowcount
    for user_id in (viewer_id, candidate_id):
        db.execute(
            "INSERT OR IGNORE INTO conversation_members (conversation_id, user_id, group_alias, joined_at) VALUES (?, ?, NULL, ?)",
            (conversation_id, user_id, utcnow()),
        )
    if created:
        score = calculate_match(viewer, candidate)
        _insert_system(conversation_id, f"匿名会话已建立。你们的匹配度为 {score['display_score']}%，先从一个问题开始吧。", {"kind": "match_started"})
    db.commit()
    return conversation_id


def conversation_list(user_id: str) -> list[dict]:
    rows = get_db().execute(
        """SELECT c.* FROM conversations c JOIN conversation_members cm ON cm.conversation_id = c.id
           WHERE cm.user_id = ? ORDER BY c.created_at DESC""", (user_id,)
    ).fetchall()
    conversations = []
    for row in rows:
        conversation = dict(row)
        if conversation["type"] == "direct" and conversation["counterpart_type"] == "ai":
            conversation["display_name"] = "AI 候场搭子"
            conversation["subtitle"] = "AI 互动兜底 · 非真人"
        elif conversation["type"] == "direct":
            other = next(member for member in _members(conversation["id"]) if member["user_id"] != user_id)
            conversation["display_name"] = other["anonymous_alias"]
            conversation["subtitle"] = "匿名一对一会话"
        else:
            event = get_db().execute("SELECT title FROM events WHERE id = ?", (conversation["event_id"],)).fetchone()
            conversation["display_name"] = event["title"] if event else "已归档饭局群聊"
            conversation["subtitle"] = "3–10 人临时群聊"
        last = get_db().execute(
            "SELECT content, created_at FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (conversation["id"],)
        ).fetchone()
        conversation["last_message"] = dict(last) if last else None
        conversations.append(conversation)
    return conversations


def _shared_points(left_id: str, right_id: str) -> list[str]:
    left, right = get_user(left_id), get_user(right_id)
    points = []
    common_purpose = set(left["purposes"]) & set(right["purposes"])
    common_interests = set(left["interests"]) & set(right["interests"])
    if common_purpose:
        points.append(f"你们都在寻找「{sorted(common_purpose)[0]}」")
    if common_interests:
        points.append(f"共同兴趣：{sorted(common_interests)[0]}")
    left_tags = {tag["tag_id"]: tag["value"] for tag in matching_tags(left_id)}
    right_tags = {tag["tag_id"]: tag["value"] for tag in matching_tags(right_id)}
    left_languages = left_tags.get("learning_languages", left_tags.get("lang_learning", {})).get("items", [])
    right_languages = right_tags.get("learning_languages", right_tags.get("lang_learning", {})).get("items", [])
    languages = set(left_languages) & set(right_languages)
    sports = set(left_tags.get("sport_primary", {}).get("items", [])) & set(
        right_tags.get("sport_primary", {}).get("items", [])
    )
    coding = set(left_tags.get("coding_primary_languages", {}).get("items", [])) & set(
        right_tags.get("coding_primary_languages", {}).get("items", [])
    )
    if languages:
        points.append(f"都在学：{sorted(languages)[0]}")
    if sports:
        points.append(f"共同运动：{sorted(sports)[0]}")
    if coding:
        points.append(f"共同技术：{sorted(coding)[0]}")
    if left["city"] == right["city"]:
        points.append("你们在同一座城市")
    return points or ["你们都愿意从匿名对话开始认识彼此"]


def _demo_progress_level(conversation_id: str, viewer_id: str, legacy_offset: int) -> int:
    rows = get_db().execute(
        """SELECT metadata_json FROM messages
           WHERE conversation_id = ? AND sender_id = ?
             AND message_type = 'system_card'
             AND json_extract(metadata_json, '$.kind') = 'demo_progress'""",
        (conversation_id, viewer_id),
    ).fetchall()
    levels = [legacy_offset]
    for row in rows:
        metadata = json.loads(row["metadata_json"])
        level = metadata.get("level")
        if isinstance(level, int):
            levels.append(level)
    return max(0, min(4, max(levels)))


def relationship_progress(conversation_id: str, viewer_id: str | None = None) -> dict:
    conversation = _conversation_row(conversation_id)
    if not conversation or conversation["type"] != "direct":
        return {"level": 0, "label": "群聊", "next_requirement": "使用破冰工具，让全桌都能自然开口。", "unlocked_points": []}
    if conversation["counterpart_type"] == "ai":
        text_count = get_db().execute(
            "SELECT COUNT(*) AS count FROM messages WHERE conversation_id = ? AND message_type = 'text'",
            (conversation_id,),
        ).fetchone()["count"]
        return {
            "level": 0,
            "label": "AI 候场",
            "next_requirement": "真人候选出现前，可在明确知情的前提下进行 AI 文字互动。",
            "heat": text_count,
            "unlocked_points": [],
            "total_point_count": 0,
        }
    members = _members(conversation_id)
    counts = get_db().execute(
        """SELECT sender_id, COUNT(*) AS count
           FROM messages WHERE conversation_id = ? AND message_type = 'text' GROUP BY sender_id""", (conversation_id,)
    ).fetchall()
    text_count = sum(row["count"] for row in counts)
    both_spoke = len(counts) == 2 and all(row["count"] > 0 for row in counts)
    active_days = get_db().execute(
        """SELECT COUNT(*) AS count FROM (
               SELECT substr(created_at, 1, 10) AS active_day
               FROM messages
               WHERE conversation_id = ? AND message_type = 'text'
               GROUP BY active_day
               HAVING COUNT(DISTINCT sender_id) = 2
           )""",
        (conversation_id,),
    ).fetchone()["count"]
    tool_count = get_db().execute(
        "SELECT COUNT(*) AS count FROM messages WHERE conversation_id = ? AND message_type = 'system_card' AND json_extract(metadata_json, '$.kind') IN ('dice', 'task_card', 'match_point')",
        (conversation_id,),
    ).fetchone()["count"]
    heat = text_count + tool_count * 3
    natural_level = 0
    if both_spoke and heat >= 10:
        natural_level = 1
    if both_spoke and active_days >= 3:
        natural_level = 2
    if both_spoke and active_days >= 7:
        natural_level = 3
    unlocked = get_db().execute(
        "SELECT content FROM messages WHERE conversation_id = ? AND json_extract(metadata_json, '$.kind') = 'match_point' ORDER BY id",
        (conversation_id,),
    ).fetchall()
    target_points = _shared_points(members[0]["user_id"], members[1]["user_id"])
    offset = (
        _demo_progress_level(conversation_id, viewer_id, conversation["demo_progress_offset"])
        if viewer_id
        else conversation["demo_progress_offset"]
    )
    level = max(natural_level, offset)
    if len(unlocked) >= len(target_points):
        level = max(level, 4)
    labels = ("L0 完全匿名", "L1 初识", "L2 熟悉", "L3 熟络", "L4 走出产品")
    next_requirements = (
        "双方发言并累积 10 点互动热度，解锁第一个匹配点。",
        "连续有效聊天满 3 天，解锁更多兴趣线索。",
        "连续有效聊天满 7 天，解锁完整标签。",
        "解锁全部匹配点，开放联系方式交换。",
        "你们已完成全部解锁。",
    )
    return {
        "level": min(level, 4), "label": labels[min(level, 4)], "next_requirement": next_requirements[min(level, 4)],
        "heat": heat, "unlocked_points": [row["content"] for row in unlocked], "total_point_count": len(target_points),
    }


def _visible_counterpart(viewer_id: str, conversation_id: str, progress: dict) -> dict:
    other = next(member for member in _members(conversation_id) if member["user_id"] != viewer_id)
    visible = {"anonymous_alias": other["anonymous_alias"], "level": progress["level"]}
    if progress["level"] >= 1:
        visible["city"] = other["city"]
        age = datetime.now().year - other["birth_year"]
        visible["age_range"] = "18–24" if age < 25 else "25–29" if age < 30 else "30–34" if age < 35 else "35+"
    if progress["level"] >= 2:
        visible["interest_category"] = other["interests"][0] if other["interests"] else "兴趣探索中"
        visible["avatar_mode"] = "blur"
    if progress["level"] >= 3:
        visible["interests"] = other["interests"]
        eligible = {
            (tag["tag_id"], json.dumps(tag["value"], sort_keys=True))
            for tag in matching_tags(other["user_id"])
        }
        visible["tags"] = [
            tag
            for tag in profile_tags(other["user_id"])
            if (tag["tag_id"], json.dumps(tag["value"], sort_keys=True)) in eligible
        ]
        visible["avatar_mode"] = "clear_placeholder"
    if progress["level"] >= 4:
        visible["contact_exchange_available"] = True
    return visible


def get_conversation(conversation_id: str, viewer_id: str) -> dict:
    _ensure_member(conversation_id, viewer_id)
    row = _conversation_row(conversation_id)
    if row is None:
        raise ValidationError("会话不存在。")
    conversation = dict(row)
    conversation["is_archived"] = bool(conversation["archived_at"])
    conversation["is_ai_fallback"] = conversation["counterpart_type"] == "ai"
    conversation["is_disabled"] = _is_cross_pool_direct(conversation_id) or (
        conversation["is_ai_fallback"] and not ai_fallback_available()
    )
    conversation["is_blocked"] = _is_direct_blocked(conversation_id)
    messages = []
    for message in get_db().execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
    ).fetchall():
        item = dict(message)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        messages.append(item)
    conversation["messages"] = messages
    if conversation["type"] == "direct":
        progress = relationship_progress(conversation_id, viewer_id)
        conversation["progress"] = progress
        if conversation["is_ai_fallback"]:
            conversation["counterpart"] = {"anonymous_alias": "AI 候场搭子", "level": 0}
        else:
            conversation["counterpart"] = _visible_counterpart(viewer_id, conversation_id, progress)
        conversation["members"] = []
    else:
        event = get_db().execute("SELECT * FROM events WHERE id = ?", (conversation["event_id"],)).fetchone()
        conversation["event"] = ({
            "title": event["title"], "start_at": event["start_at"], "poi_name": event["poi_name"],
            "poi_address": event["poi_address"],
        } if event else None)
        # Group aliases plus 1–2 interests are the only member information exposed.
        conversation["members"] = [
            {"alias": member["group_alias"], "interest_tags": member["interests"][:2]}
            for member in _members(conversation_id)
        ]
        conversation["progress"] = relationship_progress(conversation_id)
    return conversation


def _ensure_ai_reply_budget(conversation_id: str) -> None:
    try:
        configured_maximum = int(current_app.config.get("AI_FALLBACK_MAX_REPLIES", 30))
    except (TypeError, ValueError):
        configured_maximum = 30
    maximum = max(1, min(100, configured_maximum))
    count = get_db().execute(
        """SELECT COUNT(*) AS count FROM messages
           WHERE conversation_id = ? AND message_type = 'text'
             AND json_extract(metadata_json, '$.kind') = 'ai_reply'""",
        (conversation_id,),
    ).fetchone()["count"]
    if count >= maximum:
        raise ValidationError("本次 AI 候场互动已达到回复上限，请等待真人候选。")


def _ai_text_context(conversation_id: str) -> list[tuple[str, str]]:
    rows = get_db().execute(
        """SELECT sender_id, content, metadata_json FROM messages
           WHERE conversation_id = ? AND message_type = 'text'
           ORDER BY id DESC LIMIT 12""",
        (conversation_id,),
    ).fetchall()
    context = []
    for row in reversed(rows):
        try:
            metadata = json.loads(row["metadata_json"])
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        if metadata.get("kind") == "ai_reply":
            context.append(("assistant", row["content"]))
        elif row["sender_id"] is not None:
            context.append(("user", row["content"]))
    return context


def _store_ai_reply(conversation_id: str) -> None:
    try:
        reply = complete_ai_reply(_ai_text_context(conversation_id))
    except AiFallbackFailure as error:
        current_app.logger.warning("AI fallback request failed: %s", error.code)
        raise ValidationError("你的消息已保存，但 AI 候场搭子暂时没能回复，请稍后再试。") from error
    get_db().execute(
        """INSERT INTO messages
           (conversation_id, sender_id, message_type, content, metadata_json, created_at)
           VALUES (?, NULL, 'text', ?, ?, ?)""",
        (conversation_id, reply, json.dumps({"kind": "ai_reply"}), utcnow()),
    )
    get_db().commit()


def send_message(conversation_id: str, sender_id: str, content: str) -> None:
    _ensure_interactive(conversation_id, sender_id)
    content = content.strip()
    if not content or len(content) > 500:
        raise ValidationError("消息需为 1–500 个字符。")
    ai_fallback = is_ai_fallback_conversation(conversation_id)
    if ai_fallback:
        _ensure_ai_reply_budget(conversation_id)
    get_db().execute(
        "INSERT INTO messages (conversation_id, sender_id, message_type, content, metadata_json, created_at) VALUES (?, ?, 'text', ?, '{}', ?)",
        (conversation_id, sender_id, content, utcnow()),
    )
    get_db().commit()
    if ai_fallback:
        _store_ai_reply(conversation_id)


def use_tool(conversation_id: str, user_id: str, tool: str) -> str:
    _ensure_interactive(conversation_id, user_id)
    if is_ai_fallback_conversation(conversation_id):
        raise ValidationError("AI 候场会话不提供真人破冰与解锁工具，请直接发送文字。")
    if tool == "dice":
        point = random.randint(1, 6)
        content = f"摇骰子结果：{point} 点｜{DICE_TOPICS[point]}"
        metadata = {"kind": "dice", "point": point}
    elif tool == "task_card":
        category = random.choice(tuple(TASK_CARDS))
        content = f"任务卡 · {category}｜{random.choice(TASK_CARDS[category])}"
        metadata = {"kind": "task_card", "category": category}
    elif tool == "unlock":
        row = _conversation_row(conversation_id)
        if row["type"] == "event_group":
            content, metadata = "匹配点解锁任务：轮流说一个你愿意带到饭局的话题。", {"kind": "group_unlock_task"}
        else:
            members = _members(conversation_id)
            points = _shared_points(members[0]["user_id"], members[1]["user_id"])
            unlocked_count = get_db().execute(
                "SELECT COUNT(*) AS count FROM messages WHERE conversation_id = ? AND json_extract(metadata_json, '$.kind') = 'match_point'",
                (conversation_id,),
            ).fetchone()["count"]
            if unlocked_count >= len(points):
                raise ValidationError("全部匹配点已经解锁。")
            content, metadata = f"匹配点已解锁：{points[unlocked_count]}", {"kind": "match_point", "index": unlocked_count}
    else:
        raise ValidationError("未知的破冰工具。")
    _insert_system(conversation_id, content, metadata)
    get_db().commit()
    return content


def advance_demo_progress(conversation_id: str, user_id: str) -> int:
    if not current_app.config.get("DEMO_MODE", False):
        raise ValidationError("演示快捷操作只在 DEMO_MODE 中可用。")
    row = _ensure_interactive(conversation_id, user_id)
    if row["type"] != "direct":
        raise ValidationError("只有一对一会话可推进关系阶段。")
    current_level = relationship_progress(conversation_id, user_id)["level"]
    if current_level >= 4:
        raise ValidationError("你的关系阶段已经推进至 L4。")
    next_level = current_level + 1
    _insert_system(
        conversation_id,
        f"演示模式：你的可见阶段已推进至 L{next_level}。",
        {"kind": "demo_progress", "level": next_level, "viewer_consent": True},
        sender_id=user_id,
    )
    get_db().commit()
    return next_level


def report_subject(reporter_id: str, subject_type: str, subject_id: str, reason: str) -> None:
    reason = reason.strip()
    if subject_type not in ("event", "conversation") or not 1 <= len(reason) <= 200:
        raise ValidationError("请填写 1–200 字的举报原因。")
    if subject_type == "conversation":
        _ensure_member(subject_id, reporter_id)
    elif not get_db().execute("SELECT 1 FROM events WHERE id = ?", (subject_id,)).fetchone():
        raise ValidationError("举报对象不存在。")
    get_db().execute(
        "INSERT INTO reports (id, reporter_id, subject_type, subject_id, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (f"report_{uuid4().hex[:12]}", reporter_id, subject_type, subject_id, reason, utcnow()),
    )
    get_db().commit()


def block_counterpart(blocker_id: str, conversation_id: str) -> None:
    row = _conversation_row(conversation_id)
    if not row or row["type"] != "direct":
        raise ValidationError("只能拉黑一对一会话中的对方。")
    if row["counterpart_type"] == "ai":
        raise ValidationError("AI 候场搭子不是真人账户，不能使用拉黑真人操作。")
    _ensure_member(conversation_id, blocker_id)
    other = next(member for member in _members(conversation_id) if member["user_id"] != blocker_id)
    get_db().execute(
        "INSERT OR IGNORE INTO blocks (blocker_id, blocked_id, created_at) VALUES (?, ?, ?)",
        (blocker_id, other["user_id"], utcnow()),
    )
    get_db().commit()
