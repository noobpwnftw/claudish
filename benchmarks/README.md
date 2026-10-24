# Model measurements

The current model comparison is [Choosing the models (G53, 2026-10-24)](#choosing-the-models-g53-2026-10-24).
The early latency measurements below describe the older models and UI at the time of those runs.

## Current choices

The [G53 study](#choosing-the-models-g53-2026-10-24) compares 14 candidates for rewrite and
continue, calibrates its judge, and measures native CPU and browser latency. The choices serve
different constraints:

| Use | Choice | Recorded basis |
| --- | --- | --- |
| Native input method | The user's configured model; none bundled | No sub-1B candidate met the slop quality bar |
| Local setup | Gemma 4 E4B | 38/41 rewrite cases and 43/47 continue cases; 4.9 GB |
| Browser demo | Qwen2.5 0.5B | Browser-compatible size with 0.47/0.44 s rewrite/continue and 13 s loading |

The browser choice was made among models that fit and run practically there: Qwen2.5 1.5B took
26 s to load, Qwen3.5 2B took 6.2/4.6 s per rewrite/continue, and Gemma 4 E2B was too large for
wllama. Keep this measured tradeoff when reviewing the demo; the native quality table alone
does not select a browser model. These timings come from one GB10; see the study's conditions
and limitations below.

## Early DGX Spark measurements

Measured on 22 October 2026 on NVIDIA GB10, CUDA driver 580.178.04, CUDA toolkit
13.0, Linux aarch64. llama.cpp commit
`0693dbfb915f33233818373b5f6969396658d02c`, compiled for CUDA architecture 121.
All model layers requested on GPU; one slot, 2048-token context, 4 CPU threads,
temperature 0, 64 output-token cap, persistent model, prompt cache enabled.

| Model / Q4_K_M | Download bytes | Warm median | Warm p95 | Finished requests |
| --- | ---: | ---: | ---: | ---: |
| SmolLM2 135M Instruct | 105,454,144 | 61.8 ms | 189.8 ms | 9 / 12 |
| Qwen2.5 0.5B Instruct | 491,400,032 | 64.8 ms | 85.3 ms | 12 / 12 |

Download byte counts are checked against the local files. Raw samples and model
outputs are in [spark-tiny.json](spark-tiny.json) and [spark-small.json](spark-small.json).
Each run cycles through four short phrases three times, after one excluded
warmup request. These are small exploratory measurements with highly reusable
prompt prefixes, not a general performance benchmark or quality evaluation.
"Finished" means no HTTP/token-budget error, not that meaning was preserved.
Tiny-model latency includes failed responses.

Wall time includes Python client → Claudish service → llama-server → client.
It excludes model startup, the adapter's 180 ms debounce, and UI delivery.
Linux UI polling adds up to 40 ms. Thus the measured small-model median implies
roughly 245–285 ms after the last keystroke for an idle short phrase; that is an
estimate, not a measured graphical latency. At the time of those runs, Windows previews needed
a subsequent host event. The current patched PIME delivers answers as they arrive;
see [typing](../docs/using.md#typing).

The 135M model often repeats input, copies the prompt example, or emits
explanations. The 500M model produced usable stylistic rewrites on these four
inputs and was the default then. Neither model is fine-tuned for Claudish.

Weight SHA-256:

```text
bda484992f9655d22504b14e57985257fa6a86937c61f957cf99c10a3bcae169  SmolLM2-135M-Instruct-Q4_K_M.gguf
74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db  qwen2.5-0.5b-instruct-q4_k_m.gguf
```

Reproduce with `python scripts/start.py --preset small`, then
`python -m claudish bench --runs 12`. Stop the launcher before changing presets.
Original model sources: [SmolLM2](https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct),
[Qwen GGUF](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF), and
[SmolLM2 GGUF](https://huggingface.co/lmstudio-community/SmolLM2-135M-Instruct-GGUF).

## Rewrite fidelity evaluation

The runs in this section used the 41 cases [`eval/cases.json`](eval/cases.json) held then:
names, numbers, dates, negation, code identifiers and URLs, questions, very short and casual
messages, multi-sentence text, already-formal text, tone, emoji, and French and Spanish. It now
holds 80 English cases (G53, below). [`evaluate.py`](evaluate.py) sends each case to a running service and
applies mechanical checks:

- required names, numbers, and identifiers are kept;
- no number is invented, whether written as digits or as words;
- negation is preserved;
- the language is kept;
- no chat preamble or added quotes;
- the length stays sane.

Style is reported separately as "changed" and "added an em dash".

```sh
python scripts/start.py --preset small
python benchmarks/evaluate.py --label small --output benchmarks/eval/spark-small.json
```

Results on the Spark, with the hardware and llama.cpp commit above, after one
excluded warmup request and with one request per case. Wall time includes both
HTTP hops:

| Model / Q4_K_M | Pass checks | Pass and changed | Added em dash | Median | p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| SmolLM2 135M Instruct | 17 / 41 | 15 | 3 | 57.6 ms | 71.9 ms |
| Qwen2.5 0.5B Instruct | 38 / 41 | 34 | 0 | 70.0 ms | 89.8 ms |

Full outputs: [eval/spark-small.json](eval/spark-small.json) and
[eval/spark-tiny.json](eval/spark-tiny.json).

These checks set an upper bound on fidelity, not a quality score. They do not
catch meaning changes that keep the guarded tokens. Reading the 38 passing
Qwen outputs by hand found at least four such changes:

- "Thanks!" became "You're welcome!";
- "Set MAX_RETRIES to 5" became "Increase…";
- "Tell Priya…" became a message addressed to Priya;
- "Do not merge this yet" lost its object.

Qwen also translated both non-English inputs into English and spelled out "3 of
the 40" as words. It never added an em dash, so the house style is not landing
yet. SmolLM2 usually drops names and numbers or copies the prompt's example
sentence, and its three em dashes come from that copied example. Greedy
decoding makes the outputs repeatable for a given model, prompt, and llama.cpp
build.

## Prompt experiments (G11)

The aim was to make the default model of the time, Qwen2.5 0.5B, add em dashes without losing meaning.
Each variant is a templates file, [`eval/templates/g11-*.json`](eval/templates/),
run through the service (`claudish serve --templates FILE`) and scored by
`evaluate.py` with the same cases and checks. Results for Qwen2.5 0.5B on the
Spark (41 cases, before the evaluation became English only):

| Variant | Pass checks | Added em dash | Failure seen on reading the outputs |
| --- | ---: | ---: | --- |
| baseline (shipped) | 38 / 41 | 0 | a few replies and meaning shifts (see above) |
| speaker / speaker4 | 38–39 / 41 | 26–31 | not graded by hand |
| terse-system | 41 / 41 | 30 | adds claims: "$2.5 million—thank you for your generous support", "14 minutes—please proceed with caution"; Spanish leaks into French |
| restate (± framing) | 38 / 41 | 20–28 | copies its example's "—yet again" everywhere: "We raised $2.5 million—yet again" |
| varied (± framing) | 35 / 41 | 26–27 | garbles restated facts: "14 minutes—ten minutes", "3 out of 40—three out of four" |

At this size, pressure toward em dashes makes the model attach a clause. That
clause either adds a claim or restates a fact wrongly. A 41/41 score on the
checks hid the worst variant, terse-system. The shipped prompt is unchanged.
Framing the input as quoted text stopped one question from being answered
instead of rewritten. No variant stopped "Thanks!" becoming "You're welcome!".

The same experiments with Qwen2.5 1.5B Instruct Q4_K_M (1,117,320,736 bytes, SHA-256
`6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`, upstream
revision `91cad511`), on the same hardware and settings:

| Variant | Pass checks | Added em dash | Median | p95 |
| --- | ---: | ---: | ---: | ---: |
| baseline | 32 / 41 | 3 | 100 ms | 147 ms |
| terse-system | 39 / 41 | 15 | 93 ms | 140 ms |
| restate-framed | 38 / 41 | 10 | 91 ms | 120 ms |

With terse-system, 1.5B adds milder clauses than 0.5B does. They still invent
some claims ("14 minutes—quite a short time, isn't it?", "No one reviewed the
change—this needs addressing"), and "back in 20" became "meet back at 20".
"Thanks!" still becomes "You're welcome!". Paired with the shipped prompt, it
scores below 0.5B. It is not proposed as a preset.

## Meaning judge (G12)

The mechanical checks miss meaning changes, so [`judge.py`](judge.py) asks a much
larger local model whether each rewrite keeps its meaning. Its verdicts are
same, adds, reply, changed, or language, constrained to a JSON schema. The model
was calibrated against 82 hand-labelled pairs in
[`eval/judge_labels.json`](eval/judge_labels.json): the shipped prompt's 41
outputs and the G11 terse-system variant's 41, labelled by the maintainer.

Judge: Qwen2.5 14B Instruct Q4_K_M (bartowski GGUF, revision `05244aa5`,
8,988,110,976 bytes, SHA-256
`e47ad95dad6ff848b431053b375adb5d39321290ea2c638682577dafca87c008`), on the
Spark, temperature 0.

| Run | Same vs. not same | Exact label | Time |
| --- | ---: | ---: | ---: |
| First prompt | 89.0% | 76.8% | 162 s |
| Plus a "check the language first" rule | **91.5%** | 76.8% | 153 s |

Full output: [eval/judge-calibration-qwen2.5-14b.json](eval/judge-calibration-qwen2.5-14b.json).
The prompt was revised once, on the same set it is scored on, so expect a little
optimism. Exact-label misses are mostly changed versus adds, which does not
matter for flagging. The judge still calls some language switches "same"; the
mechanical language check covers those. It is also stricter than the labels in
places: it flagged "Shipped it" becoming "It was delivered", arguably correctly.

On Qwen2.5 0.5B's 41 rewrites (the default then), the judge finds **26 meaning-
preserving**, against 38 that pass the mechanical checks. The hand labels give
27. The mechanical score overstates fidelity by about a third.

```sh
llama-server -m models/Qwen2.5-14B-Instruct-Q4_K_M.gguf --port 18766 -ngl 99
python benchmarks/judge.py --calibrate
python benchmarks/judge.py --results benchmarks/eval/spark-small.json
```

## Choosing the models (G53, 2026-10-24)

The question: which model makes cd_AI's default tone, full corporate slop that keeps the
message, and which autocompletes. English only (cd_AI is the English input method).

**Method.** 14 candidates, each through the real service with the slop templates
([`eval/templates/g53-slop.json`](eval/templates/g53-slop.json)): 13 local GGUFs on llama-server
(Q4, thinking off) and Claude Haiku through the `claude` CLI. Cases: 80 rewrites
([`eval/cases.json`](eval/cases.json)) and 86 unfinished sentences
([`eval/continue_cases.json`](eval/continue_cases.json)). A case passes when it passes the
mechanical checks (`evaluate.py --slop`: names, numbers, negation, no preamble, sane length;
`evaluate_continue.py --slop`: something offered, a clean join, no talk about the task, no
invented pronoun where a case names ones to avoid) and the judge passes it. The judge is Gemma 4 26B, chosen by agreement with hand
labels: rewrite 92% on pass or fail (82 labels), continue 86% (110), slop 90% (110,
[`eval/slop_labels.json`](eval/slop_labels.json)); Qwen2.5-14B reached 60% on slop and Qwen3-30B
76% on continue. Cases split in halves by a hash of their id; the table reports the test half.
Every output and verdict: [`eval/g53-slop-results.json`](eval/g53-slop-results.json).

Rewrite, in the slop tone (test half, 41 cases; latency on the GB10 GPU):

| Model | Size | Pass | 95% interval | Median |
| --- | ---: | ---: | ---: | ---: |
| Gemma 4 26B-A4B | 14 GB | 39/41 (95%) | 84–99% | 0.70 s |
| Gemma 4 E4B | 4.9 GB | 38/41 (93%) | 81–97% | 0.59 s |
| Gemma 4 12B | 6.5 GB | 38/41 (93%) | 81–97% | 1.28 s |
| Qwen3-30B-A3B | 18 GB | 34/41 (83%) | 69–91% | 1.01 s |
| Claude Haiku (CLI) | hosted | 33/41 (80%) | 66–90% | 2.9 s |
| Gemma 4 E2B | 3.2 GB | 25/41 (61%) | 46–74% | 0.34 s |
| Qwen3.5-2B | 1.2 GB | 18/41 (44%) | 30–59% | 0.39 s |
| Gemma 3 1B | 0.8 GB | 16/41 (39%) | 26–54% | 0.21 s |
| LFM2.5-1.2B | 0.7 GB | 10/41 (24%) | 14–39% | 0.17 s |
| Qwen3.5-0.8B | 0.5 GB | 7/41 (17%) | 9–31% | 0.16 s |
| Gemma 3 270M, LFM2.5-350M | 0.2 GB | 3/41 (7%) | 3–19% | 0.06 s |
| Qwen2.5-1.5B | 1.1 GB | 2/41 (5%) | 1–16% | 0.15 s |
| Qwen2.5-0.5B (the old default) | 0.5 GB | 1/41 (2%) | 0–13% | 0.08 s |

Continue, in the slop tone (test half, 47 cases):

| Model | Pass | 95% interval | Median |
| --- | ---: | ---: | ---: |
| Qwen3-30B-A3B | 45/47 (96%) | 86–99% | 0.78 s |
| Gemma 4 12B | 44/47 (94%) | 83–98% | 1.03 s |
| Gemma 4 E4B | 43/47 (91%) | 80–97% | 0.39 s |
| Gemma 4 26B-A4B | 42/47 (89%) | 77–95% | 0.82 s |
| Gemma 4 E2B | 39/47 (83%) | 70–91% | 0.24 s |
| Claude Haiku (CLI) | 34/47 (72%) | 58–83% | 3.0 s |
| Qwen2.5-1.5B | 33/47 (70%) | 56–81% | 0.11 s |
| every other model | ≤ 20/47 | | |

Latency where people run it, through the service, median over 20 cases each (rewrite / continue):

| Model | CPU only, 4 threads | In the browser (wllama, 20 cores) |
| --- | ---: | ---: |
| Qwen2.5-0.5B | 0.27 / 0.23 s | 0.47 / 0.44 s (13 s to load) |
| LFM2.5-350M | 0.25 / 0.20 s | 0.45 / 0.65 s |
| Qwen2.5-1.5B | 0.91 / 0.94 s | 0.91 / 0.94 s (26 s to load) |
| Qwen3.5-2B | 1.4 / 1.5 s | 6.2 / 4.6 s |
| Gemma 4 E2B | 1.5 / 1.7 s | too large for wllama (3.3 GB) |
| Qwen3-30B-A3B | 2.1 / 3.0 s | |
| Gemma 4 E4B | 3.1 / 4.0 s | |
| Gemma 4 26B-A4B | 3.3 / 3.0 s | |

**Read with care.** The judge is a Gemma, and Gemma models lead; reading their outputs and
Haiku's side by side, the lead is real: Haiku's misses are mostly meaning flipped by its
cheerfulness ("I'm really frustrated with this bug" became "I'm truly thrilled to be circling
back on this bug"; "this release was a mess" became upbeat), which the rubric rightly fails.
Haiku ran through the CLI with its examples as a transcript, not as chat turns, and only Haiku of
the hosted models was tried. Some mechanical failures are strictness on both sides ("30s" written
"30 seconds", "3 of 40 failed" restated as "37 passed"). Every local number is one GB10, one run,
greedy decoding.

**Conclusions.** Nothing under 1B parameters makes usable slop (≤ 7%), so a small bundled model
was never going to carry the tone; shipping none and asking for a model is right. Gemma 4 E4B
(Apache-2.0, 4.9 GB) does slop as well as anything tried, frontier included, at 0.6 s on a GPU but
3–4 s on a CPU alone: the local model worth recommending to people with a GPU or Apple silicon,
in place of Qwen2.5-0.5B. For autocomplete at every pause, Gemma 4 E2B (83%, 0.24 s on a GPU) or
E4B (91%, 0.39 s). The earlier fidelity runs (the "polished, slightly verbose" tone) measured a
bar the project no longer aims at and are not reported here.
