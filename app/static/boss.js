/* 老闆頁：今日出勤、本月薪資、補登審核、打卡紀錄、設定、帳號（含新夥伴註冊審核） */
let BM = todayStr().slice(0, 7), BU = 0;
SUB.boss = 'today';
LOAD.boss = async function () {
  let fixes = []; try { fixes = await api('/api/boss/fixes'); } catch (e) { }
  const pend = fixes.filter(f => f.status === '待審').length;
  localNav('老闆', [['today', '今日出勤'], ['pay', '本月薪資'], ['fix', '補登審核', pend], ['punches', '打卡紀錄'], ['set', '設定'], ['acct', '帳號', ME.pending_regs || 0], ['todo', '待辦']], SUB.boss, 'bossTab');
  return ({ today: bToday, pay: bPay, fix: () => bFix(fixes), punches: bPunches, set: bSet, acct: bAcct, todo: bTodo })[SUB.boss]();
};
function bossTab(k) { SUB.boss = k; LOAD.boss(); }
async function bToday() {
  const d = await api('/api/boss/today');
  const on = d.rows.filter(r => /上班中/.test(r.status)).length, wait = d.rows.filter(r => /還沒打卡/.test(r.status)).length;
  let h = hero(`${md(d.day)}（${wkOf(d.day)}）${d.closed ? ' · ' + esc(d.closed) : ''}`, '店裡現在的狀況。', '');
  h += `<div class="grid"><div class="tile stat good"><div class="k">上班中</div><div class="v">${on}</div></div><div class="tile stat ${wait ? 'warn' : ''}"><div class="k">還沒打卡</div><div class="v">${wait}</div></div>
    <div class="tile stat"><div class="k">今天日誌</div><div class="v">${(d.journal || []).filter(j => j.wrote).length}/${(d.journal || []).length}</div></div>
    <div class="tile stat ${ME.fin_pending ? 'warn' : ''}"><div class="k">記帳待核銷</div><div class="v">${ME.fin_pending || 0}</div><div class="s"><a class="more" onclick="go('fin')">去核銷</a></div></div></div>`;
  (d.labor_calendar || []).forEach(w => { h += `<div class="banner red" data-labor-cal>勞動曆提醒：${esc(w)}（做法見 docs/labor-law.md「每年要更新的設定」）</div>`; });
  if (!d.store_set) h += `<div class="banner warn">還沒校正店家位置。人在店裡時，到「設定」按「我現在在店裡，用我的位置設為店家」。</div>`;
  if (ME.pending_regs) h += `<div class="banner blue" onclick="bossTab('acct')">有 ${ME.pending_regs} 位新夥伴註冊，等你審核 ›</div>`;
  if (ME.pending_fixes) h += `<div class="banner blue" onclick="bossTab('fix')">有 ${ME.pending_fixes} 筆補登打卡等你審核 ›</div>`;
  if ((d.setup_missing || []).length) h += `<div class="banner warn" onclick="bossTab('set')">${d.setup_missing.map(esc).join('、')} 還沒設薪資或班表：打卡會記下來，但要設好才會算薪、才會出現在今日出勤 ›</div>`;
  h += await pushCard();
  h += `<div class="card"><div class="tbl"><table><tr><th>夥伴</th><th>今天的班</th><th>打卡</th><th>狀態</th></tr>
    ${d.rows.map(r => `<tr><td><b>${esc(r.name)}</b></td><td style="white-space:nowrap">${esc(r.sched).replace(/／/g, '<br>')}</td><td>${r.punches.map(p => `${KIND[p.kind]} ${p.at}${p.source !== 'phone' ? '（' + esc(p.source) + '）' : ''}`).join('<br>') || '—'}</td>
      <td><span class="tag ${/上班中/.test(r.status) ? 't-ok' : /還沒打卡/.test(r.status) ? 't-warn' : /排休/.test(r.status) ? 't-blue' : ''}">${esc(r.status)}</span>${r.lates.map(l => `<span class="tag t-warn">晚 ${l[2]} 分</span>`).join('')}${r.issues.map(i => `<span class="tag t-warn">${esc(i)}</span>`).join('')}</td></tr>`).join('')}</table></div></div>`;
  if (d.journal && d.journal.length) h += `<div class="card"><h3>今天的我很棒日誌</h3>${d.journal.map(j => `<span class="tag ${j.wrote ? 't-ok' : 't-warn'}" style="cursor:pointer" onclick="openJournal(${jsq(j.name)})">${esc(j.name)} ${j.wrote ? '寫了' : '還沒寫'}${j.unread ? ' · ' + j.unread + ' 則沒看' : ''}</span>`).join('')}</div>`;
  $('#main').innerHTML = h;
}
async function openJournal(name) { const ts = await api('/api/journal/threads'); const t = ts.find(x => x.name === name); JU = t ? t.id : 0; go('journal'); }
async function bPay() {
  const d = await api('/api/boss/payroll?month=' + BM), rs = d.rows, st = d.status ? d.status.status : '試算中';
  const S = k => rs.reduce((a, r) => a + (r[k] || 0), 0);
  let h = hero('薪資', `${+BM.slice(5)} 月薪資。`, '打卡就是一切：只算打卡（含核准的補登）。點名字看每天明細。');
  h += `<div class="btns" style="margin:0 0 20px;align-items:center"><input type="month" value="${BM}" style="width:auto" onchange="BM=this.value;LOAD.boss()">
    <span class="tag ${st === '已發薪' ? 't-ok' : st === '已定案' ? 't-blue' : 't-warn'}">${st}</span>
    <a class="btn sec sm" href="/boss/slips?month=${BM}" ${matchMedia('(display-mode: standalone)').matches || navigator.standalone ? '' : 'target="_blank"'}>產生簽收單</a>
    ${st === '試算中' ? `<button class="btn gray sm" onclick="setMonth('已定案')">定案</button>` : ''}${st !== '已發薪' ? `<button class="btn gray sm" onclick="setMonth('已發薪')">標記已發薪</button>` : ''}
    ${st !== '試算中' ? `<button class="btn gray sm" onclick="setMonth('試算中')">改回試算中</button>` : ''}</div>
  ${(d.labor_calendar || []).map(w => `<div class="banner red" data-labor-cal>勞動曆提醒：${esc(w)}</div>`).join('')}
  ${st !== '試算中' ? `<div class="banner ok">${st}：數字已經固定（存了一份），之後補登、調薪、停用都不會改到這個月。要改請先按「改回試算中」。${rs.some(r => r.adv_left > 0) ? '沒扣完的預支已經轉到下個月。' : ''}</div>` : ''}
  <div class="grid"><div class="tile stat"><div class="k">應發合計</div><div class="v">${fmt(S('base'))}</div></div><div class="tile stat"><div class="k">預支扣回</div><div class="v">${fmt(S('ded'))}</div></div>
    <div class="tile stat"><div class="k">加班與假日加給</div><div class="v">${fmt(S('ot_pay') + S('rest_pay') + S('hol_pay'))}</div></div><div class="tile stat"><div class="k">實發合計</div><div class="v">${fmt(S('net'))}</div></div></div>
  <div class="card"><div class="tbl"><table>
    <tr><th>夥伴</th><th>計薪</th><th class="r">出勤</th><th class="r">時數</th><th class="r">本薪</th><th class="r">預支</th><th class="r">遲到</th><th class="r">調整</th><th class="r">實發</th></tr>
    ${rs.map((r, i) => `<tr><td><a class="click" onclick="document.getElementById('pd${i}').hidden^=1"><b>${esc(r.name)}</b></a>
        ${r.issues.length ? `<span class="tag t-warn">漏打卡 ${r.issues.length}</span>` : ''}${r.over.length ? `<span class="tag t-red">曠職 ${r.over.length}</span>` : ''}${(r.flags || []).length ? `<span class="tag t-blue">公休／排休日有打卡 ${r.flags.length}</span>` : ''}${(r.law_flags || []).length ? `<span class="tag t-red">勞基法提醒 ${r.law_flags.length}</span>` : ''}</td>
      <td>${esc(r.mode)}<span class="s">${r.kind === 'hourly' ? '' : r.kind === 'fixed' ? fmt(r.amount) + (r.punch ? '' : '，不用打卡') : '月薪 ' + fmt(r.amount) + '，月休 ' + r.off_days}</span></td>
      <td class="r">${r.days} 天</td><td class="r">${(r.mins / 60).toFixed(1)}</td><td class="r">${fmt(r.base)}${r.ot_pay + r.rest_pay + r.hol_pay ? `<span class="s">含加給 ${fmt(r.ot_pay + r.rest_pay + r.hol_pay)}</span>` : ''}</td><td class="r">${r.ded ? fmt(-r.ded) : '0'}${r.ins_ded ? `<span class="s">勞健保 ${fmt(-r.ins_ded)}</span>` : ''}${r.adv_left > 0 ? `<span class="s">沒扣完 ${fmt(r.adv_left)}，下月扣</span>` : ''}</td>
      <td class="r">${r.late_n} 次</td><td class="r">${r.adj ? fmt(r.adj) : '0'}</td><td class="r"><b>${fmt(r.net)}</b></td></tr>
      <tr id="pd${i}" hidden><td colspan="9" style="background:var(--bg)">${(r.law_flags || []).map(f => `<div class="banner warn">${esc(f)}</div>`).join('')}${r.per_day.map(x => `<div class="row" style="padding:7px 0"><div>${md(x.day)}（${wkOf(x.day)}）
        ${x.segs.map(g => g[0] + '–' + g[1]).join('　') || '—'} <span class="small">班：${esc(x.sched)}</span>
        ${x.lates.map(l => `<span class="tag t-warn">晚 ${l[2]} 分</span>`).join('')}${x.issues.map(s => `<span class="tag t-warn">${esc(s)}</span>`).join('')}${x.flag ? `<span class="tag t-blue">${esc(x.flag)}</span>` : ''}${{ rest: '<span class="tag t-warn">休息日出勤</span>', holiday: '<span class="tag t-warn">國定假日出勤</span>', regular_off: '<span class="tag t-red">例假出勤</span>' }[x.type] || ''}</div><b>${(x.mins / 60).toFixed(2)} H</b></div>`).join('') || '<span class="muted">這個月沒有打卡</span>'}</td></tr>`).join('')}
  </table></div></div>
  <div class="small">計薪依 config/labor_rules.toml（勞基法預設值）與 config/labor_calendar/（每年的國定假日、基本工資）：每天超過 8 小時算加班；每週第 6 個出勤日算休息日；國定假日出勤加倍。遲到的分鐘本來就不算工時，不另外扣款。以上原則上仍請依最新法規核對。</div>`;
  $('#main').innerHTML = h;
}
async function setMonth(status) {
  const paid = status === '已發薪' ? prompt('發薪日期（例：2026-11-05）', todayStr()) : null; if (status === '已發薪' && !paid) return;
  if (status === '試算中' && !confirm('改回試算中？數字會照現在的打卡、設定重算，下個月的預支結轉也會撤銷。')) return;
  try { await api('/api/boss/month/set', { month: BM, status, paid_on: paid }); LOAD.boss(); } catch (e) { alert(e.message); }
}
function bFix(fixes) {
  const p = fixes.filter(f => f.status === '待審'), o = fixes.filter(f => f.status !== '待審');
  $('#main').innerHTML = hero('補登', '補登審核。', '夥伴忘了打卡申請的補登，你核准才算。') + `<div class="card"><h3>待審（${p.length}）</h3>${p.map(f => `<div class="row"><div><div class="n">${esc(f.name)} · ${md(f.day)}（${wkOf(f.day)}）${KIND[f.kind]} ${f.time}</div>
      <div class="m">原因：${esc(f.reason)} · 申請 ${f.created.slice(5, 16)}</div></div>
      <div style="display:flex;gap:6px"><button class="btn green sm" onclick="decide(${f.id},true)">核准</button><button class="btn gray sm" onclick="decide(${f.id},false)">退回</button></div></div>`).join('') || '<div class="muted">沒有待審的補登。</div>'}</div>
    <details class="fold"><summary>處理過的<small>${o.length} 筆</small></summary><div class="in">${o.map(f => `<div class="row"><div><div class="n">${esc(f.name)} · ${md(f.day)} ${KIND[f.kind]} ${f.time}</div>
      <div class="m">${esc(f.reason)}${f.decide_note ? ' · ' + esc(f.decide_note) : ''}</div></div><span class="tag ${f.status === '核准' ? 't-ok' : 't-warn'}">${f.status}</span></div>`).join('') || '<div class="muted">沒有</div>'}</div></details>`;
}
async function decide(id, approve) { const note = approve ? '' : (prompt('退回原因（會讓夥伴看到）') || ''); if (!approve && !note) return; await api('/api/boss/fix/decide', { id, approve, note }); LOAD.boss(); }
async function bPunches() {
  const st = await api('/api/boss/settings'); const ppl = st.people.filter(p => p.kind);
  const ps = await api(`/api/boss/punches?month=${BM}&user_id=${BU}`);
  $('#main').innerHTML = hero('打卡', '打卡紀錄。', '紙本打卡卡、忘了打又沒申請的，在這裡補，一定要寫原因。') + `<div class="g2" style="margin-bottom:16px"><select onchange="BU=+this.value;LOAD.boss()"><option value="0">全部夥伴</option>${ppl.map(p => `<option value="${p.id}" ${p.id === BU ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select>
    <input type="month" value="${BM}" onchange="BM=this.value;LOAD.boss()"></div>
   <details class="fold"><summary>手動新增一筆打卡</summary><div class="in">
     <div class="g2"><div><label>夥伴</label><select id="pa_u">${ppl.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></div><div><label>日期</label><input type="date" id="pa_d" value="${todayStr()}"></div>
     <div><label>時間</label><input type="time" id="pa_t"></div><div><label>上班／下班</label><select id="pa_k"><option value="in">上班</option><option value="out">下班</option></select></div></div>
     <label>原因</label><input id="pa_r" placeholder="例：照紙本打卡卡補登"><button class="btn" style="margin-top:14px" onclick="addPunch()">新增</button><div id="pa_m"></div></div></details>
   <div class="card"><div class="tbl"><table><tr><th>時間</th><th>夥伴</th><th>上下班</th><th>來源</th><th>位置</th><th></th></tr>
    ${ps.map(p => `<tr style="${p.voided ? 'opacity:.45;text-decoration:line-through' : ''}"><td>${md(p.at)} ${p.at.slice(11, 16)}</td><td>${esc(p.name)}</td><td>${KIND[p.kind]}</td>
      <td>${esc(p.source === 'phone' ? '手機' : p.source)}${p.note ? '<span class="s">' + esc(p.note) + '</span>' : ''}${p.voided ? '<span class="s">作廢：' + esc(p.void_reason || '') + '</span>' : ''}</td>
      <td>${p.dist != null ? p.dist + ' 公尺' : '—'}${p.acc ? '<span class="s">誤差 ' + Math.round(p.acc) + '</span>' : ''}</td>
      <td>${p.voided ? '' : `<button class="btn gray sm" onclick="voidPunch(${p.id})">作廢</button>`}</td></tr>`).join('') || '<tr><td colspan="6" class="muted">這個月沒有打卡</td></tr>'}</table></div></div>`;
}
async function addPunch() { try { await api('/api/boss/punch/add', { user_id: +$('#pa_u').value, day: $('#pa_d').value, time: $('#pa_t').value, kind: $('#pa_k').value, reason: $('#pa_r').value }); LOAD.boss(); } catch (e) { msgOk('#pa_m', e); } }
async function voidPunch(id) { const r = prompt('作廢原因（必填）'); if (!r) return; await api('/api/boss/punch/void', { id, reason: r }); LOAD.boss(); }
async function bSet() {
  const d = await api('/api/boss/settings?month=' + BM), S = d.settings, ppl = d.people;
  const wc = (S.weekly_closed || '').split(','), KINDS = { monthly: '月薪', hourly: '時薪', fixed: '固定月薪' };
  const cur = uid => d.shifts.filter(s => s.user_id === uid);
  $('#main').innerHTML = hero('設定', '打卡與薪資設定。', '這裡改了，夥伴的打卡頁、薪資、簽收單都會跟著變。') + `
  <details class="fold" open><summary>店家位置與打卡範圍<small>${S.store_lat ? '已校正' : '還沒校正'}</small></summary><div class="in">
    <div class="muted">${S.store_lat ? `目前：${(+S.store_lat).toFixed(5)}, ${(+S.store_lng).toFixed(5)}` : '還沒設定。人在店裡時按下面按鈕，用你手機的位置當店家位置。'}</div>
    <button class="btn" style="margin-top:12px" onclick="setStore()">我現在在店裡，用我的位置設為店家</button><div id="st_m"></div>
    <div class="g2"><div><label>打卡範圍（公尺）</label><input id="s_radius" value="${S.radius}" inputmode="numeric"></div><div><label>定位誤差上限（公尺）</label><input id="s_acc" value="${S.max_acc}" inputmode="numeric"></div></div>
    <button class="btn gray sm" style="margin-top:14px" onclick="saveSettings('#sr_m')">儲存範圍</button><div id="sr_m"></div></div></details>
  <details class="fold"><summary>公休</summary><div class="in"><label>每週固定公休</label><div style="display:flex;gap:14px;flex-wrap:wrap">${'一二三四五六日'.split('').map((n, i) => `<label class="chk" style="margin:0"><input type="checkbox" class="wkc" value="${i}" ${wc.includes(String(i)) ? 'checked' : ''}>週${n}</label>`).join('')}</div>
    <button class="btn gray sm" style="margin-top:12px" onclick="saveSettings('#sw_m')">儲存每週公休</button><div id="sw_m"></div>
    <h3 style="margin-top:20px">特別公休日</h3>${d.closed.map(c => `<div class="row"><div>${c.day}（${wkOf(c.day)}）${esc(c.reason || '')}</div><button class="btn gray sm" onclick="closedDay('${c.day}',false)">移除</button></div>`).join('') || '<div class="muted">沒有</div>'}
    <div class="g2"><div><label>日期</label><input type="date" id="cd_d"></div><div><label>原因</label><input id="cd_r" placeholder="例：颱風、盤點"></div></div><button class="btn gray sm" style="margin-top:12px" onclick="closedDay($('#cd_d').value,true)">加入公休</button></div></details>
  <details class="fold"><summary>遲到提醒</summary><div class="in"><div class="muted">遲到的分鐘不算工時（等於依實際分鐘比例計薪），系統不另外罰扣。晚太多的會標「需確認」給你看。</div><div class="g2">
    <div><label>晚超過幾分鐘標「需確認」</label><input id="s_abs" value="${S.absent_over}" inputmode="numeric"></div>
    <div><label>晚上幾點提醒遲到的人明天準時</label><input type="time" id="s_lrem" value="${S.late_remind || '20:30'}"></div></div>
    <button class="btn" style="margin-top:14px" onclick="saveSettings('#ss_m')">儲存</button><div id="ss_m"></div></div></details>
  <details class="fold"><summary>夥伴薪資</summary><div class="in"><div class="muted">月薪：做滿 (當月天數−月休−國定假日)×8 小時領全額，沒做滿依出勤分鐘比例。時薪：分鐘×時薪。固定月薪：不看打卡。加班、休息日、國定假日依勞基法另計。勞保、健保自付額請照勞保局、健保署級距表填。</div><div class="tbl"><table>
    <tr><th>夥伴</th><th>計薪</th><th>金額</th><th>月休</th><th>勞保自付</th><th>健保自付</th><th>要打卡</th><th></th></tr>
    ${ppl.filter(p => p.role !== 'admin' || p.kind).map(p => `<tr style="${p.active ? '' : 'opacity:.45'}"><td><b>${esc(p.name)}</b></td>
      <td><select id="pk_${p.id}" style="width:auto">${Object.entries(KINDS).map(([k, n]) => `<option value="${k}" ${p.kind === k ? 'selected' : ''}>${n}</option>`).join('')}</select></td>
      <td><input id="pa_${p.id}" value="${p.amount ?? ''}" inputmode="numeric" style="width:100px"></td><td><input id="po_${p.id}" value="${p.off_days ?? 8}" inputmode="numeric" style="width:64px"></td><td><input id="pli_${p.id}" value="${p.li_self ?? 0}" inputmode="numeric" style="width:80px"></td><td><input id="phi_${p.id}" value="${p.hi_self ?? 0}" inputmode="numeric" style="width:80px"></td>
      <td><input type="checkbox" id="pp_${p.id}" style="width:22px;height:22px" ${p.kind ? (p.punch ? 'checked' : '') : 'checked'}></td><td><button class="btn gray sm" onclick="saveProfile(${p.id})">${p.kind ? '儲存' : '設定'}</button></td></tr>`).join('')}</table></div></div></details>
  <details class="fold"><summary>班表（上班時間）</summary><div class="in"><div class="muted">改班就「新增一筆、填生效日」，舊的會保留，算遲到時照當天有效的那筆。排休在「班表」頁。</div>
    ${ppl.filter(p => p.kind && p.kind !== 'fixed').map(p => { const s = cur(p.id); return `<div class="row"><div><div class="n">${esc(p.name)}</div>${s.map((x, i) => `<div class="m">${i ? '' : '<b>現在 </b>'}${x.effective} 起：${x.days ? '週' + x.days.split(',').map(i => '一二三四五六日'[+i]).join('') + ' ' : ''}${x.s1}–${x.e1}${x.s2 ? ' ／ ' + x.s2 + '–' + x.e2 : ''}${x.note ? ' · ' + esc(x.note) : ''} <a class="click" onclick="delShift(${x.id})">刪除</a></div>`).join('') || '<div class="m">還沒有班表</div>'}</div></div>`; }).join('')}
    <h3 style="margin-top:18px">新增班表</h3><div class="g2"><div><label>夥伴</label><select id="sh_u">${ppl.filter(p => p.kind && p.kind !== 'fixed').map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></div><div><label>生效日</label><input type="date" id="sh_e" value="${todayStr()}"></div>
    <div><label>第一段上班</label><input type="time" id="sh_s1"></div><div><label>第一段下班</label><input type="time" id="sh_e1"></div><div><label>第二段上班（選填）</label><input type="time" id="sh_s2"></div><div><label>第二段下班（選填）</label><input type="time" id="sh_e2"></div></div>
    <label>哪幾天有班</label><div style="display:flex;gap:14px;flex-wrap:wrap">${'一二三四五六日'.split('').map((n, i) => `<label class="chk" style="margin:0"><input type="checkbox" class="shd" value="${i}" checked>週${n}</label>`).join('')}</div>
    <label>備註</label><input id="sh_n" placeholder="例：店長 10/5 公告調班"><button class="btn" style="margin-top:14px" onclick="addShift()">新增</button><div id="sh_m"></div></div></details>
  <details class="fold"><summary>預支<small>${+BM.slice(5)} 月 ${d.advances.filter(a => !a.voided).length} 筆</small></summary><div class="in">${d.advances.map(a => `<div class="row" style="${a.voided ? 'opacity:.45;text-decoration:line-through' : ''}"><div><div class="n">${esc(a.name)} ${fmt(a.amount)}</div><div class="m">${a.day} · ${+(a.pay_month || a.day).slice(5, 7)} 月薪資扣${a.exp_id ? ' · 已記帳務支出' : ''}${a.note ? ' · ' + esc(a.note) : ''}</div></div>${a.voided ? '' : `<button class="btn gray sm" onclick="voidAdv(${a.id})">作廢</button>`}</div>`).join('') || '<div class="muted">這個月沒有預支</div>'}
    <div class="g3"><div><label>夥伴</label><select id="ad_u">${ppl.filter(p => p.kind).map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></div><div><label>日期</label><input type="date" id="ad_d" value="${todayStr()}"></div><div><label>金額</label><input id="ad_a" inputmode="numeric"></div></div>
    <div class="g2"><div><label>從哪個月的薪資扣</label><select id="ad_pm"><option value="">自動（1–5 號預支從上個月扣）</option>${[0, 1].map(k => { const x = new Date(); x.setDate(1); x.setMonth(x.getMonth() - k); const v = x.getFullYear() + '-' + String(x.getMonth() + 1).padStart(2, '0'); return `<option value="${v}">${+v.slice(5)} 月薪資</option>`; }).join('')}</select></div>
      <div><label class="chk" style="margin-top:30px"><input type="checkbox" id="ad_dr" checked> 從店內抽屜拿現金（自動記一筆帳務支出）</label></div></div>
    <label>備註</label><input id="ad_n" placeholder="例：先簽預支單"><button class="btn" style="margin-top:14px" onclick="addAdv()">登記預支</button><div id="ad_m"></div></div></details>
  <details class="fold"><summary>薪資調整<small>例：曠職扣款、補貼</small></summary><div class="in">${d.adjustments.map(a => `<div class="row" style="${a.voided ? 'opacity:.45;text-decoration:line-through' : ''}"><div><div class="n">${esc(a.name)} ${a.amount > 0 ? '＋' : ''}${fmt(a.amount)}</div><div class="m">${a.month} · ${esc(a.reason)}</div></div>${a.voided ? '' : `<button class="btn gray sm" onclick="voidAdj(${a.id})">作廢</button>`}</div>`).join('') || '<div class="muted">這個月沒有調整</div>'}
    <div class="g3"><div><label>夥伴</label><select id="aj_u">${ppl.filter(p => p.kind).map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></div><div><label>月份</label><input type="month" id="aj_m" value="${BM}"></div><div><label>金額（扣錢打負數）</label><input id="aj_a" placeholder="-1500"></div></div>
    <label>原因</label><input id="aj_r" placeholder="例：10/12 曠職未說明扣三日"><button class="btn" style="margin-top:14px" onclick="addAdj()">新增調整</button><div id="aj_mm"></div></div></details>`;
}
async function setStore() { try { const c = await getPos(); await api('/api/boss/store/set', { lat: c.latitude, lng: c.longitude, acc: c.accuracy }); msgOk('#st_m'); LOAD.boss(); } catch (e) { msgOk('#st_m', e); } }
async function saveSettings(m) {
  const wc = [...document.querySelectorAll('.wkc')].filter(x => x.checked).map(x => x.value).join(',');
  try { await api('/api/boss/settings/save', { radius: $('#s_radius').value, max_acc: $('#s_acc').value, weekly_closed: wc, absent_over: $('#s_abs').value, late_remind: $('#s_lrem').value }); msgOk(m); } catch (e) { msgOk(m, e); }
}
async function closedDay(day, on) { try { await api('/api/boss/closed/save', { day, on, reason: on ? $('#cd_r').value : '' }); LOAD.boss(); } catch (e) { alert(e.message); } }
async function saveProfile(id) { try { await api('/api/boss/profile/save', { user_id: id, kind: $('#pk_' + id).value, amount: +$('#pa_' + id).value, off_days: +$('#po_' + id).value, li_self: +$('#pli_' + id).value, hi_self: +$('#phi_' + id).value, punch: $('#pp_' + id).checked }); LOAD.boss(); } catch (e) { alert(e.message); } }
async function addShift() { try { await api('/api/boss/shift/save', { user_id: +$('#sh_u').value, effective: $('#sh_e').value, s1: $('#sh_s1').value, e1: $('#sh_e1').value, s2: $('#sh_s2').value, e2: $('#sh_e2').value, note: $('#sh_n').value, days: [...document.querySelectorAll('.shd')].filter(x => x.checked).map(x => +x.value) }); LOAD.boss(); } catch (e) { msgOk('#sh_m', e); } }
async function delShift(id) { if (confirm('刪除這筆班表？')) { await api('/api/boss/shift/delete', { id }); LOAD.boss(); } }
async function addAdv() { try { await api('/api/boss/advance/save', { user_id: +$('#ad_u').value, day: $('#ad_d').value, amount: +$('#ad_a').value, note: $('#ad_n').value, pay_month: $('#ad_pm').value || null, drawer: $('#ad_dr').checked }); LOAD.boss(); } catch (e) { msgOk('#ad_m', e); } }
async function voidAdv(id) { if (confirm('作廢這筆預支？')) { await api('/api/boss/advance/void', { id }); LOAD.boss(); } }
async function addAdj() { try { await api('/api/boss/adjust/save', { user_id: +$('#aj_u').value, month: $('#aj_m').value, amount: +$('#aj_a').value, reason: $('#aj_r').value }); LOAD.boss(); } catch (e) { msgOk('#aj_mm', e); } }
async function voidAdj(id) { if (confirm('作廢這筆調整？')) { await api('/api/boss/adjust/void', { id }); LOAD.boss(); } }
async function bAcct() {
  const [us, regs, pfs] = await Promise.all([api('/api/users'), api('/api/boss/registrations'), api('/api/profiles')]);
  const PF = Object.fromEntries(pfs.map(p => [p.id, p]));
  const ROLE = { admin: '老闆', manager: '店長', staff: '夥伴' };
  let h = hero('帳號', '夥伴帳號。', '新夥伴自己註冊，你在這裡核准；店長可以記帳、發公告、排休。');
  if (regs.length) h += `<div class="card"><h3>等你審核（${regs.length}）</h3>${regs.map(r => `<div class="row"><div><div class="n">${esc(r.name)} <span class="small">帳號 ${esc(r.username)}</span></div>
      <div class="m">應徵 ${esc(r.position || '—')}${r.phone ? ' · ' + esc(r.phone) : ''} · ${md(r.created)} 註冊${r.reg_note ? ' · 「' + esc(r.reg_note) + '」' : ''}</div></div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end"><button class="btn green sm" onclick="regDecide(${r.id},true,${jsq(r.position || '')})">核准</button><button class="btn gray sm" onclick="regDecide(${r.id},false)">不核准</button></div></div>`).join('')}
      <div class="small" style="margin-top:10px">核准後，夥伴用自己註冊的帳號密碼登入。記得到「設定」設薪資、班表，才能打卡。</div></div>`;
  h += `<div class="card"><div class="tbl"><table><tr><th>名字</th><th>帳號</th><th>角色</th><th>崗位</th><th>外送</th><th>撥號目標</th><th></th></tr>
   ${us.map(u => `<tr style="${u.active ? '' : 'opacity:.45'}"><td style="white-space:nowrap"><label title="上傳形象照" style="cursor:pointer">${avatar(PF[u.id] || { id: u.id, name: u.name }, 34)}<input type="file" accept="image/*" hidden onchange="bossPhoto(${u.id},this)"></label> ${esc(u.name)}</td><td>${esc(u.username)}</td>
     <td>${u.id === ME.id ? '老闆' : `<select style="width:auto" onchange="saveUser({id:${u.id},role:this.value})">${['staff', 'manager'].map(r => `<option value="${r}" ${u.role === r ? 'selected' : ''}>${r === 'manager' && u.title ? u.title : ROLE[r]}</option>`).join('')}${u.role === 'admin' ? '<option value="admin" selected>老闆</option>' : ''}</select>`}</td>
     <td>${u.role === 'staff' ? `<select style="width:auto" onchange="rotate(${u.id},${jsq(u.name)},this)"><option value="">（未設定）</option>${ME.positions.map(p => `<option ${u.position === p ? 'selected' : ''}>${p}</option>`).join('')}</select>` : '—'}</td>
     <td><input type="checkbox" style="width:22px;height:22px" ${u.rider ? 'checked' : ''} onchange="saveUser({id:${u.id},rider:this.checked})"></td>
     <td><input style="width:76px" value="${u.target}" onchange="saveUser({id:${u.id},target:+this.value})"></td>
     <td style="white-space:nowrap"><button class="btn gray sm" onclick="resetPw(${u.id})">重設密碼</button>
     ${u.id !== ME.id ? `<button class="btn sm ${u.active ? 'gray' : 'sec'}" onclick="saveUser({id:${u.id},active:${!u.active}})">${u.active ? '停用' : '啟用'}</button>
       <button class="btn red sm" onclick="removeUser(${u.id},${jsq(u.name)})">移除</button>` : ''}</td></tr>`).join('')}</table></div>
   <div class="small" style="margin-top:10px">點頭像可以幫夥伴上傳形象照。崗位輪調：夥伴會收到通知，系統會補上新崗位的必讀（看完才能用其他功能，打卡不受影響）。停用：暫時不能登入，名單還在。移除：從所有名單拿掉（打卡和薪資紀錄會留著，帳務照算）。重設密碼後，夥伴下次登入要先設自己的密碼。</div></div>
  <details class="fold"><summary>老闆直接開帳號</summary><div class="in"><div class="g2"><div><label>名字</label><input id="nu_name"></div><div><label>登入帳號</label><input id="nu_user" autocapitalize="off"></div>
   <div><label>密碼（至少 6 碼）</label><input id="nu_pw"></div><div><label>每日撥號目標</label><input id="nu_t" value="50" inputmode="numeric"></div></div>
   <button class="btn" style="margin-top:14px" onclick="addUser()">新增</button><div id="uerr" class="err"></div></div></details>
  <details class="fold"><summary>分配名單</summary><div class="in"><div class="muted">先到「開發 › 名單」篩好，再回來按分配，會把那些筆全部分給這個人。</div>
   <div class="g2" style="margin-top:12px"><select id="asg_u"><option value="">（不分配）</option>${us.filter(u => u.active).map(u => `<option value="${u.id}">${esc(u.name)}</option>`).join('')}</select>
   <button class="btn" onclick="assign()">分配目前篩出的 ${LEADS.length} 筆</button></div></div></details>
  <details class="fold"><summary>新增一筆名單</summary><div class="in"><div class="g2"><div><label>單位名稱</label><input id="nl_name"></div><div><label>電話</label><input id="nl_phone"></div>
   <div><label>分類</label><input id="nl_cat"></div><div><label>區域</label><input id="nl_area"></div></div>
   <label>地址</label><input id="nl_addr"><button class="btn" style="margin-top:14px" onclick="addLead()">新增</button><div id="lerr2"></div></div></details>
  <details class="fold"><summary>備份與匯出</summary><div class="in"><div class="btns" style="margin-top:0"><button class="btn sec sm" onclick="doBackup()">立即備份</button>
   <a class="btn sec sm" href="/api/export?kind=leads">匯出名單 CSV</a><a class="btn sec sm" href="/api/export?kind=calls">匯出通話 CSV</a></div>
   <div class="small" style="margin-top:10px">系統每 12 小時自動備份一次，保留最近 60 份。</div><div id="berr" class="small"></div></div></details>`;
  $('#main').innerHTML = h;
}
async function regDecide(id, approve, pos) {
  if (!approve && !confirm('不核准這位？')) return;
  try { await api('/api/boss/registration/decide', { id, approve, role: 'staff', rider: pos === '外送' }); if (approve && pos) await api('/api/user/save', { id, position: pos === 'PT' ? '外場' : pos }).catch(() => { }); await refreshBadges(); LOAD.boss(); } catch (e) { alert(e.message); }
}
async function rotate(id, name, sel) {
  if (!sel.value) return;
  if (!confirm(`${name} 的崗位調到「${sel.value}」？\n會通知他，並補上新崗位的必讀。`)) { LOAD.boss(); return; }
  saveUser({ id, position: sel.value });
}
async function saveUser(d) { try { await api('/api/user/save', d); LOAD.boss(); } catch (e) { alert(e.message); LOAD.boss(); } }
async function removeUser(id, name) { if (!confirm(`移除 ${name}？
移除後不能登入，也不會出現在打卡、日誌、班表、薪資設定裡；以前的打卡和薪資紀錄會留著。`)) return; saveUser({ id, removed: true }); }
async function resetPw(id) { const p = prompt('新密碼（至少 6 碼）'); if (p) saveUser({ id, password: p }); }
async function addUser() { try { await api('/api/user/save', { name: $('#nu_name').value, username: $('#nu_user').value, password: $('#nu_pw').value, target: $('#nu_t').value }); LOAD.boss(); } catch (e) { $('#uerr').textContent = e.message; } }
async function assign() { if (!LEADS.length) return alert('先到「開發 › 名單」篩出要分配的名單'); if (!confirm(`把 ${LEADS.length} 筆分給這個人？`)) return; const r = await api('/api/assign', { ids: LEADS.map(l => l.id), user_id: $('#asg_u').value }); alert('已分配 ' + r.n + ' 筆'); }
async function addLead() { try { await api('/api/lead/new', { name: $('#nl_name').value, phone: $('#nl_phone').value, category: $('#nl_cat').value, area: $('#nl_area').value, address: $('#nl_addr').value, data_status: '待核' }); msgOk('#lerr2'); } catch (e) { msgOk('#lerr2', e); } }
async function doBackup() { const r = await api('/api/backup', {}); $('#berr').textContent = '已備份：' + r.file; }
