/* 文章管理批量勾选 + 工具栏同步
 * - 全选 / 取消全选（当前页）
 * - 勾选数变化时显示/隐藏工具栏 + 更新计数
 * - 提交前把勾选的 ids 注入到 .batch-bar 内的隐藏 inputs */
(function () {
  var batchAll = document.getElementById("batchAll");
  var checks = document.querySelectorAll(".rowCheck");
  var bar = document.getElementById("batchBar");
  var countEl = document.getElementById("batchCount");
  var clearBtn = document.getElementById("batchClear");
  var batchIds = document.getElementById("batchIds");
  var batchIds2 = document.getElementById("batchIds2");
  if (!bar || !checks.length) return;

  function selectedIds() {
    var out = [];
    for (var i = 0; i < checks.length; i++) {
      if (checks[i].checked) out.push(checks[i].value);
    }
    return out;
  }

  function sync() {
    var ids = selectedIds();
    countEl.textContent = "已选 " + ids.length + " 篇";
    if (ids.length > 0) {
      bar.hidden = false;
    } else {
      bar.hidden = true;
      if (batchAll) batchAll.checked = false;
    }
    /* 全选状态 */
    if (batchAll) {
      var allChecked = ids.length === checks.length && checks.length > 0;
      batchAll.checked = allChecked;
    }
    /* 把 ids 灌进隐藏容器（每次更新） */
    var html = "";
    for (var i = 0; i < ids.length; i++) {
      html += '<input type="hidden" name="ids" value="' + ids[i] + '">';
    }
    if (batchIds) batchIds.innerHTML = html;
    if (batchIds2) batchIds2.innerHTML = html;
  }

  for (var i = 0; i < checks.length; i++) {
    checks[i].addEventListener("change", sync);
  }
  if (batchAll) {
    batchAll.addEventListener("change", function () {
      var on = batchAll.checked;
      for (var i = 0; i < checks.length; i++) checks[i].checked = on;
      sync();
    });
  }
  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      for (var i = 0; i < checks.length; i++) checks[i].checked = false;
      sync();
    });
  }

  sync();
})();