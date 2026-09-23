"""探測腳本 v4 — 在原始回應飛過去的當下就攔下 body。

前幾版的教訓:
  v1 只記錄 content-type 含 json 的回應 -> 把真正的端點濾掉了
  v2 放寬條件,找到端點 -> 但事後「再打一次」拿到空 list
  v4 改成在回應到達時直接讀 body,拿到的就是頁面真正收到的東西

輸出由 Python 自己寫進 out.txt(UTF-8),不經過 shell 管線,避免編碼問題。
"""

import asyncio
import json
import os

from solari_browser import Solari

PROFILE_URL = "https://tactics.tools/player/na/Majimaryou/1343"
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out.txt")

_lines = []


def log(*parts):
    line = " ".join(str(p) for p in parts)
    print(line)
    _lines.append(line)


def describe(obj, label, depth=0):
    pad = "  " * depth
    if isinstance(obj, dict):
        log(f"{pad}{label}: dict, {len(obj)} keys -> {list(obj.keys())[:20]}")
        if depth < 3:
            for k in list(obj.keys())[:8]:
                describe(obj[k], k, depth + 1)
    elif isinstance(obj, list):
        log(f"{pad}{label}: list, len={len(obj)}")
        if obj and depth < 3:
            describe(obj[0], f"{label}[0]", depth + 1)
    else:
        log(f"{pad}{label}: {type(obj).__name__} = {repr(obj)[:100]}")


async def main() -> None:
    solari = Solari(api_key=os.environ["SOLARI_API_KEY"])
    browser = await solari.launch()

    captured = []   # (url, parsed_json)
    failed = []     # (url, error)  <- 失敗一定要留痕跡,不能沉默

    try:
        page = await browser.new_page()

        async def on_response(response):
            url = response.url
            if "/player/matches/" not in url and "/player/stats2/" not in url:
                return
            try:
                captured.append((url, await response.json()))
            except Exception as err:
                failed.append((url, f"{type(err).__name__}: {err}"))

        page.on("response", on_response)

        try:
            await page.goto(PROFILE_URL, wait_until="networkidle", timeout=60000)
        except Exception as err:
            log(f"[goto 未正常完成] {type(err).__name__}: {err}")

        await asyncio.sleep(3)   # 讓還在飛的回應收完

        log("=" * 60)
        log("成功攔截:", len(captured), " / 讀取失敗:", len(failed))
        for url, err in failed:
            log("  FAIL", url[:120], "->", err)

        for url, data in captured:
            log("=" * 60)
            log("URL:", url)
            size = len(data) if isinstance(data, (list, dict)) else "?"
            log("頂層型別:", type(data).__name__, " 大小:", size)
            describe(data, "root")

        # 把第一筆非空的完整內容另存,方便細看真實欄位
        for url, data in captured:
            if data:
                raw = os.path.join(os.path.dirname(OUT_PATH), "sample.json")
                with open(raw, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                log("=" * 60)
                log("第一筆非空資料已另存 sample.json:", url)
                break
    finally:
        await browser.close()
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))


if __name__ == "__main__":
    asyncio.run(main())
