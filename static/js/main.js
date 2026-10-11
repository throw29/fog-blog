(function () {
  "use strict";

  // ---------- 代码高亮 ----------
  document.addEventListener("DOMContentLoaded", function () {
    if (window.hljs) {
      document.querySelectorAll("pre code").forEach(function (el) {
        hljs.highlightElement(el);
      });
    }
  });

  // ---------- 阅读进度条 ----------
  var bar = document.getElementById("progressBar");
  if (bar) {
    var updateBar = function () {
      var h = document.documentElement;
      var max = h.scrollHeight - h.clientHeight;
      var p = max > 0 ? (h.scrollTop / max) * 100 : 0;
      bar.style.width = p + "%";
    };
    document.addEventListener("scroll", updateBar, { passive: true });
    window.addEventListener("resize", updateBar);
    updateBar();
  }

  // ---------- 移动端菜单 ----------
  var toggle = document.getElementById("menuToggle");
  var navLinks = document.getElementById("navLinks");
  if (toggle && navLinks) {
    toggle.addEventListener("click", function () {
      navLinks.classList.toggle("open");
    });
  }

  // ---------- flash 自动消失 ----------
  document.querySelectorAll(".flash-msg[data-auto-hide]").forEach(function (el) {
    setTimeout(function () {
      el.style.transition = "opacity 0.4s";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 450);
    }, 3200);
  });

  // ---------- 文章目录滚动高亮 ----------
  var tocLinks = document.querySelectorAll(".toc a");
  if (tocLinks.length) {
    var headings = [];
    tocLinks.forEach(function (a) {
      var target = document.getElementById(a.getAttribute("href").slice(1));
      if (target) headings.push({ link: a, el: target });
    });
    var onScroll = function () {
      var pos = window.scrollY + 120;
      var current = null;
      headings.forEach(function (item) {
        if (item.el.offsetTop <= pos) current = item;
      });
      headings.forEach(function (item) {
        item.link.classList.toggle("active", item === current);
      });
    };
    document.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // ---------- 点赞 ----------
  var likeBtn = document.getElementById("likeBtn");
  if (likeBtn) {
    likeBtn.addEventListener("click", function () {
      if (likeBtn.dataset.liked === "1") return;
      fetch("/api/post/" + likeBtn.dataset.id + "/like", {
        method: "POST",
        headers: {
          "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content
        }
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) {
            likeBtn.dataset.liked = "1";
            likeBtn.classList.add("liked");
            document.getElementById("likeCount").textContent = data.likes;
          } else {
            showTip(data.msg || "操作失败", true);
          }
        })
        .catch(function () { showTip("网络异常，请稍后再试", true); });
    });
  }

  // ---------- 评论提交 ----------
  var form = document.getElementById("commentForm");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var tip = document.getElementById("commentTip");
      var btn = form.querySelector("button[type=submit]");
      var nickname = form.nickname ? form.nickname.value.trim() : "";
      var content = form.content.value.trim();
      if (!nickname || !content) {
        showTip("请填写昵称和评论内容", true);
        return;
      }
      var fd = new FormData();
      fd.append("post_id", form.dataset.post);
      fd.append("nickname", nickname);
      fd.append("email", form.email ? form.email.value.trim() : "");
      fd.append("content", content);
      fd.append("csrf_token", form.csrf_token.value);

      btn.disabled = true;
      btn.textContent = "提交中...";
      fetch("/api/comment", { method: "POST", body: fd })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) {
            form.content.value = "";
            showTip(data.msg, false, tip);
            setTimeout(function () { location.reload(); }, 1200);
          } else {
            showTip(data.msg || "评论失败", true, tip);
          }
        })
        .catch(function () { showTip("网络异常，请稍后再试", true, tip); })
        .finally(function () {
          btn.disabled = false;
          btn.textContent = "发表评论";
        });
    });
  }

  function showTip(msg, isError, holder) {
    var el = holder || document.getElementById("commentTip");
    if (!el) return;
    el.textContent = msg;
    el.style.color = isError ? "#dc2626" : "#16a34a";
    if (!holder) {
      setTimeout(function () { el.textContent = ""; }, 4000);
    }
  }
})();
