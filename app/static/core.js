/* 前端核心：工具、登入／註冊／首次設密碼、導覽（電腦＝上方全站導覽；手機＝底部分頁＋更多）、彈出視窗、聚光燈、手機通知 */
let ME = null, VIEW = '', CLOCK = null, BADGE_T = null;
const SUB = {};                                   // 每個頁面目前的子分頁
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = n => (n < 0 ? '−' : '') + Math.abs(Math.round(n || 0)).toLocaleString('zh-TW');
const md = d => d ? (+d.slice(5, 7)) + '/' + (+d.slice(8, 10)) : '';
const WK = '日一二三四五六';
const wkOf = d => WK[new Date(d.slice(0, 10) + 'T00:00:00').getDay()];
const todayStr = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
const addDays = (d, n) => { const x = new Date(d + 'T00:00:00'); x.setDate(x.getDate() + n); return x.getFullYear() + '-' + String(x.getMonth() + 1).padStart(2, '0') + '-' + String(x.getDate()).padStart(2, '0'); };
const hm = t => (t || '').slice(11, 16);
const KIND = { in: '上班', out: '下班' };
const initial = n => esc((n || '?').replace(/[（(].*$/, '').trim().slice(0, 1));

const INFLIGHT = new Set();
async function api(path, body) {
  const o = body ? { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Req': '1' }, body: JSON.stringify(body) } : {};
  // 存檔類：同一個請求還沒回來就不能再送（照片上傳慢、連按兩下不會變兩筆）；按下去的那顆按鈕先鎖住
  const key = body ? path + o.body : null, btn = body && document.activeElement && document.activeElement.tagName === 'BUTTON' ? document.activeElement : null;
  if (key) { if (INFLIGHT.has(key)) throw new Error('處理中，請稍候'); INFLIGHT.add(key); }
  if (btn) btn.disabled = true;
  try {
    let r; try { r = await fetch(path, o); } catch (e) { throw new Error('連不上網路，請確認網路後再試一次'); }
    let d = {}; try { d = await r.json(); } catch (e) { }
    if (r.status === 401 && path !== '/api/login') { showLogin(); throw new Error('請先登入'); }
    if (!r.ok) throw new Error(d.error || ('錯誤 ' + r.status));
    return d;
  } finally { if (key) INFLIGHT.delete(key); if (btn) btn.disabled = false; }
}
/* 名字放進 onclick 要用這個（單引號、反斜線都不會壞，也塞不進程式） */
const jsq = s => esc(JSON.stringify(String(s ?? '')));
/* 沒有自己接住的錯誤（例如按鈕直接呼叫 api）一律跳出來，不會按了沒反應 */
window.addEventListener('unhandledrejection', e => { const m = (e.reason && e.reason.message) || ''; if (m && !/請先登入|處理中/.test(m)) alert(m); });
function seg(b) { b.parentElement.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); }
const segVal = id => ($('#' + id + ' .on') || {}).textContent;
const msgOk = (sel, e) => { const el = $(sel); if (el) el.innerHTML = e ? `<div class="err">${esc(e.message || e)}</div>` : '<div class="okmsg">已儲存</div>'; };

/* ---------- 圖示（SF Symbols 風格的線條圖示） ---------- */
const ICON = {
  boss: '<rect x="3" y="3" width="7.5" height="9" rx="1.8"/><rect x="13.5" y="3" width="7.5" height="5" rx="1.8"/><rect x="13.5" y="11" width="7.5" height="10" rx="1.8"/><rect x="3" y="15" width="7.5" height="6" rx="1.8"/>',
  punch: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
  journal: '<path d="M5 4h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-8l-5 4v-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="M8 9.5h8M8 12.5h5"/>',
  crm: '<path d="M5.5 3.5h3l1.8 4.6-2.3 1.5a11 11 0 0 0 6.4 6.4l1.5-2.3 4.6 1.8v3a2 2 0 0 1-2.2 2A17 17 0 0 1 3.5 5.7a2 2 0 0 1 2-2.2z"/>',
  deliv: '<circle cx="6.5" cy="17" r="2.6"/><circle cx="17.5" cy="17" r="2.6"/><path d="M9.1 17h5.8M14.9 17l-1.6-6.5H10M13.3 10.5h3.2l1.9 4.1M3.5 9h5v4h-5z"/>',
  notice: '<path d="M6 9a6 6 0 0 1 12 0c0 6.5 2.5 8.5 2.5 8.5h-17S6 15.5 6 9z"/><path d="M10 21h4"/>',
  sched: '<rect x="3.5" y="5" width="17" height="15.5" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
  fin: '<path d="M6 3h12v18l-2-1.4-2 1.4-2-1.4-2 1.4-2-1.4L6 21z"/><path d="M9 8h6M9 12h6M9 16h3"/>',
  manual: '<path d="M3 5.5C5.5 4 8.5 4 12 6c3.5-2 6.5-2 9-.5V19c-2.5-1.5-5.5-1.5-9 .5-3.5-2-6.5-2-9-.5z"/><path d="M12 6v13.5"/>',
  me: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  more: '<circle cx="5.5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="18.5" cy="12" r="1.4" fill="currentColor"/>',
  photo: '<rect x="3" y="5" width="18" height="15" rx="3"/><circle cx="12" cy="12.5" r="3.5"/><path d="M8.5 5l1.5-2h4l1.5 2"/>',
  send: '<path d="M4 12l16-8-6 16-2.5-6.5z"/>',
  safety: '<path d="M10 4a2 2 0 0 1 4 0v9.5a4 4 0 1 1-4 0z"/><path d="M12 10v6"/><path d="M17 6h3M17 9h2M17 12h3"/>',
  mk: '<path d="M4 10v4a1 1 0 0 0 1 1h2l5 4V5L7 9H5a1 1 0 0 0-1 1z"/><path d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12"/>',
  news: '<rect x="3" y="4.5" width="14" height="15" rx="2"/><path d="M17 8.5h2.5a1.5 1.5 0 0 1 1.5 1.5v7.5a2 2 0 0 1-4 0M6.5 8.5h7M6.5 12h7M6.5 15.5h4"/>'
};
const svg = k => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${ICON[k]}</svg>`;
const VIEWS = {
  boss: { t: '老闆', n: '老闆' }, punch: { t: '打卡', n: '打卡' }, journal: { t: '我很棒日誌', n: '日誌' }, crm: { t: '開發', n: '開發' },
  deliv: { t: '外送', n: '外送' }, notice: { t: '公告', n: '公告' }, sched: { t: '班表', n: '班表' }, fin: { t: '記帳', n: '記帳' },
  manual: { t: '教育訓練', n: '訓練' }, news: { t: '每週新聞', n: '新聞' }, safety: { t: '食安紀錄', n: '食安' }, mk: { t: '行銷', n: '行銷' }, me: { t: '我', n: '我' }
};
function order() {
  const P = ME.perms; let o;
  if (P.admin) o = ['boss', 'fin', 'crm', 'mk', 'deliv', 'notice', 'sched', 'safety', 'journal', 'news', 'manual', 'me'];
  else if (ME.role === 'manager') o = ['fin', 'crm', 'deliv', 'notice', 'sched', 'safety', 'news', 'manual', 'me'];
  else o = ['punch', 'crm', 'deliv', 'notice', 'sched', 'safety', 'journal', 'news', 'manual', 'me'];
  if (ME.punch && !o.includes('punch')) o.splice(1, 0, 'punch');
  const MOD = { crm: 'crm', deliv: 'delivery', safety: 'safety', mk: 'marketing', news: 'news', journal: 'journal' }, on = (STORE.modules || {});   // config/store.toml 的 [modules]
  return o.filter(v => (v !== 'punch' || ME.punch) && !(MOD[v] && on[MOD[v]] === false));
}
let HOME = 'punch';
const LOAD = {};                                   // 各頁面在自己的檔案裡註冊：LOAD.punch = loadPunch …

/* ---------- 登入、註冊、首次設密碼 ---------- */
function showOnly(id) { ['loginView', 'regView', 'setpwView', 'app'].forEach(x => $('#' + x).hidden = x !== id); }
function showLogin() { showOnly('loginView'); }
function showReg() { showOnly('regView'); }
async function login() {
  $('#lerr').textContent = '';
  try { await api('/api/login', { username: $('#lu').value, password: $('#lp').value }); boot(); } catch (e) { $('#lerr').textContent = e.message; }
}
async function register() {
  $('#rerr').textContent = '';
  if ($('#rp1').value !== $('#rp2').value) return $('#rerr').textContent = '兩次密碼不一樣';
  try {
    await api('/api/register', { name: $('#rn').value, username: $('#ru').value, password: $('#rp1').value, phone: $('#rph').value, position: segVal('rpos'), note: $('#rnote').value });
    $('#regView .card').innerHTML = `<h3 style="font-size:24px">送出了</h3><p>老闆會收到通知，審核通過後就可以用你剛剛設的帳號、密碼登入。</p><button class="btn full" onclick="location.reload()">回到登入</button>`;
  } catch (e) { $('#rerr').textContent = e.message; }
}
async function setFirstPw() {
  const a = $('#sp1').value, b = $('#sp2').value; $('#sperr').textContent = '';
  if (a !== b) return $('#sperr').textContent = '兩次輸入的不一樣';
  try { await api('/api/password', { first: true, new: a }); boot(); } catch (e) { $('#sperr').textContent = e.message; }
}
document.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.id === 'lp') login(); });

/* ---------- 開機 ---------- */
let BOOTED = false, BOOT_DAY = todayStr();
async function boot() {
  try { ME = await api('/api/me'); } catch (e) { return; }
  BOOT_DAY = todayStr();
  if (ME.must_change) return showOnly('setpwView');
  showOnly('app');
  HOME = order()[0];
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => { });
  const v = (location.hash || '').slice(1);
  go(order().includes(v) ? v : HOME, true);
  clearInterval(BADGE_T); BADGE_T = setInterval(refreshBadges, 60000);
  if (BOOTED) return; BOOTED = true;
  window.addEventListener('hashchange', () => { const h = location.hash.slice(1); if (h && h !== VIEW && order().includes(h)) go(h, true); });
  // 手機 App 從昨天一直開著：回到畫面時日期變了就整頁重新整理（記帳、外送的日期才不會停在昨天）
  document.addEventListener('visibilitychange', () => { if (document.hidden) return; if (todayStr() !== BOOT_DAY) return location.reload(); refreshBadges(); });
}
async function refreshBadges() {
  try { const m = await api('/api/me'); Object.assign(ME, m); } catch (e) { return; }
  renderNav();
}
function badgeOf(v) {
  if (v === 'notice') return ME.notice_unread ? '!' : '';
  if (v === 'journal') return ME.journal_unread || '';
  if (v === 'manual') return ME.role === 'staff' ? (ME.train_left || '') : '';
  if (v === 'news') return ME.news_unread ? '新' : '';
  if (v === 'boss') return ((ME.pending_regs || 0) + (ME.pending_fixes || 0)) || '';
  if (v === 'fin') return ME.perms.admin ? (ME.fin_pending || '') : (ME.fin_back || '');
  if (v === 'deliv') return ME.my_deliveries || '';
  if (v === 'mk') return ME.mk_pending || '';
  if (v === 'me') return ((ME.inbox_unread || 0) + (ME.todo_open || 0)) || '';
  return '';
}
function renderNav() {
  const o = order(), who = ME.acting ? (ME.real_name || '老闆') + '（模擬' + (ME.acting === 'manager' ? '店長' : '夥伴') + '）'
    : ME.name + (ME.role === 'admin' ? '（老闆）' : ME.role === 'manager' ? '（' + (ME.title || '店長') + '）' : '');
  $('#gnav').innerHTML = o.filter(v => v !== 'me').map(v => { const b = badgeOf(v); return `<a class="${v === VIEW ? 'on' : ''}" data-v="${v}" onclick="go('${v}')">${VIEWS[v].n}${b ? `<span class="badge ${b === '!' ? 'bang' : ''}">${b}</span>` : ''}</a>`; }).join('');
  const ib = badgeOf('me');
  $('#gme').innerHTML = `<span class="nm">${esc(who)}</span><span class="av" style="position:relative">${initial(ME.acting ? ME.real_name : ME.name)}${ib ? `<span class="badge" style="left:auto;right:-6px;top:-4px">${ib}</span>` : ''}</span>`;
  $('#gme').title = who; $('#gme').onclick = ME.can_switch ? roleSheet : () => go('me');
  const ab = $('#actbar');
  if (ab) { ab.hidden = !ME.acting; if (ME.acting) ab.innerHTML = `<span>正在模擬<b>${ME.acting === 'manager' ? '店長' : '夥伴'}</b>看到的畫面 · 存檔類的動作不會真的存</span><button onclick="switchRole('admin')">切回老闆</button>`; }
  const prim = o.length <= 5 ? o : o.slice(0, 4), rest = o.length <= 5 ? [] : o.slice(4);
  const restBadge = rest.some(v => badgeOf(v));
  $('#tabbar').innerHTML = prim.map(v => { const b = badgeOf(v); return `<button class="${v === VIEW ? 'on' : ''}" data-v="${v}" onclick="go('${v}')" aria-label="${VIEWS[v].n}">${svg(v)}<span>${VIEWS[v].n}</span>${b ? `<span class="badge ${b === '!' ? 'bang' : ''}">${b}</span>` : ''}</button>`; }).join('')
    + (rest.length ? `<button class="${rest.includes(VIEW) ? 'on' : ''}" data-v="more" onclick="moreMenu()" aria-label="更多">${svg('more')}<span>${rest.includes(VIEW) ? VIEWS[VIEW].n : '更多'}</span>${restBadge ? '<span class="badge" style="min-width:10px;height:10px;padding:0"></span>' : ''}</button>` : '');
}
/* 老闆切換角色：老闆／模擬店長／模擬夥伴（同一個帳號，不用另外登入） */
const ROLES = [['admin', '老闆', '全部功能，老闆頁、核銷、薪資'], ['manager', '模擬店長', '記帳、發公告、排休、外送派單；看不到老闆頁'], ['staff', '模擬夥伴', '打卡、日誌、開發、公告、訓練；夥伴手機上看到的樣子']];
function roleSheet() {
  const cur = ME.acting || 'admin';
  openSheet(`<div class="shead"><h3>切換角色</h3><button class="btn gray sm" onclick="closeSheet()">完成</button></div>
    <p class="muted" style="margin:0 0 14px">同一個帳號切換，看店長、夥伴手機上的畫面。模擬時可以點、可以看，但記帳、公告、外送這些會動到正式資料的不會真的存。</p>
    <div class="rolepick">${ROLES.map(([k, t, s]) => `<button class="${k === cur ? 'on' : ''}" onclick="switchRole('${k}')"><div><div class="t">${t}</div><div class="s">${s}</div></div>${k === cur ? '<span class="ck">✓</span>' : ''}</button>`).join('')}</div>
    <div class="btns" style="margin-top:16px"><button class="btn sec" onclick="closeSheet();go('me')">我的設定、通知</button></div>`);
}
async function switchRole(to) {
  if ((ME.acting || 'admin') === to) return closeSheet();
  try { await api('/api/switch', { to }); } catch (e) { return alert(e.message); }
  history.replaceState(null, '', location.pathname); location.reload();
}
function moreMenu() {
  const o = order(), rest = o.length <= 5 ? [] : o.slice(4);
  openSheet(`<div class="shead"><h3>更多</h3><button class="btn gray sm" onclick="closeSheet()">完成</button></div>
    <div class="list">${rest.map(v => { const b = badgeOf(v); return `<button onclick="closeSheet();go('${v}')"><span class="ic">${svg(v)}</span>${VIEWS[v].t}${b ? `<span class="badge">${b}</span>` : '<span class="chev">›</span>'}</button>`; }).join('')}</div>`);
}
/* 頁面導覽（apple.com 的 localnav）：標題＋子分頁 */
let PNAV = null;
function localNav(title, links, cur, pick, action) { PNAV = { title, links: links || [], cur, pick, action }; document.title = title + '｜' + STORE.short_name; }
function segCtl() {
  if (!PNAV || !PNAV.links.length) return '';
  const n = PNAV.links.length, cols = n <= 4 ? n : 3;
  return `<div class="segctl" role="tablist" style="--segn:${cols}">${PNAV.links.map(([k, t, c]) => `<button role="tab" aria-selected="${k === PNAV.cur}" class="${k === PNAV.cur ? 'on' : ''}" onclick="${PNAV.pick}('${k}')">${esc(t)}${c ? `<span class="n">${c}</span>` : ''}</button>`).join('')}</div>`;
}
function go(v, noHash) {
  if (!LOAD[v]) v = HOME;
  if (v !== VIEW) {            // 換到別頁：上一頁開著的表單、導覽收起來（10/9 視角測試發現會留在新的頁面上）
    if (!$('#sheet').hidden) closeSheet();
    if (typeof tourEnd === 'function') tourEnd(false);
  }
  VIEW = v; if (!noHash || location.hash.slice(1) !== v) history.replaceState(null, '', '#' + v);
  if (CLOCK) { clearInterval(CLOCK); CLOCK = null; }
  closeSpot();
  renderNav(); localNav(VIEWS[v].t);
  const M = $('#main'); M.classList.remove('enter');
  M.innerHTML = '<div class="muted" style="padding:40px 0;text-align:center">載入中…</div>';
  window.scrollTo(0, 0);
  if (window.gated && gated(v)) { gatePage(); void M.offsetWidth; M.classList.add('enter'); return; }   // 崗位必讀還沒看完
  Promise.resolve(LOAD[v]()).then(() => { void M.offsetWidth; M.classList.add('enter'); if (window.maybeTour) maybeTour(v); })
    .catch(e => { M.innerHTML = `<div class="banner red">${esc(e.message)}</div>`; });
}
const hero = (eyebrow, title, sub) => `<div class="phead"><div class="tx">${eyebrow ? `<p class="eyebrow">${eyebrow}</p>` : ''}<h1 class="headline">${title}</h1>${sub ? `<p class="sub">${sub}</p>` : ''}</div>
  ${PNAV && PNAV.action ? `<div class="act"><button class="btn" onclick="${PNAV.action[1]}">${esc(PNAV.action[0])}</button></div>` : ''}</div>${segCtl()}`;

/* 表格：每一格補上欄名（手機上表格變卡片時，左邊顯示欄名） */
function labelTables(root) {
  (root || document).querySelectorAll('.tbl table').forEach(t => {
    const hr = t.querySelector('tr'); if (!hr || !hr.querySelector('th')) return;
    const names = [...hr.children].map(x => x.textContent.trim());
    t.querySelectorAll('tr').forEach(tr => { if (tr === hr) return; [...tr.children].forEach((td, i) => { if (td.tagName === 'TD' && !td.hasAttribute('data-l')) td.setAttribute('data-l', names[i] || ''); }); });
  });
}
new MutationObserver(() => labelTables()).observe(document.getElementById('main') || document.body, { childList: true, subtree: true });

/* ---------- 彈出視窗（手機從下方滑上來、電腦置中） ---------- */
function openSheet(html) { $('#sheetBody').innerHTML = '<div class="grab"></div>' + html; $('#sheet').hidden = false; $('#sheetBody').scrollTop = 0; }
function closeSheet() { $('#sheet').hidden = true; if (window.CUR !== undefined) window.CUR = null; }
function zoom(src) { const z = document.createElement('div'); z.className = 'zoom'; z.innerHTML = `<img src="${src}" alt="">`; z.onclick = () => z.remove(); document.body.appendChild(z); }
function grow(t) { t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 150) + 'px'; }
/* 照片：手機拍照或選圖 → 壓到 1600 像素 JPG */
function readPhoto(file, max = 1600) {
  return new Promise((ok, no) => {
    if (!file) return no(new Error('沒有選照片'));
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = () => { const k = Math.min(1, max / Math.max(img.width, img.height)), c = document.createElement('canvas');
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k); c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url); ok(c.toDataURL('image/jpeg', .82)); };
    img.onerror = () => no(new Error('這張照片讀不到，請換一張')); img.src = url;
  });
}

/* ---------- 聚光燈：把畫面變暗，只亮要看的那一塊 ---------- */
let SPOT = null;
function spotlight(el, label, onNext) {
  closeSpot();
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.add('spotlit');
  const lab = document.createElement('span'); lab.className = 'spotlabel'; lab.textContent = label; el.appendChild(lab);
  const fog = document.createElement('div'); fog.className = 'spotfog'; fog.title = '點一下關掉';
  fog.onclick = () => { closeSpot(); onNext && onNext(); };
  document.body.appendChild(fog);
  SPOT = { el, lab, fog };
}
function closeSpot() { if (!SPOT) return; SPOT.el.classList.remove('spotlit'); SPOT.lab.remove(); SPOT.fog.remove(); SPOT = null; }

/* ---------- 手機通知（Web Push） ---------- */
const PUSH = {
  supported: 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window,
  ios: /iPhone|iPad|iPod/.test(navigator.userAgent),
  standalone: matchMedia('(display-mode: standalone)').matches || navigator.standalone === true
};
function u8(b64) { const s = atob((b64 + '='.repeat((4 - b64.length % 4) % 4)).replace(/-/g, '+').replace(/_/g, '/')); return Uint8Array.from(s, c => c.charCodeAt(0)); }
async function pushStatus() {
  if (!ME.push_key) return 'unsupported';            // 伺服器沒裝 cryptography：不提供推播
  if (!PUSH.supported) return PUSH.ios && !PUSH.standalone ? 'ios-home' : 'unsupported';
  const r = await navigator.serviceWorker.getRegistration(); const s = r && await r.pushManager.getSubscription();
  if (s && Notification.permission === 'granted') return 'on';
  return Notification.permission === 'denied' ? 'denied' : 'off';
}
async function enablePush() {
  if (!ME.push_key) throw new Error('這台系統沒有開推播功能（伺服器要先安裝 cryptography 套件）。');
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') throw new Error('沒有允許通知。請到手機「設定 › 通知」把這個網站（或主畫面上的' + STORE.short_name + '）打開。');
  const r = await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready;
  let s = await r.pushManager.getSubscription();
  if (!s) s = await r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: u8(ME.push_key) });
  await api('/api/push/subscribe', { sub: s.toJSON(), ua: navigator.userAgent });
}
function pushHelp(st) {
  if (st === 'ios-home') return 'iPhone 要先把這個網站「加入主畫面」：用 Safari 打開 → 按下面的分享鈕 → 「加入主畫面」→ 之後從主畫面的「' + STORE.short_name + '」打開，再回來這裡按「開啟通知」。';
  if (st === 'unsupported') return '這個瀏覽器不支援通知。Android 請用 Chrome；iPhone 請用 Safari 並加入主畫面（iOS 16.4 以上）。';
  if (st === 'denied') return '之前按了「不允許」。請到手機「設定 › 通知」或瀏覽器的網站設定，把通知打開。';
  return '';
}
async function pushCard() {
  if (ME.acting) return '';
  const st = await pushStatus();
  if (st === 'on') return '';
  return `<div class="banner blue" style="cursor:default;flex-wrap:wrap"><span style="flex:1;min-width:200px">${st === 'off' ? '開啟手機通知：新公告、老闆回你的日誌、外送單，會直接跳到手機上。' : esc(pushHelp(st))}</span>
    ${st === 'off' ? `<button class="btn sm" onclick="turnOnPush(this)">開啟通知</button>` : ''}</div>`;
}
async function turnOnPush(b) { try { b && (b.disabled = true); await enablePush(); alert('通知開好了'); go(VIEW, true); } catch (e) { alert(e.message); b && (b.disabled = false); } }
