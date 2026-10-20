/* 行銷審核（老闆 10/19）：GPT 每天交的貼文（文字＋圖片）、每天海巡到的團訂需求，老闆核准才可以發。只有老闆看得到。
   發文是人工：核准 → 複製文字、存圖 → 打開 Threads／臉書社團貼上 → 回來按「我發了」。 */
let MK = null;
SUB.mk = 'review';
const MKCH = { threads: 'Threads', fb_group: '臉書社團', fb_page: '臉書粉專', ig: 'Instagram' };
LOAD.mk = async function () {
  MK = await api('/api/mk?tab=' + SUB.mk);
  const C = MK.counts, T = MK.today, G = MK.target;
  localNav('行銷', [['review', '待審貼文', C.review], ['publish', '待發布', C.publish], ['patrol', '海巡', C.patrol], ['data', '數據'], ['done', '紀錄'], ['setup', '設定']], SUB.mk, 'mkTab');
  const sub = {
    review: 'GPT 每天交的貼文。可以直接改字，改完按核准；不行就退回寫意見，GPT 隔天改好再送。',
    publish: '你核准的貼文，GPT 會排程發出去，發了會自動標「已發布」。要自己發也可以：複製文字 → 存圖片 → 貼上 → 按「我發了」。',
    patrol: '每天上網找「有人要訂便當」的貼文和活動。回覆一定要你核准；要打電話的轉成開發名單。',
    data: '近 30 天：發了幾篇、看的人多不多、海巡有沒有變成名單和訂單。每週一早上會整理週報給你，也回饋給 GPT。',
    done: '發過的貼文、處理過的海巡。',
    setup: '臉書社團清單、跟 GPT 的交接狀態。'
  }[SUB.mk];
  let h = hero('行銷', { review: '貼文審核。', publish: '核准了，排程發。', patrol: '海巡。', data: '數據。', done: '紀錄。', setup: '設定。' }[SUB.mk], sub);
  const warn = (v, [a]) => v < a ? ' style="color:#b42318"' : '';
  h += `<div class="grid"><div class="tile stat"><div class="k">今天 GPT 交</div><div class="v">${T.gpt} 篇</div></div>
    <div class="tile stat"><div class="k">今天發出</div><div class="v"${warn(T.posted, G.post)}>${T.posted} 篇</div><div class="small">目標 ${G.post[0]}–${G.post[1]} 篇</div></div>
    <div class="tile stat"><div class="k">今天海巡</div><div class="v"${warn(T.patrol, G.patrol)}>${T.patrol} 則</div><div class="small">目標 ${G.patrol[0]}–${G.patrol[1]} 則</div></div>
    <div class="tile stat"><div class="k">今天回覆</div><div class="v">${T.replied} 則</div></div></div>`;
  h += ({ review: mkReview, publish: mkPublish, patrol: mkPatrol, data: mkData, done: mkDone, setup: mkSetup })[SUB.mk]();
  $('#main').innerHTML = h;
};
function mkTab(k) { SUB.mk = k; LOAD.mk(); }
const mkImgs = p => (p.images || []).map(f => `<img src="/api/mk/img?f=${encodeURIComponent(f)}" alt="" loading="lazy" style="width:132px;height:132px;object-fit:cover;border-radius:12px;margin:0 8px 8px 0;cursor:zoom-in" onclick="zoom(this.src)">`).join('');
const mkHead = p => `<div class="small"><span class="tag">${MKCH[p.channel] || esc(p.channel)}</span>${p.grp ? ' ' + esc(p.grp) : ''}・${esc(p.batch.slice(5).replace('-', '/'))}（${wkOf(p.batch)}）${p.suggest_time ? ' ' + esc(p.suggest_time) : ''} 發${p.status === '已排程' ? `・<b style="color:#1a7f37">GPT 已排程${p.scheduled_at ? ' ' + esc(p.scheduled_at) : ''}</b>` : p.status === '已核准' ? '・等 GPT 排程' : ''}</div>`;

function mkReview() {
  if (!MK.posts.length) return `<div class="card muted">沒有等你審的貼文。GPT 每天早上交新的，交來會通知你。</div>`;
  return MK.posts.map(p => `<div class="card">${mkHead(p)}<h3 style="margin:6px 0 10px">${esc(p.title || '（沒有標題）')}</h3>
    ${p.revision_of ? `<div class="banner warn">這篇是照你的意見改過再送的（上一版 ${esc(p.revision_of)}）</div>` : ''}
    <div>${mkImgs(p)}</div>${p.image_note ? `<div class="small">圖：${esc(p.image_note)}</div>` : ''}
    <label>貼文內容（可以直接改，改完按核准）</label><textarea id="mkb${p.id}" rows="9">${esc(p.body)}</textarea>
    <div class="small">${p.body.length} 字${p.cta ? '・想讓人做的事：' + esc(p.cta) : ''}</div>
    ${p.gpt_note ? `<div class="small" style="margin-top:6px">GPT 的說明：${esc(p.gpt_note)}</div>` : ''}
    <label>意見（退回一定要寫，會回給 GPT 改）</label><input id="mkn${p.id}" placeholder="例：太像廣告、價格不要寫、圖換成店裡實拍">
    <div class="btns" style="margin-top:12px"><button class="btn green" onclick="mkPost(${p.id},'approve')">核准</button>
      <button class="btn gray" onclick="mkPost(${p.id},'reject')">退回給 GPT 改</button><button class="btn gray sm" onclick="mkPost(${p.id},'void')">這篇不要</button></div>
    <div id="mkm${p.id}"></div></div>`).join('');
}
async function mkPost(id, action) {
  const body = ($('#mkb' + id) || {}).value, note = ($('#mkn' + id) || {}).value || '';
  if (action === 'reject' && !note.trim()) return msgOk('#mkm' + id, '退回要寫意見，GPT 才知道怎麼改');
  if (action === 'void' && !confirm('這篇不要了？')) return;
  try { await api('/api/mk/post/review', { id, action, body, note }); await LOAD.mk(); refreshBadges(); } catch (e) { msgOk('#mkm' + id, e); }
}

function mkPublish() {
  if (!MK.posts.length) return `<div class="card muted">沒有待發布的貼文。核准的貼文會出現在這裡。</div>`;
  return MK.posts.map(p => {
    const g = MK.groups.find(x => x.name === p.grp);
    return `<div class="card">${mkHead(p)}<h3 style="margin:6px 0 10px">${esc(p.title || '')}</h3><div>${mkImgs(p)}</div>
      ${(p.images || []).length ? '<div class="small">存圖片：手機長按圖片 → 儲存；電腦點圖片放大後按右鍵另存。</div>' : ''}
      <div style="white-space:pre-wrap;background:var(--bg);padding:12px;border-radius:12px;margin:10px 0">${esc(p.body)}</div>
      <div class="btns"><button class="btn" onclick="mkCopy(${p.id})">① 複製文字</button>
        ${p.channel === 'threads' ? `<a class="btn sec" target="_blank" rel="noopener" href="https://www.threads.net/intent/post?text=${encodeURIComponent(p.body)}">② 用 Threads 發（文字自動帶入）</a>` : ''}
        ${g && g.url ? `<a class="btn sec" target="_blank" rel="noopener" href="${esc(g.url)}">② 打開社團</a>` : (p.channel === 'fb_group' ? '<span class="small">（社團網址還沒設定，到「設定」加）</span>' : '')}
        <button class="btn green" onclick="mkPosted(${p.id})">③ 我發了</button>${p.status === '已排程' ? `<button class="btn gray sm" onclick="mkReject(${p.id})">不要發了（叫 GPT 取消排程）</button>` : `<button class="btn gray sm" onclick="mkPost(${p.id},'reopen')">改回待審</button>`}</div>
      ${g && g.rule ? `<div class="small" style="margin-top:6px">社團規則：${esc(g.rule)}</div>` : ''}<div id="mkm${p.id}"></div></div>`;
  }).join('');
}
async function mkReject(id) {
  const note = prompt('不要發的原因（會回給 GPT，請它取消排程）：', '');
  if (!note) return;
  try { await api('/api/mk/post/review', { id, action: 'reject', note }); await LOAD.mk(); } catch (e) { msgOk('#mkm' + id, e); }
}
async function mkCopy(id) {
  const p = MK.posts.find(x => x.id === id);
  try { await navigator.clipboard.writeText(p.body); $('#mkm' + id).innerHTML = '<div class="okmsg">已複製，去 Threads／社團貼上</div>'; }
  catch (e) { prompt('複製這段：', p.body); }
}
async function mkPosted(id) {
  const url = prompt('發好了！貼文網址貼在這裡（沒有就直接按確定）：', '');
  if (url === null) return;
  try { await api('/api/mk/post/posted', { id, url }); await LOAD.mk(); } catch (e) { msgOk('#mkm' + id, e); }
}

function mkPatrol() {
  if (!MK.patrol.length) return `<div class="card muted">沒有等你看的海巡結果。每天早上自動找，找到會通知你。</div>`;
  const info = x => [x.who && '誰：' + x.who, x.need && '需求：' + x.need, x.boxes && '約 ' + x.boxes + ' 盒', x.event_date && '日期：' + x.event_date, x.phone && '電話：' + x.phone].filter(Boolean).map(esc).join('・');
  return MK.patrol.map(x => `<div class="card" style="${x.status === '要回覆' ? 'border:2px solid var(--ok, #1a7f37)' : ''}">
    <div class="small"><span class="tag">${esc(x.platform)}</span>${x.post_date ? ' ' + esc(x.post_date) : ''}${x.area ? '・' + esc(x.area) : ''}${x.score ? '・可能性 ' + x.score + '/5' : ''}${x.status === '要回覆' ? '・<b>已核准，等你去回</b>' : ''}</div>
    <h3 style="margin:6px 0"><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title || x.url)} ›</a></h3>
    ${x.snippet ? `<div class="m" style="white-space:pre-wrap">${esc(x.snippet)}</div>` : ''}
    ${info(x) ? `<div class="small" style="margin-top:6px">${info(x)}</div>` : ''}${x.why ? `<div class="small">為什麼找它：${esc(x.why)}</div>` : ''}
    ${x.status === '要回覆' ? `<div style="white-space:pre-wrap;background:var(--bg);padding:12px;border-radius:12px;margin:10px 0">${esc(x.reply)}</div>
      <div class="btns"><button class="btn" onclick="mkCopyR(${x.id})">① 複製回覆</button><a class="btn sec" href="${esc(x.url)}" target="_blank" rel="noopener">② 打開原文</a>
        <button class="btn green" onclick="mkPat(${x.id},'replied')">③ 我回了</button><button class="btn gray sm" onclick="mkPat(${x.id},'reopen')">改回待審</button></div>`
    : `<label>建議回覆（${esc(x.action || '留言')}，可以改）</label><textarea id="mkr${x.id}" rows="4">${esc(x.reply || '')}</textarea>
      <div class="btns" style="margin-top:10px"><button class="btn green" onclick="mkPat(${x.id},'reply')">核准回覆</button>
        <button class="btn sec" onclick="mkPat(${x.id},'lead')">轉開發名單（打電話）</button><button class="btn gray" onclick="mkPat(${x.id},'skip')">略過</button></div>`}
    <div id="mkq${x.id}"></div></div>`).join('');
}
async function mkPat(id, action) {
  const reply = ($('#mkr' + id) || {}).value;
  if (action === 'lead' && !confirm('轉成開發名單？夥伴會在「開發」看到，照名單打電話。')) return;
  try { await api('/api/mk/patrol/review', { id, action, reply }); await LOAD.mk(); refreshBadges(); } catch (e) { msgOk('#mkq' + id, e); }
}
async function mkCopyR(id) {
  const x = MK.patrol.find(y => y.id === id);
  try { await navigator.clipboard.writeText(x.reply); $('#mkq' + id).innerHTML = '<div class="okmsg">已複製，去原文底下貼上</div>'; } catch (e) { prompt('複製這段：', x.reply); }
}

function mkData() {
  const D = MK.data, T = D.total, n = x => fmt(x || 0);
  const kv = (o, f) => Object.entries(o || {}).map(([k, v]) => `${esc(f ? f(k) : k)} ${v}`).join('・') || '—';
  const mx = Math.max(1, ...D.daily.map(x => Math.max(x.posted, x.patrol, x.replied)));
  const bar = (v, color) => `<div style="height:8px;border-radius:4px;background:${color};width:${Math.round(v / mx * 100)}%;min-width:${v ? 3 : 0}px"></div>`;
  let h = `<div class="grid"><div class="tile stat"><div class="k">發文</div><div class="v">${D.posts.length} 篇</div><div class="small">${kv(D.by_channel, k => MKCH[k] || k)}</div></div>
    <div class="tile stat"><div class="k">觀看</div><div class="v">${n(T.views)}</div><div class="small">讚 ${n(T.likes)}・留言 ${n(T.replies)}・私訊 ${n(T.dms)}</div></div>
    <div class="tile stat"><div class="k">海巡</div><div class="v">${Object.values(D.patrol).reduce((a, b) => a + b, 0)} 則</div><div class="small">${kv(D.patrol)}</div></div>
    <div class="tile stat"><div class="k">社群來的訂單</div><div class="v">${D.orders.reduce((a, o) => a + o.n, 0)} 單</div><div class="small">${D.orders.map(o => esc(o.source) + ' ' + o.boxes + ' 盒').join('・') || '外送單來源選 Threads／臉書才算得到'}</div></div></div>`;
  if (D.no_metric) h += `<div class="banner warn">${D.no_metric} 篇發了但 GPT 還沒回報觀看數字。</div>`;
  h += `<h2>最近 14 天。<span class="g">發文、海巡、回覆。</span></h2><div class="card">${D.daily.map(x => `<div style="display:grid;grid-template-columns:64px 1fr;gap:10px;align-items:center;margin:6px 0">
      <span class="small">${md(x.day)}（${wkOf(x.day)}）</span><div title="發文 ${x.posted}、海巡 ${x.patrol}、回覆 ${x.replied}">${bar(x.posted, '#e07b12')}<div style="height:3px"></div>${bar(x.patrol, '#7a6a54')}<div style="height:3px"></div>${bar(x.replied, '#1a7f37')}</div></div>`).join('')}
    <div class="small" style="margin-top:8px"><span style="color:#e07b12">■</span> 發文　<span style="color:#7a6a54">■</span> 海巡　<span style="color:#1a7f37">■</span> 回覆</div></div>`;
  h += `<h2>海巡變成生意了嗎。</h2><div class="card"><div class="row"><div class="n">轉成電話名單後</div><div class="m">${kv(D.leads)}</div></div>
    <div class="row"><div class="n">大家在找的</div><div class="m">${D.needs.map(x => esc(x.need) + ' ' + x.n).join('・') || '—'}</div></div></div>`;
  h += `<h2>貼文成效。</h2><div class="card"><div class="tbl"><table><tr><th>發文</th><th>平台</th><th>貼文</th><th class="r">觀看</th><th class="r">讚</th><th class="r">留言</th><th class="r">私訊</th></tr>
    ${D.posts.map(x => `<tr><td>${esc((x.posted_at || '').slice(5, 16))}</td><td>${MKCH[x.channel] || ''}${x.grp ? ' ' + esc(x.grp) : ''}</td><td>${x.posted_url ? `<a href="${esc(x.posted_url)}" target="_blank" rel="noopener">${esc(x.title || x.body.slice(0, 20))}</a>` : esc(x.title || x.body.slice(0, 20))}</td>
      <td class="r">${x.views ?? '—'}</td><td class="r">${x.likes ?? '—'}</td><td class="r">${x.replies ?? '—'}</td><td class="r">${x.dms ?? '—'}</td></tr>`).join('') || '<tr><td colspan="7" class="muted">還沒有發出去的貼文</td></tr>'}</table></div></div>`;
  if (D.rejected.length) h += `<h2>你退回的原因。<span class="g">週報會回饋給 GPT。</span></h2><div class="card">${D.rejected.map(x => `<div class="row"><div class="n">${esc(x.title || x.src_id)}</div><div class="m">${esc(x.review_note)}</div></div>`).join('')}</div>`;
  return h;
}
function mkDone() {
  const ps = MK.posts, xs = MK.done_patrol;
  const pr = ps.map(p => `<tr><td>${esc((p.posted_at || p.reviewed_at || '').slice(5, 16))}</td><td>${MKCH[p.channel] || ''}${p.grp ? ' ' + esc(p.grp) : ''}</td>
    <td>${esc(p.title || p.body.slice(0, 24))}</td><td>${p.status === '已發布' ? (p.posted_url ? `<a href="${esc(p.posted_url)}" target="_blank" rel="noopener">已發布 ›</a>` : '已發布') : esc(p.status) + (p.review_note ? '：' + esc(p.review_note) : '')}</td></tr>`).join('');
  const xr = xs.map(x => `<tr><td>${esc((x.reviewed_at || '').slice(5, 16))}</td><td>${esc(x.platform)}</td><td><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title || x.url)}</a></td><td>${esc(x.status)}${x.review_note ? '<div class="small">' + esc(x.review_note) + '</div>' : ''}</td></tr>`).join('');
  return `<h2>貼文。</h2><div class="card"><div class="tbl"><table><tr><th>時間</th><th>平台</th><th>貼文</th><th>結果</th></tr>${pr || '<tr><td colspan="4" class="muted">還沒有</td></tr>'}</table></div></div>
    <h2>海巡。</h2><div class="card"><div class="tbl"><table><tr><th>時間</th><th>平台</th><th>原文</th><th>處理</th></tr>${xr || '<tr><td colspan="4" class="muted">還沒有</td></tr>'}</table></div></div>`;
}

function mkSetup() {
  return `<h2>行銷參數。<span class="g">在 config/store.toml 設定。</span></h2><div class="card"><div class="row"><div class="n">服務區域</div><div class="m">重點：${MK.area.map(esc).join('、')}</div></div><div class="row"><div class="n">接單門檻</div><div class="m">${MK.min_boxes} ${STORE.unit}以上就送；${MK.area.length ? MK.area.map(esc).join('、') + ' 以外 ' + MK.min_outside + ' ' + STORE.unit + '以上才接' : '不限區域'}</div></div>
    <div class="row"><div class="n">方向</div><div class="m">以大單為主：海巡照可能性、份數大到小排</div></div></div>
    <h2>臉書社團。<span class="g">GPT 寫社團貼文會照這份清單。</span></h2><div class="card">
    ${MK.groups.map(g => `<div class="row"><div><div class="n">${esc(g.name)}</div><div class="m">${g.url ? `<a href="${esc(g.url)}" target="_blank" rel="noopener">${esc(g.url)}</a>` : '沒有網址'}${g.rule ? '・規則：' + esc(g.rule) : ''}</div></div><button class="btn gray sm" onclick="mkGroupDel(${g.id})">移除</button></div>`).join('') || '<div class="muted">還沒有社團。把你有加入、可以發團訂貼文的社團加進來。</div>'}
    <div class="g2" style="margin-top:12px"><div><label>社團名稱</label><input id="mkg_n" placeholder="例：在地大小事"></div><div><label>社團網址</label><input id="mkg_u" placeholder="https://www.facebook.com/groups/..."></div></div>
    <label>社團規則（選填，例：只能週末發廣告）</label><input id="mkg_r">
    <button class="btn" style="margin-top:12px" onclick="mkGroupAdd()">加入清單</button><div id="mkg_m"></div></div>
    <h2>跟 GPT 的交接。</h2><div class="card"><div class="small">GPT 每天把貼文放到 <b>${esc(MK.mk_dir)}\\給CRM\\日期\\</b>，系統每 5 分鐘收一次；審核結果寫到 <b>CRM回饋</b> 資料夾給 GPT 看。</div>
    <button class="btn sec sm" style="margin-top:10px" onclick="mkSweep()">現在收一次</button><div id="mks_m"></div>
    ${MK.imports.map(i => `<div class="row"><div><div class="n">${esc(i.k)}</div><div class="m">${esc((i.done || '').slice(5, 16))} 收 ${i.n} 筆${i.msg ? '・<span style="color:#b42318">' + esc(i.msg) + '</span>' : ''}</div></div></div>`).join('')}</div>`;
}
async function mkGroupAdd() { try { await api('/api/mk/group/save', { name: $('#mkg_n').value, url: $('#mkg_u').value, rule: $('#mkg_r').value }); LOAD.mk(); } catch (e) { msgOk('#mkg_m', e); } }
async function mkGroupDel(id) { if (confirm('從清單移除這個社團？')) { await api('/api/mk/group/remove', { id }); LOAD.mk(); } }
async function mkSweep() { try { const r = await api('/api/mk/sweep', {}); $('#mks_m').innerHTML = `<div class="okmsg">收到貼文 ${r.posts} 篇、海巡 ${r.patrol} 則</div>`; setTimeout(() => LOAD.mk(), 900); refreshBadges(); } catch (e) { msgOk('#mks_m', e); } }
