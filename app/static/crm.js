/* 團訂開發：今天（誰上班、AI 新開發、優先打）、名單、單位詳細與記一通 */
let F = '', LEADS = [], TIMER = null, CUR = null;
SUB.crm = 'home';
LOAD.crm = async function () {
  localNav('開發', [['home', '今天'], ['list', '名單'], ['script', '話術']], SUB.crm, 'crmTab');
  return ({ home: crmHome, list: crmList, script: crmScript })[SUB.crm]();
};
function crmTab(k) { SUB.crm = k; LOAD.crm(); }
function dutyLine(x, label) {
  if (x.closed) return `<div class="row"><div><div class="n">${label} ${md(x.day)}（${wkOf(x.day)}）</div><div class="m">店休：${esc(x.closed)}</div></div></div>`;
  return `<div class="row"><div style="min-width:0"><div class="n">${label} ${md(x.day)}（${wkOf(x.day)}）上班 ${x.on.length} 人</div>
    <div>${x.on.map(p => `<span class="tag t-blue">${esc(p.name)} ${esc(p.sched.split('／')[0])}${p.sched.includes('／') ? '…' : ''}</span>`).join('') || '<span class="muted">沒有人排班</span>'}
    ${x.off.map(n => `<span class="tag t-warn">${esc(n)} 排休</span>`).join('')}</div></div></div>`;
}
function tags(l) {
  let t = '';
  if (l.dnc) t += '<span class="tag t-red">勿再聯絡</span>';
  if ((l.code || '').startsWith('D')) t += '<span class="tag t-blue">AI 新開發</span>';
  if (l.priority === 'A') t += '<span class="tag t-warn">A 核心</span>'; else if (l.priority === 'D') t += '<span class="tag">排後面</span>'; else if (l.priority) t += `<span class="tag">${esc(l.priority)}</span>`;
  if (l.status && l.status !== '未聯絡' && !l.dnc) t += `<span class="tag ${['有興趣', '已報價', '已成交'].includes(l.status) ? 't-ok' : ''}">${esc(l.status)}</span>`;
  if (l.today_calls && l.today_calls.length) t += `<span class="tag t-blue">今天 ${esc(l.today_calls[0].name)} 已打</span>`;
  else if (l.last_call_at && l.last_caller_name) t += `<span class="tag">上次 ${esc(l.last_caller_name)} ${md(l.last_call_at.slice(0, 10))}</span>`;
  const td = todayStr();
  if (l.next_follow && !l.dnc && l.next_follow <= td && !['已成交', '暫無需求'].includes(l.status)) t += `<span class="tag t-warn">${l.next_follow < td ? '逾期' : '今天'}追蹤</span>`;
  if (l.data_status && !['已核', '有公開依據'].includes(l.data_status)) t += `<span class="tag">${esc(l.data_status)}</span>`;
  if (l.assigned_name) t += `<span class="tag">分給 ${esc(l.assigned_name)}</span>`;
  const od = l.open_days || '', wi = (new Date().getDay() + 6) % 7;
  if (od.length === 7) { if (od[wi] === '0') t += '<span class="tag t-warn">今天沒營業</span>'; else t += `<span class="tag">營業 ${daysTxt(od)}</span>`; }
  else t += '<span class="tag">營業日未查</span>';
  return t;
}
function daysTxt(od) { const n = '一二三四五六日'; let o = ''; for (let i = 0; i < 7; i++) o += od[i] === '1' ? n[i] : (od[i] === '?' ? '?' : ''); return o ? ('週' + o) : '不明'; }
function leadRow(l, extra = '') {
  const tel = (l.phone || '').replace(/[^\d+#,]/g, '');
  return `<div class="row click" onclick="openLead(${l.id})"><div style="min-width:0"><div class="n">${esc(l.name)}</div>
    <div class="m">${esc([l.category, l.area, l.phone].filter(Boolean).join(' · '))}${extra}</div><div>${tags(l)}</div></div>
    ${tel ? `<a class="btn green sm" style="min-width:52px" href="tel:${tel}" onclick="event.stopPropagation();callStart(${l.id},${jsq(l.name)})">撥</a>` : ''}</div>`;
}
async function crmHome() {
  const d = await api('/api/dashboard'); const m = d.me, tg = d.target || 50, left = Math.max(0, tg - m.calls);
  const ai = d.ai || { rows: [] }, aiToday = ai.day === todayStr();
  $('#main').innerHTML = hero('開發', `今天打了 ${m.calls} 通。`, `目標 ${tg} 通，還差 ${left} 通。打完一定要存紀錄，大家才看得到。`) +
  `<div class="card"><h3>今天、明天誰上班</h3>${dutyLine(d.duty.today, '今天')}${dutyLine(d.duty.tomorrow, '明天')}
    <div class="small" style="margin-top:8px">客人要訂明天的便當、要外送，先看明天有誰在。</div></div>
  <div class="grid"><div class="tile stat"><div class="k">我撥號</div><div class="v">${m.calls}</div><div class="s">目標 ${tg}</div></div><div class="tile stat"><div class="k">接通</div><div class="v">${m.connected}</div></div>
    <div class="tile stat good"><div class="k">有效商機</div><div class="v">${m.hot}</div></div><div class="tile stat"><div class="k">今日成交盒數</div><div class="v">${m.won_boxes}</div></div></div>
  <div class="card" id="prio"><h3>優先名單<span class="small" style="font-weight:400;margin-left:8px">A 級一律最前面 · 按「撥」，掛掉回來自動跳出記錄</span></h3>
    ${d.priority.length ? d.priority.slice(0, 25).map(l => leadRow(l, ` · <b style="color:var(--orange)">${esc(l.why)}</b>`)).join('') + (d.priority.length > 25 ? `<details class="fold" style="margin-top:10px"><summary>再看 ${d.priority.length - 25} 筆</summary><div class="in">${d.priority.slice(25).map(l => leadRow(l, ` · <b style="color:var(--orange)">${esc(l.why)}</b>`)).join('')}</div></details>` : '')
      : '<div class="muted">今天的都打過了，到「名單」找更多。</div>'}
    <div class="small" style="margin-top:10px">${aiToday ? `今天 AI 新開發 ${ai.rows.length} 筆已經排進來。` : `AI 每天早上自動找新名單（最近一次 ${md(ai.day || '')}，${ai.rows.length} 筆）。`}<a class="more" onclick="F='${aiToday ? 'ai_today' : 'ai_all'}';crmTab('list')">看 AI 名單</a></div></div>
  <details class="fold"><summary>全隊今天<small>${d.leads_today} 個單位</small></summary><div class="in"><div class="tbl"><table><tr><th>夥伴</th><th class="r">撥號</th><th class="r">接通</th><th class="r">商機</th><th class="r">成交盒</th></tr>
    ${d.team.map(x => `<tr><td>${esc(x.name)}</td><td class="r"><b>${x.calls}</b> / ${x.target}</td><td class="r">${x.connected}</td><td class="r">${x.hot}</td><td class="r">${x.won_boxes}</td></tr>`).join('')}</table></div></div></details>
  <details class="fold"><summary>今天誰打了哪些<small>${d.recent.length} 通</small></summary><div class="in">${d.recent.length ? d.recent.map(r => `<div class="row click" onclick="openLead(${r.lead_id})"><div>
     <div class="n">${esc(r.lead)}</div><div class="m">${r.at.slice(11, 16)} · ${esc(r.caller)} · ${esc(r.method)} · ${esc(r.result)}${r.reply ? ' · 「' + esc(r.reply) + '」' : ''}</div></div></div>`).join('') : '<div class="muted">今天還沒有紀錄。</div>'}</div></details>
  <div class="small">名單 ${d.stats.total || 0} 筆 · 未聯絡 ${d.stats.untouched || 0} · 商機中 ${d.stats.hot || 0} · 已成交 ${d.stats.won || 0} · 勿再聯絡 ${d.stats.dnc || 0}</div>`;
}
function crmScript() { $('#main').innerHTML = hero('開發', '電話話術。', '照這個講，不用背，看著念就好。') + `<div class="card script">${SCRIPT}</div>`; }
const SCRIPT = `<h3>什麼時候打</h3><table><tr><td><b>09:00–10:15</b></td><td>最好打。對方剛上班，我們還沒進午餐尖峰。</td></tr>
  <tr><td><b>14:00–15:30</b></td><td>最好打。對方午休完，我們晚餐備料前。</td></tr><tr><td><b>11:30–13:30</b></td><td>不要打。對方午休、我們出餐尖峰。</td></tr>
  <tr><td><b>17:00 後</b></td><td>不要打。機關、公司多半下班。</td></tr></table>
  <h3 style="margin-top:20px">開場</h3><p class="bub" style="display:block">您好，我是${esc(STORE.name)}的＿＿。想請問你們平常午餐，或開會、辦活動的便當，是哪位同仁統一安排呢？我們想先提供菜單，讓你們多一個附近的選擇。</p>
  <h3 style="margin-top:16px">找到窗口後</h3><p class="bub" style="display:block">您好，想請問你們比較常是平日一起訂，還是有活動才訂？近期有需要安排餐點的日期嗎？</p>
  <p class="muted">有近期需求就直接確認：日期、時間、數量、品項、地址、聯絡人、付款方式。要外送先看「今天、明天誰上班」。</p>
  <h3 style="margin-top:16px">對方說已有配合店家</h3><p class="bub" style="display:block">了解，不需要現在換。我們先當另一個選擇；之後需要換口味，或原本店家當天沒辦法接，再評估我們就好。方便讓我傳一份菜單給您留著嗎？</p>
  <h3 style="margin-top:16px">對方在忙</h3><p class="bub" style="display:block">好，不耽誤您。方便改哪個時間聯絡？不方便也沒關係，謝謝。</p>
  <h3 style="margin-top:16px">活動</h3><p class="bub" style="display:block">您好，我是${esc(STORE.name)}的＿＿。看到你們在＿月＿日有＿＿活動，想請問這場活動的工作人員、志工或演出團隊，餐點是由主辦統一安排，還是各團隊自己訂呢？</p>
  <h3 style="margin-top:16px">對方說不要再打</h3><p class="bub" style="display:block">好的，了解，之後不會再打擾您，謝謝。</p><p class="muted">掛掉後立刻按「設為勿再聯絡」。全隊都會看到，任何人都不能再打。</p>
  <p class="muted">試吃、團體回饋（例如養樂多）一律先問店長，不要自己答應。</p>`;

/* ---------- 名單 ---------- */
const FILTERS = [['', '全部'], ['ai_today', '今天 AI 新開發'], ['ai_all', 'AI 開發全部'], ['core', 'A 核心'], ['mine', '分給我'], ['today_not', '今天未撥'], ['today_done', '今天已撥'], ['i_called', '我打過'], ['team_called', '全隊打過'],
  ['open_today', '今天有營業'], ['follow_due', '今日應追蹤'], ['follow', '待追蹤'], ['hot', '商機中'], ['event', '有近期活動'], ['fixed', '固定午餐'], ['won', '已成交'], ['dnc', '勿再聯絡'], ['hours_unknown', '營業日未查']];
async function crmList() {
  $('#main').innerHTML = hero('開發', '開發名單。', '誰打過、什麼時候打的，大家都看得到。') + `<div class="card">
    <input id="q" placeholder="搜尋單位、電話、地址" oninput="debounceList()">
    <div class="pills" id="fchips"></div>
    <div class="g2" style="margin-top:10px"><select id="fcat" onchange="loadList()"><option value="">全部分類</option>${ME.categories.map(x => `<option>${esc(x)}</option>`).join('')}</select>
      <select id="farea" onchange="loadList()"><option value="">全部區域</option>${ME.areas.map(x => `<option>${esc(x)}</option>`).join('')}</select></div></div>
    <div class="card" id="list"></div>`;
  buildChips(); return loadList();
}
function buildChips() { $('#fchips').innerHTML = FILTERS.map(([k, n]) => `<button class="pill" aria-pressed="${k === F}" onclick="F='${k}';buildChips();loadList()">${n}</button>`).join(''); }
function debounceList() { clearTimeout(TIMER); TIMER = setTimeout(loadList, 250); }
async function loadList() {
  const p = new URLSearchParams({ q: ($('#q') || {}).value || '', f: F, category: ($('#fcat') || {}).value || '', area: ($('#farea') || {}).value || '' });
  LEADS = await api('/api/leads?' + p);
  $('#list').innerHTML = `<div class="small">${LEADS.length} 筆${LEADS.length >= 500 ? '（只列前 500，請再篩選）' : ''}</div>` + (LEADS.map(l => leadRow(l)).join('') || '<div class="muted">沒有符合的名單</div>');
}
function refreshBehind() { if (VIEW === 'crm') (SUB.crm === 'home' ? crmHome() : SUB.crm === 'list' ? loadList() : 0); }
async function openLead(id) {
  const [l, dy] = await Promise.all([api('/api/lead?id=' + id), api('/api/onduty')]); CUR = l;
  const tel = (l.phone || '').replace(/[^\d+#,]/g, ''), tel2 = (l.phone2 || '').replace(/[^\d+#,]/g, ''), last = l.calls.find(c => !c.voided);
  let h = `<div class="shead"><div><h3>${esc(l.name)}</h3><div>${tags(l)}</div></div><button class="btn gray sm" onclick="closeSheet()">關閉</button></div>`;
  if (l.dnc) h += `<div class="banner red">勿再聯絡：對方已明確拒絕，任何人都不要再打</div>`;
  else if (l.today_calls.length) h += `<div class="banner warn">今天 ${l.today_calls.map(c => esc(c.name) + ' ' + c.at.slice(11, 16)).join('、')} 已經打過了。最後結果：${esc(l.today_calls[0].result)}${l.today_calls[0].reply ? '「' + esc(l.today_calls[0].reply) + '」' : ''}</div>`;
  h += `<div class="card">${last ? `<div class="muted">最後聯絡：<b>${esc(last.caller)}</b> ${last.at.slice(0, 16)} · ${esc(last.result)}${last.reply ? ' · 「' + esc(last.reply) + '」' : ''}</div>` : '<div class="muted">還沒有人聯絡過</div>'}
    ${l.next_follow ? `<div class="muted">下次追蹤：<b>${esc(l.next_follow)}</b></div>` : ''}
    <div class="btns">${tel ? `<a class="btn green ${l.dnc ? 'gray' : ''}" href="tel:${tel}" onclick="callStart(${l.id},${jsq(l.name)})" ${l.dnc ? 'style="pointer-events:none;opacity:.4"' : ''}>撥 ${esc(l.phone)}</a>` : '<span class="muted">沒有電話</span>'}
      ${tel2 ? `<a class="btn sec" href="tel:${tel2}" onclick="callStart(${l.id},${jsq(l.name)})">撥 ${esc(l.phone2)}</a>` : ''}</div>
    <div class="small" style="margin-top:12px">今天上班：${dy.today.closed ? '店休' : dy.today.on.map(p => esc(p.name)).join('、') || '—'}｜明天上班：${dy.tomorrow.closed ? '店休' : dy.tomorrow.on.map(p => esc(p.name)).join('、') || '—'}</div></div>
  <details class="fold"><summary>單位資料</summary><div class="in"><table>${[['營業日', (l.open_days || '').length === 7 ? daysTxt(l.open_days) : ''], ['營業時間', l.hours], ['分類', l.category], ['區域', l.area], ['地址', l.address], ['建議窗口', l.contact_hint], ['切入情境', l.angle], ['資料狀態', l.data_status], ['類型', l.opp_type],
     ['盒數', l.boxes], ['每週天數', l.weekly_days], ['活動日期', l.event_date], ['備註', l.note], ['名單編號', l.code]].filter(x => x[1] !== null && x[1] !== '' && x[1] !== undefined)
     .map(([k, v]) => `<tr><th style="width:90px">${k}</th><td>${esc(v)}</td></tr>`).join('')}</table>
    <button class="btn sec sm" style="margin-top:12px" onclick="editLead()">修改資料</button></div></details>`;
  if (!l.dnc) h += `<div class="card"><h3>記一通</h3>
    <label>方式</label><div class="seg" id="mseg">${['電話', 'LINE', 'Email', '拜訪'].map((x, i) => `<button class="${i ? '' : 'on'}" onclick="seg(this)">${x}</button>`).join('')}</div>
    <label>有沒有接通／找到人</label><div class="seg" id="cseg"><button onclick="seg(this);resultOpts()">接通</button><button class="on" onclick="seg(this);resultOpts()">沒接</button></div>
    <div id="resBox" hidden><label>結果</label><select id="cres">${ME.statuses.filter(s => !['未聯絡', '未接'].includes(s)).map(s => `<option>${s}</option>`).join('')}</select>
    <label>對方說了什麼（一句話）</label><input id="creply" placeholder="例：下週三研習要 40 盒，再報價"></div>
    <div class="g2"><div><label>預估盒數</label><input id="cbox" inputmode="numeric" placeholder="選填"></div><div><label>下次追蹤日</label><input id="cnext" type="date"></div></div>
    <label>備註</label><input id="cnote" placeholder="選填">
    <button class="btn full" style="margin-top:18px" onclick="saveCall()">存這一通</button><div id="cerr" class="err"></div></div>`;
  h += `<div class="card"><h3>聯絡紀錄（${l.calls.length}）</h3>${l.calls.map(c => `<div class="row"><div style="${c.voided ? 'text-decoration:line-through;opacity:.5' : ''}">
     <div><b>${esc(c.caller)}</b> · ${c.at.slice(0, 16)} · ${esc(c.method)} · ${esc(c.result)}${c.boxes ? ' · ' + c.boxes + ' 盒' : ''}</div>
     ${c.reply ? `<div class="m">「${esc(c.reply)}」</div>` : ''}${c.note ? `<div class="m">${esc(c.note)}</div>` : ''}${c.next_follow ? `<div class="m">追蹤：${esc(c.next_follow)}</div>` : ''}${c.voided ? `<div class="m">已作廢：${esc(c.void_reason || '')}</div>` : ''}</div>
     ${ME.perms.admin && !c.voided ? `<button class="btn gray sm" onclick="voidCall(${c.id})">作廢</button>` : ''}</div>`).join('') || '<div class="muted">沒有紀錄</div>'}</div>`;
  h += l.dnc ? (ME.perms.admin ? `<button class="btn sec full" onclick="unDnc()">解除勿再聯絡（老闆）</button>` : '')
    : `<button class="btn red full" onclick="setDnc()">對方說不要再打 → 設為勿再聯絡</button>`;
  openSheet(h);
}
function resultOpts() { $('#resBox').hidden = segVal('cseg') !== '接通'; }
async function saveCall() {
  const conn = segVal('cseg') === '接通';
  try { await api('/api/call', { lead_id: CUR.id, method: segVal('mseg'), connected: conn, result: conn ? $('#cres').value : '未接', reply: conn ? $('#creply').value : '', boxes: $('#cbox').value, next_follow: $('#cnext').value, note: $('#cnote').value });
    await openLead(CUR.id); refreshBehind(); } catch (e) { $('#cerr').textContent = e.message; }
}
async function setDnc() { const r = prompt('對方怎麼說？（例：說不要再推銷）'); if (r === null) return; try { await api('/api/lead/dnc', { id: CUR.id, on: true, reason: r }); await openLead(CUR.id); refreshBehind(); } catch (e) { alert(e.message); } }
async function unDnc() { const r = prompt('解除原因（必填，會留紀錄）'); if (!r) return; try { await api('/api/lead/dnc', { id: CUR.id, on: false, reason: r }); await openLead(CUR.id); refreshBehind(); } catch (e) { alert(e.message); } }
async function voidCall(id) { const r = prompt('作廢原因（必填）'); if (!r) return; try { await api('/api/call/void', { id, reason: r }); await openLead(CUR.id); refreshBehind(); } catch (e) { alert(e.message); } }
const EDIT = [['name', '單位名稱'], ['phone', '電話'], ['phone2', '其他電話'], ['address', '地址'], ['open_days', '營業日（7 碼，週一到週日，1=開 0=休，例 1111100）'], ['hours', '營業時間'], ['category', '分類'], ['area', '區域'], ['contact_hint', '建議窗口'],
  ['angle', '切入情境'], ['priority', '分級（A/B/C，D＝排後面先不打）'], ['data_status', '資料狀態'], ['opp_type', '類型（固定午餐/活動/其他）'], ['boxes', '盒數'], ['weekly_days', '每週天數'], ['event_date', '活動日期'], ['next_follow', '下次追蹤日'], ['note', '備註']];
function editLead() {
  const l = CUR;
  openSheet(`<div class="shead"><h3>修改：${esc(l.name)}</h3><button class="btn gray sm" onclick="openLead(${l.id})">返回</button></div>
   <div class="card">${EDIT.map(([k, n]) => `<label>${n}</label>${k === 'note' ? `<textarea id="e_${k}" rows="3">${esc(l[k] ?? '')}</textarea>` : `<input id="e_${k}" value="${esc(l[k] ?? '')}" ${['event_date', 'next_follow'].includes(k) ? 'type="date"' : ''}>`}`).join('')}
   <button class="btn full" style="margin-top:18px" onclick="saveLead()">儲存</button><div id="eerr" class="err"></div></div>`);
}
async function saveLead() {
  const f = {}; EDIT.forEach(([k]) => { const v = $('#e_' + k).value; if (String(CUR[k] ?? '') !== v) f[k] = v; });
  try { await api('/api/lead/save', { id: CUR.id, version: CUR.version, fields: f }); await openLead(CUR.id); refreshBehind(); } catch (e) { $('#eerr').textContent = e.message; }
}
