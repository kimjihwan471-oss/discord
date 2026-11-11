#!/usr/bin/env python3
"""스푼 방송 시작 -> 디스코드 @everyone 알림 (웹훅 방식, 외부 패키지 불필요)

사용법:
  1) config.json 을 같은 폴더에 만든다 (아래 CONFIG_EXAMPLE 참고)
  2) python3 spoon_notifier.py            # 실행
     python3 spoon_notifier.py --debug    # 응답 구조 확인용 (알림 안 보냄)
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

CONFIG_EXAMPLE = {
    "webhook_url": "https://discord.com/api/webhooks/....",
    "api_base": "https://api.spooncast.net",
    "djs": ["dj닉네임1", "dj태그2", "12345678"],
    "poll_seconds": 60,
    "max_pages": 5,
    "message": "@everyone {name}님이 스푼 방송을 시작했어요! 🎙️\n{title}\n{link}",
}

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.json"
STATE_PATH = HERE / "state.json"
UA = "Mozilla/5.0 (compatible; SpoonLiveNotifier/1.0)"


def http_json(url, data=None):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def load_config():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(CONFIG_EXAMPLE, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        sys.exit("config.json 을 만들어뒀어요. 웹훅 URL과 DJ 목록을 채운 뒤 다시 실행하세요.")
    cfg = {**CONFIG_EXAMPLE, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
    # GitHub Actions 에서는 Secrets 의 WEBHOOK_URL 환경변수를 우선 사용
    cfg["webhook_url"] = os.environ.get("WEBHOOK_URL") or cfg["webhook_url"]
    cfg["_watch"] = {str(x).strip().lower() for x in cfg["djs"]}
    return cfg


def fetch_lives(cfg):
    """라이브 목록을 페이지 단위로 가져온다."""
    url = f"{cfg['api_base'].rstrip('/')}/lives/?page_size=100"
    lives = []
    for _ in range(cfg["max_pages"]):
        data = http_json(url)
        lives.extend(data.get("results", []))
        url = data.get("next")
        if not url:
            break
    return lives


def author_keys(live):
    a = live.get("author") or live.get("owner") or {}
    keys = {a.get("id"), a.get("tag"), a.get("nickname"), a.get("username")}
    return {str(k).strip().lower() for k in keys if k not in (None, "")}, a


def notify(cfg, live, author):
    name = author.get("nickname") or author.get("tag") or "DJ"
    link = f"https://www.spooncast.net/kr/live/{live.get('id')}"
    content = cfg["message"].format(
        name=name, title=live.get("title", ""), link=link
    )
    http_json(
        cfg["webhook_url"],
        {"content": content, "allowed_mentions": {"parse": ["everyone"]}},
    )
    print(f"[알림] {name} -> {link}")


def load_state():
    try:
        return set(json.loads(STATE_PATH.read_text()))
    except Exception:
        return set()


def save_state(ids):
    STATE_PATH.write_text(json.dumps(sorted(ids)))


def main():
    cfg = load_config()
    if "--debug" in sys.argv:
        lives = fetch_lives(cfg)
        print(f"라이브 {len(lives)}개 수신. 첫 항목:")
        print(json.dumps(lives[0] if lives else {}, ensure_ascii=False, indent=2))
        return

    notified = load_state()
    while True:
        try:
            current_ids = set()
            for live in fetch_lives(cfg):
                lid = str(live.get("id"))
                keys, author = author_keys(live)
                if not (keys & cfg["_watch"]):
                    continue
                current_ids.add(lid)
                if lid not in notified:
                    notified.add(lid)
                    notify(cfg, live, author)
            # 방송이 끝난 id 는 정리 (같은 DJ가 다시 켜면 새 id 라서 다시 알림)
            notified &= current_ids
            save_state(notified)
        except Exception as e:  # 네트워크 오류 등은 무시하고 재시도
            print(f"[오류] {e}")
            if "--once" in sys.argv:
                sys.exit(1)
        if "--once" in sys.argv:  # GitHub Actions: 한 번 확인하고 종료
            return
        time.sleep(cfg["poll_seconds"])


if __name__ == "__main__":
    main()
