/* =========================================================================
 * 安全数据周报看板 · 云服务接入
 * 模块：Auth（邮箱登录）/ Database（周报云端存储）/ Storage（Excel 备份）/ LLM（AI 解读）
 * 依赖：cloud_config.js 提供 window.CLOUD_PUBLIC_CONFIG；CDN 提供全局 WorkBuddyCloud
 * 设计原则：云端为「增强」——任何云端调用失败都不影响看板本身的渲染与本地缓存。
 * ========================================================================= */
(function () {
  'use strict';

  var cfg = window.CLOUD_PUBLIC_CONFIG;
  var cloud = null;
  var hasSDK = typeof window.WorkBuddyCloud !== 'undefined';

  if (cfg && hasSDK) {
    try {
      cloud = window.WorkBuddyCloud.createWorkBuddyCloud({
        endpoint: cfg.endpoint,
        publishableKey: cfg.publishableKey,
      });
    } catch (e) {
      console.warn('[云服务] 初始化失败，云端功能将不可用：', e);
      cloud = null;
    }
  } else if (!hasSDK) {
    console.warn('[云服务] SDK 未加载（仅发布域名可启用云端功能）');
  }

  window.__cloud = cloud;
  var pendingOtp = null; // { email, verificationId, isExistingUser }

  /* ----------------------------- 工具 ----------------------------- */
  function toast(msg, type) {
    if (typeof window.toast === 'function') {
      window.toast(msg, type || 'info');
    } else {
      console.log('[云服务]', msg);
    }
  }

  function isCloudEnabled() { return !!cloud; }

  /* --------------------------- 认证状态 UI --------------------------- */
  function renderCloudUser(session) {
    var btn = document.getElementById('cloudLoginBtn');
    var badge = document.getElementById('cloudUserBadge');
    if (!btn) return;
    if (session && session.user) {
      btn.textContent = '退出云端';
      btn.onclick = handleLogout;
      if (badge) {
        badge.style.display = 'inline';
        badge.textContent = (session.user.email || session.user.id).slice(0, 18);
      }
    } else {
      btn.textContent = '登录云端';
      btn.onclick = openLoginModal;
      if (badge) { badge.style.display = 'none'; badge.textContent = ''; }
    }
  }

  async function refreshSessionUI() {
    if (!cloud) return;
    try {
      var r = await cloud.auth.getSession();
      renderCloudUser(r.data || null);
    } catch (e) { renderCloudUser(null); }
  }

  /* ----------------------------- 登录弹窗 ----------------------------- */
  function ensureLoginModal() {
    if (document.getElementById('cloudLoginModal')) return;
    var wrap = document.createElement('div');
    wrap.id = 'cloudLoginModal';
    wrap.className = 'cloud-modal-mask';
    wrap.innerHTML = `
      <div class="cloud-modal">
        <div class="cloud-modal-head">
          <span>登录云端 · 安全数据周报</span>
          <button class="cloud-modal-x" onclick="closeLoginModal()">×</button>
        </div>
        <div class="cloud-tabs">
          <button class="cloud-tab active" data-ctab="pwd">密码登录</button>
          <button class="cloud-tab" data-ctab="otp">验证码登录</button>
          <button class="cloud-tab" data-ctab="signup">注册</button>
          <button class="cloud-tab" data-ctab="reset">找回密码</button>
        </div>
        <div class="cloud-msg" id="cloudLoginMsg"></div>

        <div class="cloud-pane" data-pane="pwd">
          <input id="lpEmail" class="cloud-input" placeholder="邮箱" type="email">
          <input id="lpPwd" class="cloud-input" placeholder="密码" type="password">
          <button class="cloud-btn" onclick="cloudLoginPwd()">登录</button>
        </div>

        <div class="cloud-pane" data-pane="otp" style="display:none">
          <input id="loEmail" class="cloud-input" placeholder="邮箱" type="email">
          <div class="cloud-row">
            <input id="loCode" class="cloud-input" placeholder="验证码" style="flex:1">
            <button class="cloud-btn ghost" type="button" onclick="cloudSendOtp(false)">获取验证码</button>
          </div>
          <button class="cloud-btn" onclick="cloudVerifyOtpLogin()">登录 / 注册</button>
          <div class="cloud-hint">已有账号直接登录；新邮箱将自动注册（需设置密码）。</div>
        </div>

        <div class="cloud-pane" data-pane="signup" style="display:none">
          <input id="lsEmail" class="cloud-input" placeholder="邮箱" type="email">
          <div class="cloud-row">
            <input id="lsCode" class="cloud-input" placeholder="验证码" style="flex:1">
            <button class="cloud-btn ghost" type="button" onclick="cloudSendOtp(true)">获取验证码</button>
          </div>
          <input id="lsPwd" class="cloud-input" placeholder="设置密码（注册必填）" type="password">
          <button class="cloud-btn" onclick="cloudSignup()">注册并登录</button>
        </div>

        <div class="cloud-pane" data-pane="reset" style="display:none">
          <input id="lrEmail" class="cloud-input" placeholder="邮箱" type="email">
          <button class="cloud-btn" onclick="cloudResetPwd()">发送重置邮件</button>
        </div>
      </div>`;
    document.body.appendChild(wrap);

    wrap.querySelectorAll('.cloud-tab').forEach(function (t) {
      t.onclick = function () {
        wrap.querySelectorAll('.cloud-tab').forEach(function (x) { x.classList.remove('active'); });
        t.classList.add('active');
        var name = t.getAttribute('data-ctab');
        wrap.querySelectorAll('.cloud-pane').forEach(function (p) {
          p.style.display = (p.getAttribute('data-pane') === name) ? '' : 'none';
        });
      };
    });
    wrap.addEventListener('click', function (e) { if (e.target === wrap) closeLoginModal(); });
  }

  function openLoginModal() {
    if (!isCloudEnabled()) { toast('云端功能仅在发布域名可用', 'error'); return; }
    ensureLoginModal();
    document.getElementById('cloudLoginMsg').textContent = '';
    document.getElementById('cloudLoginModal').style.display = 'flex';
  }
  function closeLoginModal() {
    var m = document.getElementById('cloudLoginModal');
    if (m) m.style.display = 'none';
  }

  function setMsg(txt, type) {
    var el = document.getElementById('cloudLoginMsg');
    if (!el) return;
    el.textContent = txt || '';
    el.className = 'cloud-msg' + (type ? ' ' + type : '');
  }

  async function cloudLoginPwd() {
    if (!cloud) return;
    var email = document.getElementById('lpEmail').value.trim();
    var pwd = document.getElementById('lpPwd').value;
    if (!email || !pwd) { setMsg('请输入邮箱和密码', 'err'); return; }
    setMsg('登录中...');
    var r = await cloud.auth.signInWithPassword({ email: email, password: pwd });
    if (r.error) { setMsg('登录失败：' + r.error.message, 'err'); return; }
    setMsg('登录成功', 'ok');
    setTimeout(closeLoginModal, 400);
  }

  async function cloudSendOtp(isSignup) {
    if (!cloud) return;
    var email = (isSignup ? document.getElementById('lsEmail') : document.getElementById('loEmail')).value.trim();
    if (!email) { setMsg('请输入邮箱', 'err'); return; }
    var r = await cloud.auth.sendOtp({ email: email });
    if (r.error) { setMsg('发送失败：' + r.error.message, 'err'); return; }
    pendingOtp = { email: email, verificationId: r.data.verificationId, isExistingUser: r.data.isExistingUser };
    setMsg('验证码已发送，请查收邮箱', 'ok');
  }

  async function cloudVerifyOtpLogin() {
    if (!cloud) return;
    if (!pendingOtp) { setMsg('请先获取验证码', 'err'); return; }
    var code = document.getElementById('loCode').value.trim();
    if (!code) { setMsg('请输入验证码', 'err'); return; }
    var r = await cloud.auth.verifyOtp({
      email: pendingOtp.email,
      verificationId: pendingOtp.verificationId,
      isExistingUser: pendingOtp.isExistingUser,
      token: code,
    });
    if (r.error) { setMsg('验证失败：' + r.error.message, 'err'); return; }
    pendingOtp = null;
    setMsg('登录成功', 'ok');
    setTimeout(closeLoginModal, 400);
  }

  async function cloudSignup() {
    if (!cloud) return;
    if (!pendingOtp) { setMsg('请先获取验证码', 'err'); return; }
    var code = document.getElementById('lsCode').value.trim();
    var pwd = document.getElementById('lsPwd').value;
    if (!code) { setMsg('请输入验证码', 'err'); return; }
    if (!pwd) { setMsg('注册需设置密码', 'err'); return; }
    var r = await cloud.auth.verifyOtp({
      email: pendingOtp.email,
      verificationId: pendingOtp.verificationId,
      isExistingUser: pendingOtp.isExistingUser,
      token: code,
      password: pwd,
    });
    if (r.error) { setMsg('注册失败：' + r.error.message, 'err'); return; }
    pendingOtp = null;
    setMsg('注册并登录成功', 'ok');
    setTimeout(closeLoginModal, 400);
  }

  async function cloudResetPwd() {
    if (!cloud) return;
    var email = document.getElementById('lrEmail').value.trim();
    if (!email) { setMsg('请输入邮箱', 'err'); return; }
    var r = await cloud.auth.resetPasswordForEmail(email);
    if (r.error) { setMsg('发送失败：' + r.error.message, 'err'); return; }
    setMsg('重置邮件已发送，请查收', 'ok');
  }

  async function handleLogout() {
    if (!cloud) return;
    await cloud.auth.signOut();
    toast('已退出云端', 'info');
    renderCloudUser(null);
  }

  /* --------------------------- 数据库：保存周报 --------------------------- */
  // 在 processWorkbook 之后、syncToPublic 中调用。需登录。
  async function cloudSaveReport() {
    if (!cloud) { toast('云端功能不可用', 'error'); return false; }
    var s = await cloud.auth.getSession();
    if (!s || !s.data) { toast('请先登录云端再保存', 'error'); return false; }
    var payload = {
      doc_key: 'main',
      data_json: {
        safety: window.store ? window.store.safety : [],
        rating: window.store ? window.store.rating : [],
        compliance: window.store ? window.store.compliance : [],
        accident: window.store ? window.store.accident : [],
      },
      detail_json: window.store ? window.store.detailData : {},
    };
    var r = await cloud.database.from('weekly_report').upsert(payload).select();
    if (r.error) { toast('云端保存失败：' + r.error.message, 'error'); return false; }

    // Excel 文件云端备份（best-effort）
    try {
      var f = window.__lastExcelFile;
      if (f) {
        var path = cloud.storage.userPath(s.data.user.id, 'uploads/' + (f.name || ('report_' + Date.now() + '.xlsx')));
        await cloud.storage.upload(path, f, { contentType: f.type || 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      }
    } catch (e) { console.warn('[云服务] Excel 备份失败（不影响数据保存）', e); }

    toast('已保存到云端，团队可在发布地址查看最新数据', 'success');
    return true;
  }

  /* --------------------------- 数据库：加载周报 --------------------------- */
  // 在 loadData 末尾调用，作为「已发布」最新数据源覆盖本地包。公开可读，无需登录。
  async function cloudLoadReport() {
    if (!cloud) return false;
    try {
      var r = await cloud.database.from('weekly_report').select('*').eq('doc_key', 'main').maybeSingle();
      if (r.error) { console.warn('[云服务] 读取失败', r.error); return false; }
      if (!r.data) return false;
      var dj = r.data.data_json || {};
      if (window.store) {
        if (dj.safety) window.store.safety = dj.safety;
        if (dj.rating) window.store.rating = dj.rating;
        if (dj.compliance) window.store.compliance = dj.compliance;
        if (dj.accident) window.store.accident = dj.accident;
        if (r.data.detail_json) window.store.detailData = r.data.detail_json;
      }
      window.__cloudUpdatedAt = r.data.updated_at;
      return true;
    } catch (e) { console.warn('[云服务] 读取异常', e); return false; }
  }

  /* --------------------------- 捕获上传的 Excel --------------------------- */
  function bindExcelCapture() {
    var inp = document.getElementById('excelFile');
    if (inp) inp.addEventListener('change', function (e) { window.__lastExcelFile = e.target.files && e.target.files[0]; });
  }

  /* --------------------------- LLM：AI 解读 --------------------------- */
  function ensureAIModal() {
    if (document.getElementById('cloudAIModal')) return;
    var m = document.createElement('div');
    m.id = 'cloudAIModal';
    m.className = 'cloud-modal-mask';
    m.innerHTML = `
      <div class="cloud-modal wide">
        <div class="cloud-modal-head">
          <span>🤖 AI 周报解读</span>
          <button class="cloud-modal-x" onclick="closeAIModal()">×</button>
        </div>
        <div class="cloud-msg" id="aiStatus"></div>
        <div class="cloud-ai-body" id="aiBody"></div>
        <div class="cloud-row" style="margin-top:8px">
          <button class="cloud-btn ghost" type="button" id="aiStopBtn" style="display:none">停止</button>
        </div>
      </div>`;
    document.body.appendChild(m);
    m.addEventListener('click', function (e) { if (e.target === m) closeAIModal(); });
  }
  function openAIModal() { ensureAIModal(); document.getElementById('aiBody').textContent = ''; document.getElementById('aiStatus').textContent = '准备中...'; document.getElementById('cloudAIModal').style.display = 'flex'; }
  function closeAIModal() { var m = document.getElementById('cloudAIModal'); if (m) m.style.display = 'none'; if (window.__aiAbort) { try { window.__aiAbort.abort(); } catch (e) {} } }

  function buildReportSummary() {
    var st = window.store || {};
    var lines = [];
    function avg(arr, key) {
      if (!arr || !arr.length) return null;
      var sum = 0, n = 0;
      arr.forEach(function (r) { var v = parseFloat(r[key]); if (!isNaN(v)) { sum += v; n++; } });
      return n ? (sum / n) : null;
    }
    lines.push('【安全权益】站点数=' + (st.safety ? st.safety.length : 0) + '，平均戴盔系带率=' + fmt(avg(st.safety, '戴盔系带率')) + '，平均超速率=' + fmt(avg(st.safety, '超速率')));
    lines.push('【站长评级】站点数=' + (st.rating ? st.rating.length : 0) + '，平均闯红灯率=' + fmt(avg(st.rating, '闯红灯率')) + '，平均里程逆行率=' + fmt(avg(st.rating, '逆行率')) + '，平均美团工服率=' + fmt(avg(st.rating, '美团工服率')));
    lines.push('【履约数据】记录数=' + (st.compliance ? st.compliance.length : 0));
    lines.push('【安全事故】记录数=' + (st.accident ? st.accident.length : 0));
    return lines.join('\n');
  }
  function fmt(v) { return v == null ? '无' : (Math.round(v * 1000) / 1000); }

  async function cloudAnalyze() {
    if (!cloud) { toast('云端功能仅在发布域名可用', 'error'); return; }
    openAIModal();
    var statusEl = document.getElementById('aiStatus');
    var bodyEl = document.getElementById('aiBody');
    var stopBtn = document.getElementById('aiStopBtn');

    var models;
    try {
      models = await cloud.llm.models.list();
    } catch (e) {
      statusEl.textContent = '获取模型失败：' + (e && e.message ? e.message : e);
      return;
    }
    var model = (models || []).find(function (m) { return m.disabled !== true; }) || (models && models[0]);
    if (!model) { statusEl.textContent = '当前没有可用的模型'; return; }

    var controller = new AbortController();
    window.__aiAbort = controller;
    stopBtn.style.display = '';
    stopBtn.onclick = function () { controller.abort(); };
    statusEl.textContent = '正在生成（' + (model.name || model.id) + '）...';

    var systemPrompt = '你是企业安全履约数据分析助手。基于周报数据，给出简明、可落地的主要风险点解读与改进建议。用中文分点输出，不要编造数据中不存在的事实。';
    var userPrompt = '以下是本周安全权益履约周报的核心汇总数据，请解读主要风险并给出改进建议：\n' + buildReportSummary();

    var text = '';
    try {
      for await (var chunk of cloud.llm.chat.completions.create({
        model: model.id,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt },
        ],
        stream: true,
        temperature: 0.6,
        signal: controller.signal,
      })) {
        var delta = chunk.choices && chunk.choices[0] && chunk.choices[0].delta && chunk.choices[0].delta.content;
        if (delta) { text += delta; bodyEl.textContent = text; bodyEl.scrollTop = bodyEl.scrollHeight; }
      }
      statusEl.textContent = '解读完成';
    } catch (e) {
      if (e && e.name === 'AbortError') { statusEl.textContent = '已停止'; }
      else { statusEl.textContent = '解读失败：' + (e && e.error && e.error.message ? e.error.message : (e && e.message ? e.message : e)); }
    } finally {
      stopBtn.style.display = 'none';
      window.__aiAbort = null;
    }
  }

  /* ----------------------------- 暴露全局 ----------------------------- */
  window.openLoginModal = openLoginModal;
  window.closeLoginModal = closeLoginModal;
  window.cloudLoginPwd = cloudLoginPwd;
  window.cloudSendOtp = cloudSendOtp;
  window.cloudVerifyOtpLogin = cloudVerifyOtpLogin;
  window.cloudSignup = cloudSignup;
  window.cloudResetPwd = cloudResetPwd;
  window.handleLogout = handleLogout;
  window.cloudAnalyze = cloudAnalyze;
  window.closeAIModal = closeAIModal;
  window.cloudSaveReport = cloudSaveReport;
  window.cloudLoadReport = cloudLoadReport;
  window.isCloudEnabled = isCloudEnabled;

  /* ----------------------------- 启动 ----------------------------- */
  function boot() {
    bindExcelCapture();
    if (cloud) {
      refreshSessionUI();
      try {
        cloud.auth.onAuthStateChange(function (event, session) {
          renderCloudUser(session && session.user ? session : null);
        });
      } catch (e) { console.warn('[云服务] 监听登录态失败', e); }
    }
    injectCloudStyles();
  }

  function injectCloudStyles() {
    if (document.getElementById('cloudStyles')) return;
    var s = document.createElement('style');
    s.id = 'cloudStyles';
    s.textContent = `
      .cloud-modal-mask{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:99999;font-family:inherit}
      .cloud-modal{background:#fff;color:#111;border-radius:12px;width:380px;max-width:92vw;padding:18px;box-shadow:0 12px 40px rgba(0,0,0,.35)}
      .cloud-modal.wide{width:560px}
      .cloud-modal-head{display:flex;justify-content:space-between;align-items:center;font-weight:700;font-size:1.05rem;margin-bottom:12px}
      .cloud-modal-x{border:none;background:none;font-size:1.4rem;cursor:pointer;line-height:1;color:#666}
      .cloud-tabs{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}
      .cloud-tab{border:1px solid #d1d5db;background:#f9fafb;border-radius:8px;padding:6px 10px;cursor:pointer;font-size:.85rem}
      .cloud-tab.active{background:#2563eb;color:#fff;border-color:#2563eb}
      .cloud-input{width:100%;box-sizing:border-box;padding:9px 10px;margin:6px 0;border:1px solid #d1d5db;border-radius:8px;font-size:.9rem}
      .cloud-row{display:flex;gap:8px;align-items:center}
      .cloud-btn{width:100%;padding:10px;border:none;border-radius:8px;background:#2563eb;color:#fff;font-weight:600;cursor:pointer;margin-top:6px}
      .cloud-btn.ghost{background:#e5e7eb;color:#111;width:auto;margin-top:0;padding:9px 12px}
      .cloud-msg{font-size:.82rem;min-height:18px;margin:4px 0;color:#374151}
      .cloud-msg.ok{color:#059669}.cloud-msg.err{color:#dc2626}
      .cloud-hint{font-size:.74rem;color:#6b7280;margin-top:6px}
      .cloud-ai-body{white-space:pre-wrap;line-height:1.6;font-size:.9rem;max-height:52vh;overflow:auto;background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin-top:6px}
    `;
    document.head.appendChild(s);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
