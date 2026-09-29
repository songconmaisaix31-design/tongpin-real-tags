from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from ..constants import CITIES, EVENT_TAGS, POIS
from ..services.chat import report_subject
from ..services.events import (
    cancel_event,
    create_user_event,
    demo_settle_event,
    get_event,
    list_events,
    parse_nearby_query,
    redeem_coupon,
    review_applicants,
    review_signup,
    signup_for_event,
    viewer_coupon,
)
from ..services.users import ValidationError, current_user, login_required

bp = Blueprint("events", __name__)


@bp.get("/events")
@login_required
def index():
    user = current_user()
    filters = request.args
    try:
        nearby = parse_nearby_query(filters)
        events = list_events(user["id"], filters)
    except ValidationError as error:
        flash(f"{error} 已回退为城市与全部活动筛选。", "error")
        filters = request.args.to_dict()
        for key in ("lat", "lng", "accuracy", "radius"):
            filters.pop(key, None)
        if filters.get("sort") == "distance":
            filters.pop("sort")
        nearby = parse_nearby_query(filters)
        events = list_events(user["id"], filters)
    reset_filters = {
        key: filters.get(key) for key in ("city", "tag", "budget", "benefit", "sort") if filters.get(key)
    }
    if reset_filters.get("sort") == "distance":
        reset_filters.pop("sort")
    return render_template(
        "events.html",
        events=events,
        tags=EVENT_TAGS,
        cities=CITIES,
        filters=filters,
        nearby=nearby,
        radius_options=(1, 3, 5, 10, 20, 50),
        location_reset_url=url_for("events.index", **reset_filters),
    )


@bp.route("/events/new", methods=("GET", "POST"))
@login_required
def create():
    if request.method == "POST":
        try:
            event_id = create_user_event(current_user()["id"], request.form)
        except ValidationError as error:
            flash(str(error), "error")
        else:
            flash("饭局已提交平台审核，审核通过后会进入广场。", "success")
            return redirect(url_for("events.detail", event_id=event_id))
    default_start = (datetime.now(timezone(timedelta(hours=8))) + timedelta(days=3)).replace(hour=19, minute=0, second=0, microsecond=0)
    return render_template("event_form.html", pois=POIS, tags=EVENT_TAGS, default_start=default_start.strftime("%Y-%m-%dT%H:%M"))


@bp.get("/events/<event_id>")
@login_required
def detail(event_id: str):
    user = current_user()
    event = get_event(event_id, user["id"])
    if event is None:
        abort(404)
    applicants = (
        review_applicants(event_id, user["id"])
        if event["is_host"] and event["signup_mode"] == "review" and event["status"] == "recruiting"
        else []
    )
    template_applicants = [
        {
            "user_id": applicant["review_token"],
            "match_score": applicant["match_score"],
            "common_tag_count": applicant["common_tag_count"],
            "joined_at": applicant["joined_at"],
        }
        for applicant in applicants
    ]
    coupon = viewer_coupon(event_id, user["id"])
    return render_template(
        "event_detail.html",
        event=event,
        applicants=template_applicants,
        coupon=coupon,
        demo_mode=current_app.config["DEMO_MODE"],
    )


@bp.post("/events/<event_id>/signup")
@login_required
def signup(event_id: str):
    try:
        status = signup_for_event(event_id, current_user()["id"])
    except ValidationError as error:
        flash(str(error), "error")
    else:
        flash("报名已提交，等待发起人审核。" if status == "pending" else "报名成功。", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.post("/events/<event_id>/review/<applicant_id>/<decision>")
@login_required
def review(event_id: str, applicant_id: str, decision: str):
    if decision not in ("approve", "reject"):
        flash("无效的报名审核决定。", "error")
        return redirect(url_for("events.detail", event_id=event_id))
    try:
        review_signup(event_id, current_user()["id"], applicant_id, decision == "approve")
    except ValidationError as error:
        flash(str(error), "error")
    else:
        flash("报名已通过。" if decision == "approve" else "报名已拒绝。", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.post("/events/<event_id>/cancel")
@login_required
def cancel(event_id: str):
    try:
        cancel_event(event_id, current_user()["id"])
    except ValidationError as error:
        flash(str(error), "error")
    else:
        flash("活动已取消，相关权益已失效。", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.post("/events/<event_id>/demo/settle")
@login_required
def demo_settle(event_id: str):
    if not current_app.config["DEMO_MODE"]:
        abort(404)
    try:
        result = demo_settle_event(event_id, current_user()["id"])
    except ValidationError as error:
        flash(str(error), "error")
    else:
        flash("演示结算：活动已成团并创建群聊。" if result == "formed" else "演示结算：未达人数，活动已取消。", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.post("/events/<event_id>/redeem")
@login_required
def redeem(event_id: str):
    try:
        redeem_coupon(event_id, current_user()["id"], request.form.get("redeem_code", ""))
    except ValidationError as error:
        flash(str(error), "error")
    else:
        flash("核销成功。", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.post("/events/<event_id>/report")
@login_required
def report(event_id: str):
    try:
        report_subject(current_user()["id"], "event", event_id, request.form.get("reason", ""))
    except ValidationError as error:
        flash(str(error), "error")
    else:
        flash("举报已记录，审核人员会跟进处理。", "success")
    return redirect(url_for("events.detail", event_id=event_id))
