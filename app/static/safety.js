/* 食安紀錄（老闆 10/6）：冰箱溫度、瓦斯安全、油品管理、廢油回收、廁所清潔。照總部紙本表格的欄位；冰箱、廢油記錄當下一定要現場拍照。 */
let SF = null, SM2 = todayStr().slice(0, 7), SPHOTO = null;
SUB.safety = 'fridge';
LOAD.safety = async function () {
  SF = await api('/api/safety?kind=' + SUB.safety + '&month=' + SM2);
  localNav('食安紀錄', [['fridge', '冰箱'], ['gas', '瓦斯'], ['oil', '油品'], ['wasteoil', '廢油'], ['toilet', '廁所']], SUB.safety, 'safetyTab', ['記一筆', 'safetyForm()']);
  const K = SF.kind, sub = {
    fridge: `標準：冷凍 −10 ～ −18 度、冷藏 3 ～ 7 度。每天早上開店、下班前各量一次（店長 10/8：中午、下午一直開開關關，量了不準），每台冰箱都要記，一定要拍溫度顯示的照片。下班量之前，冰箱門關好一陣子再量。`,
    gas: '早上 8 點開店前、晚上打烊時各檢查一次。沒做到的項目會通知店長和老闆。',
    oil: `每天記誰濾油、誰換油、有沒有洗油炸機，店長複檢。極性值到 ${SF.polar_max}% 一定要換油。`,
    wasteoil: '廢油被回收的時候記一筆，一定要拍回收單（或回收廠商簽名）的照片。',
    toilet: '09:00、11:00、13:00、15:00、17:00、19:00 各巡一次，洗好就記。'
  }[K];
  let h = hero('食安', SF.kinds[K] + '。', sub);
  const t = SF.today, miss = [];
  const hr = new Date().getHours();
  if (K === 'fridge') { if (t.fridge_am.length && hr >= 8) miss.push('早上：' + t.fridge_am.join('、')); if (t.fridge_pm.length && hr >= 19) miss.push('下班：' + t.fridge_pm.join('、')); }
  if (K === 'gas') { if (t.gas_am.length && hr >= 8) miss.push('早上瓦斯檢查'); if (t.gas_pm.length && hr >= 19) miss.push('打烊瓦斯檢查'); }
  if (miss.length) h += `<div class="banner warn" onclick="safetyForm()">今天還沒記：${esc(miss.join('；'))}　點這裡記 ›</div>`;
  h += `<div class="btns" style="margin:0 0 14px;align-items:center"><input type="month" value="${SM2}" style="width:auto" onchange="SM2=this.value;LOAD.safety()">
    ${SF.can_review && SF.rows.some(r => !r.reviewed_by) ? `<button class="btn sec sm" onclick="safetyReview()">複檢這個月（${SF.rows.filter(r => !r.reviewed_by).length} 筆）</button>` : ''}</div>`;
  h += ({ fridge: sfFridge, gas: sfGas, oil: sfOil, wasteoil: sfWaste, toilet: sfToilet })[K]();
  $('#main').innerHTML = h;
};
function safetyTab(k) { SUB.safety = k; LOAD.safety(); }
const sfDays = () => { const [y, m] = SM2.split('-').map(Number), n = new Date(y, m, 0).getDate(), td = todayStr(); return Array.from({ length: n }, (_, i) => SM2 + '-' + String(i + 1).padStart(2, '0')).filter(d => d <= td); };
const sfCell = (r, txt) => r ? `<span class="${r.alert ? 'sfbad' : ''}" title="${esc(r.alert || '')}">${txt}</span>${r.photo ? ` <a class="sfph" onclick="zoom('/api/safety/photo?id=${r.id}')">📷</a>` : ''}${r.reviewed_by ? '<span class="sfok" title="已複檢">✓</span>' : ''}` : '<span class="muted">—</span>';
const sfWho = r => r ? `<span class="small">${esc(r.who)}</span>` : '';
const sfDel = r => r && (SF.can_review || (r.user_id === ME.id && r.day === todayStr())) ? ` <a class="small" onclick="safetyDel(${r.id})">刪</a>` : '';
function sfFridge() {
  const ts = SF.targets.filter(x => x.kind === 'fridge'), days = sfDays().reverse();
  return ts.map(f => {
    const g = (d, s) => SF.rows.find(r => r.target_id === f.id && r.day === d && r.slot === s);
    const v = r => r ? (f.has_freezer ? `${r.data.freeze ?? '—'} ／ ` : '') + `${r.data.chill ?? '—'}` : '';
    return `<div class="card"><h3>${esc(f.name)}<span class="small" style="font-weight:400;margin-left:8px">${f.has_freezer ? '冷凍 ／ 冷藏（度）' : '冷藏（度）'}</span></h3><div class="tbl"><table>
      <tr><th>日期</th><th>上午</th><th>填表人</th><th>下班</th><th>填表人</th></tr>
      ${days.map(d => { const a = g(d, '上午'), b = g(d, '下班'); return `<tr><td>${md(d)}（${wkOf(d)}）</td><td>${sfCell(a, v(a))}${sfDel(a)}</td><td>${sfWho(a)}</td><td>${sfCell(b, v(b))}${sfDel(b)}</td><td>${sfWho(b)}</td></tr>`; }).join('') || '<tr><td colspan="5" class="muted">這個月還沒有紀錄</td></tr>'}
      </table></div></div>`;
  }).join('') + (SF.can_review ? `<details class="fold"><summary>冰箱清單（店長、老闆）</summary><div class="in">${ts.map(f => `<div class="row"><div class="n">${esc(f.name)}</div><span class="small">${f.has_freezer ? '有冷凍' : '只有冷藏'}</span><button class="btn gray sm" onclick="sfTargetDel(${f.id},${jsq(f.name)},${f.has_freezer})">拿掉</button></div>`).join('')}
    <div class="g2" style="margin-top:10px"><div><label>新增冰箱名稱</label><input id="sf_tn" placeholder="例：2 門冰箱"></div><div><label class="chk" style="margin-top:30px"><input type="checkbox" id="sf_tf" checked> 有冷凍</label></div></div>
    <button class="btn sec sm" style="margin-top:10px" onclick="sfTargetAdd()">新增</button></div></details>` : '');
}
function sfGas() {
  const days = sfDays().reverse(), g = (d, s) => SF.rows.find(r => r.day === d && r.slot === s);
  const am = r => r ? `${r.data.pressure ?? '—'} kg ${SF.gas_am.filter(x => x[2] === 'chk').map(x => r.data[x[0]] ? '✓' : '<b class="sfbad">✗</b>').join('')}` : '';
  const pm = r => r ? `${SF.gas_pm.filter(x => x[2] === 'chk').map(x => r.data[x[0]] ? '✓' : '<b class="sfbad">✗</b>').join('')} 分支 ${r.data.branch_n ?? '—'}・${r.data.pressure ?? '—'} kg` : '';
  return `<div class="card"><div class="small">上午：壓力、管線安全、前一天有關好、總開關打開、湯台關閉。打烊：桶頭與總開關關閉、點火分支關閉、分支數量、壓力、湯台關閉。</div><div class="tbl"><table>
    <tr><th>日期</th><th>上午 08:00</th><th>填表人</th><th>打烊</th><th>填表人</th></tr>
    ${days.map(d => { const a = g(d, '上午'), b = g(d, '打烊'); return `<tr><td>${md(d)}（${wkOf(d)}）</td><td>${sfCell(a, am(a))}${sfDel(a)}</td><td>${sfWho(a)}</td><td>${sfCell(b, pm(b))}${sfDel(b)}</td><td>${sfWho(b)}</td></tr>`; }).join('')}</table></div></div>`;
}
function sfOil() {
  const days = sfDays().reverse();
  return `<div class="card"><div class="tbl"><table><tr><th>日期</th><th>濾油</th><th>換油</th><th>清洗油炸機</th><th>極性值</th><th>經辦人</th></tr>
    ${days.map(d => { const rs = SF.rows.filter(r => r.day === d); if (!rs.length) return `<tr><td>${md(d)}（${wkOf(d)}）</td><td colspan="5" class="muted">—</td></tr>`;
      return rs.map(r => `<tr><td>${md(d)}（${wkOf(d)}）</td><td>${r.data.filter ? '✓' : ''}</td><td>${r.data.change ? '✓' : ''}</td><td>${r.data.clean ? '✓' : ''}</td><td>${sfCell(r, r.data.polar != null && r.data.polar !== '' ? r.data.polar + '%' : '—')}${sfDel(r)}</td><td>${sfWho(r)}</td></tr>`).join(''); }).join('')}</table></div></div>`;
}
function sfWaste() {
  return `<div class="card">${SF.rows.length ? `<div class="tbl"><table><tr><th>日期</th><th>數量</th><th>回收廠商</th><th>車號</th><th>回收人</th><th>門市經辦</th></tr>
    ${SF.rows.slice().reverse().map(r => `<tr><td>${md(r.day)}</td><td>${sfCell(r, esc(r.data.qty) + ' ' + esc(r.data.unit || ''))}${sfDel(r)}</td><td>${esc(r.data.vendor || '')}</td><td>${esc(r.data.plate || '')}</td><td>${esc(r.data.collector || '')}</td><td>${sfWho(r)}</td></tr>`).join('')}</table></div>`
    : '<div class="muted">這個月還沒有回收紀錄。</div>'}</div>`;
}
function sfToilet() {
  const days = sfDays().reverse(), S = SF.slots.toilet;
  return `<div class="card"><div class="tbl"><table><tr><th>日期</th>${S.map(s => `<th>${s}</th>`).join('')}</tr>
    ${days.map(d => `<tr><td>${md(d)}（${wkOf(d)}）</td>${S.map(s => { const r = SF.rows.find(x => x.day === d && x.slot === s); return `<td>${r ? sfCell(r, '✓ ' + esc(r.who)) + sfDel(r) : ''}</td>`; }).join('')}</tr>`).join('')}</table></div></div>`;
}
/* 記一筆 */
function safetyForm() {
  const K = SF.kind, hr = new Date().getHours(); SPHOTO = null;
  const need = SF.photo_required.includes(K);
  const photo = `<label>照片${need ? '（一定要現場拍）' : '（選填）'}</label><input type="file" accept="image/*" capture="environment" onchange="sfPick(this)"><div class="small" id="sf_ph">${need ? '按上面會打開相機。相簿裡的舊照片不收。' : ''}</div>`;
  const nowSlot = K === 'fridge' ? (hr < 16 ? '上午' : '下班') : K === 'gas' ? (hr < 16 ? '上午' : '打烊') : K === 'toilet' ? SF.slots.toilet.reduce((a, s) => Math.abs(+s.slice(0, 2) - hr) < Math.abs(+a.slice(0, 2) - hr) ? s : a) : '';
  const seg = (id, opts, cur) => `<div class="seg" id="${id}">${opts.map(o => `<button class="${o === cur ? 'on' : ''}" onclick="seg(this);${id === 'sf_slot' && K === 'gas' ? 'sfGasFields()' : ''}">${o}</button>`).join('')}</div>`;
  let body = '';
  if (K === 'fridge') {
    const ts = SF.targets.filter(x => x.kind === 'fridge');
    const miss = (nowSlot === '上午' ? SF.today.fridge_am : SF.today.fridge_pm) || [], t0 = ts.find(f => miss.includes(f.name)) || ts[0];   // 先選這個時段還沒記的那台
    body = `<label>哪一台</label><select id="sf_t" onchange="$('#sf_fz').hidden=!+this.selectedOptions[0].dataset.f">${ts.map(f => `<option value="${f.id}" data-f="${f.has_freezer}" ${f === t0 ? 'selected' : ''}>${esc(f.name)}${miss.includes(f.name) ? '' : '（這時段記過了）'}</option>`).join('')}</select>
      <label>時段</label>${seg('sf_slot', ['上午', '下班'], nowSlot)}
      <div class="g2"><div id="sf_fz" ${t0 && !t0.has_freezer ? 'hidden' : ''}><label>冷凍（度）</label><div style="display:flex;gap:8px"><button type="button" class="btn gray" id="sf_fs" style="min-width:52px;font-size:20px" onclick="sfSgn(this)">−</button><input id="sf_f" inputmode="decimal" placeholder="例：18（已經是零下）"></div></div>
        <div><label>冷藏（度）</label><div style="display:flex;gap:8px"><button type="button" class="btn gray" id="sf_cs" style="min-width:52px;font-size:20px" onclick="sfSgn(this)">＋</button><input id="sf_c" inputmode="decimal" placeholder="例：5"></div></div></div>
      <div class="small">冷凍已經幫你加好負號，看到 −18 直接打 18 就好；要改正負，按數字左邊的符號。</div>`;
  } else if (K === 'gas') {
    body = `<label>時段</label>${seg('sf_slot', ['上午', '打烊'], nowSlot)}<div id="sf_gas"></div>`;
  } else if (K === 'oil') {
    body = `<label class="chk"><input type="checkbox" id="sf_o1"> 今天有濾油</label><label class="chk"><input type="checkbox" id="sf_o2"> 今天有換油</label><label class="chk"><input type="checkbox" id="sf_o3"> 有清洗油炸機</label>
      <label>極性值 %（有測才填）</label><input id="sf_op" inputmode="decimal" placeholder="例：18">`;
  } else if (K === 'wasteoil') {
    body = `<div class="g2"><div><label>數量</label><input id="sf_q" inputmode="decimal"></div><div><label>單位</label>${seg('sf_u', ['桶', '公斤'], '桶')}</div></div>
      <div class="g2"><div><label>回收廠商</label><input id="sf_v"></div><div><label>車號</label><input id="sf_pl"></div></div><label>回收人</label><input id="sf_col">`;
  } else {
    body = `<label>時段</label>${seg('sf_slot', SF.slots.toilet, nowSlot)}<div class="small" style="margin-top:8px">洗手台、地板、馬桶、垃圾桶、鏡子都弄乾淨再記。</div>`;
  }
  openSheet(`<div class="shead"><h3>記一筆：${SF.kinds[K]}</h3><button class="btn gray sm" onclick="closeSheet()">取消</button></div><div class="card">${body}<label>備註（選填）</label><input id="sf_n">${photo}
    <button class="btn full" style="margin-top:16px" onclick="safetySave()">存檔</button><div id="sf_m"></div></div>`);
  if (K === 'gas') sfGasFields();
}
function sfGasFields() {
  const f = segVal('sf_slot') === '上午' ? SF.gas_am : SF.gas_pm;
  $('#sf_gas').innerHTML = f.map(([k, n, t]) => t === 'num' ? `<label>${n}</label><input id="sfg_${k}" inputmode="decimal">` : `<label class="chk"><input type="checkbox" id="sfg_${k}"> ${n}</label>`).join('');
}
async function sfPick(inp) {
  const f = inp.files[0]; if (!f) return;
  if (Date.now() - f.lastModified > 15 * 60 * 1000) { inp.value = ''; SPHOTO = null; return alert('這張是舊照片。記錄當下要用相機現場拍，相簿裡的照片不收。'); }
  try { SPHOTO = await readPhoto(f, 1280); $('#sf_ph').textContent = '已拍一張'; } catch (e) { alert(e.message); }
}
function sfSgn(b) { b.textContent = b.textContent === '−' ? '＋' : '−'; }
function sfTemp(inp, btn) {     // 手機數字鍵盤沒有負號：照左邊的符號決定正負；有打 - 也算負
  const raw = (($('#' + inp) || {}).value || '').trim(); if (!raw) return '';
  const n = parseFloat(raw.replace(/^[-−－＋+]/, '')); if (isNaN(n)) return raw;
  return String(/^[-−－]/.test(raw) || $('#' + btn).textContent === '−' ? -Math.abs(n) : Math.abs(n));
}
async function safetySave() {
  const K = SF.kind, v = id => ($('#' + id) || {}).value, data = {}, body = { kind: K, day: todayStr(), slot: '', data, photo: SPHOTO };
  if (K === 'fridge') {
    body.target_id = +v('sf_t'); body.slot = segVal('sf_slot'); data.freeze = $('#sf_fz').hidden ? null : sfTemp('sf_f', 'sf_fs'); data.chill = sfTemp('sf_c', 'sf_cs');
    const f = data.freeze === null || data.freeze === '' ? null : +data.freeze, ch = data.chill === '' ? null : +data.chill;
    if (((f !== null && f > -5) || (ch !== null && (ch > 10 || ch < -3))) &&
        !confirm(`冷凍 ${f ?? '—'}、冷藏 ${ch ?? '—'}，看起來不太對。\n是不是冷凍、冷藏填反了，或冷凍的負號不見了？\n\n按「確定」照這樣存（會通知店長和老闆），按「取消」回去改。`)) return;
  }
  else if (K === 'gas') { body.slot = segVal('sf_slot'); (body.slot === '上午' ? SF.gas_am : SF.gas_pm).forEach(([k, n, t]) => data[k] = t === 'num' ? v('sfg_' + k) : $('#sfg_' + k).checked); }
  else if (K === 'oil') { data.filter = $('#sf_o1').checked; data.change = data.changed = $('#sf_o2').checked; data.clean = $('#sf_o3').checked; data.polar = v('sf_op'); }
  else if (K === 'wasteoil') { data.qty = v('sf_q'); data.unit = segVal('sf_u'); data.vendor = v('sf_v'); data.plate = v('sf_pl'); data.collector = v('sf_col'); }
  else { body.slot = segVal('sf_slot'); data.done = true; }
  data.note = v('sf_n');
  try { const r = await api('/api/safety/save', body); closeSheet(); if (r.alert) alert('已存檔，但超出標準：' + r.alert + '\n店長和老闆會收到通知。'); LOAD.safety(); } catch (e) { msgOk('#sf_m', e); }
}
async function safetyReview() { const ids = SF.rows.filter(r => !r.reviewed_by).map(r => r.id); if (!confirm(`複檢這個月 ${ids.length} 筆？`)) return; await api('/api/safety/review', { ids }); LOAD.safety(); }
async function safetyDel(id) { if (!confirm('刪除這筆紀錄？')) return; try { await api('/api/safety/remove', { id }); LOAD.safety(); } catch (e) { alert(e.message); } }
async function sfTargetAdd() { try { await api('/api/safety/target', { name: $('#sf_tn').value, has_freezer: $('#sf_tf').checked }); LOAD.safety(); } catch (e) { alert(e.message); } }
async function sfTargetDel(id, name, f) { if (!confirm(`把「${name}」從清單拿掉？以前的紀錄會留著。`)) return; await api('/api/safety/target', { id, name, has_freezer: f, remove: true }); LOAD.safety(); }
