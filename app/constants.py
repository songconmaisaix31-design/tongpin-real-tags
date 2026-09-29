from __future__ import annotations

from decimal import Decimal

GENDERS = ("male", "female", "undisclosed")
MATCH_GENDERS = ("male", "female", "any")
CITIES = ("北京", "上海", "广州", "深圳", "杭州", "成都", "海外")
PURPOSES = ("学习搭子", "运动搭子", "聊天倾诉", "兴趣同好", "饭搭子", "随便聊聊")
INTERESTS = ("音乐", "影视", "游戏", "健身", "旅行", "摄影", "美食", "二次元", "阅读", "宠物", "人工智能", "创业")
MBTIS = ("不知道", "INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP", "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP")
ZODIACS = ("不知道", "白羊", "金牛", "双子", "巨蟹", "狮子", "处女", "天秤", "天蝎", "射手", "摩羯", "水瓶", "双鱼")
SCHEDULES = ("早鸟", "正常", "夜猫子")
POIS = {
    "poi_001": {"name": "四季民福烤鸭店(故宫店)", "address": "北京市东城区南池子大街11号"},
    "poi_002": {"name": "胡大饭馆24h(簋街总店)", "address": "北京市东城区东直门内大街233号"},
    "poi_003": {"name": "聚宝源(牛街创始店)", "address": "北京市西城区牛街5-2号"},
    "poi_004": {"name": "京A Taproom·隆福寺店", "address": "北京市东城区钱粮胡同38号隆福寺北里19号楼"},
    "poi_005": {"name": "南门涮肉(天坛店)", "address": "北京市东城区永定门东街东里13号楼1-2号"},
    "poi_006": {"name": "全聚德(北京和平门店)", "address": "北京市西城区前门西大街14号楼"},
    "poi_007": {"name": "牛街清真满恒記(平安里西大街店)", "address": "北京市西城区平安里西大街14号"},
    "poi_008": {"name": "浩海火烧云傣家菜(东安市场店)", "address": "北京市东城区王府井大街138号北京apm六层L619"},
}
EVENT_TAGS = {
    "interest_ai": "对人工智能感兴趣",
    "identity_startup": "创业中",
    "lang_learning_en": "正在学英语",
    "lang_learning_ja": "正在学日语",
    "sport_running": "跑步爱好者",
    "sport_yoga": "瑜伽爱好者",
    "interest_reading": "爱阅读",
    "interest_food": "美食探索者",
}

DATA_SOURCE_STATE_COPY = {
    "ready": ("公开数据 · 已同步", "来自实时公开资料，不代表账号归属已验证"),
    "fixture_ready": ("演示数据 Fixture", "用于演示流程，不是账号实况"),
    "unavailable": ("本次演示不可用", "该数据源当前没有安全可用的产品映射"),
    "timeout": ("公开数据请求超时", "已保留上次成功结果，可稍后重试"),
    "invalid_input": ("公开账号格式无效", "请按数据源提示检查公开用户名"),
    "malformed_response": ("公开数据格式已变化", "本次未更新标签"),
    "upstream_error": ("上游服务暂时不可用", "本次未更新标签"),
}

DATA_SOURCE_ERROR_COPY = {
    "source_disabled": "该数据源在当前运行模式下不可用",
    "profile_not_found": "未找到这个公开账号，已保留上次成功结果",
    "profile_not_public": "该公开资料当前不可读取，已保留上次成功结果",
    "request_timeout": "请求在限定时间内未完成，已保留上次成功结果",
    "missing_handle": "请输入公开用户名",
    "invalid_handle": "公开用户名格式不符合该数据源规则",
    "response_too_large": "公开响应超过安全读取上限，未更新标签",
    "invalid_json": "公开响应不是有效 JSON，未更新标签",
    "schema_mismatch": "公开响应字段已变化，未更新标签",
    "redirect_rejected": "上游返回了未允许的跳转，未更新标签",
    "network_error": "网络请求失败，已保留上次成功结果",
    "rate_limited": "公开接口触发频率限制，已保留上次成功结果",
    "http_4xx": "上游拒绝了公开请求，未发送任何凭据",
    "http_5xx": "上游服务异常，已保留上次成功结果",
}

# This is server-only configuration. Do not expose it in templates or forms.
MATCH_WEIGHT_GROUPS = {
    "default": {
        "group_key": "default",
        "weights": {
            "purpose": Decimal("0.30"),
            "behavior": Decimal("0.25"),
            "interests": Decimal("0.20"),
            "active_time": Decimal("0.15"),
            "city": Decimal("0.05"),
            "mbti": Decimal("0.05"),
        },
    },
    "no_external_data": {
        "group_key": "no_external_data",
        "weights": {
            "purpose": Decimal("0.45"),
            "interests": Decimal("0.30"),
            "active_time": Decimal("0.15"),
            "city": Decimal("0.05"),
            "mbti": Decimal("0.05"),
        },
    },
}
