/* v4（老闆 10/5 晚）：每週新聞、待辦、個人檔案、崗位必讀、我很棒日誌（Apple 風格）、導覽（聚光燈，第一次點每個頁籤都帶一遍）、外送示範 */

/* ═════════ 導覽引擎：暗下來、挖一個洞照亮那個按鈕、旁邊一張說明卡 ═════════ */
let TOUR = null;
const sleep = ms => new Promise(r => setTimeout(r, ms));
function tourEl(sel) {
  for (const s of (Array.isArray(sel) ? sel : [sel])) {
    const e = typeof s === 'function' ? s() : document.querySelector(s);
    if (e) { const r = e.getBoundingClientRect(); if (r.width > 0 && r.height > 0) return e; }
  }
  return null;
}
function runTour(key, steps, onDone) {
  if (TOUR) return;
  steps = (steps || []).filter(Boolean);
  if (!steps.length) { onDone && onDone(); return; }
  closeSpot && closeSpot();
  const ov = document.createElement('div'); ov.className = 'tour';
  ov.innerHTML = '<div class="tour-block"></div><div class="tour-hole"></div><div class="tour-card" role="dialog" aria-live="polite"></div>';
  document.body.appendChild(ov);
  TOUR = { key, steps, i: 0, dir: 1, onDone, ov };
  addEventListener('resize', tourPlace); addEventListener('scroll', tourPlace, true);
  tourShow(0);
}
async function tourShow(i) {
  const T = TOUR; if (!T) return;
  if (i < 0) i = 0;
  if (i >= T.steps.length) return tourEnd(true);
  T.i = i; const s = T.steps[i];
  if (s.before) { try { await s.before(); } catch (e) { } await sleep(s.wait || 300); if (TOUR !== T) return; }
  T.el = s.sel ? tourEl(s.sel) : null;
  if (s.sel && !T.el) return tourShow(i + T.dir);          // 這一步要照的東西不在畫面上 → 跳過
  if (T.el) { T.el.scrollIntoView({ block: 'center' }); await sleep(60); }
  const last = i === T.steps.length - 1;
  T.ov.querySelector('.tour-card').innerHTML = `<div class="tour-n">${i + 1} / ${T.steps.length}</div><h4>${s.title}</h4><p>${s.text}</p>
    <div class="tour-btns"><button class="tour-skip" onclick="tourEnd(true)">${last ? '' : '略過導覽'}</button><span style="flex:1"></span>
    ${i ? '<button class="btn gray sm" onclick="TOUR.dir=-1;tourShow(TOUR.i-1)">上一步</button>' : ''}
    <button class="btn sm" onclick="TOUR.dir=1;tourShow(TOUR.i+1)">${last ? (s.last || '完成') : '下一步'}</button></div>`;
  tourPlace();
}
function tourPlace() {
  const T = TOUR; if (!T) return;
  const hole = T.ov.querySelector('.tour-hole'), card = T.ov.querySelector('.tour-card');
  const vw = innerWidth, vh = innerHeight;
  if (!T.el) { hole.style.cssText = `left:${vw / 2}px;top:${vh / 2}px;width:0;height:0`; card.classList.add('center'); card.style.cssText = ''; return; }
  card.classList.remove('center');
  const r = T.el.getBoundingClientRect(), pad = 6;
  hole.style.cssText = `left:${r.left - pad}px;top:${r.top - pad}px;width:${r.width + pad * 2}px;height:${r.height + pad * 2}px`;
  const cw = Math.min(380, vw - 24); card.style.width = cw + 'px';
  const ch = card.offsetHeight;
  let top = r.bottom + 14; if (top + ch > vh - 12) top = r.top - ch - 14; if (top < 12) top = Math.max(12, vh - ch - 12);
  const left = vw < 640 ? 12 : Math.min(Math.max(12, r.left + r.width / 2 - cw / 2), vw - cw - 12);
  card.style.left = left + 'px'; card.style.top = top + 'px';
}
function tourEnd(done) {
  const T = TOUR; if (!T) return; TOUR = null;
  T.ov.remove(); removeEventListener('resize', tourPlace); removeEventListener('scroll', tourPlace, true);
  if (done && T.key) { (ME.tours = ME.tours || []).push(T.key); api('/api/tour/done', { k: T.key }).catch(() => { }); }
  T.onDone && T.onDone();
}
/* 新功能上線：每次更新都帶大家看一遍（老闆 10/6：新功能上線都要通知大家、讓大家學會操作）。改 k 就會再跑一次 */
const WHATSNEW = {
  k: 'new:20261007',
  steps: () => [
    step(null, '系統更新了', '這次多了「食安紀錄」，下午打卡的問題也修好了。帶你看一下，大約 30 秒。'),
    step(navSel('safety'), '新功能：食安紀錄', '冰箱溫度（早上開店、下班前各一次，每台都要記、一定要拍照）、瓦斯檢查、油品、廢油回收、廁所清潔，都改在這裡記，不用再寫紙本。'),
    ME.role === 'staff' ? step(navSel('punch'), '打卡：兩頭班修好了', '中午下班、下午再上班，按一下就好。10/6 下午有被擋住的，到「打卡 › 忘了打卡？」申請補登。') : null,
    step('#helpbtn', '不會用就按「?」', '每一頁都可以重看導覽。', { last: '知道了' })
  ]
};
/* 第一次打開系統：先全盤導覽；之後第一次點每個頁籤：那一頁的導覽 */
function maybeTour(v) {
  if (TOUR || !ME || ME.must_change) return;
  const done = ME.tours || [];
  if (!done.includes('welcome')) return setTimeout(() => runTour('welcome', tourWelcome(), () => { (ME.tours = ME.tours || []).push(WHATSNEW.k); api('/api/tour/done', { k: WHATSNEW.k }).catch(() => { }); maybeTour(v); }), 500);
  if (!done.includes(WHATSNEW.k)) return setTimeout(() => runTour(WHATSNEW.k, WHATSNEW.steps(), () => maybeTour(v)), 500);
  if (!done.includes('page:' + v) && TOURS[v]) setTimeout(() => { if (VIEW === v) runTour('page:' + v, TOURS[v](), TOUR_DONE[v]); }, 450);
}
function replayTour() { if (TOURS[VIEW]) runTour('', TOURS[VIEW](), TOUR_DONE[VIEW]); else runTour('', tourWelcome()); }
async function resetTours() { await api('/api/tour/reset', {}); ME.tours = []; go(HOME); }

const navSel = v => [`#gnav a[data-v="${v}"]`, `#tabbar button[data-v="${v}"]`, '#tabbar button[data-v="more"]'];
const step = (sel, title, text, extra) => Object.assign({ sel, title, text }, extra || {});
function tourWelcome() {
  const o = order(), admin = ME.perms.admin, mgr = ME.role === 'manager' && !admin;
  const D = {
    boss: ['老闆', '今日出勤、本月薪資（定案、簽收單）、補登審核、打卡紀錄、設定（店家位置、班表、薪資、預支）、帳號（核准新夥伴、崗位輪調）、待辦。'],
    fin: ['記帳', admin ? '店長記的營收直接入帳；店內支出你在「核銷」看照片核對，核銷完自動進股東帳務。' : '打烊後記今天營收、拍日結單；店裡花的錢一筆一筆記、拍收據，老闆核銷後進帳務。'],
    punch: ['打卡', '上班、下班都在這裡打，要人在店裡（手機會定位）。打卡就是一切：沒打卡的時間不算薪水。'],
    crm: ['開發', '打電話找訂便當的單位。優先名單照 A 級排好，按「撥」打電話，掛掉回到這裡會自動跳出記錄。'],
    deliv: ['外送', '客人訂了要送的單都在這裡：開單 → 派單 → 出餐 → 取餐核對 → 到點打卡 → 送達拍照 → 繳現金。'],
    notice: ['公告', '老闆、店長的公告。新的會有紅色「！」，看完按「我已讀」。' + (ME.perms.post ? '你也可以發公告。' : '')],
    sched: ['班表', '誰上班、誰排休、誰輪廁所，一眼看清楚。' + (ME.perms.sched ? '點日期就能排。' : '')],
    journal: ['日誌', admin ? '夥伴每天寫三件做得好的事，你回覆。晚上 9 點還沒寫的人，系統會用你的名義傳一則關心。' : '每天寫三件今天做得好的事，老闆會回你。晚上 9 點還沒寫，老闆會來關心你喔。'],
    news: ['新聞', '每週一整理食安、餐飲業、客戶服務、觀光餐飲的新聞，3 分鐘看完，還有「對我們店」的提醒。'],
    safety: ['食安', '冰箱溫度（早上、下班前各一次，要拍照）、瓦斯檢查、油品、廢油回收、廁所清潔都在這裡記。'],
    manual: ['訓練', ME.role === 'staff' ? '照你的崗位排好的必讀放最前面。必讀看完才能用其他功能（打卡不受影響）。' : '店裡所有做法都在這裡，看得到誰讀過。']
  };
  const s = [step(null, admin ? '歡迎，老闆。帶你全盤看一遍' : `歡迎，${esc(ME.name)}`, admin ? '大約 1 分鐘。之後第一次點每一個頁籤，都會再帶你看那一頁的細項。隨時可以按右上角「?」重看。' : '這是' + STORE.name + '的工作系統。花 1 分鐘帶你看一遍，之後第一次點每一頁，都會再帶你看那一頁怎麼用。')];
  o.filter(v => D[v]).forEach(v => s.push(step(navSel(v), D[v][0], D[v][1])));
  s.push(step('#gme', admin ? '你的頭像：切換角色' : '你的頭像：我', admin ? '點這裡可以切換「老闆／模擬店長／模擬夥伴」，看他們手機上的畫面。個人檔案、待辦、通知、密碼也在「我」。' : '個人檔案（形象照、自我介紹）、待辦、手機通知、改密碼都在這裡。'));
  s.push(step('#helpbtn', '看不懂就按「?」', '每一頁都可以按這個，再看一次這頁的導覽。', { last: '開始使用' }));
  return s;
}

/* 每一頁的導覽 */
const TOURS = {
  punch: () => [
    step('#pbtn', '打卡按鈕', '按下去手機會定位，人在店裡才打得到。上班、下班系統會照你的班表判斷，按一次就好。'),
    step('#clock', '現在時間', '以這個時間為準。遲到一分鐘也算一次，每滿 3 次扣 1 天。'),
    step('.punchbox + .grid', '本月出勤', '出勤天數、打卡時數、遲到次數、預估實發，每天自動算。'),
    step(() => [...document.querySelectorAll('details.fold summary')].find(x => /補登/.test(x.textContent)), '忘了打卡？', '在這裡申請補登，寫原因，老闆核准才算。'),
    step('#todo_card', '待辦', '老闆交辦的事情在這裡，做完打勾。')
  ],
  crm: () => [
    step('#main .card', '今天、明天誰上班', '客人要訂明天的便當、要外送，先看明天有誰在。'),
    step('.grid', '今天的數字', '我撥了幾通、接通、有效商機、成交盒數。'),
    step('#prio', '優先名單', 'A 級一律排最前面；同一級裡，今天要追蹤的、有興趣的、分給你的、今天 AI 新找到的優先。'),
    step('#prio .btn.green', '按「撥」打電話', '手機會直接撥號。掛掉電話回到這個畫面，系統會自動跳出「記一通」，沒接也要記。'),
    step('.segctl', '名單、話術', '「名單」可以篩選、搜尋全部單位；「話術」照著念就好，不用背。')
  ],
  notice: () => [
    step('.card.notice', '公告', '最新的在最上面，有「新」的就是你還沒讀的。'),
    step('.card.notice .btn', '我已讀', '看完一定要按，老闆看得到誰讀過。'),
    step('.phead .act .btn', '發公告', '發出去所有人手機都會跳通知，看得到誰讀了。')
  ],
  sched: () => [
    step('.calbar', '月曆', '‹ › 換月份，「今天」跳回這個月。'),
    step('.cal .d.today', '今天', '紅圈是今天。橘色是誰休假，下面灰字是廁所輪值。'),
    step('.cal .d.edit', '排休、排廁所', '點日期就能勾誰休假、選誰洗廁所。排好的休假，打卡和今日出勤會自動標「排休」。')
  ],
  journal: () => ME.perms.admin && !JU ? [
    step('.jlist', '每位夥伴的日誌', '綠色＝今天寫了，橘色＝還沒寫；數字是你還沒看的。點名字進去看、回覆。'),
    step(null, '晚上 9 點的關心', '今天有上班、到 9 點還沒寫日誌的夥伴，系統會用你的名義傳一則關心（60 則輪流、60 天不重複），他們手機會跳通知。')
  ] : [
    step('#jcomp', '寫今天的日誌', '寫三件今天自己做得好的事，可以附照片。送出後，今天寫的可以收回。'),
    step('#jseg', '全部／老闆說的', '「老闆說的」只看老闆每一天回你的話。'),
    step('.jday', '每一天一張卡', '上面是你寫的，藍色框是老闆的回覆。')
  ],
  news: () => [
    step('.phead', '這一週的重點', '每週一早上出刊，手機會收到通知。'),
    step('.ncard', '一則新聞', '看標題和摘要就好，3 分鐘看完。'),
    step('.ncard .tip', '對我們店', '這則新聞對我們店的實際提醒，最重要的是這一句。'),
    step('.ncard .src a', '看原文', '想看完整報導點這裡。')
  ],
  manual: () => [
    step('#mreq', '你的必讀', ME.role === 'staff' ? '照你的崗位排好的。全部看完才能用其他功能（打卡不受影響）。' : '店裡的做法都在這裡。'),
    step('details.fold', '點開一篇', '讀完按最下面的「我讀完了」，老闆看得到。'),
    step('#mq', '搜尋', '忘了怎麼做，打關鍵字找，例如：白飯、收銀、叫菜。')
  ],
  me: () => [
    step('#prof_card', '個人檔案', '上傳形象照、寫自我介紹，大家認識你。'),
    step('#todo_card', '待辦', '交辦給你的事情，做完打勾，交辦的人會收到通知。'),
    step('#team_card', '認識夥伴', '看看每個人的照片和自我介紹。'),
    step('#push_card', '手機通知', '一定要開，新公告、外送單、老闆回覆才會跳出來。iPhone 要先用 Safari「加入主畫面」。')
  ],
  boss: () => [
    step('.segctl', '老闆頁', '今日出勤、本月薪資、補登審核、打卡紀錄、設定、帳號、待辦都在這裡切換。'),
    step('.grid', '今天的狀況', '上班中、還沒打卡、日誌寫了幾位、記帳待核銷。'),
    step('.tbl', '每個人今天的打卡', '晚幾分、漏打卡都會標出來。'),
    step(null, '本月薪資', '月底按「定案」，數字就固定；發完按「已發薪」。要改先按「改回試算中」。沒扣完的預支自動轉下個月。'),
    step(null, '帳號：崗位輪調', '在「帳號」改崗位（外場／內場／外送），夥伴會收到通知，系統會補上新崗位的必讀。'),
    step(null, '待辦', '在「待辦」交辦事情給自己、店長或每位夥伴，到期早上 9 點會提醒。')
  ],
  fin: () => ME.perms.admin ? [
    step('.segctl', '記帳', '「記今天」看某一天；「核銷」看店長記的支出；「本月」看整月。'),
    step(null, '核銷', '看收據照片對數字，對就按核銷（自動進股東帳務），不對就退回寫原因，店長會收到通知。')
  ] : [
    step('#main .card', '今天營收', '打烊後照 POS 日結單填，拍日結單，記了就自動進帳務。'),
    step(() => document.querySelectorAll('#main .card')[1], '店裡花的錢', '從抽屜拿現金付的才記，一筆一筆記、拍收據，老闆核銷後進帳務。')
  ],
  safety: () => [
    step('.segctl', '五種紀錄', '冰箱溫度、瓦斯安全、油品、廢油回收、廁所清潔，照總部的紙本表格做的。'),
    step('.phead .act .btn', '記一筆', '冰箱：早上開店、下班前每台都要記，一定要用相機現場拍溫度顯示，相簿的舊照片不收。'),
    step('#main .card', '跟紙本一樣的月表', '紅字＝超出標準，店長和老闆手機會馬上收到。📷 可以看照片，✓ 是店長複檢過。'),
    step(null, '沒記會提醒', '早上 8:30、下午 4:30 還沒記，今天上班的人和店長會收到提醒。')
  ],
  deliv: () => delivDemo()
};
const TOUR_DONE = { deliv: () => LOAD.deliv() };

/* 外送示範：一張假的單，一步一步照給大家看怎麼點（不會存） */
function delivDemo() {
  const R = (status, x) => Object.assign({ id: -1, seq: 1, source: '電話', customer: '示範公司 行政部（示範）', address: '示範路 1 號', boxes: 30, bags: 3, due: '12:00',
    pay: '現金收款', collect: 3600, amount: 3600, status, rider: '小明', rider_id: -2, items: '排骨 15、雞腿 15', late_min: -40, cancelled: 0, waiting_accept: false }, x || {});
  const page = (title, sub, inner) => { closeSheet(); $('#main').innerHTML = `<div class="banner blue" style="cursor:default">示範：這是假的單，跟著看就好，不會存。</div>` + hero('外送', title, sub) + inner; };
  const board = r => page('外送看板。', '店長、老闆看全部的單。', `<div class="lane" id="demo_card">${dcard(r)}</div>`);
  const mine = r => page('我的外送。', '外送夥伴手機上看到的。', `<div id="demo_card">${dcard(r, true)}</div><div id="demo_acts">${mineActions(r)}</div>`);
  const form = () => openSheet(`<div class="shead"><h3>開外送單（示範）</h3></div><div class="card">
      <label>客人（單位）</label><input value="示範公司 行政部" disabled><label>地址</label><input value="示範路 1 號" disabled>
      <div class="g3"><div><label>便當個數</label><input value="30" disabled></div><div><label>袋數</label><input value="3" disabled></div><div id="demo_amt"><label>金額（現金收款必填）</label><input value="3600" disabled></div></div>
      <div id="demo_due" class="g2"><div><label>要送達</label><input value="12:00" disabled></div><div><label>預計出餐</label><input value="11:30" disabled></div></div>
      <div id="demo_rider"><label>派給</label><select disabled><option>小明（外送）· 空閒</option></select></div></div>`);
  const pick = () => openSheet(`<div class="shead"><h3>取餐核對（示範）</h3></div><div class="card" id="demo_pick">
      ${['品項、份數對（30 個）', '袋數對（3 袋，袋上有貼單）', '餐具、筷子湯匙', '湯、飲料（沒有就勾）'].map(x => `<label class="chk"><input type="checkbox" checked disabled> ${x}</label>`).join('')}
      <button class="btn full" style="margin-top:14px" disabled>都對了，取餐出發</button></div>`);
  const drop = () => openSheet(`<div class="shead"><h3>送達（示範）</h3></div><div class="card" id="demo_drop">
      <label>交給誰／放哪裡</label><div class="seg"><button class="on">交給本人</button><button>放櫃台</button><button>交警衛或管理室</button><button>放門口</button></div>
      <label>照片（放櫃台、門口、管理室一定要拍）</label><input type="file" disabled>
      <label>實際收到的現金（應收 3,600）</label><input value="3600" disabled>
      <button class="btn green full" style="margin-top:14px" disabled>確認送達</button></div>`);
  const cash = () => page('外送看板。', '下班前收現金。', `<div class="card" id="demo_cash"><h3>現金待繳回</h3><div class="row"><div><div class="n">小明 3,600 元</div><div class="m">1 張單</div></div><button class="btn sm" disabled>收回現金</button></div></div>`);
  return [
    step(null, '外送怎麼做：示範一遍', '用一張假的單，從開單到送達、繳現金，一步一步照給你看哪裡要點。大約 1 分鐘。'),
    step('.phead .act .btn', '1. 客人訂了 → 開外送單', '電話、LINE、團訂談好的單，誰接到誰開。', { before: () => board(R('新單', { rider: '', rider_id: null })) }),
    step('#demo_amt', '2. 金額', '現金收款一定要填金額，送到才知道要收多少。', { before: form }),
    step('#demo_due', '3. 送達時間、出餐時間', '系統會在送達前 45 分提醒「該開始做了」、30 分還沒派人也會提醒。'),
    step('#demo_rider', '4. 派給外送夥伴', '看得到誰空閒。前一班現金還沒繳的，不能派現金單。'),
    step('#demo_card', '5. 單子出現在看板', '派出去，外送夥伴手機會跳通知。', { before: () => board(R('新單', { waiting_accept: true })) }),
    step('#demo_acts .btn.green', '6. 外送夥伴：按「接受」', '5 分鐘沒按接受，店長會收到提醒，可以改派。', { before: () => mine(R('新單', { waiting_accept: true })) }),
    step('#demo_card .btns .btn:not(.gray)', '7. 廚房：開始做 → 已出餐', '做好按「已出餐」，外送夥伴手機會收到「可以來取餐」。', { before: () => board(R('製作中')) }),
    step('#demo_acts .btn', '8. 到店取餐、核對', '外送夥伴到櫃台按這個。', { before: () => mine(R('已出餐')) }),
    step('#demo_pick', '9. 逐項核對', '份數、袋數、餐具、湯飲料、收據，全部勾了才能出發。', { before: pick }),
    step('#demo_acts', '10. 路上', '「導航」開地圖、「打給客人」、「快到了」可以複製 LINE 訊息給客人。', { before: () => mine(R('配送中')) }),
    step('#demo_acts .btn.green', '11. 到了：定位打卡', '到客人那裡先按「到了・定位打卡」，記下時間和位置（跟 Uber、熊貓一樣）。'),
    step('#demo_acts .btn.green', '12. 已送達', '打完卡才會出現「已送達」。', { before: () => mine(R('配送中', { arrive_at: todayStr() + ' 11:52:00', arrive_m: 1800 })) }),
    step('#demo_drop', '13. 送達拍照、收錢', '親手交給本人可以不拍；放櫃台、門口、管理室一定要拍（拍餐點和門牌，不要拍到人臉）。現金單填實收。', { before: drop }),
    step('#demo_cash', '14. 下班繳現金', '把現金交給店長，店長點清楚按「收回現金」。前一班沒繳，下一班不能接現金單。', { before: cash }),
    step(null, '示範結束', '剛剛都是假的單，沒有存。忘了怎麼做，按右上角「?」再看一次。', { before: () => closeSheet(), last: '開始用' })
  ];
}

/* ═════════ 必讀還沒看完 → 只能打卡、看訓練、我 ═════════ */
function gated(v) { return ME && ME.role === 'staff' && ME.train_left > 0 && !['punch', 'manual', 'me'].includes(v); }
function gatePage() {
  const pos = ME.position ? `「${esc(ME.position)}」（${esc(ME.pos_note[ME.position] || '')}）` : '還沒設定';
  $('#main').innerHTML = hero('訓練', '先看完必讀。', `你的崗位：${pos}。開始用這一頁之前，先把崗位必讀看完，還有 <b>${ME.train_left}</b> 篇。打卡不受影響。`)
    + `<div class="btns"><button class="btn" onclick="go('manual')">去看必讀</button></div>`;
}

/* ═════════ 每週新聞 ═════════ */
const NEWS_STYLE = {
  '食安': ['#ff3b30', '#ff9500', '<path d="M12 3l7 3v5c0 4.6-3 8.3-7 10-4-1.7-7-5.4-7-10V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>'],
  '餐飲業': ['#ff9500', '#ffcc00', '<path d="M3 11h18a9 9 0 0 1-18 0z"/><path d="M8 7c0-1.5 1-2 1-3.5M12 7c0-1.5 1-2 1-3.5M16 7c0-1.5 1-2 1-3.5"/>'],
  '客戶服務': ['#0071e3', '#5ac8fa', '<path d="M5 4h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-8l-5 4v-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="M8 10h.01M12 10h.01M16 10h.01"/>'],
  '觀光餐飲': ['#34c759', '#30b0c7', '<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.6"/>'],
  '外送平台': ['#af52de', '#ff2d55', ICON.deliv]
};
let NI = 0, NEWS = [];
function newsCover(cat, i) {
  const [a, b, icon] = NEWS_STYLE[cat] || NEWS_STYLE['餐飲業'];
  return `<svg viewBox="0 0 400 200" role="img" aria-label="${esc(cat)}" preserveAspectRatio="xMidYMid slice"><defs><linearGradient id="ng${i}" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs>
    <rect width="400" height="200" fill="url(#ng${i})"/><circle cx="330" cy="40" r="120" fill="rgba(255,255,255,.08)"/><circle cx="60" cy="210" r="90" fill="rgba(255,255,255,.07)"/>
    <g transform="translate(262 46) scale(4.6)" fill="none" stroke="rgba(255,255,255,.92)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">${icon}</g>
    <text x="26" y="170" fill="#fff" font-size="30" font-weight="700" font-family="-apple-system,'PingFang TC','Noto Sans TC',sans-serif">${esc(cat)}</text></svg>`;
}
LOAD.news = async function () {
  NEWS = await api('/api/news'); localNav('每週新聞');
  if (!NEWS.length) { $('#main').innerHTML = hero('每週新聞', '這週的新聞還在整理。', '每週一早上出刊：食安、餐飲業、客戶服務、觀光餐飲。') ; return; }
  if (NI >= NEWS.length) NI = 0;
  const n = NEWS[NI], wk = n.week.split('-W');
  let h = hero(`每週新聞 · ${wk[0]} 年第 ${+wk[1]} 週`, esc(n.title), esc(n.intro || ''));
  h += `<div class="ngrid">${n.items.map((x, i) => `<article class="ncard"><div class="cover">${newsCover(x.cat, i)}</div><div class="in">
      <div class="cat" style="color:${(NEWS_STYLE[x.cat] || NEWS_STYLE['餐飲業'])[0]}">${esc(x.cat)}</div><h3>${esc(x.title)}</h3><p>${esc(x.summary)}</p>
      ${x.tip ? `<div class="tip">${esc(x.tip.replace(/^對我們店[:：]\s*/, ''))}</div>` : ''}
      <div class="src">${esc(x.source || '')}${x.date ? ' · ' + md(x.date) : ''}<a href="${esc(x.url)}" target="_blank" rel="noopener">看原文 ↗</a></div></div></article>`).join('')}</div>`;
  if (NEWS.length > 1) h += `<h2>往期。</h2><div class="card">${NEWS.map((x, i) => `<div class="row click" onclick="NI=${i};LOAD.news();scrollTo(0,0)"><div><div class="n">${esc(x.title)}</div><div class="m">${esc(x.week)} · ${x.items.length} 則</div></div>${i === NI ? '<span class="tag t-blue">正在看</span>' : '<span class="chev">›</span>'}</div>`).join('')}</div>`;
  h += `<div class="small" style="margin-top:14px">摘要是我們自己整理的重點，完整內容請看原文。</div>`;
  if (ME.perms.admin) h += `<div class="btns"><button class="btn gray sm" onclick="if(confirm('下架這一期？'))api('/api/news/remove',{id:${n.id}}).then(()=>LOAD.news())">下架這一期</button></div>`;
  $('#main').innerHTML = h;
  if (!n.read) { api('/api/news/read', { id: n.id }).then(() => { n.read = true; if (NI === 0) { ME.news_unread = 0; renderNav(); } }).catch(() => { }); }
};

/* ═════════ 待辦 ═════════ */
let TODO = null;
function todoRow(t, mine) {
  const late = !t.done_at && t.due && t.due < todayStr();
  return `<div class="row todo ${t.done_at ? 'done' : ''}"><label class="tck"><input type="checkbox" ${t.done_at ? 'checked' : ''} onchange="todoDone(${t.id},this.checked)"><span></span></label>
    <div style="flex:1;min-width:0"><div class="n">${esc(t.title)}</div><div class="m">${mine ? '' : esc(t.who) + ' · '}${t.due ? (late ? '<b style="color:var(--red)">已過期 ' : '') + md(t.due) + ' 前' + (late ? '</b>' : '') : '沒有期限'}${t.note ? ' · ' + esc(t.note) : ''}${t.done_at ? ' · ' + md(t.done_at) + ' ' + esc(t.done_name || '') + ' 完成' : ''}</div></div>
    ${(t.created_by === ME.id || ME.perms.admin) ? `<button class="btn gray sm" onclick="todoRemove(${t.id})">刪除</button>` : ''}</div>`;
}
function todoForm(people) {
  const can = ME.perms.fin;
  return `<details class="fold" style="margin-top:12px"><summary>＋ 新增待辦</summary><div class="in"><label>要做什麼</label><input id="td_t" placeholder="例：幫大家拍形象照">
    <div class="g2">${can ? `<div><label>交給誰</label><select id="td_a"><option value="">我自己</option><option value="staff">每位夥伴各一份</option>${people.filter(p => p.id !== ME.id).map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></div>` : ''}
    <div><label>期限（選填）</label><input type="date" id="td_d"></div></div><label>備註（選填）</label><input id="td_n">
    <button class="btn" style="margin-top:14px" onclick="todoSave()">新增</button><div id="td_m"></div></div></details>`;
}
async function todoSave() {
  try { await api('/api/todo/save', { title: $('#td_t').value, assignee: ($('#td_a') || {}).value || null, due: $('#td_d').value || null, note: $('#td_n').value }); await refreshBadges(); go(VIEW, true); }
  catch (e) { msgOk('#td_m', e); }
}
async function todoDone(id, on) { try { await api('/api/todo/done', { id, done: on }); await refreshBadges(); go(VIEW, true); } catch (e) { alert(e.message); } }
async function todoRemove(id) { if (!confirm('刪除這個待辦？')) return; await api('/api/todo/remove', { id }); go(VIEW, true); }
async function todoCard() {
  const d = await api('/api/todos'); const mine = d.rows.filter(t => t.assignee === ME.id && !t.done_at);
  return `<div class="card" id="todo_card"><h3>我的待辦${mine.length ? ` <span class="tag t-warn">${mine.length}</span>` : ''}</h3>
    ${mine.map(t => todoRow(t, true)).join('') || '<div class="muted">目前沒有待辦。</div>'}${todoForm(d.people)}</div>`;
}
async function bTodo() {
  const d = await api('/api/todos'); TODO = d;
  const open = d.rows.filter(t => !t.done_at), done = d.rows.filter(t => t.done_at);
  $('#main').innerHTML = hero('待辦', '工作待辦。', '交辦給自己、店長或每位夥伴；到期當天早上 9 點會提醒，做完交辦的人會收到通知。')
    + `<div class="card"><h3>還沒做（${open.length}）</h3>${open.map(t => todoRow(t)).join('') || '<div class="muted">都做完了。</div>'}${todoForm(d.people)}</div>`
    + (done.length ? `<details class="fold"><summary>做完的<small>${done.length}</small></summary><div class="in">${done.slice(0, 40).map(t => todoRow(t)).join('')}</div></details>` : '');
}

/* ═════════ 個人檔案 ═════════ */
let PPHOTO = null;
const avatar = (p, size) => p && p.has_photo ? `<img class="pav" style="width:${size}px;height:${size}px" src="/api/profile/photo?id=${p.id}&t=${encodeURIComponent(p.updated || '')}" alt="">`
  : `<span class="pav ph" style="width:${size}px;height:${size}px;font-size:${Math.round(size * .42)}px">${initial(p ? p.name : '?')}</span>`;
async function profileCards() {
  const ps = await api('/api/profiles'), me = ps.find(p => p.id === ME.id) || { id: ME.id, name: ME.name };
  PPHOTO = null;
  const prof = `<div class="card" id="prof_card"><h3>個人檔案</h3><div class="profhead">${avatar(me, 96)}<div>
      <label class="btn sec sm" style="cursor:pointer">${me.has_photo ? '換形象照' : '上傳形象照'}<input type="file" accept="image/*" hidden onchange="readPhoto(this.files[0],900).then(p=>{PPHOTO=p;$('#prof_card .pav').outerHTML='<img class=pav style=width:96px;height:96px src='+p+'>'}).catch(e=>alert(e.message))"></label>
      <div class="small" style="margin-top:6px">正面、笑一個，背景乾淨就好。</div></div></div>
    <div class="g2"><div><label>大家怎麼叫你</label><input id="pf_n" value="${esc(me.nickname || '')}" placeholder="例：小明"></div><div><label>喜歡／拿手的</label><input id="pf_l" value="${esc(me.likes || '')}" placeholder="例：炸排骨、跟客人聊天"></div></div>
    <label>自我介紹</label><textarea id="pf_i" rows="4" placeholder="例：我是小明，在內場負責備料和出餐。以前在餐飲業做了三年，最拿手的是…">${esc(me.intro || '')}</textarea>
    <button class="btn" style="margin-top:14px" onclick="profSave()">存檔</button><div id="pf_m"></div></div>`;
  const team = `<details class="fold" id="team_card"><summary>認識夥伴<small>${ps.length} 位</small></summary><div class="in"><div class="team">${ps.map(p => `<div class="mate">${avatar(p, 64)}
      <div><div class="n">${esc(p.nickname || p.name)}${p.nickname ? ` <span class="small">${esc(p.name)}</span>` : ''}</div>
      <div class="small">${p.role === 'admin' ? '老闆' : p.role === 'manager' ? (p.title || '店長') : (p.position || '夥伴')}${p.likes ? ' · ' + esc(p.likes) : ''}</div>
      <div class="m">${esc(p.intro || '還沒寫自我介紹')}</div></div></div>`).join('')}</div></div></details>`;
  return prof + team;
}
async function profSave(uid) {
  try { await api('/api/profile/save', { user_id: uid || null, nickname: $('#pf_n').value, intro: $('#pf_i').value, likes: $('#pf_l').value, photo: PPHOTO }); PPHOTO = null; await refreshBadges(); go(VIEW, true); }
  catch (e) { msgOk('#pf_m', e); }
}
async function bossPhoto(uid, inp) {   // 老闆幫夥伴上傳形象照（帳號頁）
  try { const p = await readPhoto(inp.files[0], 900); await api('/api/profile/save', { user_id: uid, photo: p }); LOAD.boss(); } catch (e) { alert(e.message); }
}

/* ═════════ 我（加：個人檔案、待辦、認識夥伴、重看導覽） ═════════ */
LOAD.me = async function () {
  const st = ME.acting ? 'off' : await pushStatus(), inbox = await api('/api/inbox');
  let h = hero('我', esc(ME.acting ? ME.real_name : ME.name), ME.acting ? `正在模擬${ME.acting === 'manager' ? '店長' : '夥伴'}` : `帳號 ${esc(ME.username)}${ME.role === 'manager' ? ' · ' + (ME.title || '店長') : ME.role === 'admin' ? ' · 老闆' : ME.position ? ' · ' + esc(ME.position) : ''}`);
  if (ME.can_switch) h += `<div class="card"><h3>切換角色</h3><p class="muted">看店長、夥伴手機上的畫面，不用另外登入。</p>
    <div class="seg">${ROLES.map(([k, t]) => `<button class="${(ME.acting || 'admin') === k ? 'on' : ''}" onclick="switchRole('${k}')">${t}</button>`).join('')}</div></div>`;
  if (!ME.acting) h += await todoCard() + await profileCards();
  if (!ME.acting) h += `<div class="card" id="push_card"><h3>手機通知</h3>
    ${st === 'on' ? `<div class="banner ok">這支手機已經開啟通知。</div><div class="btns"><button class="btn sec" onclick="testPush()">傳一則測試通知給我</button></div>`
      : `<p class="muted">${st === 'off' ? '開啟後，新公告、老闆回你的日誌、外送單、遲到提醒，會直接跳到手機上。' : esc(pushHelp(st))}</p>
         ${st === 'off' ? '<button class="btn" onclick="turnOnPush(this)">開啟通知</button>' : ''}`}</div>`;
  h += `<details class="fold" ${inbox.some(x => !x.read) ? 'open' : ''}><summary>最近的通知<small>${inbox.filter(x => !x.read).length ? inbox.filter(x => !x.read).length + ' 則沒看' : ''}</small></summary><div class="in">
    ${inbox.map(x => `<div class="row click" onclick="location.hash='${esc((x.url || '/#').split('#')[1] || '')}'"><div><div class="n">${x.read ? '' : '<span class="tag t-red" style="margin:0 6px 0 0">新</span>'}${esc(x.title)}</div><div class="m">${esc(x.body || '')}</div></div><span class="small">${md(x.created)} ${hm(x.created)}</span></div>`).join('') || '<div class="muted">還沒有通知</div>'}</div></details>`;
  if (!ME.acting) h += `<details class="fold"><summary>改密碼</summary><div class="in"><label>舊密碼</label><input id="po" type="password"><label>新密碼（至少 6 碼）</label><input id="pn" type="password">
    <button class="btn" style="margin-top:16px" onclick="chpw()">改密碼</button><div id="perr"></div></div></details>`;
  h += `<div class="btns"><button class="btn sec" onclick="resetTours()">重看所有導覽</button><button class="btn gray" onclick="logout()">登出</button></div>`;
  $('#main').innerHTML = h;
  if (inbox.some(x => !x.read)) { await api('/api/inbox/read', {}); ME.inbox_unread = 0; renderNav(); }
};

/* ═════════ 我很棒日誌（Apple 風格：一天一張卡；保留照片、收回；看得到每一天老闆說了什麼） ═════════ */
let JF = 'all';
const dayTitle = d => { const x = new Date(d + 'T00:00:00'); return `${x.getMonth() + 1} 月 ${x.getDate()} 日 星期${WK[x.getDay()]}`; };
async function journalList() {
  const [ts, ps] = await Promise.all([api('/api/journal/threads'), api('/api/profiles')]), wrote = ts.filter(t => t.wrote_today).length;
  const pf = Object.fromEntries(ps.map(p => [p.id, p]));
  $('#main').innerHTML = hero('日誌', '我很棒日誌。', `今天 ${wrote} / ${ts.length} 位夥伴寫了。點名字看每一天、回覆。晚上 9 點還沒寫的人，系統會用你的名義傳一則關心。`) +
    `<div class="card jlist">${ts.map(t => `<div class="thread" onclick="JU=${t.id};LOAD.journal()">${avatar(pf[t.id] || { id: t.id, name: t.name }, 44)}
     <div class="t"><div><b>${esc(t.name)}</b> <span class="tag ${t.wrote_today ? 't-ok' : 't-warn'}">${t.wrote_today ? '今天寫了' : '今天還沒寫'}</span><span class="tag">本月 ${t.days_month} 天</span></div>
     <div class="last">${t.last ? esc(t.last.who) + '：' + esc(t.last.text) : '還沒寫過'}</div></div>
     <div style="text-align:right">${t.last ? `<div class="small">${md(t.last.at)} ${hm(t.last.at)}</div>` : ''}${t.unread ? `<span class="cnt">${t.unread}</span>` : ''}</div></div>`).join('') || '<div class="muted">還沒有夥伴帳號</div>'}</div>`;
  refreshBadges();
}
async function journalThread() {
  const admin = ME.perms.admin, d = await api('/api/journal' + (admin ? '?uid=' + JU : '')), ms = d.messages, td = todayStr(), owner = d.thread.id;
  const days = [...new Set(ms.map(m => m.day))].sort().reverse();
  if (!days.includes(td)) days.unshift(td);
  let h = admin ? `<button class="btn gray sm" onclick="JU=0;LOAD.journal()">‹ 全部夥伴</button>` + hero('日誌', esc(d.thread.name) + ' 的日誌。', d.wrote_today ? '今天寫了。' : '今天還沒寫。在每一天下面回覆，他會收到通知。')
    : hero('日誌', '我很棒日誌。', '每天寫下三件今天自己做得好的事。老闆每天都會看、會回你。');
  if (!admin) h += `<div class="card" id="jcomp"><div class="jhead"><b>今天 ${md(td)}（${wkOf(td)}）</b>${d.wrote_today ? '<span class="tag t-ok">今天寫了</span>' : ''}</div>
      <textarea id="jtext" rows="4" placeholder="1. 今天我…\n2. \n3. "></textarea><div class="preview" id="jprev" hidden></div>
      <div class="btns"><label class="btn gray sm" style="cursor:pointer">${svg('photo')} 附照片<input type="file" accept="image/*" hidden onchange="pickPhoto(this)"></label><span style="flex:1"></span><button class="btn" onclick="sendJournal()">送出</button></div></div>`;
  h += `<div class="seg" id="jseg" style="max-width:320px;margin:6px 0 18px"><button class="${JF === 'all' ? 'on' : ''}" onclick="JF='all';journalThread()">全部</button><button class="${JF === 'boss' ? 'on' : ''}" onclick="JF='boss';journalThread()">老闆說的</button></div>`;
  const ent = m => {
    const mine = m.author_id === ME.id, boss = m.author_role === 'admin';
    if (m.removed) return `<div class="jent gone">${mine ? '你' : esc(m.author)}收回了一則（${hm(m.created)}）</div>`;
    const can = mine && m.day === td;
    return `<div class="jent ${boss ? 'boss' : ''}">${boss ? `<div class="who">${admin ? '你' : '老闆'}${m.auto ? '<span class="tag">每晚關心</span>' : ''}<span class="small">${hm(m.created)}</span></div>` : `<div class="who2 small">${hm(m.created)}${can ? ` · <a onclick="unsend(${m.id})">收回</a>` : ''}</div>`}
      ${m.body ? `<div class="txt">${esc(m.body)}</div>` : ''}${m.photo ? `<img src="/api/journal/photo?id=${m.id}" loading="lazy" alt="照片" onclick="zoom(this.src)">` : ''}
      ${boss && can ? `<div class="small"><a onclick="unsend(${m.id})">收回</a></div>` : ''}</div>`;
  };
  const cards = days.map(day => {
    let list = ms.filter(m => m.day === day);
    const wrote = list.some(m => m.author_id === owner && !m.removed);
    if (JF === 'boss') { list = list.filter(m => m.author_role === 'admin'); if (!list.length) return ''; }
    if (!list.length && day === td && !admin) return '';
    return `<div class="card jday"><div class="jhead"><b>${dayTitle(day)}</b>${JF === 'all' ? `<span class="tag ${wrote ? 't-ok' : 't-warn'}">${wrote ? '有寫' : '沒寫'}</span>` : ''}</div>
      ${list.map(ent).join('') || '<div class="muted">這天還沒寫。</div>'}
      ${admin ? `<div class="jreply"><textarea rows="1" id="jr_${day}" placeholder="回覆這一天…" oninput="grow(this)"></textarea><button class="btn sm" onclick="sendReply('${day}')">回覆</button></div>` : ''}</div>`;
  }).join('');
  h += cards || `<div class="card muted">${JF === 'boss' ? '老闆還沒回過。' : '還沒寫過。'}</div>`;
  $('#main').innerHTML = h; PHOTO = null; refreshBadges();
}
async function sendJournal() {
  const t = $('#jtext'); if (!t.value.trim() && !PHOTO) return t.focus();
  try { await api('/api/journal/post', { body: t.value, photo: PHOTO }); journalThread(); } catch (e) { alert(e.message); }
}
async function sendReply(day) {
  const t = $('#jr_' + day); if (!t.value.trim()) return t.focus();
  try { await api('/api/journal/post', { body: t.value, uid: JU, day }); journalThread(); } catch (e) { alert(e.message); }
}

/* ═════════ 訓練：崗位必讀放最前面 ═════════ */
function renderManual() {
  const admin = ME.perms.admin, staff = ME.role === 'staff', q = MQ.trim();
  const list = q ? MS.filter(m => (m.chapter + m.title + m.body).includes(q)) : MS;
  const req = MS.filter(m => m.required), reqDone = req.filter(m => m.read_at).length;
  let h = hero('訓練', '教育訓練。', `現場會用到的做法都在這裡。讀完一篇按「我讀完了」${admin ? '，你看得到誰讀過' : '，老闆看得到'}。`);
  if (staff) h += `<div class="card" id="mreq"><b>你的崗位：${ME.position ? esc(ME.position) + '（' + esc(ME.pos_note[ME.position] || '') + '）' : '還沒設定（先看共同必讀）'}</b>
      <div style="margin-top:6px">必讀 ${reqDone} / ${req.length} 篇${reqDone < req.length ? '　<span class="tag t-warn">看完才能用其他功能，打卡不受影響</span>' : '　<span class="tag t-ok">必讀都看完了</span>'}</div>
      <div class="bar"><i style="width:${req.length ? Math.round(reqDone * 100 / req.length) : 100}%"></i></div></div>`;
  else h += `<div id="mreq"></div>`;
  h += `<input id="mq" placeholder="搜尋，例如：白飯、洗手、收銀、叫菜" value="${esc(MQ)}" oninput="MQ=this.value;renderManual();const e=$('#mq');e.focus();e.setSelectionRange(e.value.length,e.value.length)">`;
  const item = m => `<details class="fold"${q ? ' open' : ''}>
     <summary>${m.required && staff ? '<span class="tag t-warn" style="margin:0 8px 0 0">必讀</span>' : ''}${esc(m.title)}<small>${admin ? `${(m.readers || []).filter(r => r.at).length}/${(m.readers || []).length} 讀過` : (m.read_at ? '<span class="tag t-ok">讀完了</span>' : '')}</small></summary>
     <div class="in"><div class="mbody">${rich(m.body)}</div>
     ${admin ? `<details style="margin-top:14px"><summary class="small" style="cursor:pointer">誰讀過 · 修改</summary>
        <div style="margin-top:8px">${(m.readers || []).map(r => `<span class="tag ${r.at ? 't-ok' : 't-warn'}">${esc(r.name)} ${r.at ? md(r.at.slice(0, 10)) : '未讀'}</span>`).join('')}</div>
        <div style="margin-top:10px">${manualForm(m)}</div></details>`
      : (m.read_at ? `<div class="small" style="margin-top:12px">${md(m.read_at.slice(0, 10))} 讀完</div>` : `<button class="btn" style="margin-top:16px" onclick="mAck(${m.id})">我讀完了</button>`)}</div></details>`;
  const groups = staff && !q ? [['必讀', list.filter(m => m.required)], ['其他', list.filter(m => !m.required)]] : [['', list]];
  h += groups.map(([g, its]) => { if (!its.length) return ''; const chs = [...new Set(its.map(m => m.chapter))];
    return (g ? `<h2>${g === '必讀' ? '你的必讀。' : '其他。'}<span class="g">${g === '必讀' ? '照你的崗位排好的，先看這些。' : '有空再看，用得到的時候搜尋。'}</span></h2>` : '') +
      chs.map(ch => { const xs = its.filter(m => m.chapter === ch); return `<div class="chap">${esc(ch)}<small>${xs.length} 篇</small></div>` + xs.map(item).join(''); }).join(''); }).join('')
    || `<div class="card muted">${q ? '找不到「' + esc(q) + '」' : '還沒有內容。'}</div>`;
  $('#main').innerHTML = h;
}
async function mAck(id) {
  const before = ME.train_left;
  await api('/api/manual/ack', { id }); MS = await api('/api/manual'); await refreshBadges(); renderManual();
  if (before > 0 && ME.train_left === 0) alert('崗位必讀都看完了！其他功能都打開了。');
}

/* ═════════ 開發：按「撥」→ 掛掉回到畫面 → 自動跳出「記一通」 ═════════ */
let PCALL = null;
function callStart(id, name) {
  PCALL = { id, name, at: Date.now(), left: false };
  setTimeout(() => { if (PCALL && PCALL.id === id && !PCALL.left && !document.hidden) callToast(); }, 4000);   // 電腦上沒離開畫面：給一個「記錄這一通」
}
function callToast() {
  const t = document.createElement('div'); t.className = 'ctoast';
  t.innerHTML = `<span>打給 ${esc(PCALL.name)}，打完記一下結果</span><button class="btn sm" onclick="this.parentNode.remove();callBack()">記錄這一通</button><button class="btn gray sm" onclick="this.parentNode.remove();PCALL=null">不用</button>`;
  document.body.appendChild(t); setTimeout(() => t.remove(), 60000);
}
async function callBack() {
  if (!PCALL) return; const { id, name } = PCALL; PCALL = null;
  await openLead(id);
  const box = [...document.querySelectorAll('#sheetBody .card h3')].find(x => x.textContent === '記一通');
  if (box) { box.parentNode.insertAdjacentHTML('afterbegin', `<div class="banner blue" style="cursor:default">剛剛打給 ${esc(name)}：記一下結果（沒接也要記）</div>`); box.parentNode.scrollIntoView({ block: 'start' }); }
}
document.addEventListener('visibilitychange', () => {
  if (!PCALL) return;
  if (document.hidden) { PCALL.left = true; return; }
  if (PCALL.left && Date.now() - PCALL.at < 3 * 3600 * 1000) setTimeout(callBack, 300);
});
