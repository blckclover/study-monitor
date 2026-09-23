# Spikes

Throwaway probes written before the real thing, kept on purpose.

`spike_tft.py` answered one question: **can a headless cloud browser actually
get match history off tactics.tools?** The site is a SPA with no public API and
no login for public profiles, so this was the riskiest unknown in the project.

It went through four versions before it worked:

1. **v1** logged only responses whose `content-type` contained `json` — and the
   endpoint that mattered never showed up. The filter was hiding the answer.
   Lesson: while probing, capture everything first, filter afterwards.
2. **v2** widened the filter and found `/player/stats2/...`.
3. **v3** re-fetched that URL after page load and got back an empty list.
   The data is only there on the original response.
4. **v4** captures the body inside the `page.on("response", ...)` handler as it
   arrives. This is what `monitor.py` does today.

The payoff was bigger than "it works": each match record carries a `duration`
field in seconds, so the tool reports **real playtime**, not an estimate of
games x average length.
