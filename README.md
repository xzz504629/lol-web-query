# LOL 战绩查询 Web 应用

基于 **Riot Games API** 的英雄联盟战绩查询网站，支持韩服、美服、欧服等全球服务器。

**部署版**：可部署到 [Render](https://render.com)、Railway、Vercel 等云平台。

## 快速上手

### 1. 获取 API Key

前往 [Riot Games Developer Portal](https://developer.riotgames.com) 注册并申请 API Key（免费）。

### 2. 本地运行

```bash
pip install -r requirements.txt
export RIOT_API_KEY=你的API_Key
python app.py
```

浏览器访问 `http://localhost:5000`

### 3. 部署到云端

**一键部署到 Render**：

1. Fork 这个仓库到你的 GitHub
2. 在 [Render](https://render.com) 创建新的 Web Service，连接你的仓库
3. 设置环境变量 `RIOT_API_KEY`
4. 部署完成！

Render 会自动读取 `render.yaml` 配置。

**或用 Railway**：
```bash
railway login
railway up
```

### 配置

| 环境变量 | 说明 | 必填 |
|---------|------|:---:|
| `RIOT_API_KEY` | Riot 开发者 API Key | ✅ |

## 功能

- ✅ 按名称搜索全球各服召唤师（包括国服！）
- ✅ 排位段位、胜率、英雄熟练度
- ✅ 比赛历史（最近15场详细数据）
- ✅ 比赛详情（10人完整数据面板）
- ✅ OP.GG 风格暗黑主题 UI
- ✅ 响应式，适配手机
- ✅ 可部署到云服务器

## 支持服务器

### 国际服
韩服、美服、西欧服、北欧东欧服、日服、土耳其服、巴西服、
拉丁美洲服、大洋洲服、菲律宾服、新加坡服、泰国服、越南服、台服

### 国服（基于 Riot ID 系统）
艾欧尼亚、祖安、诺克萨斯、班德尔城、皮尔特沃夫、战争学院、
弗雷尔卓德、巨神峰、雷瑟守备、无畏先锋、钢铁烈阳、暗影岛

> 国服查询方式：选择国服分区，输入 `游戏名#标签`（如 `blowjob#89795`）

## 搜索方式

| 服务器 | 输入格式 | 示例 |
|-------|---------|------|
| 国际服 | 召唤师名称 | `Hide on bush` |
| 国服 | 游戏名#标签 | `blowjob#89795` |
