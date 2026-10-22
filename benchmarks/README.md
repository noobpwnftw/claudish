# DGX Spark measurements

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
estimate, not a measured graphical latency. Windows previews need a subsequent
host event (F6), as explained in [docs/using.md](../docs/using.md#typing).

The 135M model often repeats input, copies the prompt example, or emits
explanations. The 500M model produced usable stylistic rewrites on these four
inputs and is the default. Neither model is fine-tuned for Claudish.

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

[`eval/cases.json`](eval/cases.json) holds 41 varied inputs: names, numbers,
dates, negation, code identifiers and URLs, questions, very short and casual
messages, multi-sentence text, already-formal text, tone, emoji, and French and
Spanish. [`evaluate.py`](evaluate.py) sends each case to a running service and
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

The aim was to make the default model add em dashes without losing meaning.
[`prompt_variants.py`](prompt_variants.py) scores the system-prompt and example
variants in [`eval/prompt-variants.json`](eval/prompt-variants.json) directly
against llama-server, using the same cases and checks. Results for Qwen2.5 0.5B
on the Spark:

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

On the shipped default model's 41 rewrites, the judge finds **26 meaning-
preserving**, against 38 that pass the mechanical checks. The hand labels give
27. The mechanical score overstates fidelity by about a third.

```sh
llama-server -m models/Qwen2.5-14B-Instruct-Q4_K_M.gguf --port 18766 -ngl 99
python benchmarks/judge.py --calibrate
python benchmarks/judge.py --results benchmarks/eval/spark-small.json
```
