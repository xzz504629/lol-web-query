"""
英雄联盟战绩查询 Web 应用
基于 Riot Games API，可部署到云端
"""

import os
import logging
import requests
from functools import lru_cache

from flask import Flask, render_template, request, jsonify, abort
from riot import (
    RiotClient, SERVERS, QUEUE_NAMES, get_region_for_platform,
    parse_ranked_data, format_duration, format_time_ago,
)

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 从环境变量读取 API Key
API_KEY = os.environ.get("RIOT_API_KEY", "RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")

# 全局客户端
riot = RiotClient(API_KEY)


# ========== 页面路由 ==========

@app.route("/")
def index():
    """首页"""
    return render_template(
        "index.html",
        servers=SERVERS,
    )


@app.route("/profile")
def profile_page():
    """召唤师资料页"""
    return render_template(
        "profile.html",
        servers=SERVERS,
    )


# ========== API 路由 ==========

@app.route("/api/servers")
def api_servers():
    """获取服务器列表"""
    return jsonify({
        code: info["name"] for code, info in SERVERS.items()
    })


@app.route("/api/search")
def api_search():
    """
    搜索召唤师
    支持格式:
      - 召唤师名称 (仅非国服)
      - 游戏名#标签 (Riot ID, 全服通用)
    """
    name = request.args.get("name", "").strip()
    server = request.args.get("server", "kr")

    if not name:
        return jsonify({"error": "请输入召唤师名称"}), 400

    if server not in SERVERS:
        return jsonify({"error": "无效的服务器"}), 400

    server_info = SERVERS[server]
    routing = server_info["routing"]
    is_cn = server.startswith("cn")

    try:
        summoner = None

        # 解析 Riot ID 格式: gameName#tagLine
        if "#" in name:
            parts = name.split("#", 1)
            game_name = parts[0].strip()
            tag_line = parts[1].strip()

            # 通过 Account API 查询（全服通用）
            account = riot.get_account_by_riot_id(routing, game_name, tag_line)
            if account and account.get("puuid"):
                puuid = account["puuid"]
                logger.info(f"✅ Account API 查到了: {account.get('gameName')}#{account.get('tagLine')} puuid={puuid[:8]}...")

                # 国服: 不用 summoner-v4（国服没有这个API），直接用 account 信息
                summoner = {
                    "name": account.get("gameName", game_name),
                    "puuid": puuid,
                    "summonerLevel": 0,
                    "profileIconId": 0,
                    "id": puuid,
                    "accountId": "",
                    "gameName": account.get("gameName", game_name),
                    "tagLine": account.get("tagLine", tag_line),
                }

            if not summoner:
                return jsonify({
                    "error": f"未找到国服召唤师「{name}」，请确认 Riot ID 是否正确",
                    "code": "NOT_FOUND",
                }), 404
        else:
            # 纯名称搜索
            if is_cn:
                # 国服必须用 Riot ID 格式
                return jsonify({
                    "error": "国服请使用 游戏名#标签 格式查询（例如: blowjob#89795）",
                    "code": "NEED_RIOT_ID",
                }), 400
            else:
                # 非国服: 先用 Account API 尝试（默认标签 KR1/NA1）
                summoner = None
                for default_tag in get_default_tags(server):
                    account = riot.get_account_by_riot_id(routing, name, default_tag)
                    if account and account.get("puuid"):
                        puuid = account["puuid"]
                        logger.info(f"✅ Account API查到: {name}#{default_tag} puuid={puuid[:8]}")
                        summoner = {
                            "name": account.get("gameName", name),
                            "puuid": puuid,
                            "summonerLevel": 0,
                            "profileIconId": 0,
                            "id": puuid,
                            "accountId": "",
                            "gameName": account.get("gameName", name),
                            "tagLine": account.get("tagLine", default_tag),
                        }
                        break

                if not summoner:
                    # 兜底: 用旧版 summoner-v4
                    summoner = riot.get_summoner_by_name(server, name)
                    if summoner:
                        logger.info(f"✅ summoner-v4查到: {summoner.get('name')} puuid={'有值' if summoner.get('puuid') else '空!!!'}")
                    else:
                        return jsonify({
                            "error": f"在{server_info['name']}未找到召唤师「{name}」",
                            "code": "NOT_FOUND",
                        }), 404

        puuid = summoner.get("puuid", "")
        summoner_id = summoner.get("id", "")

        # 获取排位数据（仅非国服）
        ranked = []
        if not is_cn and summoner_id:
            try:
                ranked = riot.get_ranked_entries(server, summoner_id) or []
            except Exception:
                pass

        # 获取英雄熟练度（仅非国服）
        mastery = []
        if not is_cn and summoner_id:
            try:
                mastery = riot.get_champion_mastery(server, summoner_id, 5) or []
            except Exception:
                pass

        return jsonify({
            "summoner": {
                "name": summoner.get("name", ""),
                "summoner_level": summoner.get("summonerLevel", 0),
                "profile_icon_id": summoner.get("profileIconId", 0),
                "puuid": puuid,
                "id": summoner_id,
                "account_id": summoner.get("accountId", ""),
                "game_name": summoner.get("gameName", ""),
                "tag_line": summoner.get("tagLine", ""),
            },
            "ranked": parse_ranked_data(ranked),
            "mastery": [
                {
                    "champion_id": m.get("championId", 0),
                    "champion_name": riot.get_champion_name(m.get("championId", 0)),
                    "champion_level": m.get("championLevel", 0),
                    "champion_points": m.get("championPoints", 0),
                }
                for m in (mastery or [])
            ],
            "server": server,
            "server_name": server_info["name"],
            "is_cn": is_cn,
        })
    except Exception as e:
        logger.exception("搜索召唤师失败")
        return jsonify({"error": str(e)}), 500


@app.route("/api/matches")
def api_matches():
    """获取比赛历史"""
    puuid = request.args.get("puuid", "")
    server = request.args.get("server", "kr")
    count = request.args.get("count", 15, type=int)

    if not puuid or server not in SERVERS:
        return jsonify({"error": "参数无效"}), 400

    try:
        routing = get_region_for_platform(server)
        match_ids = riot.get_match_ids(routing, puuid, count=count)
        if not match_ids:
            return jsonify({"games": [], "total": 0})

        # 加载英雄数据（如果还没加载）
        if not riot._champion_map:
            riot.load_champion_data()

        games = []
        for match_id in match_ids:
            try:
                detail = riot.get_match_detail(routing, match_id)
                if detail:
                    match_info = riot.parse_match_info(detail)
                    if match_info:
                        summary = riot.format_game_summary(match_info, puuid)
                        if summary:
                            summary["time_ago"] = format_time_ago(summary["game_creation"])
                            summary["duration"] = format_duration(summary["duration_sec"])
                            games.append(summary)
            except Exception as e:
                logger.warning(f"获取比赛详情失败: {match_id}: {e}")
                continue

        return jsonify({
            "games": games,
            "total": len(games),
        })
    except Exception as e:
        logger.exception("获取比赛历史失败")
        return jsonify({"error": str(e)}), 500


@app.route("/api/match/<path:match_id>/detail")
def api_match_detail(match_id):
    """获取比赛详情"""
    server = request.args.get("server", "kr")
    puuid = request.args.get("puuid", "")

    if server not in SERVERS:
        return jsonify({"error": "无效服务器"}), 400

    try:
        routing = get_region_for_platform(server)
        detail = riot.get_match_detail(routing, match_id)

        if not detail:
            return jsonify({"error": "比赛数据未找到"}), 404

        match_info = riot.parse_match_info(detail)
        if not match_info:
            return jsonify({"error": "解析失败"}), 500

        participants = match_info.get("participants", [])
        teams = match_info.get("teams", [])

        # 玩家列表
        player_list = []
        for p in participants:
            player_list.append({
                "puuid": p.get("puuid", ""),
                "summoner_name": p.get("summonerName", ""),
                "champion_id": p.get("championId", 0),
                "champion_name": riot.get_champion_name(p.get("championId", 0)),
                "team_id": p.get("teamId", 0),
                "kills": p.get("kills", 0),
                "deaths": p.get("deaths", 0),
                "assists": p.get("assists", 0),
                "kda": f"{p.get('kills', 0)}/{p.get('deaths', 0)}/{p.get('assists', 0)}",
                "champ_level": p.get("champLevel", 1),
                "total_damage": p.get("totalDamageDealtToChampions", 0),
                "total_damage_taken": p.get("totalDamageTaken", 0),
                "gold_earned": p.get("goldEarned", 0),
                "cs": p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0),
                "vision_score": p.get("visionScore", 0),
                "items": [p.get(f"item{i}", 0) for i in range(7)],
                "win": p.get("win", False),
                "summoner1_id": p.get("summoner1Id", 0),
                "summoner2_id": p.get("summoner2Id", 0),
                "perks": p.get("perks", {}),
            })

        # 队伍维度
        team_info = {}
        for team in teams:
            team_info[team.get("teamId", 0)] = {
                "win": team.get("win", False),
                "objectives": team.get("objectives", {}),
            }

        # 为当前查询的玩家高亮
        player_list.sort(key=lambda x: x["team_id"])

        return jsonify({
            "match_id": match_id,
            "queue_name": QUEUE_NAMES.get(match_info.get("queue_id", 0), "未知"),
            "duration": format_duration(match_info.get("game_duration", 0)),
            "duration_sec": match_info.get("game_duration", 0),
            "game_creation": match_info.get("game_creation", 0),
            "game_version": match_info.get("game_version", ""),
            "players": player_list,
            "teams": team_info,
            "target_puuid": puuid,
        })
    except Exception as e:
        logger.exception("获取比赛详情失败")
        return jsonify({"error": str(e)}), 500


@app.route("/api/champions")
def api_champions():
    """获取英雄列表"""
    return jsonify(riot._champion_map)


# ========== 图片代理（国内用户可直接访问腾讯CDN，不用代理）==========

CDN_MIRRORS = [
    "https://game.gtimg.cn/images/lol/act/img",  # 腾讯CDN - 国内可访问
    "https://ddragon.leagueoflegends.com/cdn/14.20.1/img",
    "https://ddragon.canisback.com/img",
]

@app.route("/img/champion-icon/<int:champion_id>.png")
def proxy_champion_icon(champion_id):
    """代理英雄头像（尝试多个CDN）"""
    urls = [
        f"https://game.gtimg.cn/images/lol/act/img/champion/{champion_id}.png",
        f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champion-icons/{champion_id}.png",
        f"https://ddragon.leagueoflegends.com/cdn/14.20.1/img/champion/{champion_id}.png",
    ]
    for url in urls:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.content, 200, {"Content-Type": "image/png"}
        except Exception:
            continue
    return "", 204

@app.route("/img/<path:img_path>")
def proxy_image(img_path):
    """代理 CDN 图片"""
    if img_path.startswith("item/") or img_path.startswith("profileicon/"):
        for mirror in CDN_MIRRORS:
            try:
                resp = requests.get(f"{mirror}/{img_path}", timeout=10)
                if resp.status_code == 200:
                    return resp.content, 200, {"Content-Type": resp.headers.get("Content-Type", "image/png")}
            except Exception:
                continue
    return "", 204


@app.route("/api/debug-cdn")
def api_debug_cdn():
    """测试 CDN 能否从服务器访问"""
    import requests as req
    results = {}
    test_urls = [
        "https://game.gtimg.cn/images/lol/act/img/profileicon/1.png",
        "https://ddragon.leagueoflegends.com/cdn/14.20.1/img/profileicon/1.png",
        "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champion-icons/266.png",
        "https://game.gtimg.cn/images/lol/act/img/champion/266.png",
    ]
    for url in test_urls:
        try:
            r = req.get(url, timeout=5)
            results[url] = {"status": r.status_code, "len": len(r.content)}
        except Exception as e:
            results[url] = {"error": str(e)[:60]}
    return jsonify(results)


@app.route("/api/test-cn-match")
def api_test_cn_match():
    """测试国服PUUID能否在asia路由查到比赛"""
    puuid = request.args.get("puuid", "677f3d6f-4d8b-56ec-a86f-b4de0945f1eb")
    results = {"puuid": puuid, "tests": []}

    # 尝试 Match V5 Asia 路由
    for routing in ["asia", "sea", "americas", "europe"]:
        try:
            ids = riot.get_match_ids(routing, puuid, count=5)
            results["tests"].append({
                "routing": routing,
                "success": ids is not None,
                "match_count": len(ids) if ids else 0,
                "first_match": ids[0] if ids else None,
            })
        except Exception as e:
            results["tests"].append({
                "routing": routing,
                "error": str(e)[:50],
            })

    return jsonify(results)


# ========== 腾讯API调试（突破国服最后一关）==========

@app.route("/debug-cn")
def debug_cn():
    """腾讯API调试页面"""
    return """
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>腾讯API调试</title>
<style>body{font-family:sans-serif;background:#111;color:#ddd;padding:20px}
textarea,input{width:100%;padding:8px;margin:8px 0;background:#222;border:1px solid #444;color:#ddd;border-radius:4px}
button{padding:10px 20px;background:#c8aa6e;color:#000;border:none;border-radius:4px;cursor:pointer}
pre{background:#1a1a2e;padding:10px;border-radius:4px;overflow:auto;font-size:12px}
th{text-align:left;background:#333;padding:4px 8px}
td{padding:4px 8px;border-top:1px solid #333}
</style></head><body>
<h1>⚔ 腾讯API调试</h1>
<p>1. 打开 <a href='https://lol.qq.com' target='_blank'>lol.qq.com</a> 登录</p>
<p>2. F12 → Console → 输入 <code>document.cookie</code> → 复制结果</p>
<p>3. 粘贴到下面:</p>
<form method='get' action='/api/test-tencent'>
<textarea name='cookie' rows='3' placeholder='粘贴Cookie...'></textarea>
<button type='submit'>测试腾讯API</button>
</form>
<p>或者去<a href='/api/loop-test'>循环测试页</a>自动轮番测试</p>
</body></html>
"""

LOL_API_URL = "http://lol.sw.game.qq.com/lol/api/"

@app.route("/api/test-tencent")
def api_test_tencent():
    """用多种方式调用腾讯API"""
    cookie_str = request.args.get("cookie","")
    if not cookie_str:
        return jsonify({"error":"需要Cookie"})

    # 解析Cookie
    cookies = {}
    for i in cookie_str.split(";"):
        if "=" in i:
            k,v = i.split("=",1)
            cookies[k.strip()] = v.strip()

    results = {}
    # 从Cookie提取用户信息
    tgp_id = cookies.get("tgp_id","")
    p_uin = cookies.get("p_uin","").lstrip("o")

    # 要尝试的accountId列表
    try_ids = {
        "无accountId(自动)": None,
        "QQ号_"+p_uin: p_uin,
        "tgp_id_"+tgp_id: tgp_id,
        "已知blowjob_16241692751": "16241692751",
    }

    # 要尝试的大区
    areas = [1, 7, 14, 2, 3]

    for label, aid in try_ids.items():
        for area in areas:
            params = {"c":"Battle","a":"matchList","areaId":area,"queueId":"400,420,430,440,450","r1":"matchList"}
            if aid: params["accountId"] = aid
            try:
                r = requests.get(LOL_API_URL, params=params, cookies=cookies, timeout=10)
                body = r.text[:200]
                results[f"{label}_大区{area}"] = {"status":r.status_code,"body":body[:150]}
            except Exception as e:
                results[f"{label}_大区{area}"] = {"error":str(e)[:60]}

    # 额外试POST方式
    if p_uin:
        try:
            r = requests.post(LOL_API_URL, data={"c":"Battle","a":"matchList","areaId":1,"accountId":p_uin,"queueId":"400,420,430,440,450","r1":"matchList"}, cookies=cookies, timeout=10)
            results[f"POST_QQ号"] = {"status":r.status_code,"body":r.text[:150]}
        except: pass

    return jsonify(results)


@app.route("/api/debug-search")
def api_debug_search():
    """调试搜索 - 返回所有搜索方式的原始结果"""
    name = request.args.get("name", "").strip()
    server = request.args.get("server", "kr")

    if not name or server not in SERVERS:
        return jsonify({"error": "参数无效"}), 400

    results = {"searches": [], "server": server, "routing": get_region_for_platform(server)}
    routing = SERVERS[server]["routing"]
    results["api_key_prefix"] = riot.api_key[:15] + "..." if riot.api_key else "EMPTY"

    # 尝试 Account API 用常见标签
    for tag in (get_default_tags(server) + ["00000"]):
        try:
            result = riot.get_account_by_riot_id(routing, name, tag)
            results["searches"].append({
                "method": f"Account API ({name}#{tag})",
                "success": result is not None,
                "has_puuid": result.get("puuid") is not None if result else False,
                "raw": result,
            })
        except Exception as e:
            results["searches"].append({"method": f"Account API ({name}#{tag})", "error": str(e)})

    # 尝试 summoner-v4
    try:
        result = riot.get_summoner_by_name(server, name)
        results["searches"].append({
            "method": f"summoner-v4 ({server})",
            "success": result is not None,
            "has_puuid": result.get("puuid") is not None if result else False,
            "raw": result,
        })
    except Exception as e:
        results["searches"].append({"method": "summoner-v4", "error": str(e)})

    return jsonify(results)


def get_default_tags(server: str) -> list:
    """根据服务器获取默认的 Riot ID 标签"""
    tags = {
        "kr": ["KR1", "KR2"],
        "na1": ["NA1"],
        "euw1": ["EUW"],
        "eun1": ["EUNE"],
        "jp1": ["JP1"],
        "oc1": ["OC1"],
        "br1": ["BR1", "BR2"],
        "la1": ["LA1"],
        "la2": ["LA2"],
        "tr1": ["TR1"],
        "ph2": ["PH2"],
        "sg2": ["SG2"],
        "th2": ["TH2"],
        "vn2": ["VN2"],
        "tw2": ["TW2"],
    }
    return tags.get(server, ["00000"])


# ========== 启动 ==========

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LOL 战绩查询 Web App")
    parser.add_argument("--port", type=int, default=5000, help="端口")
    parser.add_argument("--host", default="0.0.0.0", help="绑定地址")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--api-key", help="Riot API Key（可替代环境变量 RIOT_API_KEY）")
    args = parser.parse_args()

    if args.api_key:
        riot.api_key = args.api_key
        riot.session.headers.update({"X-Riot-Token": args.api_key})

    if riot.api_key == "RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx":
        logger.warning("=" * 60)
        logger.warning("未设置 RIOT_API_KEY！")
        logger.warning("请前往 https://developer.riotgames.com 注册获取免费 API Key")
        logger.warning("设置方式: export RIOT_API_KEY=你的Key")
        logger.warning("或者: python app.py --api-key 你的Key")
        logger.warning("=" * 60)
    else:
        # 尝试加载英雄数据
        try:
            riot.load_champion_data()
        except Exception as e:
            logger.warning(f"加载英雄数据失败（启动后可重试）: {e}")

    print(f"""
╔══════════════════════════════════════════════╗
║     英雄联盟战绩查询 - 第三方网站                ║
║                                              ║
║  浏览器访问: http://localhost:{args.port}          ║
║                                              ║
║  支持服务器:                                   ║
""" + "\n".join(f"║    {code}: {info['name']}" for code, info in SERVERS.items()) + f"""
║                                              ║
║  注意: 国服暂不支持 Riot API                    ║
║  国服用户请使用 LCU 本地版                      ║
╚══════════════════════════════════════════════╝
    """)

    app.run(host=args.host, port=args.port, debug=args.debug)
