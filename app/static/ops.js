/* 營運頁：班表（排休、廁所輪值）、記帳（店長記、老闆核銷、同步帳務）、外送（看板、我的外送、報表） */

/* ═════════ 班表 ═════════ */
let SM = todayStr().slice(0, 7), SCH = null;
LOAD.sched = async function () {
  SCH = await api('/api/schedule?month=' + SM);
  const [y, m] = SM.split('-').map(Number), first = new Date(y, m - 1, 1).getDay(), td = todayStr();
  const last = SCH.days.length, tail = (7 - (first + last) % 7) % 7;
  let h = `<div class="calbar"><h1 class="ttl">${y} 年 ${m} 月</h1><div class="paddles"><button class="paddle" aria-label="上個月" onclick="schMonth(-1)">‹</button>
    <button class="today" onclick="SM=todayStr().slice(0,7);LOAD.sched()">今天</button><button class="paddle" aria-label="下個月" onclick="schMonth(1)">›</button></div></div>
    <p class="sub">${SCH.can_edit ? '點日期就能排休、排廁所輪值。排好的休假，打卡和今日出勤會自動標「排休」。' : '誰哪天排休、誰洗廁所，大家都看得到。要排休先跟店長說。'}</p>`;
  if (SCH.mine.length) h += `<div class="banner ok">你這個月排休：${SCH.mine.map(d => md(d) + '（' + wkOf(d) + '）').join('、')}</div>`;
  h += `<div class="calwrap"><div class="cal">${'日一二三四五六'.split('').map(x => `<div class="h">${x}</div>`).join('')}${'<div class="d blank"></div>'.repeat(first)}
    ${SCH.days.map(x => `<div class="d ${x.closed ? 'closed' : ''} ${x.day === td ? 'today' : ''} ${SCH.can_edit ? 'edit' : ''}" ${SCH.can_edit ? `onclick="schEdit('${x.day}')"` : ''}>
      <div class="dn"><span>${+x.day.slice(8)}</span></div>${x.closed ? `<span class="duty">${esc(x.closed)}</span>` : ''}
      ${x.off.map(o => `<span class="off ${o.user_id === ME.id ? 'me' : ''}" title="${esc(o.note || '')}">${esc(o.name)} 休</span>`).join('')}
      ${x.duty.map(o => `<span class="duty">${esc(o.kind)}：${esc(o.name)}</span>`).join('')}
      ${SCH.can_edit && x.work && !x.closed ? `<span class="duty" title="${esc(x.work.join('、'))}" style="${x.work.length < 3 ? 'background:#fde2e2;color:#b42318' : x.work.length < 4 ? 'background:#fff4d6;color:#8a5a00' : ''}">上班 ${x.work.length} 人</span>` : ''}</div>`).join('')}${'<div class="d blank"></div>'.repeat(tail)}</div></div>`;
  const off = SCH.days.flatMap(x => x.off.map(o => ({ day: x.day, ...o })));
  h += `<h2>這個月排休。<span class="g">誰哪天休，一眼看清楚。</span></h2><div class="card">${off.map(o => `<div class="row"><div><div class="n">${md(o.day)}（${wkOf(o.day)}）${esc(o.name)}</div>${o.note ? `<div class="m">${esc(o.note)}</div>` : ''}</div></div>`).join('') || '<div class="muted">這個月還沒有人排休。</div>'}</div>`;
  $('#main').innerHTML = h;
};
function schMonth(n) { const [y, m] = SM.split('-').map(Number), d = new Date(y, m - 1 + n, 1); SM = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'); LOAD.sched(); }
function schEdit(day) {
  const x = SCH.days.find(d => d.day === day), offIds = x.off.map(o => o.user_id), toilet = (x.duty.find(o => o.kind === '廁所') || {}).user_id;
  openSheet(`<div class="shead"><h3>${md(day)}（${wkOf(day)}）</h3><button class="btn gray sm" onclick="closeSheet();LOAD.sched()">完成</button></div>
    ${x.closed ? `<div class="banner warn">這天店休：${esc(x.closed)}</div>` : ''}
    <div class="card"><h3>誰排休</h3>${SCH.people.map(p => `<label class="chk"><input type="checkbox" ${offIds.includes(p.id) ? 'checked' : ''} onchange="schOff('${day}',${p.id},this.checked)"> ${esc(p.name)}</label>`).join('')}
      <label>備註（選填，例：家裡有事）</label><input id="sch_note" placeholder="勾選前先寫，會一起存"></div>
    <div class="card"><h3>廁所輪值</h3><select onchange="schDuty('${day}',this.value)"><option value="">（沒排）</option>${SCH.people.map(p => `<option value="${p.id}" ${p.id === toilet ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select>
      <div class="small" style="margin-top:8px">輪到的人下班前把廁所洗好。</div></div><div id="sch_m"></div>`);
}
async function schOff(day, uid, on, force) {
  const body = { day, user_id: uid, on, note: ($('#sch_note') || {}).value || '', force: !!force };
  try {
    const r = await api('/api/schedule/off', body);
    if (r.warn && r.warn.length) $('#sch_m').innerHTML = r.warn.map(w => `<div class="banner warn" style="margin-top:8px">${esc(w)}</div>`).join(''); else msgOk('#sch_m');
  } catch (e) {
    // 老闆 10/12：一天只能一個人排休；老闆本人確認後可以強制
    if (ME.perms.admin && !force && /一天只能一個人排休/.test(e.message) && confirm(e.message + '\n\n還是要排嗎？')) return schOff(day, uid, on, true);
    msgOk('#sch_m', e); if (on) LOAD.sched().then(() => schEdit(day));
  }
}
async function schDuty(day, uid) { try { await api('/api/schedule/duty', { day, kind: '廁所', user_id: uid || null }); msgOk('#sch_m'); } catch (e) { msgOk('#sch_m', e); } }

/* ═════════ 記帳 ═════════ */
let FD = todayStr(), FIN = null, RPHOTO = null, EPHOTO = null;
SUB.fin = 'day';
LOAD.fin = async function () {
  const P = ME.perms;
  localNav('記帳', [['day', '記今天'], ...(P.admin ? [['review', '核銷', ME.fin_pending || 0]] : []), ['month', '本月']], SUB.fin, 'finTab');
  return ({ day: finDay, review: finReview, month: finMonth })[SUB.fin]();
};
function finTab(k) { SUB.fin = k; LOAD.fin(); }
const ST = s => `<span class="tag ${s === '已核銷' || s === '已入帳' ? 't-ok' : s === '退回' ? 't-red' : 't-warn'}">${s}</span>`;
async function finDay() {
  const d = FIN = await api('/api/fin/day?day=' + FD), r = d.rev, admin = ME.perms.admin;
  RPHOTO = null; EPHOTO = null;
  let h = hero('記帳', `${md(FD)}（${wkOf(FD)}）的帳。`, admin ? '營收記了就直接進股東帳務；支出你記的直接算核銷，店長記的等你核銷。' : '打烊後記今天的營收、拍日結單，記了就自動進帳務。店裡花的錢一筆一筆記、拍發票或收據，老闆核銷後進帳務。');
  h += `<div class="btns" style="margin:0 0 18px;align-items:center"><input type="date" value="${FD}" min="${d.start}" max="${todayStr()}" style="width:auto" onchange="FD=this.value;LOAD.fin()">
    ${FD > d.start ? `<button class="btn gray sm" onclick="FD=addDays(FD,-1);LOAD.fin()">‹ 前一天</button>` : ''}${FD < todayStr() ? `<button class="btn gray sm" onclick="FD=addDays(FD,1);LOAD.fin()">後一天 ›</button>` : ''}</div>`;
  if (d.closed) h += `<div class="banner warn">這天店休（${esc(d.closed)}）。有花錢一樣要記。</div>`;
  // 營收
  h += `<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;gap:10px"><h3 style="margin:0">今天營收</h3>${r ? ST(r.status) : '<span class="tag">還沒記</span>'}</div>`;
  if (r && r.status === '退回') h += `<div class="banner red" style="margin-top:12px">老闆退回：${esc(r.verify_note || '')}　改好再存一次。</div>`;
  if (r) h += `<div class="grid" style="margin-top:14px"><div class="tile stat" style="background:var(--bg)"><div class="k">應收（現金＋儲值＋電子）</div><div class="v">${fmt(r.total)}</div><div class="s">${r.orders ?? '—'} 單 · ${r.boxes ?? '—'} 個便當</div></div>
      <div class="tile stat" style="background:var(--bg)"><div class="k">打烊抽屜現金</div><div class="v">${r.drawer != null ? fmt(r.drawer) : '—'}</div>
      <div class="s">${d.expect_drawer != null ? '照帳應有 ' + fmt(d.expect_drawer) + (r.drawer != null ? '，差 ' + fmt(r.drawer - d.expect_drawer) : '') : '前一天沒點算，算不出應有多少'}</div></div></div>
      ${r.photo ? `<img src="/api/fin/photo?kind=rev&day=${FD}&t=${encodeURIComponent(r.updated || '')}" alt="日結單" style="max-height:220px;border-radius:12px;cursor:zoom-in" onclick="zoom(this.src)">` : ''}`;
  const lock = r && r.status === '已核銷' && !admin;
  if (!lock) h += `<details class="fold" style="background:var(--bg);margin-top:14px" ${r ? '' : 'open'}><summary>${r ? '修改營收' : '記今天的營收'}</summary><div class="in">
      <div class="small">照 POS 日結單（營業總表）上的數字填，每一格下面寫了是日結單的哪一行；空白的填 0。填完「應收」要跟日結單的「應收金額」一樣，不一樣就是有填錯。</div>
      <div class="g3"><div><label>現金</label><input id="f_cash" inputmode="numeric" placeholder="【付款方式】1_現金" value="${r ? r.cash ?? '' : ''}" oninput="finTotal()"></div>
        <div><label>儲值金</label><input id="f_stored" inputmode="numeric" placeholder="【Woo霸卡相關】儲值消費" value="${r ? r.stored ?? '' : ''}" oninput="finTotal()"></div>
        <div><label>電子票證（悠遊卡等）</label><input id="f_eticket" inputmode="numeric" placeholder="【付款方式】電子票證" value="${r ? r.eticket ?? '' : ''}" oninput="finTotal()"></div>
        <div><label>單數</label><input id="f_orders" inputmode="numeric" placeholder="有效單據" value="${r ? r.orders ?? '' : ''}"></div>
        <div><label>${STORE.unit}數</label><input id="f_boxes" inputmode="numeric" placeholder="今天賣了幾${STORE.unit}" value="${r ? r.boxes ?? '' : ''}"></div>
        <div><label>應收（自動算）</label><input id="f_total" disabled></div></div>
      <div class="g3"><div><label>餐券、禮券（算在現金裡，抽屜沒有錢）</label><input id="f_voucher" inputmode="numeric" placeholder="今天收的餐券金額，沒有填 0" value="${r ? r.voucher || '' : ''}"></div>
        <div><label>客人儲值 Woo霸卡（現金進抽屜，不算營收）</label><input id="f_topup" inputmode="numeric" placeholder="【Woo霸卡儲值】" value="${r ? r.topup || '' : ''}"></div>
        <div><label>打烊抽屜現金（點算）</label><input id="f_drawer" inputmode="numeric" placeholder="抽屜全部現金（含找零金）" value="${r && r.drawer != null ? r.drawer : ''}"></div></div>
      <label>備註</label><input id="f_note" value="${r ? esc(r.note || '') : ''}" placeholder="例：招待 2 個、團訂匯款另外收">
      <label>日結單照片${r && r.photo ? '（要換才拍）' : '（一定要拍）'}</label><input type="file" accept="image/*" capture="environment" onchange="readPhoto(this.files[0]).then(p=>{RPHOTO=p;$('#f_ph').textContent='已選一張照片'}).catch(e=>alert(e.message))">
      <div class="small" id="f_ph"></div>
      ${r && r.status !== '退回' ? `<label>為什麼要改（必填）</label><input id="f_why" placeholder="例：現金打錯、漏了一張單">` : ''}
      <button class="btn" style="margin-top:16px" onclick="saveRev()">存檔，進帳務</button><div id="f_m"></div></div></details>`;
  if (d.log && d.log.length) h += `<div class="small" style="margin-top:10px">修改紀錄：${d.log.map(l => `${md(l.at)} ${hm(l.at)} ${esc(l.name || '')}「${esc(l.reason || '')}」`).join('；')}</div>`;
  h += `</div>`;
  // 支出
  const sum = d.exps.reduce((a, e) => a + e.amount, 0);
  h += `<div class="card"><div style="display:flex;justify-content:space-between;align-items:center"><h3 style="margin:0">店裡花的錢</h3><span class="small">${d.exps.length} 筆 · ${fmt(sum)} 元</span></div>
    ${d.exps.map(e => `<div class="row"><div style="min-width:0"><div class="n">${esc(e.item)} <span class="small">${esc(e.category)}${e.vendor ? ' · ' + esc(e.vendor) : ''}</span></div>
      <div class="m">${e.note ? esc(e.note) + ' · ' : ''}${ST(e.status)}${e.status === '退回' ? ' ' + esc(e.verify_note || '') : ''}</div></div>
      <div style="display:flex;gap:8px;align-items:center">${e.photo ? `<img src="/api/fin/photo?kind=exp&id=${e.id}&t=${encodeURIComponent(e.updated || '')}" alt="" style="width:44px;height:44px;object-fit:cover;border-radius:8px;cursor:zoom-in" onclick="zoom(this.src)">` : ''}
      <span class="tag">${e.pay === '零用金' ? '零用金' : '營收現金'}</span><b class="num">${fmt(e.amount)}</b>${e.status !== '已核銷' || admin ? `<button class="btn gray sm" onclick="expForm(${e.id})">改</button>` : ''}</div></div>`).join('') || '<div class="muted" style="margin-top:10px">今天還沒有記支出。</div>'}
    ${FD < d.exp_start ? `<div class="small" style="margin-top:12px">${md(FD)} 的支出已經記在帳務系統裡，系統從 ${md(d.exp_start)} 開始記。</div>` : `<button class="btn sec" style="margin-top:14px" onclick="expForm()">＋ 記一筆支出</button>`}</div>`;
  const pt = d.petty;
  h += `<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;gap:10px"><h3 style="margin:0">零用金</h3><b class="num">剩 ${fmt(pt.left)}</b></div>
    <div class="small" style="margin-top:6px">老闆撥了 ${fmt(pt.given)}，花了 ${fmt(pt.spent)}。${FD >= d.petty_from ? '店裡花費從零用金出，記支出時選「零用金」；營收現金不要動。' : ''}</div>
    ${admin ? `<details class="fold" style="background:var(--bg);margin-top:12px"><summary>撥零用金給店長</summary><div class="in"><div class="g2"><div><label>金額</label><input id="pt_a" inputmode="numeric" value="5000"></div><div><label>備註</label><input id="pt_n" placeholder="例：補到 5,000"></div></div>
      <button class="btn" style="margin-top:12px" onclick="pettyAdd()">撥出去</button><div id="pt_m"></div>
      ${pt.rows.map(x => `<div class="row"><div><div class="n">${md(x.day)} 撥 ${fmt(x.amount)}</div><div class="m">${esc(x.note || '')}</div></div><button class="btn gray sm" onclick="pettyDel(${x.id})">刪除</button></div>`).join('')}</div></details>` : ''}
    </div>`;
  h += `<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;gap:10px"><h3 style="margin:0">其他收入</h3>${pt.pending ? `<b class="num">待存 ${fmt(pt.pending)}</b>` : ''}</div>
    <div class="small" style="margin-top:6px">不是 POS 收的錢（例如廢油回收）。收到記一筆，現金另外收好、<b>不要放進收銀抽屜或零用金</b>；存進銀行那天按「已存銀行」。股東帳會列成「其他收入」。</div>
    ${(pt.inc_rows || []).map(x => `<div class="row"><div><div class="n">${md(x.day)} 收 ${fmt(x.amount)}・${x.deposited ? `<span class="ok">${md(x.deposited)} 已存銀行</span>` : '<b>待存銀行</b>'}</div><div class="m">${esc(x.note || '')}${x.name ? '・' + esc(x.name) + ' 記' : ''}</div></div>
      <div style="display:flex;gap:6px">${x.deposited ? (admin ? `<button class="btn gray sm" onclick="incDep(${x.id},1)">改回待存</button>` : '') : `<button class="btn sm" onclick="incDep(${x.id})">${FD === todayStr() ? '今天' : md(FD)}已存銀行</button>`}
      ${!x.deposited && (admin || x.created_by === ME.id) ? `<button class="btn gray sm" onclick="pettyDel(${x.id})">刪除</button>` : ''}</div></div>`).join('')}
    <details class="fold" style="background:var(--bg);margin-top:12px"><summary>＋ 記一筆其他收入</summary><div class="in">
      <div class="small">日期是上面選的 ${md(FD)}。</div>
      <div class="g2" style="margin-top:8px"><div><label>金額</label><input id="pi_a" inputmode="numeric" placeholder="例：1600"></div><div><label>是什麼</label><input id="pi_n" value="廢油回收"></div></div>
      <button class="btn" style="margin-top:12px" onclick="pettyInc()">記下來</button><div id="pi_m"></div></div></details></div>`;
  h += `<div class="card"><h3 style="margin:0">營收現金收走／存銀行</h3><div class="small" style="margin-top:6px">抽屜裡固定留找零金 ${fmt(d.float)}（只換零錢）。營收現金拿去存銀行或交給老闆時記一筆，抽屜應有金額才會對。</div>
    ${d.cash_out.map(x => `<div class="row"><div><div class="n">${esc(x.dest)} ${fmt(x.amount)}</div><div class="m">${esc(x.note || '')}</div></div><button class="btn gray sm" onclick="cashOutDel(${x.id})">刪除</button></div>`).join('')}
    <div class="g3" style="margin-top:8px"><div><label>金額</label><input id="co_a" inputmode="numeric"></div><div><label>去哪裡</label><select id="co_d"><option>存銀行</option><option>交老闆</option></select></div><div><label>備註</label><input id="co_n"></div></div>
    <button class="btn sec" style="margin-top:12px" onclick="cashOut()">記一筆</button><div id="co_m"></div></div>`;
  h += `<div class="small">店裡花的錢一筆一筆記、拍收據（老闆核銷後進帳務）。總部貨款、房租、薪資不用記。</div>`;
  $('#main').innerHTML = h; finTotal();
}
function finTotal() { const g = id => +(($('#' + id) || {}).value || 0); const t = $('#f_total'); if (t) t.value = fmt(g('f_cash') + g('f_stored') + g('f_eticket')); }
async function saveRev() {
  const v = id => $('#' + id).value;
  try { await api('/api/fin/rev', { day: FD, cash: v('f_cash'), stored: v('f_stored'), eticket: v('f_eticket'), orders: v('f_orders'), boxes: v('f_boxes'), voucher: v('f_voucher'), topup: v('f_topup'), drawer: v('f_drawer'), note: v('f_note'), photo: RPHOTO, reason: ($('#f_why') || {}).value || '' });
    await refreshBadges(); LOAD.fin(); } catch (e) { msgOk('#f_m', e); }
}
function expForm(id) {
  const e = id ? FIN.exps.find(x => x.id === id) : {}; EPHOTO = null;
  openSheet(`<div class="shead"><h3>${id ? '修改支出' : '記一筆支出'}</h3><button class="btn gray sm" onclick="closeSheet()">取消</button></div><div class="card">
    <label>類別</label><select id="x_cat">${FIN.cats.map(c => `<option ${c === e.category ? 'selected' : ''}>${c}</option>`).join('')}</select>
    <label>買了什麼</label><input id="x_item" value="${esc(e.item || '')}" placeholder="例：沙拉油、垃圾袋、加油">
    <div class="g2"><div><label>金額</label><input id="x_amt" inputmode="numeric" value="${e.amount || ''}"></div><div><label>店家（選填）</label><input id="x_vendor" value="${esc(e.vendor || '')}" placeholder="例：全聯"></div></div>
    <label>從哪裡付</label><div class="seg" id="x_pay">${['零用金', '店內現金'].map(p => `<button class="${(e.pay || (FD >= FIN.petty_from ? '零用金' : '店內現金')) === p ? 'on' : ''}" onclick="seg(this)">${p === '店內現金' ? '營收現金' : p}</button>`).join('')}</div>
    <label>備註（選填）</label><input id="x_note" value="${esc(e.note || '')}">
    <label>發票、收據或明細照片${id ? '（要換才拍）' : '（一定要拍）'}</label><input type="file" accept="image/*" capture="environment" onchange="readPhoto(this.files[0]).then(p=>{EPHOTO=p;$('#x_ph').textContent='已選一張照片'}).catch(e=>alert(e.message))">
    <div class="small" id="x_ph"></div>
    <div class="btns"><button class="btn" onclick="saveExp(${id || 0})">存檔</button>${id ? `<button class="btn gray" onclick="delExp(${id})">刪除</button>` : ''}</div><div id="x_m"></div></div>`);
}
async function saveExp(id) {
  try { await api('/api/fin/exp', { id: id || null, day: FD, category: $('#x_cat').value, item: $('#x_item').value, amount: $('#x_amt').value, vendor: $('#x_vendor').value, note: $('#x_note').value, photo: EPHOTO, pay: segVal('x_pay') === '營收現金' ? '店內現金' : '零用金' });
    closeSheet(); await refreshBadges(); LOAD.fin(); } catch (e) { msgOk('#x_m', e); }
}
async function pettyAdd() { try { await api('/api/fin/petty', { day: FD, amount: $('#pt_a').value, note: $('#pt_n').value }); LOAD.fin(); } catch (e) { msgOk('#pt_m', e); } }
async function pettyDel(id) { if (confirm('刪除這筆？')) { await api('/api/fin/petty', { remove: id }); LOAD.fin(); } }
async function incDep(id, undo) { if (undo ? confirm('改回「待存銀行」？') : confirm(`這筆在 ${md(FD)} 存進銀行了？`)) { await api('/api/fin/petty', { deposit: id, day: FD, undo: undo ? 1 : 0 }); LOAD.fin(); } }
async function pettyInc() { try { await api('/api/fin/petty', { kind: '收入', day: FD, amount: $('#pi_a').value, note: $('#pi_n').value }); LOAD.fin(); } catch (e) { msgOk('#pi_m', e); } }
async function cashOut() { try { await api('/api/fin/cashout', { day: FD, amount: $('#co_a').value, dest: $('#co_d').value, note: $('#co_n').value }); LOAD.fin(); } catch (e) { msgOk('#co_m', e); } }
async function cashOutDel(id) { if (confirm('刪除這筆？')) { await api('/api/fin/cashout', { remove: id }); LOAD.fin(); } }
async function delExp(id) { if (!confirm('刪除這筆支出？')) return; try { await api('/api/fin/exp/delete', { id }); closeSheet(); LOAD.fin(); } catch (e) { alert(e.message); } }
async function finReview() {
  const d = await api('/api/fin/list?month=' + todayStr().slice(0, 7)), sy = d.sync;   // 待核銷不分月份全部列
  let h = hero('核銷', '店裡花的錢，你來核銷。', '支出核銷後自動進帳務系統，股東網站跟著更新。營收店長記了就直接入帳，下面看得到最近幾天，不對可以退回。看照片對數字，不對就退回、寫原因。');
  if (sy) h += `<div class="banner ${sy.ok ? 'ok' : 'red'}">帳務同步：${md(sy.at)} ${hm(sy.at)} ${sy.ok ? '成功' : '失敗'}${sy.ok ? '' : '：' + esc(sy.msg.slice(-120))}</div>`;
  h += d.pending.map(x => { const r = x.rev, ex = x.exps.filter(e => e.status === '待核銷');
    return `<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap"><h3 style="margin:0">${md(x.day)}（${wkOf(x.day)}）</h3>
      ${x.day.slice(0, 7) !== todayStr().slice(0, 7) ? '<span class="tag t-warn">上個月的</span>' : ''}<button class="btn green sm" onclick="verify('all','${x.day}',0,true)">這天全部核銷</button></div>
      ${false ? `<div class="row"><div><div class="n">營收 應收 ${fmt(r.total)}</div><div class="m">現金 ${fmt(r.cash)} · 儲值 ${fmt(r.stored)} · 電子 ${fmt(r.eticket)} · 餐券 ${fmt(r.voucher)} · 儲值卡 ${fmt(r.topup)} · ${r.orders ?? '—'} 單 · ${r.boxes ?? '—'} 個 · 抽屜 ${r.drawer != null ? fmt(r.drawer) : '—'}${r.note ? ' · ' + esc(r.note) : ''}</div></div>
        <div style="display:flex;gap:6px;align-items:center">${r.photo ? `<img src="/api/fin/photo?kind=rev&day=${x.day}" alt="" style="width:52px;height:52px;object-fit:cover;border-radius:8px;cursor:zoom-in" onclick="zoom(this.src)">` : ''}
        <button class="btn green sm" onclick="verify('rev','${x.day}',0,true)">核銷</button><button class="btn gray sm" onclick="verify('rev','${x.day}',0,false)">退回</button></div></div>` : ''}
      ${ex.map(e => `<div class="row"><div><div class="n">${esc(e.item)} ${fmt(e.amount)}</div><div class="m">${esc(e.category)}${e.vendor ? ' · ' + esc(e.vendor) : ''}${e.note ? ' · ' + esc(e.note) : ''}</div></div>
        <div style="display:flex;gap:6px;align-items:center">${e.photo ? `<img src="/api/fin/photo?kind=exp&id=${e.id}&t=${encodeURIComponent(e.updated || '')}" alt="" style="width:52px;height:52px;object-fit:cover;border-radius:8px;cursor:zoom-in" onclick="zoom(this.src)">` : ''}
        <button class="btn green sm" onclick="verify('exp','${x.day}',${e.id},true)">核銷</button><button class="btn gray sm" onclick="verify('exp','${x.day}',${e.id},false)">退回</button></div></div>`).join('')}</div>`; }).join('')
    || '<div class="card muted">沒有等你核銷的帳。</div>';
  if (d.recent_rev.length) h += `<h2>最近的營收（已入帳）</h2><div class="card">${d.recent_rev.map(r => `<div class="row"><div><div class="n">${md(r.day)}（${wkOf(r.day)}）應收 ${fmt(r.total)} ${ST(r.status)}</div>
      <div class="m">現金 ${fmt(r.cash)} · 儲值 ${fmt(r.stored)} · 電子 ${fmt(r.eticket)} · 餐券 ${fmt(r.voucher)} · ${r.orders ?? '—'} 單 · ${r.boxes ?? '—'} 個 · 抽屜 ${r.drawer != null ? fmt(r.drawer) : '—'}</div></div>
      <div style="display:flex;gap:6px;align-items:center">${r.photo ? `<img src="/api/fin/photo?kind=rev&day=${r.day}" alt="" style="width:52px;height:52px;object-fit:cover;border-radius:8px;cursor:zoom-in" onclick="zoom(this.src)">` : ''}
      ${r.status !== '退回' ? `<button class="btn gray sm" onclick="verify('rev','${r.day}',0,false)">退回</button>` : ''}</div></div>`).join('')}</div>`;
  h += `<div class="btns"><button class="btn sec sm" onclick="api('/api/fin/sync',{}).then(()=>alert('已開始同步，幾秒後重新整理看結果'))">重新同步帳務系統</button></div>`;
  $('#main').innerHTML = h;
}
async function verify(kind, day, id, approve) {
  const note = approve ? '' : prompt('退回原因（店長會收到通知）'); if (!approve && !note) return;
  try { await api('/api/fin/verify', { kind, day, id, approve, note }); await refreshBadges(); LOAD.fin(); } catch (e) { alert(e.message); }
}
let FM = todayStr().slice(0, 7);
async function finMonth() {
  const d = await api('/api/fin/list?month=' + FM);
  const rev = d.days.reduce((a, x) => a + (x.rev ? x.rev.total : 0), 0), exp = d.days.reduce((a, x) => a + x.exps.reduce((b, e) => b + e.amount, 0), 0);
  let h = hero('本月', `${+FM.slice(5)} 月記帳。`, '系統記的部分（10/5 起）。之前的帳在帳務系統裡。');
  h += `<div class="btns" style="margin:0 0 16px"><input type="month" value="${FM}" style="width:auto" onchange="FM=this.value;LOAD.fin()"></div>
    <div class="grid"><div class="tile stat"><div class="k">營收（應收）</div><div class="v">${fmt(rev)}</div></div><div class="tile stat"><div class="k">店內支出</div><div class="v">${fmt(exp)}</div></div>
    <div class="tile stat"><div class="k">記了幾天</div><div class="v">${d.days.filter(x => x.rev).length}</div></div><div class="tile stat ${d.pending.length ? 'warn' : ''}"><div class="k">等核銷</div><div class="v">${d.pending.length} 天</div></div></div>
    <div class="card"><div class="tbl"><table><tr><th>日期</th><th class="r">應收</th><th class="r">${STORE.unit}數</th><th class="r">支出</th><th>狀態</th></tr>
    ${d.days.map(x => `<tr class="click" onclick="FD='${x.day}';finTab('day')"><td>${md(x.day)}（${wkOf(x.day)}）</td><td class="r">${x.rev ? fmt(x.rev.total) : '—'}</td><td class="r">${x.rev && x.rev.boxes != null ? x.rev.boxes : '—'}</td>
      <td class="r">${fmt(x.exps.reduce((b, e) => b + e.amount, 0))}</td><td>${x.rev ? ST(x.rev.status) : '<span class="tag">營收沒記</span>'}${x.exps.some(e => e.status !== '已核銷') ? '<span class="tag t-warn">支出待核</span>' : ''}</td></tr>`).join('') || '<tr><td colspan="5" class="muted">這個月還沒有記帳</td></tr>'}</table></div></div>`;
  $('#main').innerHTML = h;
}

/* ═════════ 外送（照 Uber Eats／foodpanda 的做法） ═════════ */
let DD = todayStr(), DV = null, DPHOTO = null;
SUB.deliv = null;
LOAD.deliv = async function () {
  if (!SUB.deliv) SUB.deliv = (ME.perms.rider || ME.my_deliveries) && !ME.perms.fin ? 'mine' : 'board';
  DV = await api('/api/deliveries?day=' + DD);
  localNav('外送', [['board', '看板'], ['mine', '我的外送', DV.mine.filter(r => r.status !== '已送達').length], ['report', '今日報表']], SUB.deliv, 'delivTab', ['開外送單', 'delivForm()']);
  return ({ board: delivBoard, mine: delivMine, report: delivReport })[SUB.deliv]();
};
function delivTab(k) { SUB.deliv = k; LOAD.deliv(); }
const NEXT = { '新單': ['製作中', '開始做'], '製作中': ['已出餐', '已出餐（做好了）'] };
function lateTag(r) {
  if (r.cancelled) return '<span class="tag">已取消</span>';
  if (r.late_min == null) return '';
  if (r.status === '已送達') return r.late_min <= 0 ? '<span class="tag t-ok">準時</span>' : `<span class="tag t-red">晚 ${r.late_min} 分</span>`;
  if (r.late_min > 0) return `<span class="tag t-red">已經晚 ${r.late_min} 分</span>`;
  if (r.late_min > -15) return `<span class="tag t-warn">${-r.late_min} 分後要到</span>`;
  return '';
}
function steps(r) { const i = DV.states.indexOf(r.status); return `<div class="steps">${DV.states.map((s, k) => `<i class="${k <= i ? 'on' : ''}" title="${s}"></i>`).join('')}</div>`; }
function dcard(r, mine) {
  const late = r.late_min != null && r.late_min > 0 && r.status !== '已送達' && !r.cancelled;
  return `<div class="dcard st-${r.status} ${late ? 'late' : ''}" ${r.cancelled ? 'style="opacity:.45"' : ''}>
    <div class="top"><span class="due">${r.due || '—'}</span><span class="small">#${r.seq}${r.part ? ' · ' + esc(r.part) : ''} · ${esc(r.source || '')}</span></div>
    <div class="n" style="margin-top:4px">${esc(r.customer)}</div>
    <div class="small">${r.boxes || '?'} 個${r.bags ? ' · ' + r.bags + ' 袋' : ''} · ${esc(r.address)}</div>
    ${steps(r)}
    <div>${'<span class="tag">' + esc(r.status) + '</span>'}${lateTag(r)}${r.rider ? `<span class="tag t-blue">${esc(r.rider)}${r.waiting_accept ? ' · 等接受' : ''}</span>` : '<span class="tag t-warn">還沒派人</span>'}
      ${r.collect ? `<span class="tag t-warn">收現 ${fmt(r.collect)}</span>` : `<span class="tag">${esc(r.pay || '')}</span>`}${r.receipt ? '<span class="tag">要收據</span>' : ''}
      ${r.issue ? `<span class="tag t-red">${esc(r.issue)}</span>` : ''}</div>
    <div class="btns" style="margin-top:10px"><button class="btn gray sm" onclick="delivOpen(${r.id})">${mine ? '打開' : '詳細／操作'}</button>
      ${!mine && NEXT[r.status] && !r.cancelled ? `<button class="btn sm" onclick="dStatus(${r.id},'${NEXT[r.status][0]}')">${NEXT[r.status][1]}</button>` : ''}</div></div>`;
}
async function delivBoard() {
  const s = DV.stats;
  let h = hero('外送', `${md(DD)} 外送看板。`, '開單 → 派給外送夥伴（夥伴按接受）→ 廚房做好按「已出餐」→ 夥伴核對取餐 → 送達拍照、收錢。');
  h += `<div class="btns" style="margin:0 0 16px"><input type="date" value="${DD}" style="width:auto" onchange="DD=this.value;LOAD.deliv()"></div>`;
  h += `<div class="grid"><div class="tile stat"><div class="k">今天外送</div><div class="v">${s.n} 單</div><div class="s">${s.boxes} 個便當</div></div>
    <div class="tile stat good"><div class="k">已送達</div><div class="v">${s.done}</div><div class="s">準時 ${s.done ? Math.round(s.ontime * 100 / s.done) + '%' : '—'}</div></div>
    <div class="tile stat ${s.issues ? 'warn' : ''}"><div class="k">有問題</div><div class="v">${s.issues}</div></div>
    <div class="tile stat ${s.cash_due ? 'warn' : ''}"><div class="k">現金待繳回</div><div class="v">${fmt(s.cash_due)}</div></div></div>`;
  h += `<div class="card"><h3>外送夥伴</h3>${DV.riders.filter(u => u.rider || u.n).map(u => `<div class="row"><div><div class="n">${esc(u.name)} <span class="tag ${u.state === '空閒' ? 't-ok' : u.state === '配送中' ? 't-blue' : 't-warn'}">${u.state}</span></div>
      <div class="m">今天 ${u.n} 單、送達 ${u.done}${u.cash ? ' · 身上現金 ' + fmt(u.cash) : ''}</div></div></div>`).join('') || '<div class="muted">還沒有外送夥伴。到「老闆 › 帳號」勾選「外送」。</div>'}</div>`;
  if (DV.cash.length) h += `<div class="card"><h3>現金待繳回</h3>${DV.cash.map(x => `<div class="row"><div><div class="n">${esc(x.name)} ${fmt(x.amt)} 元</div><div class="m">${x.n} 張單，從 ${md(x.since)} 起</div></div>
      ${ME.perms.fin ? `<button class="btn sm" onclick="settle(${x.rider_id},${jsq(x.name)},${x.amt},${jsq(x.ids)})">收回現金</button>` : ''}</div>`).join('')}</div>`;
  const live = DV.rows.filter(r => !r.cancelled);
  h += DV.states.map(st => { const rs = live.filter(r => r.status === st); return rs.length ? `<h2>${st} <span class="small" style="font-weight:400">${rs.length}</span></h2><div class="lane">${rs.map(r => dcard(r)).join('')}</div>` : ''; }).join('')
    || '<div class="card muted">今天還沒有外送單。按上面「開外送單」。</div>';
  const cx = DV.rows.filter(r => r.cancelled); if (cx.length) h += `<h2>取消</h2><div class="lane">${cx.map(r => dcard(r)).join('')}</div>`;
  $('#main').innerHTML = h;
}
async function delivMine() {
  const rs = DV.mine;
  let h = hero('外送', '我的外送。', '派給你的單在這裡。先按「接受」，取餐要逐項核對；到了先按「到了・定位打卡」，放門口、櫃台要拍照；收到的現金每班結束交給店長。');
  h += await pushCard();
  h += rs.map(r => `${dcard(r, true)}${mineActions(r)}`).join('<div style="height:14px"></div>') || '<div class="card muted">目前沒有派給你的外送單。</div>';
  $('#main').innerHTML = h;
}
function mineActions(r) {
  if (r.status === '已送達') return '';
  const nav = 'https://www.google.com/maps/dir/?api=1&destination=' + encodeURIComponent(r.address), tel = (r.phone || '').replace(/[^\d+#,]/g, '');
  let a = '';
  if (r.waiting_accept) a = `<button class="btn green" onclick="dAccept(${r.id},true)">接受</button><button class="btn gray" onclick="dAccept(${r.id},false)">沒辦法送</button>`;
  else if (r.status === '新單' || r.status === '製作中') a = `<span class="muted">廚房還在做，好了會通知你。</span>`;
  else if (r.status === '已出餐') a = `<button class="btn" onclick="pickForm(${r.id})">到店取餐、核對</button>`;
  else if (r.status === '配送中') a = `<a class="btn sec" href="${nav}" target="_blank">導航</a>${tel ? `<a class="btn sec" href="tel:${tel}">打給客人</a>` : ''}
      <button class="btn gray" onclick="dNear(${r.id})">快到了</button>
      ${r.arrive_at ? `<span class="tag t-blue">${hm(r.arrive_at)} 到點${r.arrive_m != null ? ' · 距店 ' + (r.arrive_m / 1000).toFixed(1) + ' 公里' : r.arrive_note ? ' · ' + esc(r.arrive_note) : ''}</span><button class="btn green" onclick="dropForm(${r.id})">已送達</button>`
        : `<button class="btn green" id="arr${r.id}" onclick="dArrive(${r.id})">到了・定位打卡</button>`}`;
  return `<div class="btns" style="margin-top:8px">${a}<button class="btn gray" onclick="issueForm(${r.id})">回報問題</button></div>`;
}
function delivForm(id) {
  const r = id ? DV.rows.find(x => x.id === id) : { pay: '現金收款', source: '電話', day: DD };
  openSheet(`<div class="shead"><h3>${id ? '修改外送單' : '開外送單'}</h3><button class="btn gray sm" onclick="closeSheet()">取消</button></div><div class="card">
    <label>來源</label><div class="seg" id="d_src">${['電話', 'LINE', '團訂', '現場', 'Threads', '臉書'].map(x => `<button class="${(r.source || '電話') === x ? 'on' : ''}" onclick="seg(this)">${x}</button>`).join('')}</div>
    <div class="g2"><div><label>客人／單位</label><input id="d_cus" value="${esc(r.customer || '')}"></div><div><label>電話</label><input id="d_tel" inputmode="tel" value="${esc(r.phone || '')}"></div></div>
    <label>地址（含樓層、哪個門）</label><input id="d_addr" value="${esc(r.address || '')}">
    <label>品項與份數</label><textarea id="d_items" rows="3" placeholder="例：排骨 10、雞腿 8、素食 2；湯 20 杯">${esc(r.items || '')}</textarea>
    <div class="g3"><div><label>便當個數</label><input id="d_box" inputmode="numeric" value="${r.boxes || ''}"></div><div><label>袋數</label><input id="d_bags" inputmode="numeric" value="${r.bags || ''}"></div><div><label>金額（現金收款必填）</label><input id="d_amt" inputmode="numeric" value="${r.amount || ''}"></div></div>
    <label>付款</label><div class="seg" id="d_pay">${['現金收款', '已付款', '匯款', '月結'].map(x => `<button class="${(r.pay || '現金收款') === x ? 'on' : ''}" onclick="seg(this)">${x}</button>`).join('')}</div>
    <div class="g3"><div><label>要送達時間</label><input id="d_due" type="time" value="${r.due || ''}"></div><div><label>預計出餐時間</label><input id="d_ready" type="time" value="${r.ready_by || ''}"></div><div><label>日期</label><input id="d_day" type="date" value="${r.day || DD}"></div></div>
    <label>要收據（寫抬頭、統編；不用就空白）</label><input id="d_rcpt" value="${esc(r.receipt || '')}">
    <label>備註</label><input id="d_note" value="${esc(r.note || '')}" placeholder="例：到了先打電話、從後門進">
    <label>派給</label><select id="d_rider"><option value="">（先不派）</option>${DV.riders.map(u => `<option value="${u.id}" ${u.id === r.rider_id ? 'selected' : ''}>${esc(u.name)}${u.rider ? '（外送）' : ''} · ${u.state}</option>`).join('')}</select>
    <div class="btns"><button class="btn" onclick="saveDeliv(${id || 0})">${id ? '儲存' : '開單'}</button></div><div id="d_m"></div></div>`);
}
async function saveDeliv(id) {
  const v = k => $('#' + k).value;
  try { await api('/api/delivery/save', { id: id || null, source: segVal('d_src'), customer: v('d_cus'), phone: v('d_tel'), address: v('d_addr'), items: v('d_items'), boxes: v('d_box'), bags: v('d_bags'),
      amount: v('d_amt'), pay: segVal('d_pay'), due: v('d_due'), ready_by: v('d_ready'), day: v('d_day'), receipt: v('d_rcpt'), note: v('d_note'), rider_id: v('d_rider') || null });
    closeSheet(); LOAD.deliv(); } catch (e) { msgOk('#d_m', e); }
}
function delivOpen(id) {
  const r = DV.rows.find(x => x.id === id) || DV.mine.find(x => x.id === id); if (!r) return;
  const can = ME.perms.fin || r.created_by === ME.id || true;
  const msg = (k) => ({ '接單': `您好，這裡是${STORE.name}，您的 ${r.boxes || ''} ${STORE.unit}訂單已收到${r.due ? '，預計 ' + r.due + ' 送達' : ''}，謝謝！`,
    '出發': `您好，${STORE.name}的餐點已經出發${r.due ? '，大約 ' + r.due + ' 送到' : ''}，送餐夥伴${r.rider ? ' ' + r.rider : ''}。`,
    '快到了': `您好，${STORE.name}的餐點快到了，大約 5 分鐘內抵達，麻煩留意電話。`,
    '送達': `您好，便當已經送達（${r.handoff || '交給本人'}），請趁熱享用，謝謝您！` })[k];
  openSheet(`<div class="shead"><div><h3>#${r.seq} ${esc(r.customer)}</h3><div>${lateTag(r)}</div></div><button class="btn gray sm" onclick="closeSheet()">關閉</button></div>
    <div class="card">${steps(r)}<table>${[['狀態', r.status + (r.cancelled ? '（已取消：' + (r.cancel_reason || '') + '）' : '')], ['要送達', r.due], ['預計出餐', r.ready_by], ['地址', r.address], ['電話', r.phone], ['品項', r.items], ['個數／袋數', (r.boxes || '?') + ' 個' + (r.bags ? '／' + r.bags + ' 袋' : '')],
      ['付款', r.pay + (r.collect ? '，收現 ' + fmt(r.collect) : '')], ['收據', r.receipt], ['備註', r.note], ['外送夥伴', r.rider ? r.rider + (r.waiting_accept ? '（還沒按接受）' : '') : '還沒派'],
      ['開單', r.creator + ' ' + hm(r.created)], ['出餐', hm(r.ready_at)], ['取餐', hm(r.picked_at)], ['到點', r.arrive_at ? hm(r.arrive_at) + (r.arrive_m != null ? ' · 距店 ' + (r.arrive_m / 1000).toFixed(1) + ' 公里' : '') + (r.arrive_note ? ' · ' + r.arrive_note : '') : ''], ['送達', r.delivered_at ? hm(r.delivered_at) + ' · ' + (r.handoff || '') : ''], ['實收', r.cash_got != null && r.collect ? fmt(r.cash_got) + (r.cash_got !== r.collect ? '（跟應收不同）' : '') : ''], ['問題', r.issue]]
      .filter(x => x[1]).map(([k, v]) => `<tr><th style="width:84px">${k}</th><td>${esc(v)}</td></tr>`).join('')}</table>
      ${r.arrive_lat != null ? `<div class="btns" style="margin-top:8px"><a class="btn sec sm" target="_blank" href="https://www.google.com/maps?q=${r.arrive_lat},${r.arrive_lng}">到點位置地圖</a>${r.drop_lat != null ? `<a class="btn sec sm" target="_blank" href="https://www.google.com/maps?q=${r.drop_lat},${r.drop_lng}">送達位置地圖</a>` : ''}</div>` : ''}
      ${r.proof ? `<img src="/api/delivery/photo?id=${r.id}" alt="送達照片" style="max-height:200px;border-radius:12px;margin-top:10px;cursor:zoom-in" onclick="zoom(this.src)">` : ''}</div>
    ${!r.cancelled && r.status !== '已送達' ? `<div class="card"><h3>操作</h3>
      ${NEXT[r.status] ? `<button class="btn" onclick="dStatus(${r.id},'${NEXT[r.status][0]}')">${NEXT[r.status][1]}</button>` : ''}
      <label>派給</label><select onchange="dAssign(${r.id},this.value)"><option value="">（不派）</option>${DV.riders.map(u => `<option value="${u.id}" ${u.id === r.rider_id ? 'selected' : ''}>${esc(u.name)} · ${u.state}</option>`).join('')}</select>
      <label>出餐延後</label><div class="btns" style="margin-top:0">${[5, 10, 20, 30].map(m => `<button class="btn gray sm" onclick="dDelay(${r.id},${m})">＋${m} 分</button>`).join('')}</div>
      <div class="btns"><button class="btn gray sm" onclick="closeSheet();delivForm(${r.id})">修改</button><button class="btn gray sm" onclick="dCopy(${r.id})">拆單（多一位送）</button>
      ${r.issue ? `<button class="btn gray sm" onclick="dResolve(${r.id})">問題解決了</button>` : `<button class="btn gray sm" onclick="issueForm(${r.id})">回報問題</button>`}
      <button class="btn red sm" onclick="dCancel(${r.id})">取消這張單</button></div></div>` : ''}
    ${r.cancelled && ME.perms.fin ? `<button class="btn sec" onclick="dUncancel(${r.id})">復原這張單</button>` : ''}
    ${ME.perms.fin ? `<div class="btns"><button class="btn red sm" onclick="dDelete(${r.id})">刪除這張單（測試或開錯）</button></div>` : ''}
    ${r.status === '已送達' && r.collect && r.cash_got !== r.collect && !r.cash_ok_by && ME.perms.fin ? `<button class="btn" onclick="api('/api/delivery/cash_ok',{id:${r.id}}).then(()=>{closeSheet();LOAD.deliv()})">核可收款差額</button>` : ''}
    <div class="card"><h3>複製給客人的 LINE 訊息</h3><div class="btns" style="margin-top:0">${['接單', '出發', '快到了', '送達'].map(k => `<button class="btn sec sm" onclick="copyMsg(${JSON.stringify(msg(k)).replace(/"/g, '&quot;')})">${k}</button>`).join('')}</div></div>`);
}
async function copyMsg(t) { try { await navigator.clipboard.writeText(t); alert('已複製，貼到 LINE 給客人：\n\n' + t); } catch (e) { prompt('複製這段：', t); } }
const dErr = e => alert(e.message);
async function dStatus(id, to, extra) { try { await api('/api/delivery/status', Object.assign({ id, to }, extra || {})); closeSheet(); LOAD.deliv(); } catch (e) { dErr(e); } }
async function dAssign(id, rid) { try { await api('/api/delivery/assign', { id, rider_id: rid || null }); closeSheet(); LOAD.deliv(); } catch (e) { dErr(e); } }
async function dDelay(id, mins) { try { await api('/api/delivery/delay', { id, mins }); closeSheet(); LOAD.deliv(); } catch (e) { dErr(e); } }
async function dCopy(id) { try { await api('/api/delivery/copy', { id }); closeSheet(); alert('已複製一張，點開那張改份數、派給另一位夥伴。'); LOAD.deliv(); } catch (e) { dErr(e); } }
async function dResolve(id) { try { await api('/api/delivery/resolve', { id }); closeSheet(); LOAD.deliv(); } catch (e) { dErr(e); } }
async function dCancel(id) { const n = prompt('取消原因（必填）'); if (!n) return; try { await api('/api/delivery/cancel', { id, note: n }); closeSheet(); LOAD.deliv(); } catch (e) { dErr(e); } }
async function dAccept(id, ok) { const note = ok ? '' : prompt('為什麼沒辦法送？（店長會收到）'); if (!ok && note === null) return; try { await api('/api/delivery/accept', { id, accept: ok, note }); LOAD.deliv(); } catch (e) { dErr(e); } }
/* 到點定位打卡：抓 GPS → 記時間和離店距離。抓不到也能打（標「沒定位」，老闆看得到） */
async function dArrive(id) {
  const b = $('#arr' + id); if (b) { b.disabled = true; b.textContent = '定位中…'; }
  let body = { id };
  try { const c = await getPos(); body = { id, lat: c.latitude, lng: c.longitude, acc: c.accuracy }; }
  catch (e) {
    if (!confirm(e.message + '\n\n還是要先打卡嗎？會標記「沒定位」，老闆看得到。')) { if (b) { b.disabled = false; b.textContent = '到了・定位打卡'; } return; }
    body.why = e.message.slice(0, 40);
  }
  try { await api('/api/delivery/arrive', body); LOAD.deliv(); } catch (e) { dErr(e); if (b) { b.disabled = false; b.textContent = '到了・定位打卡'; } }
}
async function dNear(id) { try { await api('/api/delivery/near', { id }); const r = DV.mine.find(x => x.id === id); copyMsg('您好，' + STORE.name + '的餐點快到了，大約 5 分鐘內抵達，麻煩留意電話。'); } catch (e) { dErr(e); } }
async function settle(rid, name, amt, ids) { if (!confirm(`${name} 交回現金 ${fmt(amt)} 元，點清楚了嗎？`)) return; try { await api('/api/delivery/settle', { rider_id: rid, ids: String(ids || '').split(',').filter(Boolean).map(Number), amount: amt }); LOAD.deliv(); } catch (e) { dErr(e); } }
async function dDelete(id) { if (!confirm('刪除這張單？\n看板、報表、現金都不會再算它。')) return; try { await api('/api/delivery/delete', { id, note: '刪除' }); closeSheet(); LOAD.deliv(); } catch (e) { dErr(e); } }
async function dUncancel(id) { try { await api('/api/delivery/uncancel', { id }); closeSheet(); LOAD.deliv(); } catch (e) { dErr(e); } }
function pickForm(id) {
  const r = DV.mine.find(x => x.id === id) || DV.rows.find(x => x.id === id);
  const items = [['品項份數', `品項、份數對（${r.boxes || '?'} 個）`], ['袋數', `袋數對（${r.bags || '?'} 袋，袋上有貼單）`], ['餐具', '餐具、筷子湯匙'], ['湯和飲料', '湯、飲料（沒有就勾）']].concat(r.receipt ? [['收據', `收據（${r.receipt}）`]] : []);
  openSheet(`<div class="shead"><h3>取餐核對：${esc(r.customer)}</h3><button class="btn gray sm" onclick="closeSheet()">取消</button></div><div class="card">
    <div class="muted">${esc(r.items || '')}</div>${items.map(([k, n]) => `<label class="chk"><input type="checkbox" class="pk" data-k="${k}"> ${esc(n)}</label>`).join('')}
    <button class="btn full" style="margin-top:18px" onclick="doPick(${id})">都對了，取餐出發</button></div>`);
}
function doPick(id) { const ck = {}; document.querySelectorAll('.pk').forEach(x => ck[x.dataset.k] = x.checked); dStatus(id, '配送中', { checked: ck }); }
function dropForm(id) {
  const r = DV.mine.find(x => x.id === id); DPHOTO = null;
  openSheet(`<div class="shead"><h3>送達：${esc(r.customer)}</h3><button class="btn gray sm" onclick="closeSheet()">取消</button></div><div class="card">
    <label>交給誰／放哪裡</label><div class="seg" id="d_ho">${DV.handoffs.map((x, i) => `<button class="${i ? '' : 'on'}" onclick="seg(this)">${x}</button>`).join('')}</div>
    <label>照片（放櫃台、門口、管理室一定要拍；交給本人可以不拍。拍餐點和門牌或招牌，不要拍到人臉）</label><input type="file" accept="image/*" capture="environment" onchange="readPhoto(this.files[0],1280).then(p=>{DPHOTO=p;$('#d_ph').textContent='已選一張照片'}).catch(e=>alert(e.message))">
    <div class="small" id="d_ph"></div>
    ${r.collect ? `<label>實際收到的現金（應收 ${fmt(r.collect)}）</label><input id="d_cash" inputmode="numeric" value="${r.collect}">` : ''}
    <button class="btn green full" style="margin-top:18px" onclick="doDrop(${id})">確認送達</button></div>`);
}
async function doDrop(id) {
  const c = $('#d_cash'), x = { handoff: segVal('d_ho'), photo: DPHOTO, cash_got: c ? c.value : null };
  if (x.handoff !== '交給本人' && !DPHOTO) return alert('放櫃台、門口或交管理室，一定要拍照（拍餐點和門牌或招牌，不要拍到人臉）');
  try { const p = await Promise.race([getPos(), new Promise((_, no) => setTimeout(() => no(new Error('timeout')), 8000))]); x.lat = p.latitude; x.lng = p.longitude; } catch (e) { }
  dStatus(id, '已送達', x);
}
function issueForm(id) {
  openSheet(`<div class="shead"><h3>回報問題</h3><button class="btn gray sm" onclick="closeSheet()">取消</button></div><div class="card">
    <div class="muted">按一個，店長和老闆手機會馬上收到。客人聯絡不上：先打 2 次、等 10 分鐘。</div>
    <label>補充說明（選填）</label><input id="is_note">
    <div class="btns">${DV.issues.map(k => `<button class="btn gray sm" onclick="sendIssue(${id},'${k}')">${k}</button>`).join('')}</div></div>`);
}
async function sendIssue(id, kind) { try { await api('/api/delivery/issue', { id, kind, note: $('#is_note').value }); closeSheet(); alert('已通知店長和老闆'); LOAD.deliv(); } catch (e) { dErr(e); } }
async function delivReport() {
  const s = DV.stats;
  let h = hero('報表', `${md(DD)} 外送報表。`, '單數、準時率、平均送達時間、出餐延誤、問題、每位夥伴的表現和現金。');
  h += `<div class="btns" style="margin:0 0 16px"><input type="date" value="${DD}" style="width:auto" onchange="DD=this.value;LOAD.deliv()"></div>
    <div class="grid"><div class="tile stat"><div class="k">外送單</div><div class="v">${s.n}</div><div class="s">${s.boxes} 個便當</div></div>
    <div class="tile stat good"><div class="k">準時率</div><div class="v">${s.done ? Math.round(s.ontime * 100 / s.done) + '%' : '—'}</div><div class="s">${s.ontime}/${s.done} 準時送達</div></div>
    <div class="tile stat"><div class="k">平均送達</div><div class="v">${s.avg_min != null ? s.avg_min + ' 分' : '—'}</div><div class="s">取餐到送達</div></div>
    <div class="tile stat ${s.prep_late ? 'warn' : ''}"><div class="k">出餐延誤</div><div class="v">${s.prep_late}</div><div class="s">比預計出餐晚</div></div>
    <div class="tile stat ${s.issues ? 'warn' : ''}"><div class="k">問題</div><div class="v">${s.issues}</div></div>
    <div class="tile stat ${s.cash_due ? 'warn' : ''}"><div class="k">現金待繳回</div><div class="v">${fmt(s.cash_due)}</div></div></div>
    <div class="card"><h3>每位夥伴</h3><div class="tbl"><table><tr><th>夥伴</th><th class="r">單數</th><th class="r">送達</th><th class="r">準時</th><th class="r">身上現金</th></tr>
    ${DV.riders.filter(u => u.n || u.cash).map(u => `<tr><td>${esc(u.name)}</td><td class="r">${u.n}</td><td class="r">${u.done}</td><td class="r">${u.ontime}</td><td class="r">${fmt(u.cash)}</td></tr>`).join('') || '<tr><td colspan="5" class="muted">今天沒有外送</td></tr>'}</table></div></div>`;
  $('#main').innerHTML = h;
}
