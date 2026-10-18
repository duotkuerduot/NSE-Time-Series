# Results

The results of the latest `uv run nsefc run` on the full dataset (2 January 2007 to 30 June
2026), default profile. Every run writes the same tables to `data/reports/evaluation.md` and
`data/reports/evaluation.json`, and `uv run nsefc dev update-readme` copies the summary into
the README. [methodology.md](methodology.md) explains every term used here.

## The finding

**The champion is the no-change guess.** No model beat it by the margins the gates set in
advance, so the framework correctly refused to ship models that did not beat a strong
baseline.

LightGBM came closest. In the selection period its average miss was 1.269% of the price,
against 1.271% for the no-change guess: a skill of +0.14%, with a Diebold–Mariano p of 0.069.
On the holdout its skill was +0.59% (p = 0.005). It passed five gates and failed two:

| Gate | Result | Detail |
| --- | --- | --- |
| G-INT, integrity checks | Passed | Model file hash verified; reloading reproduces its predictions within 1e-9 |
| G-SKILL, beats the no-change guess | **Failed** | Skill +0.14%, needs at least 1%; DM p = 0.069, needs below 0.05 |
| G-BASE, beats the simple baselines | Passed | Beats the AR(1) baseline (p < 0.001) |
| G-STAB, stable from year to year | **Failed** | Positive in 2 of the 5 selection years, needs 4; worst year −0.40% |
| G-DIR, direction no worse than simple rules | Passed | Better than the best trivial sign rule, on 2,742 calls |
| G-CAL, 80% range is calibrated | Passed | The range contained the actual close 80.0% of the time, needs 75% to 85% |
| G-HOLD, confirmed on the holdout period | Passed | Holdout skill +0.59%, against +0.14% in selection |

Even the AR(1) baseline, which captures the carry-over that average-price closes and thin
trading create, missed by slightly more than the no-change guess in both periods.

## The run

| Item | Value |
| --- | --- |
| Data | 4,682 held sessions from 2 January 2007 to 30 June 2026; 92 securities, 75 of them ordinary shares |
| Profile | Default: frozen hyperparameters, refits every quarter (37 refits) |
| Models | No-change guess, drift, 5-session average and AR(1) baselines; Ridge, Huber and LightGBM |
| Selection period | 1 January 2018 to 31 December 2022: 21,081 forecasts over 1,038 sessions |
| Holdout | 1 January 2023 to 29 June 2026, the last day whose next close is known: 11,250 forecasts |
| Forecast universe | 16 to 31 stocks at the refit dates (median 20); 33 at the last session |
| Rows | Of 45,974 universe rows in the walk-forward span, the gap guard excluded 12,234 (a missing session or an event in the 60-session window) and 150 had no label |
| Forecast | 32 forecasts for Wednesday 1 July 2026; one universe stock (WTK) has none because of a recent large move |

## Every model

Selection period unless stated. Average miss is the mean absolute error as a share of the
last close.

| Model | Average miss | Skill | DM p | 80% range coverage | Range width | Holdout skill | Gates failed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| No-change guess | 1.271% | +0.00% | 1.000 | 79.9% | 4.33% | +0.00% | reference |
| Drift baseline | 1.287% | −1.26% | 1.000 | 80.0% | 4.33% | −1.13% | G-SKILL, G-BASE, G-STAB, G-HOLD |
| 5-session average baseline | 1.957% | −53.97% | 1.000 | 80.0% | 6.12% | −54.94% | G-SKILL, G-BASE, G-STAB, G-DIR, G-HOLD |
| AR(1) baseline | 1.275% | −0.37% | 0.998 | 80.0% | 4.32% | −0.03% | G-SKILL, G-STAB, G-HOLD |
| Ridge regression | 1.305% | −2.70% | 1.000 | 80.0% | 4.34% | −1.26% | G-SKILL, G-BASE, G-STAB, G-HOLD |
| Huber regression | 1.288% | −1.33% | 1.000 | 80.0% | 4.30% | −0.19% | G-SKILL, G-BASE, G-STAB, G-HOLD |
| LightGBM | 1.269% | +0.14% | 0.069 | 80.0% | 4.32% | +0.59% | G-SKILL, G-STAB |

## Skill by year

Skill against the no-change guess. 2018 to 2022 is the selection period, 2023 to 2026 the
holdout.

| Model | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Drift baseline | −2.1% | −0.9% | −0.2% | −1.8% | −0.8% | −0.9% | −0.6% | −0.9% | −3.0% |
| 5-session average baseline | −60.7% | −48.3% | −60.0% | −49.6% | −50.4% | −53.1% | −53.1% | −58.1% | −52.8% |
| AR(1) baseline | −0.2% | −0.0% | +0.2% | −0.8% | −1.0% | +0.3% | −0.2% | +0.1% | −0.4% |
| Ridge regression | −4.4% | −2.2% | +0.3% | −3.9% | −1.8% | −3.6% | −1.4% | +0.0% | −1.2% |
| Huber regression | −2.6% | −0.9% | +1.0% | −2.2% | −0.9% | −1.5% | −0.4% | +0.6% | −0.2% |
| LightGBM | −0.0% | +0.1% | +1.4% | −0.4% | −0.0% | +0.0% | −0.3% | +1.2% | +1.3% |

## Ranges

The 80% expected ranges are calibrated for every model: selection coverage is between 79.9%
and 80.0%, and the no-change guess's range, the one the app shows, contained the actual close
80.3% of the time on the holdout. Its average width is 4.33% of the price in the selection
period and 4.13% on the holdout.

## Plausibility tripwire

Not triggered. The highest skill of any model in either period was +0.59%, far below the 15%
limit, and every model's directional calls stayed below the 65% limit.

## What this means

On daily NSE closes, past prices, volumes and the market add at most a fraction of a percent
over assuming the price will not change, and not consistently from year to year. LightGBM's
holdout result is statistically significant but smaller than the 1% the gates require, and it
was negative or flat in three of the five selection years. A tool that showed LightGBM's
forecasts as an improvement would be overstating them, so the app shows the no-change guess,
its calibrated 80% range and the full gate table instead.

## Reproducing

With the dataset files in `data/source/` ([data/README.md](../data/README.md)):

```bash
uv run nsefc run --no-serve
uv run nsefc status
```

The run takes a few minutes on a laptop and writes these tables to
`data/reports/evaluation.md`. The same data, settings and code give the same numbers on any
machine.
