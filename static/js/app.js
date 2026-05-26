/**
 * LoLStats - 英雄联盟战绩查询前端
 * OP.GG 风格 · 单页应用
 */

// ============== 全局状态 ==============
let currentState = {
    puuid: null,
    server: 'kr',
    summonerName: '',
    games: [],
    matchCache: {},
};

// CDN 图片 - 使用服务器代理加载（自动尝试多个CDN源）
// 国内用户：Render服务器 -> 腾讯CDN -> 拳头CDN
const CDN = '/img';

// ============== DOM 引用 ==============
const $ = (id) => document.getElementById(id);

const DOM = {
    hero: $('heroSection'),
    loading: $('loadingOverlay'),
    loadingText: $('loadingText'),
    results: $('resultsContainer'),
    errorBox: $('errorBox'),
    errorText: $('errorText'),

    searchInput: $('searchInput'),
    serverSelect: $('serverSelect'),
    navRegion: $('navRegion'),

    profileName: $('profileName'),
    profileLevel: $('profileLevel'),
    profileIcon: $('profileIcon'),
    profileServer: $('profileServer'),

    rankSolo: $('rankSolo'),
    rankFlex: $('rankFlex'),
    soloEmblem: $('soloEmblem'),
    flexEmblem: $('flexEmblem'),
    soloTier: $('soloTier'),
    flexTier: $('flexTier'),
    soloStats: $('soloStats'),
    flexStats: $('flexStats'),

    masteryBar: $('masteryBar'),
    masteryList: $('masteryList'),

    statGames: $('statGames'),
    statWins: $('statWins'),
    statWinRate: $('statWinRate'),
    statKda: $('statKda'),
    statVision: $('statVision'),
    recentResults: $('recentResults'),

    matchesCount: $('matchesCount'),
    matchList: $('matchList'),

    modal: $('matchModal'),
    modalQueueName: $('modalQueueName'),
    modalDuration: $('modalDuration'),
    modalBody: $('modalBody'),
};

// ============== 段位徽章 ==============
const TIER_ORDER = ['IRON', 'BRONZE', 'SILVER', 'GOLD', 'PLATINUM',
                    'EMERALD', 'DIAMOND', 'MASTER', 'GRANDMASTER', 'CHALLENGER'];

function getTierEmblem(tier) {
    if (!tier) return '';
    const t = tier.toLowerCase();
    return `${CDN}/profileicon/${t === 'grandmaster' ? 'grandmaster' : t}.png`;
    // 使用 profileicon 作为 fallback，实际上段位图标需要特殊处理
}

function getTierNumber(tier) {
    return TIER_ORDER.indexOf(tier.toUpperCase()) + 1;
}

// ============== 搜索入口 ==============
function handleSearch() {
    const name = DOM.searchInput.value.trim();
    const server = DOM.serverSelect.value;
    if (!name) {
        showError('请输入召唤师名称');
        return;
    }
    searchSummoner(name, server);
}

function quickSearch(name) {
    DOM.searchInput.value = name;
    handleSearch();
}

// ============== 搜索召唤师 ==============
async function searchSummoner(name, server) {
    showLoading('正在搜索召唤师...');
    hideError();
    DOM.results.style.display = 'none';

    try {
        const resp = await fetch(`/api/search?name=${encodeURIComponent(name)}&server=${server}`);
        const data = await resp.json();

        if (!resp.ok) {
            showError(data.error || '查询失败');
            hideLoading();
            return;
        }

        currentState.puuid = data.summoner.puuid;
        currentState.server = server;
        currentState.summonerName = data.summoner.name;

        // 更新导航栏
        DOM.navRegion.textContent = data.server_name;

        // 渲染召唤师信息
        renderSummoner(data.summoner, data.ranked);
        renderMastery(data.mastery);

        // 加载比赛
        DOM.results.style.display = 'block';
        DOM.results.scrollIntoView({ behavior: 'smooth', block: 'start' });
        await loadMatches(data.summoner.puuid, server);

    } catch (e) {
        showError('网络错误: ' + e.message);
    } finally {
        hideLoading();
    }
}

// ============== 渲染召唤师 ==============
function renderSummoner(summoner, ranked) {
    DOM.profileName.textContent = summoner.name;
    DOM.profileLevel.textContent = summoner.summoner_level || '-';
    DOM.profileIcon.src = `${CDN}/profileicon/${summoner.profile_icon_id || 1}.png`;
    DOM.profileServer.textContent = DOM.navRegion.textContent;

    // 段位
    const solo = ranked?.RANKED_SOLO_5x5;
    const flex = ranked?.RANKED_FLEX_5x5;

    renderRank('solo', solo);
    renderRank('flex', flex);
}

function renderRank(type, data) {
    const tierEl = type === 'solo' ? DOM.soloTier : DOM.flexTier;
    const statsEl = type === 'solo' ? DOM.soloStats : DOM.flexStats;
    const emblemEl = type === 'solo' ? DOM.soloEmblem : DOM.flexEmblem;
    const container = type === 'solo' ? DOM.rankSolo : DOM.rankFlex;

    if (!data) {
        tierEl.textContent = 'Unranked';
        statsEl.textContent = '未定级';
        emblemEl.src = '';
        return;
    }

    const tier = data.tier;
    const rank = data.rank;
    const lp = data.lp;
    const wins = data.wins;
    const losses = data.losses;

    tierEl.textContent = `${tier} ${rank} · ${lp}LP`;
    statsEl.textContent = `${wins}胜 ${losses}负 (${data.win_rate}%)`;

    // 段位徽章
    const tierLower = tier.toLowerCase();
    emblemEl.src = `${CDN}/profileicon/${tierLower}.png`;
    emblemEl.onerror = function() {
        this.src = `${CDN}/profileicon/1.png`;
        this.style.opacity = '0.3';
    };
}

// ============== 英雄熟练度 ==============
function renderMastery(mastery) {
    if (!mastery || mastery.length === 0) {
        DOM.masteryBar.style.display = 'none';
        return;
    }

    DOM.masteryBar.style.display = 'flex';
    DOM.masteryList.innerHTML = mastery.map(m => `
        <div class="mastery-champ">
            <img src="${CDN}/champion-icon/${m.champion_id || m.champion_name}.png"
                 onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%23333%22 width=%22100%22 height=%22100%22/><text x=%2250%22 y=%2265%22 text-anchor=%22middle%22 fill=%22%23666%22 font-size=%2230%22>${m.champion_name[0]}</text></svg>'"
                 alt="${m.champion_name}">
            <span class="mastery-champ-name">${m.champion_name}</span>
            <span class="mastery-champ-level">M${m.champion_level}</span>
        </div>
    `).join('');
}

// ============== 加载比赛 ==============
async function loadMatches(puuid, server, count = 15) {
    showLoading('加载比赛记录...');
    DOM.matchList.innerHTML = '';

    try {
        const resp = await fetch(`/api/matches?puuid=${puuid}&server=${server}&count=${count}`);
        const data = await resp.json();

        if (!resp.ok) {
            DOM.matchList.innerHTML = `<div class="no-matches">加载失败: ${data.error}</div>`;
            return;
        }

        currentState.games = data.games || [];
        renderMatches(currentState.games);
        renderStats(currentState.games);

    } catch (e) {
        DOM.matchList.innerHTML = `<div class="no-matches">网络错误: ${e.message}</div>`;
    } finally {
        hideLoading();
    }
}

// ============== 渲染比赛列表 ==============
function renderMatches(games) {
    DOM.matchesCount.textContent = `最近 ${games.length} 场`;

    if (!games || games.length === 0) {
        DOM.matchList.innerHTML = '<div class="no-matches">暂无比赛记录</div>';
        return;
    }

    let html = '';
    for (const g of games) {
        const cls = g.win ? 'win' : 'lose';
        const resultText = g.win ? '胜利' : '失败';
        const kdaCls = g.kda_ratio >= 3 ? 'good' : g.kda_ratio >= 1.5 ? 'ok' : 'bad';

        html += `
            <div class="match-card ${cls}" onclick="openMatchDetail('${g.match_id}')">
                <div class="match-col-result">
                    <div class="match-result-text">${resultText}</div>
                    <div class="match-queue">${g.queue_name || ''}</div>
                    <div class="match-duration">${g.duration}</div>
                </div>
                <div class="match-col-champ">
                    <div class="champ-icon-wrap">
                        <img class="champ-icon"
                             src="${CDN}/champion-icon/${g.champion_id}.png"
                             onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%23333%22 width=%22100%22 height=%22100%22/><text x=%2250%22 y=%2260%22 text-anchor=%22middle%22 fill=%22%23666%22 font-size=%2228%22>?</text></svg>'"
                             alt="">
                        <span class="champ-level">${g.champ_level}</span>
                    </div>
                    <span class="champ-name">${g.champion_name}</span>
                </div>
                <div class="match-col-kda">
                    <div class="kda-main">${g.kda}</div>
                    <div class="kda-ratio ${kdaCls}">${g.kda_ratio}:1 KDA</div>
                </div>
                <div class="match-col-stats">
                    <span class="match-stat-line">⚔ ${formatNum(g.total_damage)}</span>
                    <span class="match-stat-line">💰 ${formatGold(g.gold_earned)}</span>
                    <span class="match-stat-line">👁 ${g.vision_score} · ${g.cs}CS</span>
                </div>
                <div class="match-col-items">
                    <div class="items-row">
                        ${g.items.map(id =>
                            id > 0
                                ? `<img class="match-item-icon" src="${CDN}/item/${id}.png"
                                        onerror="this.style.display='none'">`
                                : '<span class="item-empty"></span>'
                        ).join('')}
                    </div>
                </div>
                <div class="match-col-time">
                    <span class="time-ago">${g.time_ago || ''}</span>
                </div>
            </div>
        `;
    }

    DOM.matchList.innerHTML = html;
}

// ============== 渲染统计 ==============
function renderStats(games) {
    if (!games || games.length === 0) return;

    const wins = games.filter(g => g.win).length;
    const total = games.length;
    const wr = total > 0 ? Math.round(wins / total * 100) : 0;

    let totalK = 0, totalD = 0, totalA = 0, totalV = 0;
    for (const g of games) {
        totalK += g.kills || 0;
        totalD += g.deaths || 0;
        totalA += g.assists || 0;
        totalV += g.vision_score || 0;
    }

    const avgKda = totalD > 0 ? ((totalK + totalA) / totalD).toFixed(1) : 'Perfect';
    const avgV = total > 0 ? Math.round(totalV / total) : 0;

    DOM.statGames.textContent = total;
    DOM.statWins.textContent = wins;
    DOM.statWinRate.textContent = wr + '%';
    DOM.statKda.textContent = avgKda;
    DOM.statVision.textContent = avgV;

    // 最近10场
    const recent = games.slice(0, 10);
    DOM.recentResults.innerHTML = recent.map(g =>
        `<span class="mini-result ${g.win ? 'w' : 'l'}">${g.win ? 'W' : 'L'}</span>`
    ).join('') + `<span class="stat-label" style="margin-left:4px">最近${recent.length}场</span>`;
}

// ============== 比赛详情 ==============
async function openMatchDetail(matchId) {
    DOM.modal.style.display = 'flex';
    DOM.modalBody.innerHTML = '<div class="modal-loading"><div class="spinner-sm"></div><span>加载比赛详情...</span></div>';

    // 检查缓存
    if (currentState.matchCache[matchId]) {
        renderMatchDetail(currentState.matchCache[matchId]);
        return;
    }

    try {
        const resp = await fetch(
            `/api/match/${matchId}/detail?server=${currentState.server}&puuid=${currentState.puuid}`
        );
        const data = await resp.json();

        if (!resp.ok) {
            DOM.modalBody.innerHTML = `<div class="modal-loading" style="color:var(--red)">加载失败: ${data.error}</div>`;
            return;
        }

        currentState.matchCache[matchId] = data;
        renderMatchDetail(data);

    } catch (e) {
        DOM.modalBody.innerHTML = `<div class="modal-loading" style="color:var(--red)">网络错误</div>`;
    }
}

function renderMatchDetail(data) {
    DOM.modalQueueName.textContent = data.queue_name || '比赛详情';
    DOM.modalDuration.textContent = data.duration || '';

    const players = data.players || [];
    const blueTeam = players.filter(p => p.team_id === 100);
    const redTeam = players.filter(p => p.team_id === 200);
    const teams = data.teams || {};

    const renderTeamTable = (teamPlayers, teamId, label) => {
        const teamData = teams[teamId] || {};
        const isWin = teamData.win;
        const resultCls = isWin ? 'win' : 'lose';

        let html = `
            <div class="team-container">
                <div class="team-header ${resultCls}">
                    <span class="team-label">${label}</span>
                    <span class="team-result ${resultCls}">${isWin ? '胜利' : '失败'}</span>
                </div>
                <table class="team-table">
                    <thead>
                        <tr>
                            <th>英雄</th>
                            <th>玩家</th>
                            <th>KDA</th>
                            <th>伤害</th>
                            <th>经济</th>
                            <th>CS</th>
                            <th>装备</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        for (const p of teamPlayers) {
            const isTarget = p.puuid === data.target_puuid;
            const kdaRatio = p.deaths > 0
                ? ((p.kills + p.assists) / p.deaths).toFixed(1)
                : 'Perfect';

            html += `
                <tr class="${isTarget ? 'highlight' : ''}">
                    <td>
                        <div class="detail-champ">
                            <img src="${CDN}/champion-icon/${p.champion_id}.png"
                                 onerror="this.style.display='none'">
                            <span class="detail-champ-level">${p.champ_level || '-'}</span>
                        </div>
                    </td>
                    <td class="detail-player-name">${p.summoner_name}</td>
                    <td>
                        <span class="detail-kda">${p.kills}/${p.deaths}/${p.assists}</span>
                        <span class="detail-kda-ratio">(${kdaRatio}:1)</span>
                    </td>
                    <td>${formatNum(p.total_damage)}</td>
                    <td>${formatGold(p.gold_earned)}</td>
                    <td>${p.cs}</td>
                    <td>
                        <div class="detail-items">
                            ${p.items.map(id =>
                                id > 0
                                    ? `<img class="match-item-icon" src="${CDN}/item/${id}.png"
                                            onerror="this.style.display='none'">`
                                    : '<span class="item-empty"></span>'
                            ).join('')}
                        </div>
                    </td>
                </tr>
            `;
        }

        html += '</tbody></table></div>';
        return html;
    };

    DOM.modalBody.innerHTML = `
        ${renderTeamTable(blueTeam, 100, '🔵 蓝色方')}
        ${renderTeamTable(redTeam, 200, '🔴 红色方')}
    `;
}

// ============== 工具函数 ==============
function formatNum(n) {
    if (!n) return '0';
    if (n >= 10000) return (n / 10000).toFixed(1) + '万';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return n.toLocaleString();
}

function formatGold(n) {
    if (!n) return '0';
    return (n / 1000).toFixed(1) + 'k';
}

function showLoading(text) {
    DOM.loadingText.textContent = text || '正在查询...';
    DOM.loading.style.display = 'block';
}

function hideLoading() {
    DOM.loading.style.display = 'none';
}

function showError(msg) {
    DOM.errorBox.style.display = 'flex';
    DOM.errorText.textContent = msg;
    DOM.errorBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function hideError() {
    DOM.errorBox.style.display = 'none';
}

function closeModal(e) {
    if (!e || e.target === DOM.modal) {
        DOM.modal.style.display = 'none';
    }
}

// ============== 键盘事件 ==============
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
    if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
        if (document.activeElement !== DOM.searchInput) {
            e.preventDefault();
            DOM.searchInput.focus();
        }
    }
});

// ============== URL hash 搜索（分享链接） ==============
// 支持直接通过 #summoner=Name&server=kr 访问
function checkHashSearch() {
    const hash = window.location.hash.slice(1);
    if (!hash) return;

    const params = new URLSearchParams(hash);
    const name = params.get('summoner');
    const server = params.get('server') || 'kr';

    if (name) {
        DOM.searchInput.value = name;
        DOM.serverSelect.value = server;
        searchSummoner(name, server);
    }
}

// 监听 hash 变化
window.addEventListener('hashchange', checkHashSearch);

// 启动时检查
document.addEventListener('DOMContentLoaded', checkHashSearch);

// 图片加载失败时隐藏（避免破损图标）
document.addEventListener('error', function(e) {
    if (e.target.tagName === 'IMG') {
        e.target.style.display = 'none';
    }
}, true);
