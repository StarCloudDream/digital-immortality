"""生活轮廓侧写 —— 从作息和内容里读出"这个人平时怎么过日子"。

回答这些问题：
- 平时几点聊天？→ 作息推断上班还是上学
- 做什么工作、擅长什么、喜欢什么？→ 自我陈述 + 话题命中
- 身边有什么人？→ 亲属称谓提取 + 高频联系人
- 会什么、不会什么？→ 知识边界，本人说不知道的就是不知道

全是确定性启发式，产出都带证据（evidence），可溯源、可人工修正。
"""
from __future__ import annotations

import re
from collections import Counter

from sinian.core.message import UnifiedMessage
from sinian.core.persona import LifeLayer, SocialRelation, KnowledgeDomain


class LifeProfiler:
    #: 亲属/社会关系自称词表。"我妈"出现一次就是一条铁证
    KINSHIP = {
        "我妈": "母亲", "我妈妈": "母亲", "老妈": "母亲",
        "我爸": "父亲", "我爸爸": "父亲", "老爸": "父亲",
        "我姐": "姐姐", "我哥": "哥哥", "我弟": "弟弟", "我妹": "妹妹",
        "我爷爷": "爷爷", "我奶奶": "奶奶", "我外公": "外公", "我外婆": "外婆",
        "老婆": "伴侣", "老公": "伴侣", "我对象": "伴侣",
        "女朋友": "伴侣", "男朋友": "伴侣",
        "闺蜜": "闺蜜", "室友": "室友", "同事": "同事",
        "老板": "上司", "老师": "老师",
    }

    #: 兴趣领域关键词地图。命中即计数，证据留发言原文。后续抽配置
    INTEREST_DOMAINS = {
        "科技数码": ["芯片", "发布会", "大模型", "显卡", "数码", "苹果", "华为",
                    "小米", "算法", "AI", "手机圈", "评测"],
        "游戏": ["游戏", "上分", "排位", "副本", "抽卡", "开黑", "通关", "段位"],
        "动漫": ["新番", "动漫", "二次元", "漫画", "cos", "追番"],
        "音乐": ["新歌", "专辑", "演唱会", "乐队", "歌词"],
        "影视": ["电影", "追剧", "综艺", "票房", "剧集"],
        "运动": ["跑步", "健身", "球赛", "比赛", "球队"],
        "美食": ["火锅", "奶茶", "烧烤", "做饭", "探店", "外卖"],
        "旅行": ["旅行", "旅游", "机票", "景点", "攻略"],
        "理财": ["股票", "基金", "理财", "炒股", "涨停"],
        "读书": ["小说", "作者", "读书", "书评"],
    }

    def profile(self, messages: list[UnifiedMessage],
                self_name: str) -> tuple[LifeLayer, list[SocialRelation], list[KnowledgeDomain]]:
        self_msgs = [m for m in messages if m.is_self and m.content.strip()]
        life = LifeLayer(
            life_stage=self._life_stage(self_msgs),
            occupation=self._extract_occupation(self_msgs),
            skills=self._extract_skills(self_msgs),
            interests=self._extract_interests(self_msgs),
        )
        relations = self._extract_relations(messages, self_msgs, self_name)
        knowledge = self._extract_knowledge(self_msgs)
        return life, relations, knowledge

    # ---------- 作息 → 上班还是上学 ----------

    @staticmethod
    def _life_stage(self_msgs: list[UnifiedMessage]) -> str | None:
        """工作日白天（9-18点）的发言占比是最硬的作息信号。

        上班族工作日白天在搬砖，发言集中在早晚；学生党时间碎，全天都冒头。
        深夜占比单独看，夜猫子是一种独立于身份的特质。
        """
        if len(self_msgs) < 30:
            return None  # 样本太少不下结论，不知道就是不知道
        weekday_day, late_night = 0, 0
        for m in self_msgs:
            if m.timestamp.weekday() < 5 and 9 <= m.timestamp.hour < 18:
                weekday_day += 1
            if m.timestamp.hour >= 23 or m.timestamp.hour < 5:
                late_night += 1
        total = len(self_msgs)
        day_ratio = weekday_day / total
        if day_ratio < 0.15:
            stage = "可能是上班族（工作日白天潜水，早晚出没）"
        elif day_ratio > 0.45:
            stage = "可能是学生或自由职业（工作日白天也活跃）"
        else:
            stage = "作息规律不明显"
        if late_night / total > 0.25:
            stage += "，夜猫子"
        return stage

    # ---------- 自我陈述提取 ----------

    @staticmethod
    def _extract_occupation(self_msgs: list[UnifiedMessage]) -> str | None:
        for m in self_msgs:
            hit = re.search(r"我(?:是|现在)?做([\u4e00-\u9fff]{1,8})的", m.content)
            if hit:
                return hit.group(1)
            hit = re.search(r"我(?:是|是(?:一|个|名))([一-鿿]{2,6})(?:，|。|$)", m.content)
            if hit and any(k in hit.group(1) for k in
                           ("设计", "程序", "老师", "医生", "运营", "销售", "工程师", "学生")):
                return hit.group(1)
        return None

    def _extract_skills(self, self_msgs: list[UnifiedMessage]) -> list[str]:
        skills = []
        for m in self_msgs:
            hit = re.search(r"我(?:很|特别|超|最)?擅长\s*(.{1,10}?)(?=[，。但可！~、]|$)", m.content)
            if hit:
                skills.append(hit.group(1))
        return list(dict.fromkeys(skills))[:8]

    def _extract_interests(self, self_msgs: list[UnifiedMessage]) -> list[str]:
        counts: Counter = Counter()
        for m in self_msgs:
            # 免责声明（"我是真的不懂炒股"）里的词不算兴趣，人是在划界不是在聊爱好
            if re.search(r"不(?:太|大)?[懂会]", m.content):
                continue
            for domain, keywords in self.INTEREST_DOMAINS.items():
                if any(k in m.content for k in keywords):
                    counts[domain] += 1
        return [d for d, _ in counts.most_common(6)]

    # ---------- 关系网 ----------

    def _extract_relations(self, messages: list[UnifiedMessage],
                           self_msgs: list[UnifiedMessage],
                           self_name: str) -> list[SocialRelation]:
        relations: dict[str, SocialRelation] = {}

        # 亲属称谓：自称即铁证
        for m in self_msgs:
            for word, rel in self.KINSHIP.items():
                if word in m.content:
                    key = word
                    if key not in relations:
                        relations[key] = SocialRelation(name=word, relation=rel)
                    relations[key].mentions += m.content.count(word)
                    if len(relations[key].evidence) < 3:
                        relations[key].evidence.append(m.content[:50])

        # 高频联系人：聊得多的非本人，关系标"朋友（高频联系人）"
        partner_counts = Counter(
            m.sender_name for m in messages
            if not m.is_self and m.sender_name != self_name
        )
        for name, n in partner_counts.most_common(10):
            if n >= 3 and name not in relations:
                relations[name] = SocialRelation(
                    name=name, relation="朋友（高频联系人）", mentions=n)

        return sorted(relations.values(), key=lambda r: -r.mentions)[:20]

    # ---------- 知识边界 ----------

    def _extract_knowledge(self, self_msgs: list[UnifiedMessage]) -> list[KnowledgeDomain]:
        """本人亲口说的"不会/不懂/擅长"，是知识边界的直接证据。

        没表态过的领域不在这里——不在档案里 ≠ 会，模拟器对未知领域
        的规则是谨慎作答而非冒充专家。
        """
        domains: dict[str, KnowledgeDomain] = {}

        def add(domain: str, level: str, evidence: str):
            domain = domain.strip("，。！~的了 ")
            if not domain or len(domain) > 10:
                return
            if domain not in domains:
                domains[domain] = KnowledgeDomain(domain=domain, level=level)
            # "不会"的自述优先级最高，一旦出现不被后来的"了解"覆盖
            if level == "不会" or domains[domain].level != "不会":
                domains[domain].level = level
            if len(domains[domain].evidence) < 3:
                domains[domain].evidence.append(evidence[:50])

        for m in self_msgs:
            for hit in re.finditer(r"我(?:是真的|真的是|真的|完全|根本|实在|也|是)?不(?:太|大)?[懂会]\s*([一-鿿A-Za-z]{1,8})", m.content):
                add(hit.group(1), "不会", m.content)
            for hit in re.finditer(r"我(?:很|特别|超|最)?擅长\s*(.{1,10}?)(?=[，。但可！~、]|$)", m.content):
                add(hit.group(1), "擅长", m.content)
            # 兴趣领域里高频出没的，算"了解"
        interest_domains = self._extract_interests(self_msgs)
        for d in interest_domains:
            if d not in domains:
                domains[d] = KnowledgeDomain(domain=d, level="了解")

        return list(domains.values())
