/* 侧栏小部件：免费天气（后端代理）+ 时间倒计时 */
(function () {
  var ICONS = {
    thunder: "⛈️", rain: "🌧️", drizzle: "🌦️", snow: "❄️", sleet: "🌨️",
    fog: "🌫️", mist: "🌫️", haze: "🌫️", cloud: "☁️", overcast: "☁️",
    partly: "⛅", sunny: "☀️", clear: "☀️", windy: "💨"
  };
  function iconFor(en) {
    var t = (en || "").toLowerCase();
    if (t.indexOf("thunder") >= 0 || t.indexOf("storm") >= 0) return ICONS.thunder;
    if (t.indexOf("snow") >= 0 || t.indexOf("sleet") >= 0) return t.indexOf("sleet") >= 0 ? ICONS.sleet : ICONS.snow;
    if (t.indexOf("drizzle") >= 0) return ICONS.drizzle;
    if (t.indexOf("rain") >= 0) return ICONS.rain;
    if (t.indexOf("fog") >= 0 || t.indexOf("mist") >= 0 || t.indexOf("haze") >= 0) return ICONS.fog;
    if (t.indexOf("overcast") >= 0 || (t.indexOf("cloud") >= 0 && t.indexOf("part") < 0)) return ICONS.overcast;
    if (t.indexOf("part") >= 0 && t.indexOf("cloud") >= 0) return ICONS.partly;
    if (t.indexOf("sun") >= 0 || t.indexOf("clear") >= 0) return ICONS.sunny;
    return "🌤️";
  }
  var TXT = {
    thunder: "雷雨", rain: "雨", drizzle: "小雨", snow: "雪", sleet: "雨夹雪",
    fog: "雾", mist: "雾", haze: "霾", cloud: "多云", overcast: "阴",
    partly: "多云间晴", sunny: "晴", clear: "晴", windy: "大风"
  };
  function textFor(en) {
    var t = (en || "").toLowerCase();
    for (var k in TXT) {
      if (t.indexOf(k) >= 0 && (k !== "cloud" || (t.indexOf("part") < 0 && t.indexOf("overcast") < 0))) return TXT[k];
    }
    if (t.indexOf("part") >= 0) return "多云";
    return en || "";
  }

  var card = document.getElementById("weatherCard");
  if (card) {
    function render(wx) {
      var city = document.getElementById("wxCity");
      var body = document.getElementById("wxBody");
      if (!wx || !wx.ok) {
        city.textContent = "暂不可用";
        body.innerHTML = '<p class="wx-err">天气服务暂不可用（可后台配置默认城市）</p>';
        return;
      }
      city.textContent = wx.city || "";
      var hum = wx.humidity ? " · 湿度 " + wx.humidity + "%" : "";
      var wind = wx.wind ? " · 风力 " + wx.wind + "km/h" : "";
      body.innerHTML =
        '<div class="wx-body-row">' +
        '<span class="wx-icon">' + iconFor(wx.text_en) + "</span>" +
        '<span class="wx-temp">' + (wx.temp != null ? wx.temp + "°" : "--") + "</span>" +
        '<span class="wx-info">' + textFor(wx.text_en) + hum + wind + "</span>" +
        "</div>" +
        '<p class="wx-refresh">自动每 30 分钟更新 · 数据来源免费接口</p>';
    }
    function load() {
      fetch("/api/weather", { headers: { "Accept": "application/json" } })
        .then(function (r) { return r.json(); })
        .then(render)
        .catch(function () {
          var city = document.getElementById("wxCity");
          var body = document.getElementById("wxBody");
          if (city) city.textContent = "暂不可用";
          if (body) body.innerHTML = '<p class="wx-err">天气加载失败</p>';
        });
    }
    load();
    setInterval(load, 30 * 60 * 1000);
  }

  // ---------- 倒计时 ----------
  var cdToday = document.getElementById("cdToday");
  var cdMonth = document.getElementById("cdMonth");
  var cdYear = document.getElementById("cdYear");
  if (cdToday && cdMonth && cdYear) {
    function fmtHm(ms) {
      if (ms <= 0) return "已结束";
      var totalMin = Math.floor(ms / 60000);
      if (totalMin < 60) return totalMin + " 分钟";
      var h = Math.floor(totalMin / 60), m = totalMin % 60;
      return (m ? h + " 小时 " + m + " 分" : h + " 小时");
    }
    function fmtDH(ms) {
      if (ms <= 0) return "已结束";
      var totalH = Math.floor(ms / 3600000);
      if (totalH < 48) return fmtHm(ms);
      var d = Math.floor(totalH / 24), h = totalH % 24;
      return (h ? d + " 天 " + h + " 小时" : d + " 天");
    }
    function tick() {
      var now = new Date();
      var eod = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
      var eom = new Date(now.getFullYear(), now.getMonth() + 1, 1);
      var eoy = new Date(now.getFullYear() + 1, 0, 1);
      cdToday.textContent = fmtHm(eod - now);
      cdMonth.textContent = fmtDH(eom - now);
      cdYear.textContent = fmtDH(eoy - now);
    }
    tick();
    setInterval(tick, 30000);
  }

  // ---------- 配色选择器（实时同步） ----------
  (function () {
    var wrap = document.getElementById("paletteWrap");
    if (!wrap) return;
    var btn = document.getElementById("paletteToggle");
    var picker = document.getElementById("palettePicker");
    var reset = document.getElementById("paletteReset");
    if (!btn || !picker) return;

    var isAdmin = !!(window.WB_THEME && window.WB_THEME.isAdmin);
    var isLoggedIn = !!(window.WB_THEME && (window.WB_THEME.isAdmin || window.WB_THEME.isMember));

    function getCsrf() {
      var m = document.querySelector('meta[name="csrf-token"]');
      return m ? m.content : "";
    }

    function syncToServer(palette) {
      /* 访客（未登录）只写 localStorage —— 不污染其他访客偏好
         登录用户（含普通会员/管理员）都写 server —— 让所有设备/标签/前后台一致 */
      if (!isLoggedIn && !isAdmin) return;
      try {
        fetch("/api/site-prefs", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": getCsrf(),
            "X-Requested-With": "fetch"
          },
          body: JSON.stringify({ color_palette: palette }),
          credentials: "same-origin"
        })
          .then(function (r) { if (!r.ok) console.warn("palette sync failed:", r.status); })
          .catch(function (e) { console.warn("palette sync error:", e); });
      } catch (e) {}
    }

function defPalette() {
    return document.documentElement.getAttribute("data-default-palette") || "amber";
  }
  function currentPalette() {
    return document.documentElement.getAttribute("data-palette") || defPalette();
  }
  function applyPalette(v, persist) {
    document.documentElement.setAttribute("data-palette", v);
    document.documentElement.setAttribute("data-user-palette", v);
    var pick = document.getElementById("palettePicker");
    if (pick) {
      var opts = pick.querySelectorAll("[data-palette]");
      for (var i = 0; i < opts.length; i++) {
        var on = opts[i].getAttribute("data-palette") === v;
        opts[i].classList.toggle("is-active", on);
      }
    }
    /* 同步所有绑定过的表单 select（站点设置页 / 其他入口） */
    var sels = document.querySelectorAll('select[data-bind="color_palette"]');
    for (var j = 0; j < sels.length; j++) {
      if (sels[j].value !== v) sels[j].value = v;
      /* 自定义事件，让 settings.html 可以监听（即时保存提示） */
      sels[j].dispatchEvent(new CustomEvent("wb:palette-applied", { detail: { value: v, persist: !!persist } }));
    }
    if (persist) {
      try { localStorage.setItem("wb-palette", v); } catch (e) {}
      syncToServer(v);
    }
  }
  window.WB_PALETTE_APPLY = applyPalette;
  window.WB_PALETTE_GET_CURRENT = currentPalette;
  window.WB_PALETTE_GET_DEFAULT = defPalette;
    function close() { picker.hidden = true; }
    function toggle() { picker.hidden = !picker.hidden; }

    applyPalette(currentPalette(), false);

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      toggle();
    });
    var opts = picker.querySelectorAll("[data-palette]");
    for (var i = 0; i < opts.length; i++) {
      opts[i].addEventListener("click", function (ev) {
        var v = ev.currentTarget.getAttribute("data-palette");
        applyPalette(v, true);
        close();
      });
    }
    if (reset) {
      reset.addEventListener("click", function () {
        try { localStorage.removeItem("wb-palette"); } catch (e) {}
        applyPalette(defPalette(), false);
        if (isAdmin) syncToServer(defPalette());
        close();
      });
    }
    document.addEventListener("click", function (e) {
      if (picker.hidden) return;
      if (!wrap.contains(e.target)) close();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !picker.hidden) close();
    });
  })();

  /* 跨标签同步：同源其它标签写 wb-palette → 实时 applyPalette */
  window.addEventListener("storage", function (ev) {
    if (ev.key !== "wb-palette") return;
    var v = localStorage.getItem("wb-palette");
    var picker = document.getElementById("palettePicker");
    var root = document.documentElement;
    if (v) {
      root.setAttribute("data-palette", v);
      if (picker) {
        var opts = picker.querySelectorAll("[data-palette]");
        for (var i = 0; i < opts.length; i++) {
          opts[i].classList.toggle("is-active", opts[i].getAttribute("data-palette") === v);
        }
      }
      /* 同步 select（即使本页发起 storage 也兜底一下） */
      var sels = document.querySelectorAll('select[data-bind="color_palette"]');
      for (var j = 0; j < sels.length; j++) {
        if (sels[j].value !== v) sels[j].value = v;
      }
    } else {
      var dv = document.documentElement.getAttribute("data-default-palette") || "amber";
      root.setAttribute("data-palette", dv);
      var sels2 = document.querySelectorAll('select[data-bind="color_palette"]');
      for (var k = 0; k < sels2.length; k++) {
        if (sels2[k].value !== dv) sels2[k].value = dv;
      }
    }
  });
})();
