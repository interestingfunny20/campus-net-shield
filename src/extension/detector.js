/**
 * 校园钓鱼网页检测助手 —— 核心检测逻辑（JavaScript 移植版）
 *
 * 与 Python 桌面版共用同一套算法：
 *   - Levenshtein 编辑距离计算域名形近相似度（0~100 分）
 *   - 形近字符归一化（o/0、l/1/i、rn/m 等）
 *   - 官方域名白名单 / 已知安全域名
 *   - 可疑 TLD / 可疑子域名关键词
 *   - 页面敏感关键词检测（学号、密码、银行卡等）
 *
 * 评分：0~30 安全 / 31~65 可疑 / 66~100 高危
 */

// ---------------- 特征库（与 data/features.json 对应） ----------------
const OFFICIAL_DOMAINS = {
  "mku.edu.cn": "闽南科技学院",
};

const KNOWN_SAFE_DOMAINS = {
  "baidu.com": "百度",
  "qq.com": "腾讯（含微信）",
  "taobao.com": "淘宝",
  "tmall.com": "天猫",
  "jd.com": "京东",
  "alipay.com": "支付宝",
  "163.com": "网易",
  "126.com": "网易邮箱",
  "sina.com.cn": "新浪",
  "sohu.com": "搜狐",
  "zhihu.com": "知乎",
  "bilibili.com": "哔哩哔哩",
  "douyin.com": "抖音",
  "gov.cn": "中国政府网站",
};

const TRUSTED_SUFFIXES = ["edu.cn", "gov.cn"];

const SUSPICIOUS_TLDS = [
  "tk", "ml", "ga", "cf", "gq", "xyz", "top", "icu", "vip", "site",
  "club", "online", "fun", "link", "live", "rest", "monster", "review", "stream",
];

// 可疑子域名词元表：按词元精确比对，不做子串包含
// 命中：login.mku.edu.cn / user-login.xxx.com / pay-portal.xxx.com
// 不命中：payload.xxx.com / library.xxx.com / cardgame.xxx.com（包含但不等于）
const SUSPICIOUS_SUBDOMAINS = [
  "login", "verify", "secure", "account", "update", "webmail", "sso", "portal",
  "pay", "finaid", "jw", "jwc", "xsc", "lib", "bank", "card", "auth",
  "security", "grant", "subsidy",
];

const CAMPUS_KEYWORDS = [
  "教务系统", "奖助学金", "奖学金", "助学金", "校园缴费", "校园补助",
  "学费缴纳", "成绩查询", "学分查询", "选课系统", "四六级报名",
  "学生证", "学籍信息", "校园卡", "宿舍费", "医保缴费",
];

const SENSITIVE_FIELDS = [
  "学号", "studentid", "student_id", "password", "passwd", "idcard",
  "身份证", "银行卡", "cardno", "验证码", "captcha", "verifycode",
];

const SENSITIVE_TEXT = [
  "请输入学号", "输入学号", "填写学号", "请输入身份证", "输入身份证",
  "输入银行卡号", "输入验证码", "领取奖学金", "申领助学金", "补助到账",
  "激活账户", "账户异常", "补录信息", "解除冻结",
];

const URGENT_TEXT = [
  "24小时内", "逾期", "过期", "冻结", "注销", "否则将", "最后一天", "名额有限",
];

const WEIGHTS = {
  domain_ip_direct: 20,
  domain_visual_similar: 40,
  domain_homograph: 30,
  domain_many_subdomains: 15,
  domain_suspicious_subdomain: 15,
  domain_suspicious_tld: 10,
  content_sensitive_field: 25,
  content_campus_keyword: 5,
  content_sensitive_sentence: 8,
  content_urgent_sentence: 3,
};

const SIMILAR_THRESHOLD = 60; // Levenshtein 相似度阈值（与桌面端 features.json 的 domain_similar_threshold 保持一致）

// ---------------- Levenshtein 编辑距离 ----------------
function levenshteinDistance(a, b) {
  if (a === b) return 0;
  const la = a.length, lb = b.length;
  if (la === 0) return lb;
  if (lb === 0) return la;
  let prev = Array.from({ length: lb + 1 }, (_, i) => i);
  for (let i = 1; i <= la; i++) {
    const cur = [i];
    for (let j = 1; j <= lb; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      cur[j] = Math.min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
    }
    prev = cur;
  }
  return prev[lb];
}

// 形近字符归一化映射
const NORMALIZE_MAP = {
  "0": "o", "o": "o",
  "1": "l", "l": "l", "i": "l",
  "5": "s", "s": "s",
  "2": "z", "z": "z",
  "8": "b", "b": "b",
  "9": "g", "g": "g",
};

function normalize(s) {
  s = s.toLowerCase().trim();
  s = s.replace(/rn/g, "m").replace(/vv/g, "w");
  return s.split("").map(ch => NORMALIZE_MAP[ch] || ch).join("");
}

function similarityScore(a, b) {
  a = (a || "").toLowerCase().trim();
  b = (b || "").toLowerCase().trim();
  if (!a || !b) return 0;
  if (a === b) return 100;
  const raw = (() => {
    const d = levenshteinDistance(a, b);
    return (1 - d / Math.max(a.length, b.length)) * 100;
  })();
  const norm = (() => {
    const na = normalize(a), nb = normalize(b);
    if (na === nb) return 100;
    const d = levenshteinDistance(na, nb);
    return (1 - d / Math.max(na.length, nb.length)) * 100;
  })();
  return Math.max(raw, norm);
}

// ---------------- 域名解析 ----------------
function parseUrl(urlStr) {
  try {
    const url = new URL(urlStr);
    const host = url.hostname;
    // 简单判断是否 IP
    const ipMatch = /^\d{1,3}(\.\d{1,3}){3}$/.test(host);
    // 分割主域名：取最后两段（如 mku.edu.cn → registered = mku.edu.cn, subdomain = www）
    const parts = host.split(".");
    // 处理 .edu.cn 这类两段后缀
    let registered, suffix, subdomain;
    if (parts.length >= 3 && parts.slice(-2).join(".") === "edu.cn") {
      registered = parts.slice(-3).join(".");
      subdomain = parts.slice(0, -3).join(".");
      suffix = "edu.cn";
    } else if (parts.length >= 3 && parts.slice(-2).join(".") === "gov.cn") {
      registered = parts.slice(-3).join(".");
      subdomain = parts.slice(0, -3).join(".");
      suffix = "gov.cn";
    } else if (parts.length >= 2) {
      registered = parts.slice(-2).join(".");
      subdomain = parts.slice(0, -2).join(".");
      suffix = parts[parts.length - 1];
    } else {
      registered = host;
      subdomain = "";
      suffix = parts[parts.length - 1] || "";
    }
    return {
      protocol: url.protocol.replace(":", ""),
      host,
      subdomain,
      registeredDomain: registered,
      suffix,
      isIp: ipMatch,
    };
  } catch (e) {
    return null;
  }
}

// ---------------- 子域名词元切分 ----------------
// 标签内的 - 与 _ 视为词元分隔符，切分后逐个精确比对
// 例："user-login" → ["user", "login"]；"payload" → ["payload"]（不命中 pay）
function tokenizeLabel(label) {
  return String(label || "")
    .toLowerCase()
    .split(/[-_\s]+/)
    .filter(t => t.length > 0);
}

// ---------------- 检测 ----------------
function detect(urlStr, pageText = "") {
  const info = parseUrl(urlStr);
  if (!info) {
    return { level: "未知", score: 0, reasons: ["无法解析该网址"], url: urlStr };
  }

  const findings = [];
  let domainScore = 0;

  // 1. IP 直连
  if (info.isIp) {
    findings.push("网站使用IP地址直接访问，正规高校官网不会这样做");
    domainScore += WEIGHTS.domain_ip_direct;
  }

  // 2. 形近仿冒（与官方域名比对）
  const rdMain = info.registeredDomain.split(".")[0].toLowerCase();
  for (const [official, name] of Object.entries(OFFICIAL_DOMAINS)) {
    if (info.registeredDomain === official) continue;
    // 2a. 官方域名被整体拼接进子域名：mku.edu.cn.evil.com / mku.edu.cn.login-verify.top
    // 官方自身及其正常子域（www.mku.edu.cn）不算
    const legitSub = info.host === official || info.host.endsWith("." + official);
    if (!legitSub && (info.host.startsWith(official + ".") || info.host.includes("." + official + "."))) {
      findings.push(`官方域名「${official}」被拼接进子域名（${info.host}），属于典型仿冒手法`);
      domainScore += WEIGHTS.domain_visual_similar;
      continue;
    }
    const offMain = official.split(".")[0].toLowerCase();
    if (!offMain) continue;
    const sim = similarityScore(rdMain, offMain);
    if (sim >= SIMILAR_THRESHOLD) {
      findings.push(`与${name}官方域名「${official}」主名相似度 ${sim.toFixed(0)}/100，疑似形近仿冒`);
      domainScore += WEIGHTS.domain_visual_similar;
      continue;
    }
    // 蹭名：mku-verify.xyz
    if (rdMain.startsWith(offMain) && rdMain !== offMain
        && rdMain.length > offMain.length
        && "-_".includes(rdMain[offMain.length])) {
      findings.push(`以官方名「${offMain}」开头并附加单词，疑似蹭名仿冒`);
      domainScore += WEIGHTS.domain_homograph;
    }
  }

  // 3. 子域名异常
  if (info.subdomain) {
    const subParts = info.subdomain.split(".");
    if (subParts.length >= 3) {
      findings.push(`子域名层级过多（${subParts.length}层），异常网站常用多层伪装`);
      domainScore += WEIGHTS.domain_many_subdomains;
    }
    for (const part of subParts) {
      const tokens = tokenizeLabel(part);
      const hit = tokens.find(t => SUSPICIOUS_SUBDOMAINS.includes(t));
      if (hit) {
        findings.push(`子域名含可疑关键词「${hit}」，钓鱼网站常伪装登录/验证入口`);
        domainScore += WEIGHTS.domain_suspicious_subdomain;
        break;
      }
    }
  }

  // 4. 可疑 TLD
  if (SUSPICIOUS_TLDS.includes(info.suffix)) {
    findings.push(`域名后缀「.${info.suffix}」为免费/低价注册后缀，钓鱼网站高发区`);
    domainScore += WEIGHTS.domain_suspicious_tld;
  }

  // 5. 页面内容检测（如果有 pageText）
  let contentScore = 0;
  if (pageText) {
    const lower = pageText.toLowerCase();
    for (const kw of SENSITIVE_FIELDS) {
      if (lower.includes(kw.toLowerCase())) {
        findings.push(`页面索要「${kw}」等敏感信息`);
        contentScore += WEIGHTS.content_sensitive_field;
        break;
      }
    }
    for (const kw of CAMPUS_KEYWORDS) {
      if (pageText.includes(kw)) {
        findings.push(`页面出现校园高发钓鱼关键词「${kw}」`);
        contentScore += WEIGHTS.content_campus_keyword;
        break;
      }
    }
    for (const kw of SENSITIVE_TEXT) {
      if (pageText.includes(kw)) {
        findings.push(`出现敏感索取话术「${kw}」`);
        contentScore += WEIGHTS.content_sensitive_sentence;
        break;
      }
    }
    for (const kw of URGENT_TEXT) {
      if (pageText.includes(kw)) {
        findings.push(`出现紧急催促话术「${kw}」，钓鱼网站常用恐吓手段`);
        contentScore += WEIGHTS.content_urgent_sentence;
        break;
      }
    }
  }

  // 信任折减：官方/知名站点内容分打折
  const isOfficial = Object.keys(OFFICIAL_DOMAINS).includes(info.registeredDomain);
  const isKnownSafe = Object.keys(KNOWN_SAFE_DOMAINS).includes(info.registeredDomain);
  const isTrustedSuffix = TRUSTED_SUFFIXES.includes(info.suffix);
  if (isOfficial || isKnownSafe) {
    contentScore = Math.min(contentScore * 0.4, 25);
  } else if (isTrustedSuffix) {
    contentScore = Math.min(contentScore * 0.7, 35);
  }

  const total = Math.min(domainScore + contentScore, 100);

  let level;
  if (total <= 30) level = "安全";
  else if (total <= 65) level = "可疑";
  else level = "高危";

  if (findings.length === 0) {
    findings.push("未发现明显钓鱼风险特征");
  }

  return {
    level,
    score: total,
    domainScore: Math.min(domainScore, 100),
    contentScore: Math.round(contentScore),
    reasons: findings,
    url: urlStr,
    host: info.host,
  };
}

// ES module 导出（service worker 和 popup 共用）
export { detect, parseUrl, similarityScore };
