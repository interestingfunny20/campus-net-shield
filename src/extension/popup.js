import { detect } from "./detector.js";

const urlEl = document.getElementById("current-url");
const badgeEl = document.getElementById("level-badge");
const scoreEl = document.getElementById("score");
const reasonListEl = document.getElementById("reason-list");
const historyEl = document.getElementById("history-list");
const headerEl = document.querySelector("header");
const trustBtn = document.getElementById("trust-btn");
let currentHost = "";

// 小猫钓鱼主题：等级 → 表情 + 文案
const LEVEL_TEXT = {
  "安全": "🐱 安全",
  "可疑": "😼 可疑",
  "高危": "🙀 高危",
  "未知": "🐾 未知",
};
const LEVEL_MSG = {
  "安全": "钓到小鱼啦，这个网站可以放心逛~",
  "可疑": "好像有奇怪的鱼，小心一点哦",
  "高危": "钓到炸弹了！千万别输入信息！",
  "未知": "页面没抓到，无法确认，建议核实后再访问",
};

function setLoading(isLoading) {
  headerEl.classList.toggle("loading", isLoading);
}

function renderResult(result) {
  urlEl.textContent = result.host || result.url;
  currentHost = result.host || "";
  badgeEl.textContent = LEVEL_TEXT[result.level] || result.level;
  badgeEl.className = "level-badge " + result.level;
  scoreEl.textContent = result.score + " 分";
  const reasons = result.reasons && result.reasons.length
    ? result.reasons.map(r => `<li>${escapeHtml(r)}</li>`).join("")
    : `<li>${LEVEL_MSG[result.level] || ""}</li>`;
  reasonListEl.innerHTML = reasons;
  // 可疑/高危才显示信任按钮
  trustBtn.style.display = (result.level === "可疑" || result.level === "高危") ? "block" : "none";
  setLoading(false);
}

// 信任此站
trustBtn.addEventListener("click", async () => {
  if (!currentHost) return;
  await chrome.runtime.sendMessage({ type: "TRUST_HOST", host: currentHost });
  trustBtn.textContent = "✅ 已加入信任名单";
  trustBtn.disabled = true;
  badgeEl.textContent = "🐱 已信任";
  badgeEl.className = "level-badge 安全";
});

function renderHistory(history) {
  if (!history || history.length === 0) {
    historyEl.innerHTML = '<li class="empty">暂无检测记录</li>';
    return;
  }
  historyEl.innerHTML = history.map(h => `
    <li>
      <span class="h-host">${escapeHtml(h.host)}</span>
      <span class="h-level ${h.level}">${LEVEL_TEXT[h.level] || h.level} ${h.score}</span>
    </li>
  `).join("");
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

// 获取当前活动标签页并检测
chrome.tabs.query({ active: true, currentWindow: true }).then((tabs) => {
  const tab = tabs[0];
  if (!tab || !tab.url || !/^https?:\/\//.test(tab.url)) {
    badgeEl.textContent = "非网页";
    badgeEl.className = "level-badge 非网页";
    urlEl.textContent = tab?.url || "—";
    setLoading(false);
    return;
  }
  setLoading(true);
  // 轻微延迟，让钓鱼动画先展示
  setTimeout(() => {
    // 优先取后台的融合结果（域名分 + 内容分），与上报后台的口径一致
    chrome.runtime
      .sendMessage({ type: "GET_FUSED", url: tab.url })
      .then((resp) => {
        const result = resp && resp.ok && resp.result ? resp.result : detect(tab.url);
        renderResult(result);
      })
      .catch(() => renderResult(detect(tab.url)));
  }, 400);
});

// 加载历史记录
chrome.storage.local.get({ history: [] }).then(({ history }) => {
  renderHistory(history);
});
