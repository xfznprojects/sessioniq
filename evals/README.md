# Retrieval evaluation

SessionIQ's claim is that answers are grounded in the files they cite. That claim is only worth
something if retrieval actually finds the right files, so this directory measures whether it does —
and measures it against known answers rather than against a feeling.

```
python evals/run.py              # offline: lexical + metadata
python evals/run.py --vector     # adds the ChromaDB vector layer
```

Both runs write a Markdown and JSON report to `evals/results/`. The JSON is the machine-readable
form; the Markdown is what the numbers in the main README come from.

## Results

Measured 2026-09-17 over 30 labeled questions on a 17-file corpus.

| configuration | hit@1 | hit@3 | hit@5 | recall@5 | MRR | p50 | p95 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lexical + metadata | 0.733 | 0.867 | 0.900 | 0.871 | 0.806 | 1.0 ms | 1.9 ms |
| + vector (ChromaDB) | 0.767 | 0.867 | 0.900 | 0.879 | 0.822 | 322 ms | 851 ms |

Every expected file was retrieved somewhere in all 30 questions. What separates the two
configurations is how often the right file comes *first*, and what that costs in latency.

### Where retrieval is strong, and where it isn't

| question type | n | hit@1 | hit@5 | MRR |
| --- | --- | --- | --- | --- |
| key | 3 | 1.000 | 1.000 | 1.000 |
| status | 3 | 1.000 | 1.000 | 1.000 |
| tag | 4 | 1.000 | 1.000 | 1.000 |
| format | 2 | 1.000 | 1.000 | 1.000 |
| project-scoped | 2 | 1.000 | 1.000 | 1.000 |
| content | 6 | 0.833 | 1.000 | 0.917 |
| synonym-expanded | 3 | 0.333 | 1.000 | 0.556 |
| superlative | 6 | 0.167 | 0.500 | 0.336 |

Topical questions — which files are in this key, which are ready, which carry a tag, what a note
says — are answered essentially perfectly. Superlative questions are not, and that is by design
rather than by accident: *"which track is the loudest"* is a comparison, not a similarity search.
Every audio file contains the words *loud*, *track* and *bpm* about equally often, so ranking by
text overlap has no basis on which to pick a winner. It surfaces the right neighbourhood and stops
there.

That is what the tool layer is for, so this harness measures it separately.

## Computable questions (tool layer)

`evals/tool_set.py` lists seven superlative questions and the tool call that should answer each.
The harness executes the call and checks the asset it names.

**7 / 7 returned the correct asset.** Each one is an exact comparison over real numbers — the
loudest file, the slowest tempo, the brightest spectral centroid — rather than a guess about which
file sounds relevant.

Reading the two tables together is the point: retrieval finds candidates, tools compute answers.
Neither replaces the other, and a single end-to-end "accuracy" number would hide that.

## How the corpus works

The evaluation runs against the library that `scripts/seed_demo.py` generates, not against a real
one. That generator synthesizes every file in code, so the corpus is identical on every machine and
in CI, and no licensing question arises from committing it (nothing is committed — it is rebuilt
each run).

Ground truth is labeled against what the analyzers actually report, not against what the
synthesizer was asked for. These differ: `cue_draft.wav` is synthesized on D and detected in A.
Labels follow the analyzers, because the analyzers are what retrieval indexes.

The corpus lives in a temporary directory. `evals/run.py` refuses to start unless the resolved
upload root sits inside the directory it created, so it cannot purge a real library.

## What is measured

**Ranking quality** over the rank-ordered result list, at k = 1, 3, 5:

- **hit@k** — did any expected file appear in the top k
- **recall@k** — what share of the expected files appeared in the top k
- **precision@k** — what share of the top k slots held an expected file, divided by k rather than
  by the number of results returned, so configurations that return different counts stay comparable
- **MRR** — 1 / rank of the first expected file

Results the retriever scored at zero are not counted as retrieved; the retriever returns
recently-analyzed files as a fallback when nothing matches, and those are not candidate answers.

**Latency** as p50, p95 and max over 150 calls.

**Blend weights** by holding the component scores fixed and varying only the weights, so each row
isolates what the weighting contributes. Before any ablation number is trusted, the harness re-ranks
the library under the production weights and asserts the order matches what `search()` really
returns. It passes on all 30 questions; if it ever stops passing, the harness has drifted from the
code it describes and the evaluation exits non-zero.

## Limits

- **One corpus, one domain.** Thirty questions over seventeen synthesized audio, MIDI and note
  files. It is large enough to separate retrieval configurations and far too small to be a
  benchmark.
- **Synthetic audio.** The loops are tonal and rhythmic enough for librosa, but they are not real
  music, and real libraries have messier filenames and metadata.
- **Generated answers are not scored.** This measures retrieval and the tool layer. It does not
  score the wording of an answer, and it does not measure hallucination. With no model configured
  the offline engine answers deterministically, and scoring it would measure that engine rather
  than a model.
- **Vector latency is machine-dependent.** The 322 ms p50 above includes embedding the query with
  ChromaDB's default local model; repeated runs on one machine varied between roughly 320 ms and
  851 ms p95 depending on load. Read it as "hundreds of milliseconds", not as a precise figure.
- **The vector configuration is not perfectly repeatable.** Across runs its MRR moved between 0.821
  and 0.822 and its recall@5 between 0.879 and 0.887, while hit@1, hit@3 and hit@5 held steady.
  Differences that small are within noise at 30 questions — treat the vector rows as approximate.
- **The offline configuration is stable but not bit-identical across platforms.** Hit rates
  reproduced exactly on every run and on both Windows and the Linux CI runner; MRR came out 0.806
  on Windows against 0.805 on Linux, which is tie ordering rather than a behavioural difference.
- **Labels are hand-written.** They were read off a real ingestion run, and
  `tests/test_evals.py` checks that every label still names a file the corpus creates, but a
  mistaken label would quietly depress the score rather than announce itself.

## Reproducing

```
python evals/run.py --keep     # leave the generated corpus on disk for inspection
python -m pytest tests/test_evals.py
```

Regenerate the corpus and re-check the labels after changing `seed_demo.py`; the detected tempo,
key and centroid values the labels depend on are recorded at the top of `evals/golden_set.py`.
