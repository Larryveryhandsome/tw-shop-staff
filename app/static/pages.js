/* 夥伴每天用的頁面：打卡、日誌、公告（聚光燈）、教育訓練、我 */

/* ---------- 打卡 ---------- */
let PNEXT = 'in', PCLOSED = '';
LOAD.punch = async function () {
  if (CLOCK) { clearInterval(CLOCK); CLOCK = null; }
  const s = await api('/api/punch/state'); PNEXT = s.next; PCLOSED = s.closed || ''; const m = s.month, out = s.next === 'out';
  let h = hero(`${md(s.today)}（${wkOf(s.today)}）${s.closed ? ' · ' + esc(s.closed) : ''}`, out ? '上班中，辛苦了。' : '今天也加油。', '');
  if (ME.notice_unread) h += `<div class="banner blue" onclick="go('notice')"><b>!</b> 有 ${ME.notice_unread} 則新公告，點這裡看 ›</div>`;
  if (s.off_today) h += `<div class="banner ok">今天你排休，好好休息。</div>`;
  if (s.late_last) h += `<div class="banner red">${md(s.late_last.day)} 上班晚了 ${s.late_last.mins} 分鐘。今天請準時打卡（${esc(s.sched)}）。</div>`;
  if (!s.journal_today && !s.off_today) h += `<div class="banner blue" onclick="go('journal')">今天的我很棒日誌還沒寫，點這裡寫 ›</div>`;
  if (!s.store_set) h += `<div class="banner warn">老闆還沒校正店家位置，打卡會先標「位置未校正」。</div>`;
  h += await pushCard();
  h += `<div class="card punchbox"><div class="clock" id="clock">--:--</div>
    <div class="muted" style="margin-top:8px">今天的班：${esc(s.sched)}</div>
    <button class="punch ${out ? 'out' : ''}" id="pbtn" onclick="doPunch()">${out ? '下班打卡' : '上班打卡'}<small>${out ? '辛苦了' : '按下就打卡'}</small></button>
    <div class="small" id="geo">打卡會用手機定位確認你在店裡（${s.radius} 公尺內）。</div>
    <div style="margin-top:12px">${s.punches.map(p => `<span class="tag ${p.kind === 'in' ? 't-blue' : ''}">${KIND[p.kind]} ${p.at}${p.source !== 'phone' ? '（' + esc(p.source) + '）' : ''}</span>`).join('') || '<span class="muted">今天還沒打卡</span>'}</div></div>`;
  if (m) {
    h += `<div class="grid"><div class="tile stat"><div class="k">本月出勤</div><div class="v">${m.days} 天</div></div>
      <div class="tile stat"><div class="k">打卡時數</div><div class="v">${(m.mins / 60).toFixed(1)}</div><div class="s">小時${m.need ? '，做滿是 ' + (m.need / 60) + ' 小時' : ''}</div></div>
      <div class="tile stat ${m.late_n ? 'warn' : ''}"><div class="k">遲到</div><div class="v">${m.late_n} 次</div><div class="s">遲到的分鐘不算工時</div></div>
      <div class="tile stat"><div class="k">預估實發</div><div class="v">${fmt(m.net)}</div><div class="s">照目前打卡試算，月底定案</div></div></div>`;
    if (m.issues.length) h += `<div class="banner warn">有 ${m.issues.length} 處漏打卡：${m.issues.map(x => md(x[0]) + ' ' + esc(x[1])).join('；')}。沒打卡的時間不算薪水，請用下面「申請補登」。</div>`;
    h += `<details class="fold"><summary>本月每天<small>${m.per_day.length} 天有打卡</small></summary><div class="in"><div class="tbl"><table><tr><th>日期</th><th>打卡</th><th class="r">時數</th></tr>
      ${m.per_day.slice().reverse().map(x => `<tr><td>${md(x.day)}（${wkOf(x.day)}）</td><td>${x.segs.map(g => g[0] + '–' + g[1]).join('　') || '—'}${x.open_in ? '　' + x.open_in + '–上班中' : ''}
        ${x.lates.map(l => `<span class="tag t-warn">晚 ${l[2]} 分</span>`).join('')}${x.issues.map(i => `<span class="tag t-warn">${esc(i)}</span>`).join('')}</td><td class="r">${(x.mins / 60).toFixed(2)}</td></tr>`).join('')}</table></div></div></details>`;
  } else if (!s.has_profile) h += `<div class="banner warn">老闆還沒幫你設定班表和薪資。照常打卡就好，設定好以後會照打卡算。</div>`;
  h += `<details class="fold"><summary>忘了打卡？申請補登</summary><div class="in">
    <div class="muted">打卡就是一切：沒打卡的時間不算薪水。忘了打卡就在這裡申請，老闆核准後才算。</div>
    <div class="g2"><div><label>日期</label><input type="date" id="fx_day" value="${s.today}" max="${s.today}"></div><div><label>時間</label><input type="time" id="fx_time"></div></div>
    <label>上班還是下班</label><div class="seg" id="fx_kind"><button class="on" onclick="seg(this)">上班</button><button onclick="seg(this)">下班</button></div>
    <label>原因</label><input id="fx_reason" placeholder="例：手機沒電、忘了打">
    <button class="btn" style="margin-top:16px" onclick="sendFix()">送出申請</button><div id="fx_msg"></div>
    ${s.fixes.length ? `<h3 style="margin-top:22px">我的申請</h3>` + s.fixes.map(f => `<div class="row"><div><div class="n">${md(f.day)} ${KIND[f.kind]} ${f.time}</div><div class="m">${esc(f.reason)}${f.decide_note ? ' · 老闆：' + esc(f.decide_note) : ''}</div></div>
      <span class="tag ${f.status === '核准' ? 't-ok' : f.status === '退回' ? 't-warn' : ''}">${f.status}</span></div>`).join('') : ''}</div></details>`;
  $('#main').innerHTML = h;
  const tick = () => { const e = $('#clock'); if (e) e.textContent = new Date().toLocaleTimeString('zh-TW', { hour12: false }); };
  tick(); CLOCK = setInterval(tick, 1000);
};
function getPos() {
  return new Promise((ok, no) => {
    if (!navigator.geolocation) return no(new Error('這支手機不支援定位'));
    navigator.geolocation.getCurrentPosition(p => ok(p.coords), e => no(new Error(e.code === 1 ? '你沒有允許定位。請到手機設定把這個網站的「位置」改成允許，再按一次。' : '抓不到位置，請到門口或打開 GPS 再試。')),
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
  });
}
async function doPunch() {
  if (PCLOSED && !confirm(`今天店休（${PCLOSED}），店沒開的日子打卡不計薪水。\n還是要打卡嗎？`)) return;
  const b = $('#pbtn'); b.disabled = true; $('#geo').textContent = '定位中…';
  try { const c = await getPos(); $('#geo').textContent = '打卡中…';
    const r = await api('/api/punch', { lat: c.latitude, lng: c.longitude, acc: c.accuracy, kind: PNEXT });
    alert(`${KIND[r.kind]}打卡成功：${r.at}${r.dist != null ? '（離店 ' + r.dist + ' 公尺）' : ''}`);
    if (r.safety_missing && r.safety_missing.length && confirm(`下班前還沒記：${r.safety_missing.join('、')}。\n現在去「食安」記錄嗎？`)) return go('safety');
    LOAD.punch();
  } catch (e) { $('#geo').innerHTML = `<span class="err">${esc(e.message)}</span>`; b.disabled = false; }
}
async function sendFix() {
  try { await api('/api/punch/fix', { day: $('#fx_day').value, time: $('#fx_time').value, kind: segVal('fx_kind') === '上班' ? 'in' : 'out', reason: $('#fx_reason').value }); LOAD.punch(); }
  catch (e) { $('#fx_msg').innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}

/* ---------- 我很棒日誌（像 LINE） ---------- */
let JU = 0, PHOTO = null;
LOAD.journal = async function () { return ME.perms.admin && !JU ? journalList() : journalThread(); };
async function journalList() {
  const ts = await api('/api/journal/threads'), wrote = ts.filter(t => t.wrote_today).length;
  $('#main').innerHTML = hero('日誌', '我很棒日誌。', `今天 ${wrote} / ${ts.length} 位夥伴寫了。點名字看對話、回覆。`) +
    `<div class="card">${ts.map(t => `<div class="thread" onclick="JU=${t.id};LOAD.journal()"><div class="av">${initial(t.name)}</div>
     <div class="t"><div><b>${esc(t.name)}</b> <span class="tag ${t.wrote_today ? 't-ok' : 't-warn'}">${t.wrote_today ? '今天寫了' : '今天還沒寫'}</span><span class="tag">本月 ${t.days_month} 天</span></div>
     <div class="last">${t.last ? esc(t.last.who) + '：' + esc(t.last.text) : '還沒寫過'}</div></div>
     <div style="text-align:right">${t.last ? `<div class="small">${md(t.last.at)} ${hm(t.last.at)}</div>` : ''}${t.unread ? `<span class="cnt">${t.unread}</span>` : ''}</div></div>`).join('') || '<div class="muted">還沒有夥伴帳號</div>'}</div>`;
  refreshBadges();
}
async function journalThread() {
  const admin = ME.perms.admin, d = await api('/api/journal' + (admin ? '?uid=' + JU : '')), ms = d.messages;
  let h = admin ? `<button class="btn gray sm" onclick="JU=0;LOAD.journal()">‹ 全部夥伴</button><h1 class="headline" style="margin-top:16px">${esc(d.thread.name)}</h1>
      <p class="sub">${d.wrote_today ? '今天寫了。' : '今天還沒寫。'}你的回覆會像 LINE 一樣出現在${esc(d.thread.name)}的日誌裡。</p>`
    : hero('日誌', '我很棒日誌。', `每天寫下三件今天自己做得好的事，老闆會看，也會回你。${d.wrote_today ? '<span class="tag t-ok">今天寫了</span>' : ''}`);
  let last = '';
  h += '<div class="chat">' + (ms.map(m => {
    const mine = m.author_id === ME.id, boss = m.author_role === 'admin';
    const sep = m.day !== last ? `<div class="daysep"><span>${md(m.day)}（${wkOf(m.day)}）</span></div>` : ''; last = m.day;
    const body = m.removed ? `<div class="bub gone">${mine ? '你' : esc(m.author)}收回了一則訊息</div>`
      : `<div class="bub">${m.photo ? `<img src="/api/journal/photo?id=${m.id}" loading="lazy" alt="照片" onclick="zoom(this.src)">` : ''}${esc(m.body || '')}</div>`;
    const can = mine && !m.removed && m.day === todayStr();
    return sep + `<div class="msg ${mine ? 'mine' : ''}">${mine ? '' : `<div class="av ${boss ? 'boss' : ''}">${initial(m.author)}</div>`}
      <div class="col">${mine ? '' : `<div class="who">${esc(m.author)}${boss ? '（老闆）' : ''}</div>`}${body}</div>
      <div class="meta">${hm(m.created)}${can ? `<a onclick="unsend(${m.id})">收回</a>` : ''}</div></div>`;
  }).join('') || `<div class="card muted" style="text-align:center;padding:34px">${admin ? '還沒寫過。' : '還沒寫過。今天做得好的三件事是什麼？寫在下面送出就好。'}</div>`) + '</div>';
  h += `<div class="composer"><div class="preview" id="jprev" hidden></div><div>
     <label class="ibtn" title="附照片">${svg('photo')}<input type="file" accept="image/*" hidden onchange="pickPhoto(this)"></label>
     <textarea id="jtext" rows="1" placeholder="${admin ? '回覆 ' + esc(d.thread.name) + '…' : '今天我做得很好的是…'}" oninput="grow(this)"></textarea>
     <button class="ibtn send" title="送出" onclick="sendJournal()">${svg('send')}</button></div></div>`;
  $('#main').innerHTML = h; PHOTO = null;
  requestAnimationFrame(() => window.scrollTo(0, document.body.scrollHeight)); refreshBadges();
}
async function pickPhoto(inp) {
  try { PHOTO = await readPhoto(inp.files[0], 1280);
    $('#jprev').innerHTML = `<img src="${PHOTO}" alt=""><span>附一張照片</span><button class="btn gray sm" onclick="PHOTO=null;$('#jprev').hidden=true">拿掉</button>`; $('#jprev').hidden = false;
  } catch (e) { alert(e.message); }
}
async function sendJournal() {
  const t = $('#jtext'); if (!t.value.trim() && !PHOTO) return t.focus();
  try { await api('/api/journal/post', { body: t.value, photo: PHOTO, uid: JU || null }); journalThread(); } catch (e) { alert(e.message); }
}
async function unsend(id) { if (!confirm('收回這則？')) return; try { await api('/api/journal/remove', { id }); journalThread(); } catch (e) { alert(e.message); } }

/* ---------- 公告（新公告：紅色驚嘆號＋聚光燈） ---------- */
let NS = [];
LOAD.notice = async function () {
  NS = await api('/api/notices'); const P = ME.perms;
  localNav('公告', null, null, null, P.post ? ['發公告', 'noticeNew()'] : null);
  const fresh = NS.filter(n => n.need_ack && !n.read);
  let h = hero('公告', '店裡的公告。', P.post ? '老闆和店長要喊話就發在這裡，發出去大家手機會跳通知；看得到誰讀過。' : '看完按「我已讀」，老闆看得到誰讀過。');
  h += NS.map(n => `<div class="card notice" id="nt${n.id}"><div style="display:flex;justify-content:space-between;gap:12px;align-items:start">
      <div><h3 style="margin:0;font-size:21px">${n.pinned ? '<span class="tag t-blue" style="margin:0 6px 0 0">置頂</span>' : ''}${!n.read && n.need_ack ? '<span class="tag t-red" style="margin:0 6px 0 0">新</span>' : ''}${esc(n.title)}</h3>
      <div class="small" style="margin-top:4px">${esc(n.author || '老闆')} · ${md((n.updated || n.created || '').slice(0, 10))}</div></div>
      ${n.need_ack && !n.mine ? (n.read ? `<span class="tag t-ok">已讀 ${n.read_at ? md(n.read_at.slice(0, 10)) : ''}</span>` : `<button class="btn sm" onclick="ack(${n.id})">我已讀</button>`) : ''}</div>
    <div class="body" style="margin-top:14px">${esc(n.body)}</div>
    ${n.readers ? `<details style="margin-top:14px"><summary class="small" style="cursor:pointer">誰讀過（${n.readers.filter(r => r.at).length}/${n.readers.length}）${(P.admin || n.mine) ? ' · 修改' : ''}</summary>
      <div style="margin-top:8px">${n.readers.map(r => `<span class="tag ${r.at ? 't-ok' : 't-warn'}">${esc(r.name)} ${r.at ? md(r.at.slice(0, 10)) : '未讀'}</span>`).join('')}</div>
      ${(P.admin || n.mine) ? `<div style="margin-top:12px">${noticeForm(n)}</div>` : ''}</details>` : ''}</div>`).join('') || '<div class="card muted">目前沒有公告。</div>';
  $('#main').innerHTML = h;
  if (fresh.length) setTimeout(() => spotNotice(fresh, 0), 250);
};
function spotNotice(list, i) {
  if (i >= list.length) return;
  const el = $('#nt' + list[i].id); if (!el) return;
  spotlight(el, list.length > 1 ? `新公告 ${i + 1}/${list.length}　看完按「我已讀」` : '新公告　看完按「我已讀」', () => spotNotice(list, i + 1));
  const b = el.querySelector('.btn'); if (b) b.onclick = async () => { await ack(list[i].id, true); spotNotice(list, i + 1); };
}
function noticeForm(n) {
  const k = n.id || 'new';
  return `<label>標題</label><input id="nt_t_${k}" value="${esc(n.title || '')}">
  <label>內容</label><textarea id="nt_b_${k}" rows="${n.id ? 9 : 6}">${esc(n.body || '')}</textarea>
  <label class="chk"><input type="checkbox" id="nt_p_${k}" ${n.pinned ? 'checked' : ''}> 置頂</label>
  ${n.id ? `<label class="chk"><input type="checkbox" id="nt_r_${k}"> 內容改了，請大家重新按已讀（會再發通知）</label>` : ''}
  <div class="btns"><button class="btn" onclick="saveNotice(${n.id || 0})">${n.id ? '儲存修改' : '發布並通知大家'}</button>
  ${n.id ? `<button class="btn gray" onclick="removeNotice(${n.id})">下架</button>` : ''}</div><div id="nt_m_${k}"></div>`;
}
function noticeNew() { openSheet(`<div class="shead"><h3>發公告</h3><button class="btn gray sm" onclick="closeSheet()">取消</button></div><div class="card">${noticeForm({})}</div>`); }
async function saveNotice(id) {
  const k = id || 'new';
  try { await api('/api/notice/save', { id: id || null, title: $('#nt_t_' + k).value, body: $('#nt_b_' + k).value, pinned: $('#nt_p_' + k).checked, reack: id ? $('#nt_r_' + k).checked : false });
    closeSheet(); LOAD.notice(); } catch (e) { $('#nt_m_' + k).innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}
async function removeNotice(id) { if (!confirm('確定下架這則公告？')) return; await api('/api/notice/remove', { id }); LOAD.notice(); }
async function ack(id, keep) { await api('/api/notice/ack', { id }); ME.notice_unread = Math.max(0, (ME.notice_unread || 1) - 1); renderNav(); if (!keep) LOAD.notice(); else { const el = $('#nt' + id); if (el) { const b = el.querySelector('.btn'); if (b) b.outerHTML = '<span class="tag t-ok">已讀</span>'; const t = el.querySelector('.t-red'); if (t) t.remove(); } } }

/* ---------- 教育訓練 ---------- */
let MS = [], MQ = '';
const rich = t => esc(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/^■ ?(.+)$/gm, '<span class="subt">$1</span>');
LOAD.manual = async function () { MS = await api('/api/manual'); localNav('教育訓練', null, null, null, ME.perms.admin ? ['新增一篇', 'manualNew()'] : null); renderManual(); };
function renderManual() {
  const admin = ME.perms.admin, q = MQ.trim(), done = MS.filter(m => m.read_at).length;
  const list = q ? MS.filter(m => (m.chapter + m.title + m.body).includes(q)) : MS;
  let h = hero('訓練', '教育訓練。', `現場會用到的做法都在這裡。讀完一篇按「我讀完了」${admin ? '，你看得到誰讀過' : '，老闆看得到'}。`);
  if (!admin && MS.length) h += `<div class="card"><b>你讀完 ${done} / ${MS.length} 篇</b><div class="bar"><i style="width:${Math.round(done * 100 / MS.length)}%"></i></div></div>`;
  h += `<input id="mq" placeholder="搜尋，例如：白飯、洗手、收銀、叫菜" value="${esc(MQ)}" oninput="MQ=this.value;renderManual();const e=$('#mq');e.focus();e.setSelectionRange(e.value.length,e.value.length)">`;
  const chs = [...new Set(list.map(m => m.chapter))];
  h += chs.map(ch => { const its = list.filter(m => m.chapter === ch); return `<div class="chap">${esc(ch)}<small>${its.length} 篇</small></div>` + its.map(m => `<details class="fold"${q ? ' open' : ''}>
     <summary>${esc(m.title)}<small>${admin ? `${(m.readers || []).filter(r => r.at).length}/${(m.readers || []).length} 讀過` : (m.read_at ? '<span class="tag t-ok">讀完了</span>' : '')}</small></summary>
     <div class="in"><div class="mbody">${rich(m.body)}</div>
     ${admin ? `<details style="margin-top:14px"><summary class="small" style="cursor:pointer">誰讀過 · 修改</summary>
        <div style="margin-top:8px">${(m.readers || []).map(r => `<span class="tag ${r.at ? 't-ok' : 't-warn'}">${esc(r.name)} ${r.at ? md(r.at.slice(0, 10)) : '未讀'}</span>`).join('')}</div>
        <div style="margin-top:10px">${manualForm(m)}</div></details>`
      : (m.read_at ? `<div class="small" style="margin-top:12px">${md(m.read_at.slice(0, 10))} 讀完</div>` : `<button class="btn" style="margin-top:16px" onclick="mAck(${m.id})">我讀完了</button>`)}</div></details>`).join(''); }).join('')
    || `<div class="card muted">${q ? '找不到「' + esc(q) + '」' : '還沒有內容。'}</div>`;
  $('#main').innerHTML = h;
}
function manualForm(m) {
  const k = m.id || 'new', chs = [...new Set(MS.map(x => x.chapter))];
  return `<label>章節</label><input id="mc_${k}" list="mchs" value="${esc(m.chapter || '')}"><datalist id="mchs">${chs.map(c => `<option value="${esc(c)}">`).join('')}</datalist>
  <label>標題</label><input id="mt_${k}" value="${esc(m.title || '')}"><label>內容（■ 開頭是小標題，**字** 是粗體）</label><textarea id="mb_${k}" rows="${m.id ? 12 : 8}">${esc(m.body || '')}</textarea>
  <label>排序（數字小的在前面，空白就排到這章最後）</label><input id="ms_${k}" value="${m.sort || ''}" inputmode="numeric">
  ${m.id ? `<label class="chk"><input type="checkbox" id="mr_${k}"> 內容改了，請大家重新讀</label>` : ''}
  <div class="btns"><button class="btn" onclick="saveManual(${m.id || 0})">${m.id ? '儲存修改' : '新增'}</button>
  ${m.id ? `<button class="btn gray" onclick="removeManual(${m.id})">下架</button>` : ''}</div><div id="mm_${k}"></div>`;
}
function manualNew() { openSheet(`<div class="shead"><h3>新增一篇</h3><button class="btn gray sm" onclick="closeSheet()">取消</button></div><div class="card">${manualForm({})}</div>`); }
async function saveManual(id) {
  const k = id || 'new';
  try { await api('/api/boss/manual/save', { id: id || null, chapter: $('#mc_' + k).value, title: $('#mt_' + k).value, body: $('#mb_' + k).value, sort: +$('#ms_' + k).value || 0, reack: id ? $('#mr_' + k).checked : false });
    closeSheet(); LOAD.manual(); } catch (e) { $('#mm_' + k).innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}
async function removeManual(id) { if (!confirm('確定下架這一篇？')) return; await api('/api/boss/manual/remove', { id }); LOAD.manual(); }
async function mAck(id) { await api('/api/manual/ack', { id }); MS = await api('/api/manual'); renderManual(); refreshBadges(); }

/* ---------- 我 ---------- */
LOAD.me = async function () {
  const st = await pushStatus(), inbox = await api('/api/inbox');
  let h = hero('我', esc(ME.acting ? ME.real_name : ME.name), ME.acting ? `正在模擬${ME.acting === 'manager' ? '店長' : '夥伴'}` : `帳號 ${esc(ME.username)}${ME.role === 'manager' ? ' · ' + (ME.title || '店長') : ME.role === 'admin' ? ' · 老闆' : ''}`);
  if (ME.can_switch) h += `<div class="card"><h3>切換角色</h3><p class="muted">看店長、夥伴手機上的畫面，不用另外登入。</p>
    <div class="seg">${ROLES.map(([k, t]) => `<button class="${(ME.acting || 'admin') === k ? 'on' : ''}" onclick="switchRole('${k}')">${t}</button>`).join('')}</div></div>`;
  if (ME.acting) { h += `<div class="btns"><button class="btn gray" onclick="logout()">登出</button></div>`; $('#main').innerHTML = h; return; }
  h += `<div class="card"><h3>手機通知</h3>
    ${st === 'on' ? `<div class="banner ok">這支手機已經開啟通知。</div><div class="btns"><button class="btn sec" onclick="testPush()">傳一則測試通知給我</button></div>`
      : `<p class="muted">${st === 'off' ? '開啟後，新公告、老闆回你的日誌、外送單、遲到提醒，會直接跳到手機上。' : esc(pushHelp(st))}</p>
         ${st === 'off' ? '<button class="btn" onclick="turnOnPush(this)">開啟通知</button>' : ''}`}
    ${PUSH.ios && !PUSH.standalone ? '' : '<div class="small" style="margin-top:12px">換手機或換瀏覽器要再開一次。</div>'}</div>`;
  h += `<details class="fold" ${inbox.some(x => !x.read) ? 'open' : ''}><summary>最近的通知<small>${inbox.filter(x => !x.read).length ? inbox.filter(x => !x.read).length + ' 則沒看' : ''}</small></summary><div class="in">
    ${inbox.map(x => `<div class="row click" onclick="location.hash='${esc((x.url || '/#').split('#')[1] || '')}'"><div><div class="n">${x.read ? '' : '<span class="tag t-red" style="margin:0 6px 0 0">新</span>'}${esc(x.title)}</div><div class="m">${esc(x.body || '')}</div></div><span class="small">${md(x.created)} ${hm(x.created)}</span></div>`).join('') || '<div class="muted">還沒有通知</div>'}</div></details>`;
  h += `<details class="fold"><summary>改密碼</summary><div class="in"><label>舊密碼</label><input id="po" type="password"><label>新密碼（至少 6 碼）</label><input id="pn" type="password">
    <button class="btn" style="margin-top:16px" onclick="chpw()">改密碼</button><div id="perr"></div></div></details>
    <div class="btns"><button class="btn gray" onclick="logout()">登出</button></div>`;
  $('#main').innerHTML = h;
  if (inbox.some(x => !x.read)) { await api('/api/inbox/read', {}); ME.inbox_unread = 0; renderNav(); }
};
async function testPush() { try { const r = await api('/api/push/test', {}); alert(`已送出，${r.devices} 支手機應該會收到。`); } catch (e) { alert(e.message); } }
async function chpw() { try { await api('/api/password', { old: $('#po').value, new: $('#pn').value }); $('#perr').innerHTML = '<div class="okmsg">已更新</div>'; } catch (e) { $('#perr').innerHTML = `<div class="err">${esc(e.message)}</div>`; } }
async function logout() {
  try {   // 店裡共用手機：登出就不要再收到這個人的通知
    const reg = 'serviceWorker' in navigator && await navigator.serviceWorker.getRegistration();
    const sub = reg && reg.pushManager && await reg.pushManager.getSubscription();
    if (sub && !ME.acting) { await api('/api/push/unsubscribe', { endpoint: sub.endpoint }).catch(() => { }); await sub.unsubscribe().catch(() => { }); }
  } catch (e) { }
  await api('/api/logout', {}).catch(() => { }); location.hash = ''; location.reload();
}
