/* ══════════════════════════════════════════════════════════════════
   MyFarm — Shared Navigation & Session Logic
   Included by every app page (dashboard, livestock, livestock_list,
   add_livestock). Renders the sidebar + topbar and wires up
   role-based visibility, logout, and tab navigation.

   Usage in each page's <body>:
     <div id="sidebar-mount"></div>
     <div class="main">
       <div id="topbar-mount"></div>
       <div class="content"> ... page content ... </div>
     </div>

   Then call: initLayout('dashboard');  // pass the current page's tab key
════════════════════════════════════════════════════════════════ */

var ROLE_LABELS = { 1: 'Admin', 2: 'IT Manager', 3: 'Farm Manager' };

var ROLE_SUBS = {
    1: 'Full administrative access — all features are available to you.',
    2: 'Personnel & system management view.',
    3: 'Monitor livestock, herd performance, and farm activity.',
};

/* Each page's actual filename. null = not built yet (tab is inert). */
var TAB_PAGES = {
    dashboard:     'dashboard.html',
    livestock:     'livestock.html',
    myfarm:        null,
    personnel:     null,
    notifications: null,
};

var FARM_NAME, USER_NAME, USER_ID, USER_ROLE;

function loadSession() {
    FARM_NAME = localStorage.getItem('farmName') || 'MyFarm';
    USER_NAME = localStorage.getItem('userName') || '';
    USER_ID   = localStorage.getItem('userId')   || '—';
    USER_ROLE = parseInt(localStorage.getItem('userRole'), 10) || 3;

    if (!localStorage.getItem('farmName')) {
        window.location.href = 'login.html';
    }
}

function logout() {
    ['farmName','farmId','userName','userId','userRole','userRoleLabel']
        .forEach(function(k) { localStorage.removeItem(k); });
    window.location.href = 'login.html';
}

function toggleMenu() {
    document.getElementById('avatar-menu').classList.toggle('open');
}

var SIDEBAR_HTML =
'<aside class="sidebar">' +
'  <div class="logo" onclick="window.location.href=\'dashboard.html\'">MF</div>' +
'  <div class="sidebar-top">' +
'    <button class="tab-btn" data-tab="dashboard" onclick="goTab(\'dashboard\')">' +
'      <div class="dashboard-icon"><span></span><span></span><span></span></div>' +
'      <span class="tab-tip">Dashboard</span>' +
'    </button>' +
'    <button class="tab-btn" data-tab="livestock" onclick="goTab(\'livestock\')">' +
'      <span class="icon"><svg viewBox="0 0 24 24"><path d="M3 8h18M3 8l2-4h14l2 4M3 8l-1 9h20l-1-9"/><circle cx="9" cy="14" r="1.5"/><circle cx="15" cy="14" r="1.5"/><path d="M9 8V5m6 3V5"/></svg></span>' +
'      <span class="tab-tip">Livestock</span>' +
'    </button>' +
'    <button class="tab-btn" data-tab="myfarm" onclick="goTab(\'myfarm\')">' +
'      <span class="icon"><svg viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg></span>' +
'      <span class="tab-tip">MyFarm</span>' +
'    </button>' +
'    <button class="tab-btn requires-it" data-tab="personnel" onclick="goTab(\'personnel\')">' +
'      <span class="icon"><svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></span>' +
'      <span class="tab-tip">Personnel</span>' +
'    </button>' +
'  </div>' +
'  <div class="sidebar-bottom">' +
'    <div class="notif-wrap">' +
'      <button class="tab-btn" data-tab="notifications" onclick="goTab(\'notifications\')">' +
'        <span class="icon"><svg viewBox="0 0 24 24"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg></span>' +
'        <span class="tab-tip">Notifications</span>' +
'      </button>' +
'      <div class="notif-badge" id="notif-badge">3</div>' +
'    </div>' +
'  </div>' +
'</aside>';

function topbarHtml(title, subtitle) {
    return (
'<div class="topbar">' +
'  <div>' +
'    <div class="farm-name" id="farm-name">' + title + '</div>' +
'    <div class="farm-sub" id="farm-sub">' + subtitle + '</div>' +
'  </div>' +
'  <div class="topbar-right">' +
'    <div class="role-badge" id="user-role">—</div>' +
'    <div class="avatar-wrap">' +
'      <div class="user-avatar" id="user-avatar" onclick="toggleMenu()">…</div>' +
'      <div class="avatar-menu" id="avatar-menu">' +
'        <div class="menu-item" style="opacity:.5;cursor:default;pointer-events:none;">' +
'          <svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>' +
'          <span id="menu-uname">—</span>' +
'        </div>' +
'        <div class="menu-item" style="opacity:.5;cursor:default;pointer-events:none;font-size:.75rem;">' +
'          <svg viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/></svg>' +
'          <span>ID: <span id="menu-uid">—</span></span>' +
'        </div>' +
'        <hr style="border:none;border-top:1px solid var(--border);margin:6px 0;">' +
'        <button class="menu-item danger" onclick="logout()">' +
'          <svg viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>' +
'          Sign Out' +
'        </button>' +
'      </div>' +
'    </div>' +
'  </div>' +
'</div>'
    );
}

function goTab(name) {
    var target = TAB_PAGES[name];
    if (target) {
        window.location.href = target;
    }
    /* Pages with no target yet (myfarm, personnel, notifications) do nothing. */
}

/* ══ Main entry point — call this at the top of every app page ══ */
function initLayout(currentTab, opts) {
    opts = opts || {};
    loadSession();

    document.body.classList.add('role-' + USER_ROLE);

    document.getElementById('sidebar-mount').outerHTML = SIDEBAR_HTML;
    document.getElementById('topbar-mount').outerHTML  = topbarHtml(
        opts.title    || ('Welcome to ' + FARM_NAME),
        opts.subtitle || (ROLE_SUBS[USER_ROLE] || ROLE_SUBS[3])
    );

    /* Highlight the active tab */
    var btn = document.querySelector('.tab-btn[data-tab="' + currentTab + '"]');
    if (btn) btn.classList.add('active');

    /* Populate role + avatar */
    document.getElementById('user-role').textContent = ROLE_LABELS[USER_ROLE] || 'Farm Manager';
    var initials = USER_NAME.trim().split(/\s+/)
        .map(function(w){ return w[0] ? w[0].toUpperCase() : ''; })
        .join('').slice(0,2) || 'MF';
    document.getElementById('user-avatar').textContent = initials;
    document.getElementById('menu-uname').textContent  = USER_NAME || '—';
    document.getElementById('menu-uid').textContent    = USER_ID;

    /* Close avatar dropdown on outside click */
    document.addEventListener('click', function(e) {
        var wrap = document.querySelector('.avatar-wrap');
        if (wrap && !wrap.contains(e.target)) {
            document.getElementById('avatar-menu').classList.remove('open');
        }
    });
}

/* ══ Reusable counter animation ══ */
function countUp(id, target, duration) {
    var el = document.getElementById(id);
    if (!el) return;
    var t0 = performance.now();
    function frame(t) {
        var p    = Math.min((t - t0) / duration, 1);
        var ease = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(ease * target).toLocaleString();
        if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
}

function escHtml(s) {
    return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
