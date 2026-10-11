/* ==========================================================================
 * 开屏动效（首页） —— 毛玻璃 + 中央光晕 + 飘动文章卡片
 * - 仅在首页触发（依赖 .post-card 列表）
 * - 从已有 DOM 抓取文章数据（最近/最热），不增加后端渲染负担
 * - 飘动：随机速度 + 边界反弹 + 中心圆避让
 * - localStorage wb-splash-seen 控制频次（24h 内不再显示）
 * - 点击中央圆 / 跳过 / ESC → 关闭；点击卡片 → 进入对应文章
 * ========================================================================== */
(function () {
  'use strict';

  var KEY = 'wb-splash-seen';
  var STORAGE_TTL = 24 * 60 * 60 * 1000;  // 24 小时

  function shouldShow() {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return true;
      var ts = parseInt(raw, 10);
      if (!ts || isNaN(ts)) return true;
      return Date.now() - ts > STORAGE_TTL;
    } catch (e) { return true; }
  }

  function markSeen() {
    try { localStorage.setItem(KEY, String(Date.now())); } catch (e) {}
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* 从首页 .post-card 提取最多 6 篇文章数据 */
  function gatherPosts() {
    var cards = document.querySelectorAll('.post-card');
    var items = [];
    cards.forEach(function (c) {
      if (items.length >= 6) return;
      var titleEl = c.querySelector('h2 a');
      if (!titleEl) return;
      var url = titleEl.getAttribute('href');
      if (!url) return;
      var title = (titleEl.textContent || '').trim();
      var badgeEls = c.querySelectorAll('.post-card-top .badge');
      var tag = badgeEls.length ? (badgeEls[badgeEls.length - 1].textContent || '').trim() : '';
      var dateEl = c.querySelector('.post-card-top span:not(.badge)');
      var date = dateEl ? (dateEl.textContent || '').trim() : '';
      items.push({ url: url, title: title, tag: tag, date: date });
    });
    return items;
  }

  function rectOverlap(a, b, pad) {
    pad = pad || 0;
    return !(a.x + a.w + pad < b.x || b.x + b.w + pad < a.x ||
             a.y + a.h + pad < b.y || b.y + b.h + pad < a.y);
  }
  function dist(x1, y1, x2, y2) {
    return Math.hypot(x1 - x2, y1 - y2);
  }

  function init() {
    var cards = document.querySelectorAll('.post-card');
    if (!cards.length) return;  // 非首页直接放弃
    var splash = document.getElementById('splash');
    if (!splash) return;
    if (!shouldShow()) return;

    var posts = gatherPosts();
    if (!posts.length) return;

    /* 显示并淡入 */
    splash.hidden = false;
    splash.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { splash.classList.add('show'); });
    });

    var container = splash.querySelector('#splashCards');

    var isMobile = window.innerWidth <= 720;
    var CW = isMobile ? 165 : 220;
    var CH = isMobile ? 110 : 130;
    var CENTER_RADIUS = isMobile ? 130 : 170;  // 中心圆安全半径

    /* 初始位置：避开中心圆 + 不互相重叠 */
    function placeAll() {
      var W = window.innerWidth;
      var H = window.innerHeight;
      var positions = [];
      posts.forEach(function (_, i) {
        var x = 0, y = 0, tries = 0, ok = false;
        while (tries < 80 && !ok) {
          x = 12 + Math.random() * Math.max(1, W - CW - 24);
          y = 12 + Math.random() * Math.max(1, H - CH - 70);  // 留底部 hint bar
          tries++;
          var cx = x + CW / 2, cy = y + CH / 2;
          var dc = dist(cx, cy, W / 2, H / 2);
          if (dc < CENTER_RADIUS + Math.max(CW, CH) / 2 + 12) continue;
          var collide = positions.some(function (p) {
            return rectOverlap({ x: x, y: y, w: CW, h: CH }, p, 8);
          });
          if (collide) continue;
          ok = true;
        }
        positions.push({ x: x, y: y });
      });
      return positions;
    }

    var positions = placeAll();
    var cardEls = [];

    posts.forEach(function (p, i) {
      var el = document.createElement('a');
      el.className = 'splash-card';
      el.href = p.url;
      el.style.animationDelay = (i * 0.08) + 's';
      var tagHtml = p.tag ? '<span class="sc-tag">' + escapeHtml(p.tag) + '</span>' : '';
      var dateHtml = p.date ? '<span>' + escapeHtml(p.date) + '</span>' : '';
      el.innerHTML =
        tagHtml +
        '<div class="sc-title">' + escapeHtml(p.title) + '</div>' +
        '<div class="sc-meta">' + dateHtml + '</div>';
      var pos = positions[i];
      el.style.transform = 'translate3d(' + pos.x + 'px, ' + pos.y + 'px, 0)';
      el.addEventListener('click', function () { markSeen(); });
      container.appendChild(el);
      cardEls.push({
        el: el,
        x: pos.x, y: pos.y,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        drift: Math.random() * Math.PI * 2
      });
    });

    /* 主循环 */
    var running = true;
    var lastTs = performance.now();
    function tick() {
      if (!running) return;
      var t = performance.now();
      var dt = Math.min(40, t - lastTs);
      lastTs = t;

      var W = window.innerWidth;
      var H = window.innerHeight;
      var CX = W / 2, CY = H / 2;

      for (var i = 0; i < cardEls.length; i++) {
        var c = cardEls[i];
        c.drift += dt * 0.0008;
        /* 漂浮加速度（轻微正弦扰动，避免匀速呆板） */
        c.vx += Math.cos(c.drift) * 0.012;
        c.vy += Math.sin(c.drift * 1.3) * 0.012;
        /* 限速 */
        var sp = Math.hypot(c.vx, c.vy);
        var MAX = 0.7;
        if (sp > MAX) {
          c.vx = c.vx / sp * MAX;
          c.vy = c.vy / sp * MAX;
        }
        /* 阻尼 */
        c.vx *= 0.99;
        c.vy *= 0.99;
        c.x += c.vx * (dt / 16);
        c.y += c.vy * (dt / 16);

        /* 边界反弹 */
        if (c.x < 8)              { c.x = 8;              c.vx = Math.abs(c.vx); }
        if (c.x > W - CW - 8)     { c.x = W - CW - 8;     c.vx = -Math.abs(c.vx); }
        if (c.y < 8)              { c.y = 8;              c.vy = Math.abs(c.vy); }
        if (c.y > H - CH - 60)    { c.y = H - CH - 60;    c.vy = -Math.abs(c.vy); }

        /* 中心圆避让 */
        var ccx = c.x + CW / 2, ccy = c.y + CH / 2;
        var d2c = dist(ccx, ccy, CX, CY);
        var minD = CENTER_RADIUS + Math.max(CW, CH) / 2 + 4;
        if (d2c < minD) {
          var ang = Math.atan2(ccy - CY, ccx - CX);
          c.x = CX + Math.cos(ang) * minD - CW / 2;
          c.y = CY + Math.sin(ang) * minD - CH / 2;
          c.vx = Math.cos(ang) * 0.5;
          c.vy = Math.sin(ang) * 0.5;
        }

        c.el.style.transform = 'translate3d(' + c.x + 'px, ' + c.y + 'px, 0)';
      }
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);

    /* 关闭 */
    function closeSplash() {
      if (splash.classList.contains('closing')) return;
      splash.classList.add('closing');
      running = false;
      splash.classList.remove('show');
      window.removeEventListener('resize', onResize);
      document.removeEventListener('keydown', onKey);
      setTimeout(function () {
        splash.hidden = true;
        splash.setAttribute('aria-hidden', 'true');
      }, 400);
    }

    function onResize() {
      isMobile = window.innerWidth <= 720;
      CW = isMobile ? 165 : 220;
      CH = isMobile ? 110 : 130;
      CENTER_RADIUS = isMobile ? 130 : 170;
      var newPos = placeAll();
      for (var i = 0; i < cardEls.length; i++) {
        cardEls[i].x = newPos[i].x;
        cardEls[i].y = newPos[i].y;
      }
    }
    function onKey(e) {
      if (e.key === 'Escape' && !splash.hidden) {
        markSeen();
        closeSplash();
      }
    }
    window.addEventListener('resize', onResize);
    document.addEventListener('keydown', onKey);

    var btnEnter = document.getElementById('splashEnter');
    var btnSkip = document.getElementById('splashSkip');
    if (btnEnter) btnEnter.addEventListener('click', function () {
      markSeen(); closeSplash();
    });
    if (btnSkip) btnSkip.addEventListener('click', function () {
      markSeen(); closeSplash();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();