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
host event (F6), as explained in the project README.

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
| SmolLM2 135M Instruct | 18 / 41 | 16 | 3 | 57.6 ms | 71.9 ms |
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
