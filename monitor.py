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
# 來源 3:你說過的下一步  —— TODO(你的部分,這個最有意思)
# ---------------------------------------------------------------------------

def fetch_stated_intentions() -> list[dict]:
    """回傳 [{"date": "09-04", "text": "看 Solari 的 browser 能力"}, ...]

    transcript.md 是散文,沒有「下一步」這個欄位,那些話散在段落裡而且
    每次寫法都不一樣。這是 LLM 的工作,不是 regex 的工作。

    要自己想的:
      1. 餵多少內容給 Claude?(整份 transcript 會太長)
      2. system prompt 怎麼寫,才會拿到穩定的 JSON?
         (你 W2 練過的東西:格式規格 + few-shot 範例 + try/except)
      3. 什麼樣的句子才算「一個承諾」?什麼不算?
         —— 這個判斷標準要寫進 prompt 裡,而且它就是這支程式的核心判斷。

    現在先回傳空 list,讓整支程式能跑起來。但 build_report 必須把
    「這一塊還沒接上」明白印出來 —— 缺席要看得見,不能靜靜地消失。
    """
    return []


# ---------------------------------------------------------------------------
# 組裝  —— TODO(你的部分。這是你設計的東西,不該由我寫)
# ---------------------------------------------------------------------------

def build_report(tft, output, intentions, days: int = WINDOW_DAYS) -> str:
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

    intentions 現在會是空的(那支還沒寫)。這種情況要在輸出裡
    明講「這一塊還沒接上」,不要當它不存在 —— 不然你會看著一份
    少了一整個區塊的報告,卻以為自己看到的是完整的。
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
    lines.append("你記下的下一步:")

    if intentions:
        for item in intentions:
            lines.append(f"  {item['date']}  「{item['text']}」")
    else:
        # 缺席要看得見
        lines.append("  (這一塊還沒接上 —— fetch_stated_intentions() 尚未實作)")

    return "\n".join(lines)


async def main() -> None:
    tft = await fetch_tft_days()
    output = fetch_output_days()
    intentions = fetch_stated_intentions()
    report = build_report(tft, output, intentions)

    print(report)

    # 每次執行都留一份。一個每三天跑一次的工具,歷次報告本身就是資料——
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
