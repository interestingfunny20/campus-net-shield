/**
 * Content Script：注入网页，抓取页面标题和文本内容
 * 同时接收 background 指令，高危时显示全屏红色警告遮罩
 */
(function () {
  if (window.top !== window) return;

  function getPageContent() {
    const title = document.title || "";
    const bodyText = (document.body?.innerText || "").slice(0, 3000);
    return { title, bodyText };
  }

  function reportContent() {
    try {
      chrome.runtime.sendMessage({
        type: "PAGE_CONTENT",
        url: location.href,
        title: getPageContent().title,
        bodyText: getPageContent().bodyText,
      });
    } catch (e) {}
  }

  setTimeout(reportContent, 1000);

  // ===== 高危红色警告遮罩 =====
  function showWarningOverlay(result) {
    // 已存在就不重复加
    if (document.getElementById("__phish_warning__")) return;

    const overlay = document.createElement("div");
    overlay.id = "__phish_warning__";
    overlay.style.cssText = `
      position: fixed; inset: 0; z-index: 2147483647;
      background: rgba(180, 0, 0, 0.96);
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      font-family: "Microsoft YaHei", sans-serif; color: #fff;
    `;
    overlay.innerHTML = `
      <div style="font-size: 72px; margin-bottom: 16px;">⚠️</div>
      <div style="font-size: 32px; font-weight: bold; margin-bottom: 12px;">危险网站</div>
      <div style="font-size: 16px; margin-bottom: 8px; opacity: 0.9;">${result.host}</div>
      <div style="font-size: 14px; margin-bottom: 24px; opacity: 0.8;">风险评分 ${result.score} 分 · ${result.reasons && result.reasons[0] ? result.reasons[0] : "疑似钓鱼网站"}</div>
      <div style="font-size: 14px; margin-bottom: 32px; max-width: 480px; text-align: center; opacity: 0.85; line-height: 1.6;">
        请勿在此页面输入账号、密码、验证码或个人信息。<br>建议立即关闭此页面。
      </div>
      <div style="display: flex; gap: 12px; align-items: center; justify-content: center;">
      <button id="__phish_leave__" style="
        padding: 12px 32px; font-size: 16px; background: #fff; color: #b40000;
        border: none; border-radius: 6px; cursor: pointer; font-weight: bold; margin-right: 12px;
        width: auto !important; min-width: 0 !important; flex: 0 0 auto; align-self: center;
      ">立即离开</button>
      <button id="__phish_stay__" style="
        padding: 12px 32px; font-size: 14px; background: transparent; color: #fff;
        border: 1px solid #fff; border-radius: 6px; cursor: pointer;
        width: auto !important; min-width: 0 !important; flex: 0 0 auto; align-self: center;
      ">我已知晓，仍然访问</button>
      </div>
    `;
    document.body.appendChild(overlay);

    document.getElementById("__phish_leave__").onclick = () => {
      history.back();
      setTimeout(() => window.close(), 500);
    };
    document.getElementById("__phish_stay__").onclick = () => {
      overlay.remove();
    };
  }

  // 监听 background 发来的高危警告
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "SHOW_WARNING" && msg.result) {
      showWarningOverlay(msg.result);
    }
  });
})();
