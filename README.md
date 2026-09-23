# study-monitor

A tool that puts three things on one table and then says nothing about them:
how many hours I spent on a game, what I actually produced, and what I said I
would do next.

Built with [Solari](https://getsolari.com) cloud browsers.

---

## Why

I noticed that most of what I do, I do because of how someone else will judge
it. Good or bad, right or wrong — someone else's call, and I move accordingly.
I wanted something that would let me look at myself instead: here is what you
actually did; now think; now decide.

People spend a lot of their waking life not really conscious of it. You wake up
and reach for your phone. You're bored, so you reach for your phone. You eat
without paying much attention to what you're eating. Your head is noisy all
day, and then it's evening and you cannot actually remember what you did.

<!-- 下面這句是我提的,你覺得不要就整句砍掉 -->
In my case it ran to two weeks. Between September 8th and September 22nd I made
no progress on anything I had said I would do — no commits, no study notes —
and nothing noticed. Including me.

So: the smallest possible diary. Something that tells me what I did today,
without my having had to notice at the time.

Time-tracking tools cannot do this. They know I had a browser open for six
hours. They do not know that two weeks earlier I had written down that my next
step was to find out what the browser SDK could do — so they can never put
those two facts on the same line. **"What you said you were going to do" is not
a thing any of them measure.**

---

## What it looks like

```
TODO: 貼一份真實的報告進來
```

<!-- 用 reports/ 裡任何一份。如果覺得時數太私密,可以只留日期跟相對比例,
     但我的建議是照貼 —— 真實數字是這個專案唯一的說服力來源。 -->

---

## How it works

Three sources, each needing a different capability:

| Source | Where it comes from | Why it needs what it needs |
|---|---|---|
| Leisure hours | tactics.tools, via a Solari cloud browser | No public API, no login for public profiles. The numbers exist only in a single XHR response on a SPA. |
| Actual output | local `git log` | Commits are the one output signal that carries its own timestamp. |
| Stated intentions | an LLM over my own study log | The log is prose. There is no "next step" field. Regex cannot find a promise; a model can. |

### Why a cloud browser and not a scraper

tactics.tools renders from a JSON payload fetched at `/player/stats2/...`.
Three things follow from that:

- **Parsing the DOM would have been the wrong call.** The rendered table is a
  lossy view of the payload. The payload has a per-match `duration` in seconds,
  which means the tool reports *actual playtime*, not `games x average length`.
- **The response has to be caught in flight.** Re-requesting the same URL after
  page load returns an empty list. `monitor.py` reads the body inside the
  `page.on("response", ...)` handler, as it arrives.
- **Solari gives a real browser without running one.** After `launch()` it is
  plain Playwright, so the interception code is ordinary Playwright code — but
  it runs in the cloud, on a schedule, without a browser open on my machine.

`spikes/` has the throwaway probe that established all of this, including the
two versions that were wrong. See [`spikes/README.md`](spikes/README.md).

---

## Design decisions

These are the parts that took thought rather than typing.

**The report owns its own time window.** The obvious implementation unions the
day-keys from each source. That is wrong: the table's date range would then
depend on how much I happened to play, and days where *nothing happened* would
vanish entirely — precisely the rows the tool exists to surface. So
`build_report()` generates the window itself and asks each source about those
days.

**Absence is rendered, never dropped.** A day with no output shows a dash. The
unimplemented third source prints "not wired up yet" instead of quietly
rendering a shorter report. A tool built to show you what you are not doing
must not be able to hide anything, including its own gaps.

**Every source fails loudly.** If the browser captures nothing, `fetch_tft_days()`
raises with the errors it collected. If `git log` exits non-zero, that raises
too, because "no commits" and "git is broken" look identical in an empty dict
and only one of them is true. A silent failure here would produce a clean,
reassuring, wrong report — the worst possible output for this particular tool.

**The baseline is computed over a longer span than the window.** A three-day
average compared against three days of data is the same numbers said twice.

**It does not judge.** Almost everything in this space runs on guilt or on
achievement — streaks to protect, scores to raise, a red square on a calendar.
Those work by making you *feel something about* the number instead of looking
at it, and the feeling is doing the pushing. This tool reports what happened
and stops. No streaks, no score, no "you're falling behind." The point is to
give you a chance to think and then decide for yourself — the standard is
yours, so the judgment has to be yours too.

---

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env        # then paste your Solari API key into .env
python monitor.py
```

Each run prints the report and saves a copy to `reports/`. That history is the
data for the next comparison, so it accumulates rather than overwriting.

`reports/` and `.env` are gitignored.

---

## Not done yet

- `fetch_stated_intentions()` is a stub. The hard part is not the API call, it
  is the judgment written into the prompt: **what counts as a promise?**
  That criterion is the core of the tool, so it is being written last, not first.
- The output signal is `git log`, which misses work that was never committed.
  Under-counting output is a false negative in a tool whose whole value is not
  lying to you. Open question.
- Solari can record a session as rrweb replay via `launch(recording=True)`.
  Not wired up; it would make failures diagnosable after the fact.

## Where it goes next

Right now the tool only reads. The next version lets you write back: after it
prints the day, it asks for a line or two — what you thought, what you want
tomorrow's version of you to know. That note goes back in as input, so the next
report shows you what you told yourself yesterday, next to what you actually
did about it.

That closes the loop the third source is currently reaching for, and it makes
the loop the tool's own: said -> did -> saw -> said.
