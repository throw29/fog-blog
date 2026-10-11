/* 深色模式：手动切换 / 时段与系统自动 / 高亮主题联动 / 正文深色字反色修复
 * + 实时同步（管理员）：切换时双写 DB（/api/site-prefs）；
 * + 跨标签实时同步（storage 事件：所有标签通过 localStorage 同步偏好）。 */
(function () {
  var T = window.WB_THEME || { def: "light", auto: "off", start: 19, end: 7, fix: "0", isAdmin: false };
  var root = document.documentElement;

  /* 管理员 → 同步到后端（fire-and-forget；失败仅 console.warn 不影响视觉） */
  function syncToServer(field, value) {
    if (!T.isAdmin) return;
    var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
    try {
      fetch("/api/site-prefs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
          "X-Requested-With": "fetch"
        },
        body: JSON.stringify((function () { var o = {}; o[field] = value; return o; })()),
        credentials: "same-origin"
      })
        .then(function (r) { if (!r.ok) console.warn("site-prefs sync failed:", r.status); })
        .catch(function (e) { console.warn("site-prefs sync error:", e); });
    } catch (e) {}
  }

  /* 当前深浅档位（light / dark / auto），用于显示按钮图标 */
  function currentMode() {
    try {
      var m = localStorage.getItem("wb-theme");
      if (m === "light" || m === "dark") return m;
    } catch (e) {}
    return "auto";
  }
  function setButtonMode() {
    var btn = document.getElementById("themeToggle");
    if (btn) btn.setAttribute("data-mode", currentMode());
  }

  function isDarkHour() {
    var h = new Date().getHours(), s = Number(T.start), e = Number(T.end);
    if (s === e) return false;
    return (s < e) ? (h >= s && h < e) : (h >= s || h < e);
  }

  function effective() {
    var f = localStorage.getItem("wb-theme");
    if (f === "light" || f === "dark") return f;
    if (T.auto === "system") {
      try { if (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches) return "dark"; } catch (e) {}
    } else if (T.auto === "schedule" && isDarkHour()) return "dark";
    return T.def === "dark" ? "dark" : "light";
  }

  function apply() {
    var dark = effective() === "dark";
    root.setAttribute("data-theme", dark ? "dark" : "light");
    // highlight.js 深浅主题联动
    var light = document.getElementById("hljsLight");
    var darkSheet = document.getElementById("hljsDark");
    if (light) light.disabled = dark;
    if (darkSheet) darkSheet.disabled = !dark;
    fixContentColors(dark);
    var btn = document.getElementById("themeToggle");
    if (btn) {
      var f = localStorage.getItem("wb-theme") || "auto";
      root.setAttribute("data-user", f);
      var nxt = plannedNext();
      btn.title = nxt === "dark" ? "当前浅色，点击切换深色" :
                  nxt === "light" ? "当前深色，点击切换浅色" :
                  "恢复自动（跟随系统/时段）";
    }
    setButtonMode();
  }

  /* 反色修复：正文里「写死成深色」的内联文字，深色下自动提亮 */
  function luminance(rgb) {
    var c = rgb.map(function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  function parseColor(str) {
    var m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(str || "");
    if (m) return [+m[1], +m[2], +m[3]];
    var h = /^#([0-9a-f]{6})$/i.exec((str || "").trim());
    if (h) { var n = parseInt(h[1], 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
    return null;
  }
  function fixContentColors(dark) {
    var targets = document.querySelectorAll(".post-content *, .page-content *");
    if (!dark || T.fix !== "1") {
      for (var r = 0; r < targets.length; r++) {
        if (targets[r].dataset && targets[r].dataset.wbOrig) {
          targets[r].style.color = targets[r].dataset.wbOrig;
          delete targets[r].dataset.wbOrig;
        }
      }
      return;
    }
    for (var i = 0; i < targets.length; i++) {
      var el = targets[i];
      var cs = el.style && el.style.color;
      if (!cs) continue;
      var rgb = parseColor(cs);
      if (rgb && luminance(rgb) < 0.45 && !el.dataset.wbOrig) {
        el.dataset.wbOrig = cs;
        el.style.color = "#eadfcb";
      }
    }
  }

  /* 模拟"自动"档位的视觉 */
  function autoVisual() {
    var had = localStorage.getItem("wb-theme");
    localStorage.removeItem("wb-theme");
    var v = effective();
    if (had) localStorage.setItem("wb-theme", had);
    return v;
  }

  function plannedNext() {
    var f = localStorage.getItem("wb-theme");
    var cur = effective();
    if (f === "light") return "dark";
    if (f === "dark") return autoVisual() === "dark" ? "light" : "auto";
    return cur === "dark" ? "light" : "dark";
  }

  function toggle() {
    var next = plannedNext();
    if (next === "auto") localStorage.removeItem("wb-theme");
    else localStorage.setItem("wb-theme", next);
    apply();
    syncToServer("theme_default", effective() === "dark" ? "dark" : "light");
  }

  var btn = document.getElementById("themeToggle");
  if (btn) btn.addEventListener("click", toggle);

  if (T.auto === "system" && window.matchMedia) {
    try {
      matchMedia("(prefers-color-scheme: dark)").addEventListener("change", apply);
    } catch (e) {}
  }

  /* 个人中心头像下拉菜单 */
  var chip = document.getElementById("userChip");
  var menu = document.getElementById("userMenu");
  if (chip && menu) {
    var cbtn = chip.querySelector(".user-chip-btn");
    cbtn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = menu.hidden;
      menu.hidden = !open;
      cbtn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", function (e) {
      if (!chip.contains(e.target)) { menu.hidden = true; cbtn.setAttribute("aria-expanded", "false"); }
    });
  }

  /* 把当前 theme 状态同步到表单 select（站点设置页的下拉框） */
  function syncThemeSelects(prefs) {
    if (!prefs) prefs = {};
    function setSel(name, val) {
      if (val == null || val === "") return;
      var sels = document.querySelectorAll('select[data-bind="' + name + '"]');
      for (var i = 0; i < sels.length; i++) {
        var opts = sels[i].querySelectorAll("option");
        for (var oi = 0; oi < opts.length; oi++) {
          if (opts[oi].value === val && sels[i].value !== val) {
            sels[i].value = val;
            sels[i].dispatchEvent(new CustomEvent("wb:theme-pref-applied",
              { detail: { field: name, value: val } }));
          }
        }
      }
    }
    function setInput(name, val) {
      if (val == null || val === "") return;
      var ins = document.querySelectorAll('input[data-bind="' + name + '"]');
      for (var i = 0; i < ins.length; i++) {
        if (ins[i].value !== String(val)) {
          ins[i].value = String(val);
          ins[i].dispatchEvent(new CustomEvent("wb:theme-pref-applied",
            { detail: { field: name, value: val } }));
        }
      }
    }
    var sd = prefs.theme_default || (T.def === "dark" ? "dark" : "light");
    setSel("theme_default", sd);
    setSel("theme_auto", prefs.theme_auto || T.auto || "off");
    setInput("theme_dark_start", prefs.theme_dark_start || String(T.start));
    setInput("theme_dark_end", prefs.theme_dark_end || String(T.end));
  }
  window.WB_THEME_SYNC_FORMS = syncThemeSelects;

  /* 跨标签实时同步：同源其它标签写 wb-theme → 立刻 apply() */
  window.addEventListener("storage", function (ev) {
    if (!ev.key || ev.key === "wb-theme" || ev.key === "wb-palette") apply();
  });

  /* 暴露给模板 / 跨页面主动同步用 */
  window.WB_THEME_APPLY = apply;
  window.WB_THEME_GET = function () {
    return {
      theme_default: T.def === "dark" ? "dark" : "light",
      theme_auto: T.auto || "off",
      theme_dark_start: String(T.start),
      theme_dark_end: String(T.end),
      theme_fix_content: T.fix
    };
  };

  /* 从服务端拉最新偏好并应用（仅管理员调用） */
  function applyServerPrefs(prefs) {
    if (!prefs || typeof prefs !== "object") return;
    var palette = prefs.color_palette;
    var themeDefault = prefs.theme_default;
    var themeAuto = prefs.theme_auto;
    var loggedIn = !!(T.isAdmin || T.isMember);
    /* 配色：登录用户 server 权威（直接覆盖，即便 localStorage 有陈旧值）；
       访客保留 per-browser override */
    if (palette) {
      try {
        if (loggedIn || !localStorage.getItem("wb-palette")) {
          document.documentElement.setAttribute("data-palette", palette);
          root.setAttribute("data-default-palette", palette);
        }
        if (loggedIn && localStorage.getItem("wb-palette") !== palette) {
          /* 登录后清掉 localStorage 陈旧值 —— 不再让浏览器本地偏好污染 server 同步 */
          localStorage.removeItem("wb-palette");
        }
      } catch (e) {}
    }
    /* 默认主题覆盖：服务端说现在 light，就把 T.def 改成 light */
    if (themeDefault) {
      T.def = themeDefault;
    }
    if (themeAuto) {
      T.auto = themeAuto;
    }
    apply();
    syncThemeSelects(prefs);
  }
  window.WB_THEME_APPLY_SERVER_PREFS = applyServerPrefs;

  /* 页面初始化时也同步一次（保证 settings 页 select 显示当前生效值） */
  syncThemeSelects();

  apply();
})();
