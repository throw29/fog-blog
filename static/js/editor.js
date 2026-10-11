/* ============ 富文本编辑器：Markdown / HTML 双模式 ============ */
(function () {
  "use strict";

  if (!document.getElementById("richEditor")) return;

  var wrap = document.getElementById("richEditor");
  var taMd = wrap.querySelector('textarea[data-ta="markdown"]');
  var taHtml = wrap.querySelector('textarea[data-ta="html"]');
  var previewBox = wrap.querySelector("[data-preview]");
  var iframe = previewBox.querySelector("iframe");
  var modeSeg = wrap.querySelector("[data-mode-seg]");
  var viewSeg = wrap.querySelector("[data-view-seg]");
  var viewBox = wrap.querySelector("[data-view-box]");
  var renderModeInput = document.getElementById("renderMode");
  var statusMode = wrap.querySelector("[data-status-mode]");
  var modal = document.getElementById("mediaModal");
  var emojiPop = document.getElementById("emojiPop");

  var EMOJIS = ("😀😁😂🤣😊😇🙂😉😍🥰😘😋😜🤪😝🤔🤨😐😑😶😏😒🙄😬😮💨🤯😳🥺😢😭😤😠😡🤬🤯😱😨😰😥😓🤗🤭🤫🤥😶‍🌫️😴🤤😪😵🤮🤢🤧😷🤒🤕🤑🤠😈👿🤡💩👻💀👽🤖🎃😺😸😹😻😼😽🙀😿😾👋🤚🖐️✋🖖👌🤌🤏✌️🤞🤟🤘🤙👈👉👆🖕👇☝️👍👎✊👊🤛🤜👏🙌👐🤲🤝🙏💪🦵🦶👂👃🧠🦷👀👅👄💋👶👧👦👨👩👴👵💼🎒👔👗👙👘🧥🎓🕶️👑🎩💍💄💅🧼🚿🛁🧹🧺🧻🧯🚪🪑🛏️🛋️🚽🚿🪥🪒🧴🛒💰💵💴💶💷💳🪙💎⚖️🧰🔧🔨⚒️🛠️⛏️🔩⚙️🗜️🔗⛓️🧲🔬🔭🔮🧪🧫🧬💊💉🩸🩹🩺🌡️🚨🚔🚓🚒🚑🚐🚚🚛🚜🏍️🚲🛴🚗🚕🚙🚌🚎🏎️🚓🚑🚒🚐🛻🚚🚛🚜🛵🏍️🚲🛴🚏🛣️🛤️✈️🚀🛸🛰️⛵🚤🛥️🛳️⚓🚁🚂🚄🚅🚈🚇🚝🚉🚊✈️🌍🌎🌏🌐🗺️🗾🧭⏱️⏲️⏰⌚🌡️⛱️🏖️🏝️🏜️🌋🏔️🗻🏕️🌄🌅🌇🌆🌃🌉🌌🌠🎇🎆🌃🌉🌌🌠🌈🌉🌁❄️⛄☃️🌊💧☔🌂🔥✨🌟⭐💫⚡☄️💥💢❕❗💯🔞🚫⛔🚷🚯🚳🚱🔇🔕📵🚭🈲🈴🈵🈶🈷️🈸🈹🈺🈯🈲🈴🈵🈶🈷️🈸🈹🈺🈯💤💦🈁🈂️⭕❌❎✅🔴🔵⚪⚫🟠🟡🟢🔺🔻🔸🔹🔶🔷🔽↗️🔍🔎⌨️🖥️🖨️💻🖱️🖲️📀💾💿📼📷📸📹🎥📽️🎞️📞☎️📟📠📺📻🎙️🎚️🎛️🧭⏱️⏲️⏰⌛⏳📡🔋🔌💡🔦🕯️🪔🧯🛢️💸💵💰💳💎⚖️🧾📈📉📊📋📌📍📎🖇️📏📐✂️🗃️🗄️🗑️🔒🔓🔏🔐🔑🗝️🔨🪓⛏️⚒️🛠️🗡️⚔️🔫🏹🛡️🚬⚰️🪦⚱️🏺🔮📿🧿🪬💈⚗️🔭🔬🕳️💊💉🩺🌡️🚿🛁🚽🚿🧻🧻🧴🧺🧹🧽🧼🪥🪒🧷🧸🪀🪁🪄🔮🪞🪟🛋️🛍️🎈🎏🎀🎁🎊🎉🧨🎎🎐🎏🎀🎁🎊🎉🧨🎈🎏🎐🧧🎀🪅🪆🎭🩰🎪🎟️🎫🎬🎤🎧🎼🎹🪗🪘🥁🎷🎺🪗🎸🪕🎻🪈🎲♟️🎯🎳🎮🎰🕹️🎲🀄🎴🃏🂠🀄🎴🃏🎽🎿🛷🥌🎣🪁🎽🎿🥋🥊🛹🛼🎸🎻🎺🎷🥁🪘🪇🪈🪗🎹🪕").split("");

  // ---------- 模式 ----------
  var currentMode = renderModeInput.value === "html" ? "html" : "markdown";

  function activeTa() {
    return currentMode === "html" ? taHtml : taMd;
  }

  function setMode(mode) {
    if (mode === currentMode) return;
    currentMode = mode;
    modeSeg.querySelectorAll("button").forEach(function (b) {
      b.classList.toggle("active", b.dataset.mode === mode);
    });
    wrap.querySelectorAll("[data-toolbar]").forEach(function (tb) {
      tb.hidden = tb.dataset.toolbar !== mode;
    });
    taMd.hidden = mode !== "markdown";
    taHtml.hidden = mode !== "html";
    renderModeInput.value = mode;
    statusMode.textContent = mode === "html" ? "HTML 模式" : "Markdown 模式";
    renderPreview();
    updateStats();
  }

  modeSeg.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-mode]");
    if (btn) setMode(btn.dataset.mode);
  });

  // ---------- 视图 ----------
  viewSeg.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-view]");
    if (!btn) return;
    viewSeg.querySelectorAll("button").forEach(function (b) {
      b.classList.toggle("active", b.dataset.view === btn.dataset.view);
    });
    viewBox.dataset.view = btn.dataset.view;
    if (btn.dataset.view !== "write") renderPreview();
  });

  // ---------- 光标 / 选区工具 ----------
  function lineStart(txt, pos) {
    var i = txt.lastIndexOf("\n", pos - 1);
    return i + 1;
  }
  function lineEnd(txt, pos) {
    var i = txt.indexOf("\n", pos);
    return i === -1 ? txt.length : i;
  }
  function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function plainText(s) {
    var d = document.createElement("div");
    d.innerHTML = s;
    return d.textContent || "";
  }

  function replaceRange(ta, start, end, text) {
    ta.value = ta.value.slice(0, start) + text + ta.value.slice(end);
    var p = start + text.length;
    ta.focus();
    ta.setSelectionRange(p, p);
  }

  function surround(ta, before, after, sel, placeholder) {
    var s = ta.selectionStart, f = ta.selectionEnd;
    var mid = ta.value.slice(s, f) || sel || placeholder || "";
    replaceRange(ta, s, f, before + mid + after);
    ta.setSelectionRange(s + before.length, s + before.length + mid.length);
  }

  function insertAtCursor(ta, text) {
    var s = ta.selectionStart, f = ta.selectionEnd;
    replaceRange(ta, s, f, text);
  }

  function lineBlock(prefix) {
    var ta = activeTa();
    var s = ta.selectionStart, f = ta.selectionEnd;
    var txt = ta.value;
    var seg = txt.slice(s, f);
    if (seg.indexOf("\n") === -1) {
      var ls = lineStart(txt, s), le = lineEnd(txt, f);
      var line = txt.slice(ls, le);
      var stripped = line.replace(/^#{1,6}\s*/, "");
      var isHeading = /^#{1,6}\s/.test(line);
      var isPlain = prefix === null;
      var out;
      if (isPlain && isHeading) out = stripped;
      else if (!isPlain) out = prefix + (isHeading ? stripped : line);
      else out = line;
      replaceRange(ta, ls, le, out);
      var caret = ls + out.length;
      ta.setSelectionRange(caret, caret);
    } else {
      // 多行选中：逐行加前缀
      var lines = seg.split("\n");
      var fixed = lines.map(function (l) {
        var st = l.replace(/^#{1,6}\s*/, "");
        if (prefix === null) return st;
        return prefix + (/^#{1,6}\s/.test(l) ? st : l);
      });
      var joined = fixed.join("\n");
      replaceRange(ta, s, f, joined);
      ta.setSelectionRange(s, s + joined.length);
    }
  }

  // ---------- Markdown 命令 ----------
  var MD = {
    undo: function () { historyUndo(); },
    redo: function () { historyRedo(); },
    heading: function (v) {
      var map = { h1: "# ", h2: "## ", h3: "### ", h4: "#### ", h5: "##### ", h6: "###### ", p: null };
      if (v in map) lineBlock(map[v]);
    },
    bold: function () { surround(activeTa(), "**", "**", null, "加粗文字"); },
    italic: function () { surround(activeTa(), "*", "*", null, "斜体文字"); },
    strike: function () { surround(activeTa(), "~~", "~~", null, "删除线文字"); },
    code: function () { surround(activeTa(), "`", "`", null, "code"); },
    ul: function () { lineBlock("- "); },
    ol: function () { lineBlock("1. "); },
    task: function () { lineBlock("- [ ] "); },
    quote: function () { lineBlock("> "); },
    codeblock: function (lang) {
      var ta = activeTa();
      var s = ta.selectionStart, f = ta.selectionEnd;
      var mid = ta.value.slice(s, f) || "print('hello')";
      var code = "\n```" + lang + "\n" + mid + "\n```\n";
      replaceRange(ta, s, f, code);
      ta.setSelectionRange(s, s + code.length - 4);
    },
    table: function () {
      insertAtCursor(activeTa(), "\n| 列1 | 列2 | 列3 |\n| --- | --- | --- |\n| 内容 | 内容 | 内容 |\n");
    },
    hr: function () { insertAtCursor(activeTa(), "\n---\n"); },
    link: function () {
      var ta = activeTa();
      var s = ta.selectionStart, f = ta.selectionEnd;
      var sel = ta.value.slice(s, f);
      if (sel && !/^https?:/.test(sel)) {
        surround(ta, "[", "](https://)", sel);
      } else if (sel) {
        surround(ta, "[链接文字](", ")", null);
      } else {
        surround(ta, "[链接文字](https://)", "");
      }
    },
    toc: function () { insertAtCursor(activeTa(), "\n[TOC]\n"); },
    emoji: function () { toggleEmoji(event, null); },
  };

  // ---------- HTML 命令 ----------
  var HTMLCMD = {
    undo: function () { historyUndo(); },
    redo: function () { historyRedo(); },
    heading: function (v) {
      var ta = activeTa();
      var map = { h2: "<h2>", h3: "<h3>", h4: "<h4>", p: "" };
      if (!(v in map)) return;
      var s = ta.selectionStart, f = ta.selectionEnd;
      var mid = ta.value.slice(s, f) || "标题文字";
      if (v === "p") {
        surround(ta, "<p>", "</p>", null, "段落文字");
      } else {
        var tag = map[v].replace(/[<>]/g, "");
        surround(ta, map[v], "</" + tag + ">", null, "标题文字");
      }
    },
    bold: function () { surround(activeTa(), "<strong>", "</strong>", null, "加粗文字"); },
    italic: function () { surround(activeTa(), "<em>", "</em>", null, "斜体文字"); },
    strike: function () { surround(activeTa(), "<s>", "</s>", null, "删除线文字"); },
    code: function () { surround(activeTa(), "<code>", "</code>", null, "code"); },
    quote: function () { surround(activeTa(), "\n<blockquote>\n", "\n</blockquote>\n", null, "引用内容"); },
    table: function () {
      insertAtCursor(activeTa(), "\n<table><thead><tr><th>列1</th><th>列2</th></tr></thead><tbody><tr><td>内容</td><td>内容</td></tr></tbody></table>\n");
    },
    hr: function () { insertAtCursor(activeTa(), "\n<hr>\n"); },
    link: function () {
      var ta = activeTa();
      var s = ta.selectionStart, f = ta.selectionEnd;
      var sel = ta.value.slice(s, f);
      if (sel) surround(ta, '<a href="https://" target="_blank" rel="noopener">', "</a>", sel);
      else insertAtCursor(ta, '<a href="https://" target="_blank" rel="noopener">链接文字</a>');
    },
    emoji: function () { toggleEmoji(event, null); },
  };

  // ---------- 撤销 / 重做 ----------
  var hist = { md: { undo: [], redo: [] }, html: { undo: [], redo: [] } };
  var lastSaved = { md: null, html: null };
  var debTimer = null;

  function histKey() { return currentMode; }
  function schedulePush(ta) {
    var key = histKey();
    var cur = ta.value;
    if (cur === lastSaved[key]) return;
    if (debTimer) clearTimeout(debTimer);
    debTimer = setTimeout(function () {
      if (lastSaved[key] !== null) {
        hist[key].undo.push(lastSaved[key]);
        if (hist[key].undo.length > 100) hist[key].undo.shift();
      }
      hist[key].redo = [];
      lastSaved[key] = cur;
    }, 500);
  }
  taMd.addEventListener("input", function () { schedulePush(taMd); });
  taHtml.addEventListener("input", function () { schedulePush(taHtml); });

  function historyUndo() {
    var key = histKey();
    var ta = activeTa();
    if (debTimer) { clearTimeout(debTimer); debTimer = null; }
    if (!hist[key].undo.length) return toast("没有可撤销的操作");
    var cur = ta.value;
    hist[key].redo.push(cur);
    ta.value = hist[key].undo.pop();
    lastSaved[key] = ta.value;
    afterChange();
  }
  function historyRedo() {
    var key = histKey();
    var ta = activeTa();
    if (!hist[key].redo.length) return toast("没有可重做的操作");
    hist[key].undo.push(ta.value);
    ta.value = hist[key].redo.pop();
    lastSaved[key] = ta.value;
    afterChange();
  }

  function afterChange() {
    activeTa().focus();
    renderPreview();
    updateStats();
  }

  // ---------- 预览 ----------
  var previewTimer = null;
  function renderPreview() {
    if (viewBox.dataset.view === "write") return;
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(buildPreview, 220);
  }
  taMd.addEventListener("input", function () { renderPreview(); updateStats(); });
  taHtml.addEventListener("input", function () { renderPreview(); updateStats(); });

  var ORIGIN = window.location.origin;
  var MEDIA_RE = /<img[^>]*?src="([^"]+?\.(?:mp4|webm|mov|m4v|ogv|avi|mkv|flv|mp3|wav|ogg|m4a|flac|aac))"[^>]*>/gi;

  function mediaMarkup(html) {
    return html.replace(MEDIA_RE, function (m, src) {
      var tag = /\.(?:mp3|wav|ogg|m4a|flac|aac)$/i.test(src) ? "audio" : "video";
      return "<" + tag + " controls preload=\"metadata\" src=\"" + src + "\"></" + tag + ">";
    });
  }

  function buildPreview() {
    var body, needHigh = true;
    if (currentMode === "markdown") {
      var html = "";
      try { html = marked.parse(taMd.value || ""); } catch (e) { html = "<p style='color:#c0392b'>渲染出错</p>"; }
      body = mediaMarkup(html);
    } else {
      body = taHtml.value || "";
      needHigh = false;
    }
    var script = needHigh
      ? '<scr' + 'ipt src="/static/vendor/highlight.js/highlight.min.js"></scr' + 'ipt>' +
        '<scr' + 'ipt src="/static/vendor/highlight.js/languages/python.min.js"></scr' + 'ipt>' +
        '<scr' + 'ipt src="/static/vendor/highlight.js/languages/bash.min.js"></scr' + 'ipt>' +
        '<scr' + 'ipt src="/static/vendor/highlight.js/languages/sql.min.js"></scr' + 'ipt>' +
        '<scr' + 'ipt src="/static/vendor/highlight.js/languages/javascript.min.js"></scr' + 'ipt>' +
        '<scr' + 'ipt>document.querySelectorAll("pre code").forEach(function(el){try{hljs.highlightElement(el)}catch(e){}});</scr' + 'ipt>'
      : "";
    iframe.srcdoc =
      '<!DOCTYPE html><html><head><meta charset="utf-8"><base href="' + ORIGIN + '/">' +
      '<link rel="stylesheet" href="/static/css/style.css">' +
      '<link rel="stylesheet" href="/static/vendor/highlight.js/styles/atom-one-light.min.css">' +
      '<style>body{background:#fffdf8;padding:18px 22px;margin:0;font-size:15px}</style>' +
      '</head><body><div class="post-content">' + body + '</div>' + script + '</body></html>';
  }

  // ---------- 工具栏绑定 ----------
  wrap.addEventListener("click", function (e) {
    var mdBtn = e.target.closest("button[data-md]");
    if (mdBtn) {
      if (mdBtn.dataset.md === "emoji") return;
      if (mdBtn.dataset.md === "undo" || mdBtn.dataset.md === "redo") { MD[mdBtn.dataset.md](); return; }
      MD[mdBtn.dataset.md]();
      afterChange();
      return;
    }
    var hBtn = e.target.closest("button[data-html]");
    if (hBtn) {
      if (hBtn.dataset.html === "emoji") return;
      HTMLCMD[hBtn.dataset.html]();
      afterChange();
      return;
    }
    var mediaBtn = e.target.closest("[data-media]");
    if (mediaBtn) openMediaModal(mediaBtn.dataset.media);
  });

  wrap.addEventListener("change", function (e) {
    if (e.target.matches('[data-md="heading"]')) {
      MD.heading(e.target.value); e.target.value = "";
    } else if (e.target.matches('[data-md="codeblock"]')) {
      MD.codeblock(e.target.value); e.target.value = "";
    } else if (e.target.matches('[data-html="heading"]')) {
      HTMLCMD.heading(e.target.value); e.target.value = "";
    }
    if (e.target.matches('[data-md="heading"], [data-md="codeblock"], [data-html="heading"]')) afterChange();
  });

  // ---------- 互转 ----------
  wrap.querySelector('[data-convert="md2html"]').addEventListener("click", function () {
    var md = taMd.value || "";
    if (!md.trim()) return toast("Markdown 内容为空，无可转换内容");
    var html = "";
    try { html = marked.parse(md); } catch (e) { return toast("转换失败：Markdown 语法有误"); }
    taHtml.value = html;
    renderModeInput.value = "html";
    if (currentMode !== "html") setMode("html");
    renderPreview(); updateStats();
    toast("已转换到 HTML 模式（内容写入 HTML 编辑区）");
  });
  wrap.querySelector('[data-convert="html2md"]').addEventListener("click", function () {
    var html = taHtml.value || "";
    if (!html.trim()) return toast("HTML 内容为空，无可转换内容");
    var md = "";
    try {
      var td = new TurndownService({ headingStyle: "atx", codeBlockStyle: "fenced", bulletListMarker: "-", emDelimiter: "*" });
      md = td.turndown(html);
    } catch (e) { return toast("转换失败：HTML 结构有误"); }
    taMd.value = md;
    renderModeInput.value = "markdown";
    if (currentMode !== "markdown") setMode("markdown");
    renderPreview(); updateStats();
    toast("已转换到 Markdown 模式（内容写入 Markdown 编辑区）");
  });

  // ---------- 统计 ----------
  function updateStats() {
    var ta = activeTa();
    var v = ta.value || "";
    var cjk = (v.match(/[\u4e00-\u9fa5]/g) || []).length;
    var words = (v.match(/[A-Za-z0-9]+/g) || []).length;
    var total = cjk + words;
    wrap.querySelector("[data-stat='words']").textContent = total;
    wrap.querySelector("[data-stat='lines']").textContent = v.split("\n").length;
    wrap.querySelector("[data-stat='minutes']").textContent = Math.max(1, Math.round(total / 400));
  }

  // ---------- 表情 ----------
  function toggleEmoji(ev, _) {
    ev.preventDefault();
    ev.stopPropagation();
    if (!emojiPop.hidden) { emojiPop.hidden = true; return; }
    if (!emojiPop.children.length) {
      EMOJIS.forEach(function (ch) {
        var b = document.createElement("button");
        b.type = "button"; b.textContent = ch;
        b.addEventListener("click", function () {
          insertAtCursor(activeTa(), ch);
          emojiPop.hidden = true;
          afterChange();
        });
        emojiPop.appendChild(b);
      });
    }
    var rect = (ev.currentTarget || ev.target).closest("button").getBoundingClientRect();
    emojiPop.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - 330)) + "px";
    emojiPop.style.top = (rect.bottom + 6) + "px";
    emojiPop.hidden = false;
  }

  // ---------- Toast ----------
  var toastTimer = null;
  function toast(msg) {
    var old = document.querySelector(".ed-toast");
    if (old) old.remove();
    var t = document.createElement("div");
    t.className = "ed-toast";
    t.textContent = msg;
    document.body.appendChild(t);
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.remove(); }, 2200);
  }

  // ---------- 媒体弹窗（上传 / 文件库） ----------
  var mediaScope = "file"; // image | file
  var libKindSelect = document.getElementById("edLibKind");
  var libSearch = document.getElementById("edLibSearch");
  var libGrid = document.getElementById("edLibGrid");
  var libEmpty = document.getElementById("edLibEmpty");

  function openMediaModal(scope) {
    mediaScope = scope;
    modal.querySelector("[data-modal-title]").textContent =
      scope === "image" ? "插入图片" : "插入文件（图片 / PDF / 文档 / 视频）";
    modal.hidden = false;
    switchModalTab("upload");
    if (scope === "image") libKindSelect.value = "image";
    loadLibrary();
  }

  modal.querySelector("[data-close-modal]").addEventListener("click", function () { modal.hidden = true; });
  modal.addEventListener("click", function (e) {
    if (e.target === modal) modal.hidden = true;
  });
  modal.querySelectorAll("[data-mtab]").forEach(function (b) {
    b.addEventListener("click", function () { switchModalTab(b.dataset.mtab); });
  });

  function switchModalTab(name) {
    modal.querySelectorAll("[data-mtab]").forEach(function (b) {
      b.classList.toggle("active", b.dataset.mtab === name);
    });
    modal.querySelectorAll("[data-mpanel]").forEach(function (p) {
      p.hidden = p.dataset.mpanel !== name;
    });
    if (name === "library") loadLibrary();
  }

  // 上传
  var drop = document.getElementById("edDrop");
  var fileInput = document.getElementById("edFileInput");
  var upList = document.getElementById("edUploadList");
  var CSRF = document.querySelector('input[name="csrf_token"]').value;

  drop.addEventListener("click", function () { fileInput.click(); });
  fileInput.addEventListener("change", function () {
    uploadFiles(Array.prototype.slice.call(fileInput.files));
    fileInput.value = "";
  });
  ["dragover", "dragleave", "drop"].forEach(function (ev) {
    drop.addEventListener(ev, function (e) {
      e.preventDefault();
      drop.classList.toggle("dragover", ev === "dragover" || ev === "drop");
    });
  });
  drop.addEventListener("drop", function (e) {
    if (e.dataTransfer.files.length) uploadFiles(Array.prototype.slice.call(e.dataTransfer.files));
  });

  function uploadFiles(files) {
    if (!files.length) return;
    files.forEach(function (file) {
      var li = document.createElement("li");
      li.className = "ed-up-item";
      li.innerHTML = '<span class="up-name">' + escapeHtml(file.name) + "</span>" +
        '<span class="up-state">上传中…</span>';
      upList.insertBefore(li, upList.firstChild);
      var fd = new FormData();
      fd.append("file", file);
      fd.append("csrf_token", CSRF);
      var xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/upload");
      xhr.onload = function () {
        var data = {};
        try { data = JSON.parse(xhr.responseText); } catch (e) {}
        if (xhr.status === 200 && data.ok) {
          li.classList.add("ok");
          li.dataset.url = data.url;
          li.dataset.kind = data.kind;
          var ins = document.createElement("button");
          ins.type = "button";
          ins.className = "up-insert";
          ins.textContent = "再插一次";
          li.querySelector(".up-state").textContent = "已上传 ✓";
          li.appendChild(ins);
          insertMedia(data);
        } else {
          li.classList.add("err");
          li.querySelector(".up-state").textContent = data.msg || "上传失败";
        }
      };
      xhr.onerror = function () {
        li.classList.add("err");
        li.querySelector(".up-state").textContent = "网络异常";
      };
      xhr.send(fd);
    });
  }
  upList.addEventListener("click", function (e) {
    var b = e.target.closest(".up-insert");
    if (!b) return;
    var li = b.closest(".ed-up-item");
    var name = li.querySelector(".up-name").textContent;
    var url = li.dataset.url, kind = li.dataset.kind;
    if (!url) return;
    insertMedia({ url: url, name: name, kind: kind || "file" });
  });

  // 文件库
  function loadLibrary() {
    var kind = libKindSelect.value;
    if (mediaScope === "image" && kind === "all") kind = "image";
    var url = "/api/files?kind=" + encodeURIComponent(kind) +
      (libSearch.value ? "&q=" + encodeURIComponent(libSearch.value) : "");
    fetch(url, { headers: { "X-CSRF-Token": CSRF } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderLib(data.files || []);
      })
      .catch(function () { toast("文件库加载失败"); });
  }
  libKindSelect.addEventListener("change", loadLibrary);
  libSearch.addEventListener("input", debounce(loadLibrary, 350));
  modal.querySelector("[data-lib-refresh]").addEventListener("click", loadLibrary);

  function debounce(fn, ms) {
    var t = null;
    return function () {
      if (t) clearTimeout(t);
      t = setTimeout(fn, ms);
    };
  }

  function renderLib(files) {
    libGrid.innerHTML = "";
    libEmpty.hidden = files.length > 0;
    files.forEach(function (f) {
      var item = document.createElement("div");
      item.className = "ed-lib-item";
      item.title = f.name + "（" + f.size_label + "）点击插入";
      var thumb = "";
      if (f.kind === "image") thumb = '<img src="' + f.url + '" alt="" loading="lazy">';
      else thumb = '<span>' + escapeHtml((f.ext || "FILE").toUpperCase().slice(0, 6)) + "</span>";
      item.innerHTML =
        '<div class="lb-thumb">' + thumb + "</div>" +
        '<div class="lb-name">' + escapeHtml(f.name) + "</div>" +
        '<div class="lb-size">' + f.size_label + " · " + escapeHtml(f.created) + "</div>";
      item.addEventListener("click", function () { insertMedia(f); });
      libGrid.appendChild(item);
    });
  }

  // 按当前模式与文件类型插入
  function snippetFor(f) {
    var name = f.name || "文件";
    if (f.kind === "image") {
      if (currentMode === "html") {
        return '<img src="' + f.url + '" alt="' + escapeHtml(name) + '">\n';
      }
      var alt = name.replace(/[()\[\]]/g, "-");
      return "![" + alt + "](" + f.url + ")\n";
    }
    if (f.kind === "video") {
      return '\n<video controls preload="metadata" src="' + f.url + '"></video>\n';
    }
    if (f.kind === "audio") {
      return '\n<audio controls preload="metadata" src="' + f.url + '"></audio>\n';
    }
    // 文档 / 压缩包 → 文件卡片
    var ext = (f.ext || "FILE").toUpperCase().slice(0, 6);
    return '\n<a class="file-card" href="' + f.url + '" target="_blank" rel="noopener">' +
      '<span class="fc-icon">' + ext + "</span>" +
      '<span class="fc-meta"><span class="fc-name">' + escapeHtml(name) + "</span>" +
      '<span class="fc-sub">' + (f.size_label || "") + " · " + ext.toLowerCase() + "</span></span>" +
      '<span class="fc-dl"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M4 21h16"/></svg>打开</span></a>\n';
  }

  function insertMedia(f) {
    var ta = activeTa();
    var seg = ta.value.slice(ta.selectionStart, ta.selectionEnd);
    insertAtCursor(ta, snippetFor(f));
    afterChange();
    toast("已插入：" + (f.name || "文件"));
  }

  // 上传项补记 url/kind 已完成（见 uploadFiles 内 li.dataset 赋值）

  // ---------- 粘贴：图片自动上传 / 富文本转 Markdown ----------
  document.addEventListener("paste", function (e) {
    var ta = e.target;
    if (!(ta === taMd || ta === taHtml)) return;
    var cd = e.clipboardData || window.clipboardData;
    if (!cd) return;
    var imgFile = null;
    for (var i = 0; i < cd.items.length; i++) {
      var it = cd.items[i];
      if (it.kind === "file" && it.type && it.type.indexOf("image/") === 0) {
        imgFile = it.getAsFile();
        break;
      }
    }
    if (imgFile) {
      e.preventDefault();
      var f = new File([imgFile], (imgFile.name || "pasted-image.png").replace(/[^\w.\-\u4e00-\u9fa5]/g, "-"), { type: imgFile.type });
      var fd = new FormData();
      fd.append("file", f);
      fd.append("csrf_token", CSRF);
      var xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/upload");
      xhr.onload = function () {
        var data = {};
        try { data = JSON.parse(xhr.responseText); } catch (e2) {}
        if (data.ok) {
          insertMedia(data);
        } else { toast(data.msg || "图片上传失败"); }
      };
      xhr.onerror = function () { toast("图片上传失败"); };
      xhr.send(fd);
      return;
    }
    // 富文本粘贴 → Markdown（仅 Markdown 模式）
    var html = cd.getData("text/html");
    if (html && currentMode === "markdown" && ta === taMd) {
      e.preventDefault();
      var md = "";
      try {
        var td = new TurndownService({ headingStyle: "atx", codeBlockStyle: "fenced", bulletListMarker: "-" });
        md = td.turndown(html);
      } catch (e3) { md = cd.getData("text/plain") || ""; }
      insertAtCursor(taMd, md);
      afterChange();
    }
  });

  // ---------- 拖拽文件到编辑区 ----------
  ["dragover", "dragenter"].forEach(function (ev) {
    viewBox.addEventListener(ev, function (e) {
      if (e.dataTransfer && Array.prototype.some.call(e.dataTransfer.types, function (t) { return t === "Files"; })) {
        e.preventDefault();
      }
    });
  });
  viewBox.addEventListener("drop", function (e) {
    if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
    e.preventDefault();
    var files = Array.prototype.slice.call(e.dataTransfer.files);
    var hasImg = files.some(function (f) { return f.type.indexOf("image/") === 0; });
    if (files.some(function (f) { return f.type.indexOf("image/") === 0; })) {
      uploadFiles(files); // 图片与文件统一走上传弹窗列表（自动插入）
      if (!modal.hidden) return;
      modal.hidden = false;
      switchModalTab("upload");
      toast("正在上传 " + files.length + " 个文件");
    } else {
      uploadFiles(files);
      toast("正在上传 " + files.length + " 个文件");
    }
  });

  // ---------- 快捷键 ----------
  document.addEventListener("keydown", function (e) {
    var ta = activeTa();
    var inEditor = document.activeElement === ta || (document.activeElement && (document.activeElement.tagName === "TEXTAREA" || document.activeElement.isContentEditable));
    var mod = e.ctrlKey || e.metaKey;

    if (e.key === "Escape" && document.body.classList.contains("ed-fullscreen")) {
      document.body.classList.remove("ed-fullscreen");
      return;
    }
    if (e.key === "Escape" && !modal.hidden) { modal.hidden = true; return; }

    if (mod && e.key.toLowerCase() === "b") { e.preventDefault(); (currentMode === "html" ? HTMLCMD.bold() : MD.bold()); afterChange(); }
    else if (mod && e.key.toLowerCase() === "i") { e.preventDefault(); (currentMode === "html" ? HTMLCMD.italic() : MD.italic()); afterChange(); }
    else if (mod && e.key.toLowerCase() === "k") { e.preventDefault(); (currentMode === "html" ? HTMLCMD.link() : MD.link()); afterChange(); }
    else if (mod && e.key.toLowerCase() === "z" && !e.shiftKey) { e.preventDefault(); historyUndo(); }
    else if ((mod && e.key.toLowerCase() === "y") || (mod && e.shiftKey && e.key.toLowerCase() === "z")) { e.preventDefault(); historyRedo(); }
    else if (e.key === "Tab" && inEditor) {
      e.preventDefault();
      var selText = ta.value.slice(ta.selectionStart, ta.selectionEnd);
      if (selText.indexOf("\n") !== -1) {
        var lines = selText.split("\n").map(function (l) { return "    " + l; });
        replaceRange(ta, ta.selectionStart, ta.selectionEnd, lines.join("\n"));
        ta.focus();
        ta.setSelectionRange(ta.selectionStart + 4, ta.selectionEnd + 4);
        afterChange();
      } else {
        insertAtCursor(ta, "    ");
      }
    }
  });

  // ---------- 全屏 ----------
  wrap.querySelector('[data-ed="fullscreen"]').addEventListener("click", function () {
    document.body.classList.toggle("ed-fullscreen");
    renderPreview();
  });

  // ---------- 初始化 ----------
  function init() {
    // 记录初始值作为撤销基线
    lastSaved.md = taMd.value;
    lastSaved.html = taHtml.value;
    hist.md.undo = [];
    hist.html.undo = [];
    // 应用初始模式（即使与默认 markdown 相同也要重置一次，因为模板里只硬编码了 markdown 样式）
    modeSeg.querySelectorAll("button").forEach(function (b) {
      b.classList.toggle("active", b.dataset.mode === currentMode);
    });
    wrap.querySelectorAll("[data-toolbar]").forEach(function (tb) {
      tb.hidden = tb.dataset.toolbar !== currentMode;
    });
    taMd.hidden = currentMode !== "markdown";
    taHtml.hidden = currentMode !== "html";
    statusMode.textContent = currentMode === "html" ? "HTML 模式" : "Markdown 模式";
    if (currentMode === "html") {
      taMd.hidden = true;
    } else {
      taHtml.hidden = true;
    }
    renderPreview();
    updateStats();
    // 初始若两个模式都空且 HTML 模式是新文章，保持 markdown
    if (!renderModeInput.value) renderModeInput.value = "markdown";
  }
  init();

  // ---------- 自动保存草稿（localStorage，防意外退出丢稿） ----------
  var editorForm = wrap.closest("form");
  var pidMatch = (location.pathname || "").match(/\/admin\/posts\/(\d+)\/edit/);
  var draftKey = "wb-editor-draft-" + (pidMatch ? "post-" + pidMatch[1] : "new");
  var draftBar = null;

  function readDraft() {
    try {
      var raw = localStorage.getItem(draftKey);
      if (!raw) return null;
      var d = JSON.parse(raw);
      return d && typeof d === "object" && d.savedAt ? d : null;
    } catch (e) { return null; }
  }
  function writeDraft() {
    try {
      if (!editorForm) return;
      var titleEl = editorForm.elements.namedItem("title");
      var has = titleEl && titleEl.value.trim();
      if (!has && !taMd.value.trim() && !taHtml.value.trim()) return;  // 全空不写
      var data = { savedAt: Date.now(), fields: {}, md: taMd.value, html: taHtml.value };
      Array.prototype.forEach.call(editorForm.elements, function (el) {
        if (!el.name || el.name === "content" || el.name === "content_html") return;
        if (el.type === "checkbox") data.fields[el.name] = el.checked ? "1" : "";
        else if (el.type === "radio") { if (el.checked) data.fields[el.name] = el.value; }
        else data.fields[el.name] = el.value;
      });
      localStorage.setItem(draftKey, JSON.stringify(data));
    } catch (e) { /* localStorage 不可用/满则静默 */ }
  }
  function clearDraft() {
    try { localStorage.removeItem(draftKey); } catch (e) {}
  }
  function humanTime(ts) {
    var diff = Date.now() - ts;
    if (diff < 60 * 1000) return "刚刚";
    if (diff < 3600 * 1000) return Math.floor(diff / 60000) + " 分钟前";
    var d = new Date(ts);
    function p(n) { return (n < 10 ? "0" : "") + n; }
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
  }
  function removeDraftBar() {
    if (draftBar && draftBar.parentNode) draftBar.parentNode.removeChild(draftBar);
    draftBar = null;
  }
  function restoreDraft(d) {
    Object.keys(d.fields).forEach(function (name) {
      var el = editorForm.elements.namedItem(name);
      if (!el) return;
      if (el.type === "checkbox") el.checked = d.fields[name] === "1";
      else el.value = d.fields[name];
    });
    taMd.value = d.md;
    taHtml.value = d.html;
    lastSaved.md = d.md; lastSaved.html = d.html;   // 撤销基线跟随草稿
    hist.md.undo = []; hist.html.undo = [];
    /* 模式跟随草稿（若与当前不符），否则仅重渲染 */
    if (typeof setMode === "function" &&
        (d.fields.render_mode === "html" || d.fields.render_mode === "markdown") &&
        d.fields.render_mode !== currentMode) {
      setMode(d.fields.render_mode);
    } else {
      if (typeof renderPreview === "function") renderPreview();
      if (typeof updateStats === "function") updateStats();
    }
    removeDraftBar();
    clearDraft();
    if (typeof toast === "function") toast("已恢复本地草稿");
  }
  function maybeShowDraftBar() {
    if (!editorForm) return;
    var d = readDraft();
    if (!d) return;
    draftBar = document.createElement("div");
    draftBar.className = "ed-draft-bar";
    var info = document.createElement("span");
    info.className = "ed-draft-info";
    info.textContent = "检测到本地草稿（" + humanTime(d.savedAt) + "保存，尚未提交到服务器）";
    var bRestore = document.createElement("button");
    bRestore.type = "button"; bRestore.className = "ed-draft-restore";
    bRestore.textContent = "恢复草稿";
    bRestore.addEventListener("click", function () {
      if (window.confirm("用本地草稿覆盖当前编辑内容？")) restoreDraft(d);
    });
    var bDiscard = document.createElement("button");
    bDiscard.type = "button"; bDiscard.className = "ed-draft-discard";
    bDiscard.textContent = "丢弃";
    bDiscard.addEventListener("click", function () { removeDraftBar(); clearDraft(); });
    draftBar.appendChild(info); draftBar.appendChild(bRestore); draftBar.appendChild(bDiscard);
    editorForm.insertBefore(draftBar, editorForm.firstChild);
  }

  var _submitted = false;
  var _debTimer = null;
  if (editorForm) {
    /* 输入防抖 1.2s 自动保存（标题/正文/选项任意字段变化都会触发） */
    editorForm.addEventListener("input", function () {
      if (_submitted) return;
      clearTimeout(_debTimer);
      _debTimer = setTimeout(writeDraft, 1200);
    });
    /* 表单提交：已上服务器，清草稿并停止后续兜底写入 */
    editorForm.addEventListener("submit", function () {
      _submitted = true;
      clearTimeout(_debTimer);
      clearDraft();
    });
  }
  /* 关标签 / 刷新 / 意外退出前的兜底：同步写一次 */
  window.addEventListener("beforeunload", function () {
    if (_submitted) return;
    clearTimeout(_debTimer);
    writeDraft();
  });
  maybeShowDraftBar();
})();
