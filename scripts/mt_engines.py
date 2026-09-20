"""机翻后端：Bing（走 ttranslatev3，实测是 LLM 后端，质量好、保留换行与标签）+ Google 兜底。

Bing 需要先从 /translator 页面抠出 IG / IID / key / token（token 约 1 小时过期，过期自动刷新）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COOKIE = ROOT / "temp" / "bing_cookies.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
GOOGLE_API = "https://translate.googleapis.com/translate_a/single"


def _curl(args: list[str], timeout: int = 45, stdin: str | None = None) -> str:
    proc = subprocess.run(["curl", "-s", "--max-time", str(timeout), *args],
                          input=stdin, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout + 15)
    return proc.stdout or ""


class Bing:
    """Bing 翻译会话（自动刷新凭证、失败重试）。"""

    def __init__(self) -> None:
        self.ig = self.iid = self.key = self.token = ""
        self.born = 0.0
        self.refresh()

    def refresh(self) -> bool:
        COOKIE.parent.mkdir(parents=True, exist_ok=True)
        page = _curl(["-c", str(COOKIE), "-A", UA, "https://www.bing.com/translator"], timeout=30)
        ig = re.search(r'IG:"([^"]+)"', page)
        iid = re.search(r'data-iid="([^"]+)"', page)
        kt = re.search(r'params_AbusePreventionHelper\s*=\s*\[\s*(\d+)\s*,\s*"([^"]+)"', page)
        if not (ig and iid and kt):
            return False
        self.ig, self.iid = ig.group(1), iid.group(1)
        self.key, self.token = kt.group(1), kt.group(2)
        self.born = time.time()
        return True

    def translate(self, text: str, src: str = "en") -> str | None:
        if not self.token or time.time() - self.born > 2400:
            self.refresh()
        url = f"https://www.bing.com/ttranslatev3?isVertical=1&&IG={self.ig}&IID={self.iid}"
        raw = _curl(["-b", str(COOKIE), "-A", UA, "-X", "POST", url,
                     "--data-urlencode", f"fromLang={src}",
                     "--data-urlencode", f"text={text}",
                     "--data-urlencode", "to=zh-Hans",
                     "--data-urlencode", f"token={self.token}",
                     "--data-urlencode", f"key={self.key}"])
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self.refresh()          # 多半是 token 过期
            return None
        if isinstance(data, dict) and data.get("statusCode"):
            self.refresh()
            return None
        try:
            return data[0]["translations"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return None


_BING: Bing | None = None


def bing(text: str, src: str = "en") -> str | None:
    global _BING
    if _BING is None:
        _BING = Bing()
    return _BING.translate(text, src)


def google(text: str, src: str = "en") -> str | None:
    raw = _curl(["-X", "POST", "--data-urlencode", f"q={text}",
                 "--data", "client=gtx", "--data", f"sl={src}", "--data", "tl=zh-CN", "--data", "dt=t",
                 GOOGLE_API], timeout=40)
    try:
        return "".join(seg[0] for seg in (json.loads(raw)[0] or []) if seg and seg[0])
    except Exception:  # noqa: BLE001
        return None


#: 本地小模型（Ollama / LM Studio / llama.cpp 都吃 OpenAI 兼容接口）配置：
#:   data/translate/engine.json  {"local": {"base_url": "http://127.0.0.1:11434/v1",
#:                                           "model": "qwen2.5:7b", "api_key": ""}}
#: 也可以只设环境变量 LB_MT_LOCAL_URL / LB_MT_LOCAL_MODEL。零 token 成本，适合整批粗翻。
CFG = ROOT / "data" / "translate" / "engine.json"


def local_config() -> dict:
    cfg = {"base_url": os.environ.get("LB_MT_LOCAL_URL", "http://127.0.0.1:11434/v1"),
           "model": os.environ.get("LB_MT_LOCAL_MODEL", ""),
           "api_key": os.environ.get("LB_MT_LOCAL_KEY", "")}
    if CFG.is_file():
        try:
            cfg.update((json.loads(CFG.read_text(encoding="utf-8")).get("local") or {}))
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


def local(text: str, src: str = "en", timeout: int = 180) -> str | None:
    """调用本地小模型（OpenAI 兼容 /chat/completions），术语与方括号由调用方先占位保护。"""
    cfg = local_config()
    if not cfg.get("model"):
        return None
    prompt = (f"把下面的{('韩文' if src == 'ko' else '英文')}游戏文本翻译成简体中文。"
              "保留所有 <标签>、{0} 占位符、[方括号] 与换行，只输出译文本身：\n" + text)
    payload = json.dumps({"model": cfg["model"], "temperature": 0.2,
                          "messages": [{"role": "user", "content": prompt}]}, ensure_ascii=False)
    raw = _curl(["-X", "POST", f"{cfg['base_url'].rstrip('/')}/chat/completions",
                 "-H", "Content-Type: application/json",
                 "-H", f"Authorization: Bearer {cfg.get('api_key') or 'none'}",
                 "--data-binary", "@-"], timeout=timeout, stdin=payload)
    try:
        return json.loads(raw)["choices"][0]["message"]["content"].strip()
    except Exception:  # noqa: BLE001
        return None


def translate(text: str, engine: str = "bing", src: str = "en") -> str | None:
    """按引擎翻译；bing 失败时退回 google。src 为源语言（默认英语，韩文残留用 ko）。
    引擎可用环境变量 LB_MT_ENGINE 覆盖（local / google / bing）。"""
    engine = os.environ.get("LB_MT_ENGINE", engine)
    if engine == "local":
        return local(text, src)
    if engine == "google":
        return google(text, src)
    out = bing(text, src)
    if out is None:
        out = google(text, src)
    return out
