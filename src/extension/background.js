/**
 * 后台 Service Worker：监听网页加载，自动检测钓鱼风险并弹窗
 * 融合：域名检测 + 页面内容检测（content script 抓取）
 * 优化：同一域名只弹窗一次，不重复打扰用户
 */
import { detect } from "./detector.js";

const HISTORY_LIMIT = 50;
const REPORT_SERVER = "http://127.0.0.1:5000"; // Web 后台地址

const pendingContent = new Map(); // url -> {title, bodyText}

// 内容敏感关键词
const SENSITIVE_KEYWORDS = [
  { kw: "学号", score: 15, reason: "页面索要学号" },
  { kw: "身份证", score: 15, reason: "页面索要身份证号" },
  { kw: "银行卡", score: 15, reason: "页面索要银行卡号" },
  { kw: "验证码", score: 10, reason: "页面索要验证码" },
  { kw: "密码", score: 10, reason: "页面索要密码" },
  { kw: "奖助学金", score: 10, reason: "出现奖助学金关键词" },
  { kw: "校园缴费", score: 10, reason: "出现校园缴费关键词" },
  { kw: "教务系统", score: 8, reason: "出现教务系统关键词" },
  { kw: "补助", score: 8, reason: "出现补助申领关键词" },
  { kw: "紧急", score: 5, reason: "页面使用紧急话术" },
  { kw: "立即登录", score: 5, reason: "出现诱导登录话术" },
  { kw: "请核实", score: 5, reason: "出现诱导核实话术" },
];

/**
 * 检查某域名是否已经弹过窗
 * 已弹过返回 false（不弹），未弹过返回 true（弹）
 */
async function shouldNotifyOnce(hostname) {
  const { notifiedHosts = [] } = await chrome.storage.local.get({ notifiedHosts: [] });
  if (notifiedHosts.includes(hostname)) {
    return false; // 已经弹过了，不重复弹
  }
  // 标记为已弹过
  notifiedHosts.push(hostname);
  // 最多保留 200 条，防止无限增长
  chrome.storage.local.set({ notifiedHosts: notifiedHosts.slice(-200) });
  return true;
}

function levelEmoji(level) {
  if (level === "高危") return "🔴";
  if (level === "可疑") return "🟡";
  return "🟢";
}

function contentScore(title, bodyText) {
  /** 从页面文本算内容风险分（0~40） */
  const text = (title + " " + bodyText).toLowerCase();
  let score = 0;
  const reasons = [];
  for (const { kw, score: s, reason } of SENSITIVE_KEYWORDS) {
    if (text.includes(kw.toLowerCase())) {
      score += s;
      reasons.push(reason);
    }
  }
  return { score: Math.min(score, 40), reasons };
}

function fuseResult(domainResult, contentScore) {
  /** 融合域名分 + 内容分，重算等级 */
  const total = Math.min(domainResult.score + contentScore.score, 100);
  let level = "安全";
  if (total > 65) level = "高危";
  else if (total > 30) level = "可疑";
  const allReasons = [...domainResult.reasons, ...contentScore.reasons];
  return { ...domainResult, score: total, level, reasons: allReasons };
}

function reportToServer(entry) {
  /** 上报到 Web 后台（失败静默忽略） */
  try {
    fetch(`${REPORT_SERVER}/api/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(entry),
    }).catch(() => {});
  } catch (e) {}
}

async function showNotification(result, tabId) {
  const { level, score, host, reasons, url } = result;
  const title = `${levelEmoji(level)} 钓鱼检测：${level}`;
  const message = `${host}（${score}分）\n${reasons[0] || ""}`;

  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon48.png",
    title,
    message,
    priority: level === "高危" ? 2 : 0,
  });

  // 高危：往页面注入全屏红色警告遮罩
  if (level === "高危" && tabId) {
    try {
      await chrome.tabs.sendMessage(tabId, { type: "SHOW_WARNING", result });
    } catch (e) { /* content script 可能还没注入 */ }
  }

  const entry = {
    url,
    host,
    level,
    score,
    reason: reasons[0] || "",
    time: new Date().toISOString(),
  };
  chrome.storage.local.get({ history: [] }).then(({ history }) => {
    const newHistory = [entry, ...history].slice(0, HISTORY_LIMIT);
    chrome.storage.local.set({ history: newHistory });
  });
  reportToServer(entry);
}

// 检查是否在信任名单
async function isTrusted(hostname) {
  const { trustedHosts = [] } = await chrome.storage.local.get({ trustedHosts: [] });
  return trustedHosts.includes(hostname);
}

// 监听 content script 发来的页面内容
chrome.runtime.onMessage.addListener(async (msg, sender) => {
  if (msg.type !== "PAGE_CONTENT") return;
  const url = msg.url;
  // 保存待处理的内容
  pendingContent.set(url, { title: msg.title, bodyText: msg.bodyText });

  // 如果已经有域名检测结果（页面加载完先跑了域名检测），现在融合
  const domainResult = detect(url);
  const cScore = contentScore(msg.title, msg.bodyText);
  const fused = fuseResult(domainResult, cScore);

  const hostname = new URL(url).hostname;
  // 信任名单不弹
  if (await isTrusted(hostname)) return;
  // 同一域名只弹一次
  if (await shouldNotifyOnce(hostname)) {
    showNotification(fused, sender.tab?.id);
  }
});

// 监听标签页加载完成（先跑域名检测）
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (!changeInfo.status || changeInfo.status !== "complete") return;
  if (!tab.url || !/^https?:\/\//.test(tab.url)) return;

  try {
    const url = new URL(tab.url);
    const hostname = url.hostname;
    if (hostname.startsWith("chrome") || hostname.startsWith("edge")) return;

    // 先跑域名检测，等 content script 内容回来再融合
    const domainResult = detect(tab.url);
    // 信任名单跳过
    if (await isTrusted(hostname)) return;
    // 如果 content script 已经发过内容了，直接融合
    const cached = pendingContent.get(tab.url);
    if (cached) {
      const cScore = contentScore(cached.title, cached.bodyText);
      const fused = fuseResult(domainResult, cScore);
      if (await shouldNotifyOnce(hostname)) showNotification(fused, tabId);
    }
    // 否则等 content script 消息触发融合
  } catch (e) {
    console.warn("检测失败:", e, tab.url);
  }
});

chrome.notifications.onClicked.addListener((notificationId) => {
  chrome.notifications.clear(notificationId);
});

// 监听 popup 的"信任此站"请求
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "TRUST_HOST" && msg.host) {
    chrome.storage.local.get({ trustedHosts: [] }).then(({ trustedHosts }) => {
      if (!trustedHosts.includes(msg.host)) {
        trustedHosts.push(msg.host);
        chrome.storage.local.set({ trustedHosts });
      }
      sendResponse({ ok: true, trustedHosts });
    });
    return true; // 异步 sendResponse
  }
});

// 监听 popup 取"本页融合结果"：与上报后台的口径保持一致（域名分 + 内容分）
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "GET_FUSED" && msg.url) {
    try {
      const domainResult = detect(msg.url);
      const cached = pendingContent.get(msg.url);
      if (cached) {
        sendResponse({
          ok: true,
          result: fuseResult(domainResult, contentScore(cached.title, cached.bodyText)),
        });
      } else {
        sendResponse({ ok: false, result: domainResult });
      }
    } catch (e) {
      sendResponse({ ok: false });
    }
    return true;
  }
});

console.log("校园钓鱼检测助手已启动（同一域名只弹一次）");
