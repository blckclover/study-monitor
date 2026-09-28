"""study-monitor — 把「休閒時數」「實際產出」「你自己說過的下一步」擺在一起。

設計原則(不要改掉這條):
    只呈現事實,不下判斷。
    智慧在「挑哪些事實、怎麼並置」,不在「說出結論」。
    結論由讀的人自己得出。

三個來源各自需要不同的能力:
    TFT 時數   -> Solari browser(沒有公開 API,只能開瀏覽器)
    實際產出   -> 本機 git / 檔案系統
    說過的下一步 -> LLM(從散文裡抽出結構,regex 做不到)
"""

import asyncio
import datetime
import json
import os
import subprocess
import zoneinfo

from solari_browser import Solari, SolariError

# 從 .env 讀金鑰,不要每次開新終端機都手動設 —— 手動貼來貼去,
# 遲早有一次會貼到不該貼的地方。.env 已經在 .gitignore 裡。
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # 沒裝就退回系統環境變數,但要講出來 —— 靜默降級會讓你以為
    # .env 有生效,然後對著一個「明明設了卻讀不到」的錯誤查半天。
    print("[提示] 未安裝 python-dotenv,改用系統環境變數。要用 .env:pip install python-dotenv")

TZ = zoneinfo.ZoneInfo("America/Los_Angeles")
PROFILE_URL = "https://tactics.tools/player/na/Majimaryou/1343"

# 報告顯示的天數。三天是刻意的:實際觀察到的斷檔是 4 天,
# 三天的窗口會在斷檔還在發生的時候觸發,而不是事後才報。
WINDOW_DAYS = 3

# 平均值要用比較長的區間算 —— 三天算不出有意義的基準。
BASELINE_DAYS = 14


# ---------------------------------------------------------------------------
# 來源 1:TFT 時數  —— 已驗證可用,直接沿用 spike 的做法
# ---------------------------------------------------------------------------

async def fetch_tft_days() -> dict[str, dict]:
    """回傳 {"09-07 Mon": {"games": 14, "hours": 8.6}, ...}

    做法:開 Solari 的雲端瀏覽器載入個人頁,在 stats2 這支 API 的回應
    飛過去的當下把 body 攔下來。不事後重打——重打會拿到空 list。
    """
    solari = Solari(api_key=os.environ["SOLARI_API_KEY"])

    # SDK 把真正的原因塞在 err.cause / err.status 裡,不會出現在 traceback 上。
    # 只印「exhausted 2 attempts」等於只說了「壞了」,沒說「為什麼壞」——
    # 大聲失敗還不夠,失敗要帶著原因。
    try:
        browser = await solari.launch()
    except SolariError as err:
        await solari.close()
        raise RuntimeError(
            f"開不了 Solari 瀏覽器:{err}\n"
            f"  HTTP status:{err.status}\n"
            f"  gateway code:{err.code}\n"
            f"  底層原因:{err.cause!r}"
        ) from err

    payload = None
    errors = []

    try:
        page = await browser.new_page()

        async def on_response(response):
            nonlocal payload
            if "/player/stats2/" not in response.url:
                return
            try:
                payload = await response.json()
            except Exception as err:
                errors.append(f"{type(err).__name__}: {err}")

        page.on("response", on_response)

        try:
            await page.goto(PROFILE_URL, wait_until="networkidle", timeout=60000)
        except Exception as err:
            errors.append(f"goto: {type(err).__name__}: {err}")

        await asyncio.sleep(3)  # 讓還在飛的回應收完
    finally:
        await browser.close()
        # browser.close() 只釋放雲端那個 session。本機還有一個 patchright driver
        # 子行程,要 solari.close() 才會停 —— 沒停的話,Python 結束時會噴一串
        # "unclosed transport / I/O operation on closed pipe"。
        await solari.close()

    # 失敗要留痕跡,不能沉默地回傳空的 —— 沉默的失敗比看得見的失敗危險
    if payload is None:
        raise RuntimeError(f"沒有攔到 stats2 的回應。過程中的錯誤:{errors or '無'}")

    days: dict[str, dict] = {}
    for match in payload.get("matches", []):
        when = datetime.datetime.fromtimestamp(match["dateTime"] / 1000, TZ)
        key = when.strftime("%m-%d %a")
        day = days.setdefault(key, {"games": 0, "hours": 0.0})
        day["games"] += 1
        day["hours"] += match["duration"] / 3600
    return days


# ---------------------------------------------------------------------------
# 來源 2:實際產出  —— TODO(你的部分)
# ---------------------------------------------------------------------------

def fetch_output_days(days: int = WINDOW_DAYS) -> dict[str, int]:
    """回傳 {"09-08 Tue": 2, ...} —— 每天的 commit 數。

    沒有 commit 的日子不會出現在 dict 裡(不是 0,是根本沒有 key)。
    這是刻意的:呈現時「那天沒有任何產出」跟「那天有 0 個 commit 但做了別的事」
    是兩件不同的事,交給 build_report 決定怎麼顯示。
    """
    repo = os.path.dirname(os.path.abspath(__file__))

    result = subprocess.run(
        [
            "git", "log",
            f"--since={days} days ago",
            "--date=format:%m-%d %a",
            "--pretty=format:%ad",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    # 失敗要炸,不要回傳空的 dict —— 「沒有 commit」跟「git 掛了」
    # 長得一模一樣,而後者靜默過去的話你永遠不會發現報告是錯的。
    if result.returncode != 0:
        raise RuntimeError(f"git log 失敗(returncode={result.returncode}):{result.stderr.strip()}")

    counts: dict[str, int] = {}
    for line in result.stdout.splitlines():
        key = line.strip()
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# 來源 3:你寫給自己的話
# ---------------------------------------------------------------------------
# 9/28 的設計決定:
#   - 不從 transcript.md 用 LLM 猜承諾。改成工具自己產生自己的輸入:
#     每天看完報告寫一句話給明天,明天的報告把它擺回你面前。
#   - 「做了沒」由你自己標,不是工具判斷。標準是你訂的,判斷也是你的。
#   - 只問最新一筆。跳過的日子就讓它過去,不追討。

NOTES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.jsonl")


def load_notes() -> list[dict]:
    """讀出所有筆記,一行一筆 JSON。

    檔案不存在 = 還沒寫過任何一筆,這是正常狀態,回傳空 list。
    但某一行壞掉的話會直接炸 —— 那是真的出錯了,不能靜靜跳過。
    """
    if not os.path.exists(NOTES_PATH):
        return []
    notes = []
    with open(NOTES_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                notes.append(json.loads(line))
    return notes


def save_notes(notes: list[dict]) -> None:
    with open(NOTES_PATH, "w", encoding="utf-8") as f:
        for n in notes:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")


def ask_about_latest(notes: list[dict]) -> dict | None:
    """問最新那一筆「做了嗎?」,回傳那一筆(沒有任何筆記就回傳 None)。

    不問的情況:
      - 已經回答過了(done 不是 None)
      - 那一筆是今天才寫的 —— 一天跑兩次的話,不該問你一小時前寫的東西
    """
    if not notes:
        return None
    latest = notes[-1]
    today = datetime.datetime.now(TZ).strftime("%Y-%m-%d")
    if latest["done"] is None and latest["date"] != today:
        while True:
            ans = input(f"{latest['date'][5:]} 你寫了:「{latest['note']}」—— 做了嗎?(y/n) ").strip().lower()
            if ans in ("y", "n"):
                latest["done"] = (ans == "y")
                save_notes(notes)
                break
            print("  請輸入 y 或 n")
    return latest


def write_note_for_tomorrow(notes: list[dict]) -> str:
    """問一句給明天的話,存起來,回傳那句話(直接 Enter 就是空字串)。"""
    text = input("寫一句話給明天的自己(直接 Enter 跳過):").strip()
    if text:
        today = datetime.datetime.now(TZ).strftime("%Y-%m-%d")
        notes.append({"date": today, "note": text, "done": None})
        save_notes(notes)
    return text


# ---------------------------------------------------------------------------
# 組裝  —— TODO(你的部分。這是你設計的東西,不該由我寫)
# ---------------------------------------------------------------------------

def build_report(tft, output, latest_note, days: int = WINDOW_DAYS) -> str:
    """把三個來源併成那張表。

    9/10 定案的形狀:

        過去 N 天                    平均 TFT x.xh/天

        日期        TFT     產出
        09-07 Mon   8.6h    —          <- 最高的那天要標出來
        09-08 Tue   3.8h    spike 探測
                            合計 xx.xh

        你記下的下一步:
          09-04  「...」   -> 完成 / 未完成

    三件事要記得(這是它跟一張光禿禿的表的差別):
      1. 兩條軸要在同一張表裡,不是一個在表裡一個在旁邊
      2. 要有比較基準(平均、最高值),不然單一數字沒有資訊量
      3. 「你自己說過的話」要出現 —— 標準是你訂的,不是這支程式訂的

    latest_note 是 None 的時候(還沒寫過任何一筆),要在輸出裡明講,
    不要讓整個區塊消失 —— 缺席要看得見。
    """
    # 窗口由這裡產生,不是由來源決定。
    # 原因:兩個來源涵蓋的範圍本來就不一樣(TFT 是最近 50 場,
    # 可能橫跨六天;git 是最近三天),如果讓來源各自決定要顯示哪幾天,
    # 這張表的列就會取決於「哪個來源剛好有資料」,而不是取決於
    # 「我想看哪幾天」。報告要決定自己的骨架。
    today = datetime.datetime.now(TZ).date()
    window = [today - datetime.timedelta(days=i) for i in range(days - 1, -1, -1)]
    keys = [d.strftime("%m-%d %a") for d in window]

    # 基準用 TFT 樣本裡「所有」的天來算,不是只用窗口內這三天 ——
    # 三天算出來的平均沒有比較的意義,那只是把同一批數字再說一次。
    sampled = [v["hours"] for v in tft.values()]
    avg = sum(sampled) / len(sampled) if sampled else 0.0

    window_hours = [tft.get(k, {}).get("hours", 0.0) for k in keys]
    total = sum(window_hours)
    peak = max(window_hours) if window_hours else 0.0

    lines = [
        f"過去 {days} 天        TFT 平均 {avg:.1f}h/天(取樣 {len(sampled)} 天)",
        "",
        "  日期          TFT     產出",
        "  " + "-" * 40,
    ]

    for key in keys:
        hours = tft.get(key, {}).get("hours", 0.0)
        commits = output.get(key)

        hours_text = f"{hours:.1f}h" if hours else "—"
        out_text = f"commit x{commits}" if commits else "—"
        mark = "   <- 期間最高" if hours and hours == peak else ""

        lines.append(f"  {key:<12}  {hours_text:>5}   {out_text}{mark}")

    lines.append("  " + "-" * 40)
    lines.append(f"  {'合計':<11}  {total:>4.1f}h")
    lines.append("")
    lines.append("你上次寫給自己的話:")

    if latest_note is None:
        # 缺席要看得見
        lines.append("  (還沒有任何一筆 —— 今天看完報告,寫下第一句)")
    else:
        status = {True: "做了", False: "沒做", None: "還沒問"}[latest_note["done"]]
        lines.append(f"  {latest_note['date'][5:]}  「{latest_note['note']}」   -> {status}")

    return "\n".join(lines)


async def main() -> None:
    # 順序是 9/28 你自己定的:
    # 1. 先問上次那句「做了嗎」—— 在看到今天的數字之前,用記憶回答,
    #    而且答案要出現在今天這份報告裡,所以一定在組報告之前。
    notes = load_notes()
    latest = ask_about_latest(notes)

    # 2. 抓資料、組報告
    tft = await fetch_tft_days()
    output = fetch_output_days()
    report = build_report(tft, output, latest)

    # 3. 先印出來 —— 看完才寫得出給明天的話
    print(report)
    print()
    note = write_note_for_tomorrow(notes)
    if note:
        report += f"\n\n給明天的話:\n  「{note}」"

    # 4. 最後才存檔 —— 這樣每一份都是「當天的數字 + 你寫的那句話」,一天一篇。
    # 每次執行都留一份。歷次報告本身就是資料——
    # 之後想看「這個月跟上個月比」的時候,靠的就是這堆檔案。
    # (reports/ 已加進 .gitignore:裡面是你的實際時數,不該進公開 repo。
    #  要放進 README 的話,自己挑一份貼過去。)
    reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    os.makedirs(reports_dir, exist_ok=True)

    stamp = datetime.datetime.now(TZ).strftime("%Y-%m-%d_%H%M")
    path = os.path.join(reports_dir, f"{stamp}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report + "\n")

    print(f"\n(已存檔:reports/{stamp}.txt)")


if __name__ == "__main__":
    asyncio.run(main())
