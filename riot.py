"""
Riot Games API 客户端 - 查询英雄联盟全球各服数据
注册 API Key: https://developer.riotgames.com
"""

import time
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)

# Riot API 区域路由配置
REGION_ROUTING = {
    "br1": "americas", "eun1": "europe", "euw1": "europe",
    "jp1": "asia", "kr": "asia", "la1": "americas",
    "la2": "americas", "na1": "americas", "oc1": "sea",
    "ph2": "sea", "sg2": "sea", "th2": "sea",
    "tr1": "europe", "tw2": "sea", "vn2": "sea",
    # 国服使用 asia 路由
    "cn1": "asia", "cn2": "asia", "cn3": "asia",
    "cn4": "asia", "cn5": "asia", "cn6": "asia",
    "cn7": "asia", "cn8": "asia", "cn9": "asia",
    "cn10": "asia", "cn13": "asia", "cn14": "asia",
}

# 可查询的服务器列表（国服 Riot ID 需要通过 account-v1 API 查询）
SERVERS = {
    "kr": {"name": "韩服", "routing": "asia"},
    "na1": {"name": "美服", "routing": "americas"},
    "euw1": {"name": "西欧服", "routing": "europe"},
    "eun1": {"name": "北欧东欧服", "routing": "europe"},
    "jp1": {"name": "日服", "routing": "asia"},
    "oc1": {"name": "大洋洲", "routing": "sea"},
    "br1": {"name": "巴西服", "routing": "americas"},
    "la1": {"name": "拉丁美洲北", "routing": "americas"},
    "la2": {"name": "拉丁美洲南", "routing": "americas"},
    "tr1": {"name": "土耳其服", "routing": "europe"},
    "ph2": {"name": "菲律宾服", "routing": "sea"},
    "sg2": {"name": "新加坡服", "routing": "sea"},
    "th2": {"name": "泰国服", "routing": "sea"},
    "vn2": {"name": "越南服", "routing": "sea"},
    "tw2": {"name": "台服", "routing": "sea"},
    # 国服
    "cn1": {"name": "艾欧尼亚", "routing": "asia"},
    "cn2": {"name": "祖安", "routing": "asia"},
    "cn3": {"name": "诺克萨斯", "routing": "asia"},
    "cn4": {"name": "班德尔城", "routing": "asia"},
    "cn5": {"name": "皮尔特沃夫", "routing": "asia"},
    "cn6": {"name": "战争学院", "routing": "asia"},
    "cn7": {"name": "弗雷尔卓德", "routing": "asia"},
    "cn8": {"name": "巨神峰", "routing": "asia"},
    "cn9": {"name": "雷瑟守备", "routing": "asia"},
    "cn10": {"name": "无畏先锋", "routing": "asia"},
    "cn13": {"name": "钢铁烈阳", "routing": "asia"},
    "cn14": {"name": "暗影岛", "routing": "asia"},
}

# 队列类型映射
QUEUE_NAMES = {
    400: "匹配模式", 420: "单排/双排", 430: "匹配模式",
    440: "灵活排位", 450: "极地大乱斗", 700: "斗魂竞技场",
    830: "人机", 840: "人机", 850: "人机", 900: "无限火力",
    1020: "无限乱斗", 1300: "云顶之弈(排位)",
    1400: "云顶之弈(双人)", 1700: "斗魂竞技场", 1900: "斗魂竞技场(排位)",
}


class RateLimiter:
    """Riot API 速率限制器"""

    def __init__(self, requests_per_sec: int = 20, requests_per_2min: int = 100):
        self.requests_per_sec = requests_per_sec
        self.requests_per_2min = requests_per_2min
        self.sec_timestamps: List[float] = []
        self.min_timestamps: List[float] = []

    def wait_if_needed(self):
        """在需要时等待以遵守速率限制"""
        now = time.time()

        # 清理旧的时间戳
        self.sec_timestamps = [t for t in self.sec_timestamps if now - t < 1]
        self.min_timestamps = [t for t in self.min_timestamps if now - t < 120]

        # 检查 2 分钟限制
        if len(self.min_timestamps) >= self.requests_per_2min:
            sleep_time = self.min_timestamps[0] + 120 - now
            if sleep_time > 0:
                logger.info(f"速率限制等待: {sleep_time:.1f}s")
                time.sleep(sleep_time)
                return self.wait_if_needed()

        # 检查每秒限制
        if len(self.sec_timestamps) >= self.requests_per_sec:
            sleep_time = self.sec_timestamps[0] + 1 - now
            if sleep_time > 0:
                time.sleep(sleep_time)
                return self.wait_if_needed()

    def record_request(self):
        """记录一次请求"""
        now = time.time()
        self.sec_timestamps.append(now)
        self.min_timestamps.append(now)


# 保底英雄列表（在线数据加载失败时使用）
FALLBACK_CHAMPIONS = {
    266: "暗裔剑魔", 103: "九尾妖狐", 84: "暗黑元首", 12: "牛头酋长",
    32: "暗影之拳", 34: "殇之木乃伊", 1: "黑暗之女", 22: "寒冰射手",
    136: "影流之主", 268: "虚空掠夺者", 157: "疾风剑豪", 76: "诺克萨斯之手",
    98: "曙光女神", 78: "酒桶", 102: "龙血武姬", 81: "战争女神",
    92: "虚空恐惧", 122: "不祥之刃", 131: "皎月女神", 119: "荣耀行刑官",
    36: "祖安狂人", 2: "狂战士", 21: "皮城女警", 4: "卡牌大师",
    29: "恶魔小丑", 30: "亡灵战神", 37: "琴瑟仙女", 40: "蒸汽机器人",
    41: "潮汐海灵", 43: "不祥之刃", 44: "永恒梦魇", 45: "魔蛇之拥",
    48: "皮城执法官", 51: "诡术妖姬", 53: "魂锁典狱长", 55: "邪恶小法师",
    58: "蛮族之王", 59: "刀锋舞者", 60: "蜘蛛女皇", 61: "战争女神",
    62: "齐天大圣", 63: "复仇焰魂", 67: "暗夜猎手", 69: "众星之子",
    72: "水晶先锋", 74: "审判天使", 75: "沙漠死神", 77: "永恒梦魇",
    79: "元素女皇", 80: "虚空先知", 82: "铁铠冥魂", 85: "复仇之矛",
    86: "无极剑圣", 89: "众星之子", 90: "战争之影", 91: "影流之主",
    96: "深渊巨口", 99: "魔蛇之拥", 101: "虚空行者", 104: "惩戒之箭",
    105: "机械先驱", 106: "雷霆咆哮", 110: "猩红收割者", 111: "法外狂徒",
    112: "机械公敌", 113: "盲僧", 114: "远古巫灵", 115: "爆破鬼才",
    117: "生化魔人", 120: "战争之影", 121: "虚空女皇", 126: "审判天使",
    127: "寒冰射手", 133: "德玛西亚之力", 134: "亡灵战神", 141: "不祥之刃",
    142: "水晶先锋", 143: "祖安狂人", 145: "诺克萨斯首领", 150: "暮光之眼",
    154: "皮城执法官", 157: "疾风剑豪", 161: "虚空女皇", 163: "赏金猎人",
    166: "魂锁典狱长", 201: "元素女皇", 202: "无极剑圣", 203: "刀锋之影",
    221: "赏金猎人", 222: "魂锁典狱长", 223: "沙漠死神", 234: "暗夜猎手",
    235: "殇之木乃伊", 236: "皮城女警", 238: "疾风剑豪", 240: "诺克萨斯之手",
    242: "战争女神", 245: "时间刺客", 246: "冰晶凤凰", 254: "虚空遁地兽",
    257: "圣枪游侠", 261: "虚空恐惧", 262: "战争之影", 263: "虚空先知",
    264: "暗裔剑魔", 267: "魂锁典狱长", 268: "虚空掠夺者", 350: "暮光之眼",
    412: "魂锁典狱长", 420: "正义天使", 421: "虚空掠夺者", 427: "魔法猫咪",
    429: "暗影之拳", 432: "暗黑元首", 497: "虚空女皇", 498: "虚空女皇",
    516: "亡灵勇士", 517: "不灭狂雷", 518: "纳祖玛之裔", 523: "星界游神",
    555: "星籁歌姬", 777: "暗裔剑魔", 887: "魔法猫咪", 888: "皮城女警",
    950: "刀锋舞者", 951: "九尾妖狐",
}


class RiotClient:
    """Riot Games API 客户端"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "X-Riot-Token": api_key,
            "Accept": "application/json",
        })
        self.rate_limiter = RateLimiter()
        # 缓存
        self._cache: Dict[str, tuple[Any, float]] = {}
        self._cache_ttl = 120  # 默认缓存 2 分钟
        # 英雄映射
        self._champion_map: Dict[int, str] = {}
        self._champion_name_to_id: Dict[str, int] = {}

    def _request(self, method: str, url: str, **kwargs) -> Optional[Any]:
        """发送带速率限制和缓存的 API 请求"""
        # 检查缓存
        cache_key = f"{method}:{url}"
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                return data

        self.rate_limiter.wait_if_needed()

        try:
            resp = self.session.request(method, url, timeout=30, **kwargs)
            self.rate_limiter.record_request()

            if resp.status_code == 429:  # Rate limited
                retry_after = int(resp.headers.get("Retry-After", 2))
                logger.warning(f"被限速，等待 {retry_after}s")
                time.sleep(retry_after)
                return self._request(method, url, **kwargs)

            if resp.status_code == 403:
                logger.error("API Key 无效或已过期")
                return None

            if resp.status_code == 404:
                return None

            if resp.status_code >= 500:
                logger.error(f"Riot 服务器错误: {resp.status_code}")
                return None

            data = resp.json()

            # 写入缓存
            self._cache[cache_key] = (data, time.time())

            return data
        except requests.exceptions.Timeout:
            logger.error(f"请求超时 (30s): {url[:80]}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"连接失败: {e}")
            return None
        except Exception as e:
            logger.error(f"请求异常: {e}")
            return None

    def _build_url(self, platform: str, path: str) -> str:
        """构建 Riot API URL"""
        return f"https://{platform}.api.riotgames.com{path}"

    def _build_routing_url(self, routing: str, path: str) -> str:
        """构建基于路由的 Riot API URL"""
        return f"https://{routing}.api.riotgames.com{path}"

    # ========== 账号 API (Riot ID 系统) ==========
    # 适用于所有服（包括国服）的 Riot ID 查询
    # 使用路由: americas / asia / europe / sea

    def get_summoner_by_name(self, platform: str, summoner_name: str) -> Optional[Dict]:
        """通过游戏名称获取召唤师信息"""
        return self._request(
            "GET",
            self._build_url(platform, f"/lol/summoner/v4/summoners/by-name/{summoner_name}"),
        )

    def get_summoner_by_puuid(self, platform: str, puuid: str) -> Optional[Dict]:
        """通过 PUUID 获取召唤师信息"""
        return self._request(
            "GET",
            self._build_url(platform, f"/lol/summoner/v4/summoners/by-puuid/{puuid}"),
        )

    # ========== 账号 API (Riot ID 系统) ==========
    # 适用于所有服（包括国服）的 Riot ID 查询
    # 使用路由: americas / asia / europe / sea

    def get_account_by_riot_id(
        self, routing: str, game_name: str, tag_line: str
    ) -> Optional[Dict]:
        """通过 Riot ID (游戏名 + 标签) 获取账号信息"""
        return self._request(
            "GET",
            self._build_routing_url(
                routing,
                f"/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}",
            ),
        )

    def get_account_by_puuid(self, routing: str, puuid: str) -> Optional[Dict]:
        """通过 PUUID 获取账号信息"""
        return self._request(
            "GET",
            self._build_routing_url(
                routing,
                f"/riot/account/v1/accounts/by-puuid/{puuid}",
            ),
        )

    def get_active_shard(self, routing: str, puuid: str, game: str = "lol") -> Optional[Dict]:
        """获取玩家活跃分区"""
        return self._request(
            "GET",
            self._build_routing_url(
                routing,
                f"/riot/account/v1/active-shards/by-game/{game}/by-puuid/{puuid}",
            ),
        )

    # ========== 排位 API ==========

    def get_ranked_entries(self, platform: str, summoner_id: str) -> Optional[List]:
        """获取召唤师的排位数据"""
        return self._request(
            "GET",
            self._build_url(
                platform,
                f"/lol/league/v4/entries/by-summoner/{summoner_id}",
            ),
        )

    # ========== 比赛 API (Match-V5) ==========

    def get_match_ids(
        self, routing: str, puuid: str, count: int = 20, start: int = 0
    ) -> Optional[List[str]]:
        """获取比赛 ID 列表"""
        return self._request(
            "GET",
            self._build_routing_url(
                routing,
                f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
                f"?start={start}&count={count}",
            ),
        )

    def get_match_detail(self, routing: str, match_id: str) -> Optional[Dict]:
        """获取比赛详情"""
        return self._request(
            "GET",
            self._build_routing_url(
                routing,
                f"/lol/match/v5/matches/{match_id}",
            ),
        )

    def get_match_timeline(self, routing: str, match_id: str) -> Optional[Dict]:
        """获取比赛时间线"""
        return self._request(
            "GET",
            self._build_routing_url(
                routing,
                f"/lol/match/v5/matches/{match_id}/timeline",
            ),
        )

    # ========== 英雄熟练度 API ==========

    def get_champion_mastery(
        self, platform: str, summoner_id: str, count: int = 5
    ) -> Optional[List]:
        """获取英雄熟练度"""
        return self._request(
            "GET",
            self._build_url(
                platform,
                f"/lol/champion-mastery/v4/champion-masteries/by-summoner/{summoner_id}"
                f"/top?count={count}",
            ),
        )

    def get_champion_mastery_total(self, platform: str, summoner_id: str) -> Optional[int]:
        """获取总熟练度分数"""
        result = self._request(
            "GET",
            self._build_url(
                platform,
                f"/lol/champion-mastery/v4/scores/by-summoner/{summoner_id}",
            ),
        )
        return result

    # ========== 英雄数据 ==========

    def load_champion_data(self):
        """加载英雄数据"""
        # 先用保底英雄列表
        self._champion_map = dict(FALLBACK_CHAMPIONS)
        logger.info(f"使用保底英雄列表: {len(self._champion_map)} 个英雄")

        # 尝试在线加载更完整的数据（失败也不影响保底）
        try:
            url = "https://ddragon.leagueoflegends.com/cdn/14.10.1/data/zh_CN/champion.json"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                for champ_name, champ_data in data.items():
                    self._champion_map[int(champ_data["key"])] = champ_data.get("name", champ_name)
                logger.info(f"在线数据已更新: {len(self._champion_map)} 个英雄")
        except Exception as e:
            logger.info(f"在线数据不可用，使用保底列表: {e}")

        return True

    def get_champion_name(self, champion_id: int) -> str:
        """获取英雄中文名"""
        return self._champion_map.get(champion_id, f"英雄({champion_id})")

    # ========== 辅助函数 ==========

    def parse_match_info(self, match_data: Dict) -> Optional[Dict]:
        """解析比赛数据为前端可用格式"""
        if not match_data:
            return None

        info = match_data.get("info", {})
        metadata = match_data.get("metadata", {})

        return {
            "match_id": metadata.get("matchId", ""),
            "game_duration": info.get("gameDuration", 0),
            "queue_id": info.get("queueId", 0),
            "game_mode": info.get("gameMode", ""),
            "game_type": info.get("gameType", ""),
            "game_creation": info.get("gameCreation", 0),
            "game_version": info.get("gameVersion", ""),
            "participants": info.get("participants", []),
            "teams": info.get("teams", []),
        }

    def extract_participant(self, match_info: Dict, puuid: str) -> Optional[Dict]:
        """从比赛数据中提取指定玩家的信息"""
        participants = match_info.get("participants", [])
        for p in participants:
            if p.get("puuid") == puuid:
                return p
        return None

    def format_game_summary(self, match_info: Dict, puuid: str) -> Optional[Dict]:
        """格式化比赛摘要"""
        participant = self.extract_participant(match_info, puuid)
        if not participant:
            return None

        champ_id = participant.get("championId", 0)
        kills = participant.get("kills", 0)
        deaths = participant.get("deaths", 0)
        assists = participant.get("assists", 0)

        return {
            "match_id": match_info.get("match_id", ""),
            "champion_id": champ_id,
            "champion_name": self.get_champion_name(champ_id),
            "queue_id": match_info.get("queue_id", 0),
            "queue_name": QUEUE_NAMES.get(match_info.get("queue_id", 0), f"模式({match_info.get('queue_id', 0)})"),
            "kills": kills,
            "deaths": deaths,
            "assists": assists,
            "kda": f"{kills}/{deaths}/{assists}",
            "kda_ratio": round((kills + assists) / max(deaths, 1), 2),
            "win": participant.get("win", False),
            "duration_sec": match_info.get("game_duration", 0),
            "game_creation": match_info.get("game_creation", 0),
            "champ_level": participant.get("champLevel", 1),
            "total_damage": participant.get("totalDamageDealtToChampions", 0),
            "total_damage_taken": participant.get("totalDamageTaken", 0),
            "gold_earned": participant.get("goldEarned", 0),
            "cs": participant.get("totalMinionsKilled", 0) + participant.get("neutralMinionsKilled", 0),
            "vision_score": participant.get("visionScore", 0),
            "items": [
                participant.get(f"item{i}", 0) for i in range(6)
            ],
            "summoner1_id": participant.get("summoner1Id", 0),
            "summoner2_id": participant.get("summoner2Id", 0),
            "multikill": participant.get("largestMultiKill", 0),
            "perks": participant.get("perks", {}),
        }


# ========== 工具函数 ==========

def format_duration(seconds: int) -> str:
    """格式化游戏时长"""
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def format_time_ago(ms_timestamp: int) -> str:
    """格式化时间差"""
    dt = datetime.fromtimestamp(ms_timestamp / 1000)
    now = datetime.now()
    diff = now - dt

    if diff.days == 0:
        if diff.seconds < 3600:
            mins = diff.seconds // 60
            return f"{mins}分钟前"
        hours = diff.seconds // 3600
        return f"{hours}小时前"
    elif diff.days == 1:
        return "昨天"
    elif diff.days < 7:
        return f"{diff.days}天前"
    elif diff.days < 30:
        return f"{diff.days // 7}周前"
    else:
        return dt.strftime("%m-%d")


def parse_ranked_data(entries: List[Dict]) -> Dict:
    """解析排位数据"""
    result = {}
    for entry in entries:
        queue_type = entry.get("queueType", "")
        tier = entry.get("tier", "")
        rank = entry.get("rank", "")
        lp = entry.get("leaguePoints", 0)
        wins = entry.get("wins", 0)
        losses = entry.get("losses", 0)
        games = wins + losses

        if tier:
            wr = round(wins / games * 100, 1) if games > 0 else 0
            key = "RANKED_SOLO_5x5" if "SOLO" in queue_type else "RANKED_FLEX_5x5"
            result[key] = {
                "tier": tier,
                "rank": rank,
                "lp": lp,
                "wins": wins,
                "losses": losses,
                "win_rate": wr,
                "games": games,
                "tier_full": f"{tier} {rank}",
            }
    return result


def get_region_for_platform(platform: str) -> str:
    """获取平台对应的路由区域"""
    return REGION_ROUTING.get(platform, "asia")
