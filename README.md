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

A real report, unedited (Sept 25, 11am — so the last row is a partial day):

```
過去 3 天        TFT 平均 5.1h/天(取樣 6 天)

  日期          TFT     產出
  ----------------------------------------
  09-23 Wed      3.5h   commit x2
  09-24 Thu     10.5h   —   <- 期間最高
  09-25 Fri      1.2h   —
  ----------------------------------------
  合計           15.3h

你記下的下一步:
  (這一塊還沒接上 —— fetch_stated_intentions() 尚未實作)
```

---

## How it works

Three sources, each needing a different capability:

| Source | Where it comes from | Why it needs what it needs |
|---|---|---|
| Leisure hours | tactics.tools, via a Solari cloud browser | No public API, no login for public profiles. The numbers exist only in a single XHR response on a SPA. |
| Actual output | local `git log` | Commits are the one output signal that carries its own timestamp. |
| What I said I'd do | a line I type at the end of each run, saved to `notes.jsonl` | The tool writes its own input. The next run puts that line back in front of me and asks whether I did it. |

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

Loud is not enough, though. The first real failure — Solari's gateway
returning 503 on session create — surfaced only as `exhausted 2 attempts`,
because the SDK keeps the underlying error on `err.cause` instead of chaining
it. `fetch_tft_days()` now unwraps it, so a failure says *why*, not just
*that*.

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

- The output signal is `git log`, which misses work that was never committed.
  Under-counting output is a false negative in a tool whose whole value is not
  lying to you. Open question.
- Solari can record a session as rrweb replay via `launch(recording=True)`.
  Not wired up; it would make failures diagnosable after the fact.

## The third source: a note to tomorrow

At the end of each run the tool asks for one line to tomorrow's version of me,
and saves it. The next run starts by showing that line and asking one
question: *did you do it?* (y/n). The answer goes into that day's report, next
to the hours and the commits.

Three choices went into this:

- **I mark it, not the tool.** The standard is one I set myself, so the
  judgment has to be mine too. The tool can't see work that never got
  committed anyway (see above). The one who actually knows is me.
- **It asks before showing the numbers.** I answer from memory, not after the
  data has already nudged me.
- **Only the latest note gets asked about.** A skipped day just goes by. The
  tool doesn't come back to collect on it.

The first design was different: an LLM reading my study log and pulling out
"promises" from prose. I dropped it. It depended on a file I had stopped
updating, which is exactly the thing this tool is supposed to catch.
Writing the input inside the tool closes the loop: said -> did -> saw -> said.
