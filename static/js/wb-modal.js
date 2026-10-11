/* 全局自定义 modal 确认：替代 window.confirm
 * - 触发源 1：<form data-confirm="提示文本"> 提交时
 * - 触发源 2：<button data-confirm-msg="提示文本"> 点击时（按钮在 form 内）
 * 行为：拦截默认动作 → 弹中央 modal → 用户点"确定"再真实提交/触发
 * 提供 WBModal.confirm(msg, opts) 给其他场景异步复用 */
(function () {
  /* 单例 DOM：第一次调用时挂到 body */
  var backdrop = null;
  var titleEl = null, bodyEl = null, extraEl = null;
  var cancelBtn = null, okBtn = null;
  var resolver = null;

  function ensureDom() {
    if (backdrop) return;
    backdrop = document.createElement("div");
    backdrop.className = "wb-modal-backdrop";
    backdrop.hidden = true;
    backdrop.innerHTML =
      '<div class="wb-modal" role="dialog" aria-modal="true" aria-labelledby="wbModalTitle">' +
        '<div class="wb-modal-title" id="wbModalTitle">确认操作</div>' +
        '<div class="wb-modal-body" id="wbModalBody"></div>' +
        '<div class="wb-modal-extra" id="wbModalExtra" hidden></div>' +
        '<div class="wb-modal-actions">' +
          '<button type="button" class="wb-modal-btn" data-act="cancel">取消</button>' +
          '<button type="button" class="wb-modal-btn danger" data-act="ok">确定</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(backdrop);
    titleEl = backdrop.querySelector("#wbModalTitle");
    bodyEl = backdrop.querySelector("#wbModalBody");
    extraEl = backdrop.querySelector("#wbModalExtra");
    cancelBtn = backdrop.querySelector('[data-act="cancel"]');
    okBtn = backdrop.querySelector('[data-act="ok"]');
    backdrop.addEventListener("click", function (e) {
      if (e.target === backdrop) close(false);
    });
    cancelBtn.addEventListener("click", function () { close(false); });
    okBtn.addEventListener("click", function () { close(true); });
    document.addEventListener("keydown", function (e) {
      if (backdrop.hidden) return;
      if (e.key === "Escape") close(false);
      else if (e.key === "Enter") {
        /* textarea 等输入元素里的回车不该触发 */
        var ae = document.activeElement;
        if (ae && (ae.tagName === "TEXTAREA" || (ae.tagName === "INPUT" && /^(text|search|email|url|password)$/.test((ae.type || "").toLowerCase())))) return;
        e.preventDefault();
        close(true);
      }
    });
  }

  function open(opts) {
    ensureDom();
    titleEl.textContent = opts.title || "确认操作";
    bodyEl.textContent = opts.message || "确定继续吗？";
    if (opts.extra) {
      extraEl.textContent = opts.extra;
      extraEl.hidden = false;
    } else {
      extraEl.hidden = true;
    }
    okBtn.textContent = opts.okText || "确定";
    cancelBtn.textContent = opts.cancelText || "取消";
    if (opts.danger === false) okBtn.classList.remove("danger");
    else okBtn.classList.add("danger");
    backdrop.hidden = false;
    /* 把焦点放到确定按钮（用户回车即确认） */
    setTimeout(function () { okBtn.focus(); }, 30);
    return new Promise(function (res) { resolver = res; });
  }

  function close(ok) {
    if (backdrop.hidden) return;
    backdrop.hidden = true;
    var r = resolver; resolver = null;
    if (r) r(ok);
  }

  /* 公开 API */
  window.WBModal = {
    confirm: function (message, opts) { return open(Object.assign({ message: message }, opts || {})); },
    close: function (ok) { close(ok); },
  };

  /* 自动接管 form[data-confirm] 与 button[data-confirm-msg] */
  function attachForms(root) {
    var forms = (root || document).querySelectorAll("form[data-confirm]");
    for (var i = 0; i < forms.length; i++) {
      (function (f) {
        if (f.__wbModalBound) return;
        f.__wbModalBound = true;
        f.addEventListener("submit", function (e) {
          if (f.__wbModalSkip) return;
          e.preventDefault();
          WBModal.confirm(f.getAttribute("data-confirm"), {
            title: "确认操作",
            danger: true,
          }).then(function (ok) {
            if (!ok) return;
            f.__wbModalSkip = true;
            if (typeof f.requestSubmit === "function") f.requestSubmit();
            else f.submit();
          });
        });
      })(forms[i]);
    }
    /* 文件库删除：<button data-confirm-msg> 触发 fetch 删除 */
    var btns = (root || document).querySelectorAll("[data-confirm-msg]");
    for (var j = 0; j < btns.length; j++) {
      (function (b) {
        if (b.__wbModalBound) return;
        b.__wbModalBound = true;
        b.addEventListener("click", function (e) {
          if (b.__wbModalSkip) return;
          /* 若已有 onClick 自己处理 confirm/弹窗，则不重复拦截 */
          e.preventDefault();
          e.stopPropagation();
          WBModal.confirm(b.getAttribute("data-confirm-msg"), {
            title: "确认操作",
            danger: true,
          }).then(function (ok) {
            if (!ok) return;
            b.__wbModalSkip = true;
            /* 重新派发 click 让原有 onclick 接管 */
            b.click();
          });
        });
      })(btns[j]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { attachForms(); });
  } else {
    attachForms();
  }
  /* 暴露给需要动态插入新表单/按钮的页面（如批量删除工具栏） */
  window.WBModalAttachForms = attachForms;
})();