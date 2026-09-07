# FaceTrace Benchmarks

These measurements describe the current implementation on one development machine. They are reproducible engineering measurements, not capacity claims or guarantees for other hardware and networks.

## Benchmark Environment

| Item | Value |
|---|---|
| OS | Windows 11 (10.0.26200), AMD64 |
| CPU | Intel64 Family 6 Model 140 |
| Python | 3.12.14 |
| Node.js | 24.14.0 |
| Benchmark image | `examples/demo.jpg`, 712×520, 45,301 bytes |
| MediaPipe / OpenCV / NumPy | 0.10.21 / 4.11.0.86 / 1.26.4 |
| Web3.py | 8.0.0 |
| Local EVM | Hardhat, chain ID 31337 |
| Public EVM | Ethereum Sepolia, chain ID 11155111 |

## Methodology

Run from the repository root while a local Hardhat node is available:

```bash
python benchmark.py examples/demo.jpg
```

Face operations use 2 warm-ups followed by 20 measured runs. Cryptographic and Merkle operations use 200 measured runs (candidate ranking and the combined provenance stage use 100). Local-chain figures cover 3 fresh contract deployments, attestations, and verification reads. Timings use `time.perf_counter`; the table reports arithmetic mean and interpolated p95. Raw machine-readable results are written to the ignored `output/benchmark_results.json`.

`--live` performs one image upload and one exact-match query, with one visual-match fallback only when needed. It consumes provider quota and sends the supplied image to SerpApi, so run it only with permission to disclose that image. The release run did not repeat that upload; its real provider timing comes from the already-saved search response.

## Local Component Benchmarks

| Operation | Runs | Mean | p50 | p95 |
|---|---:|---:|---:|---:|
| Image validation | 20 | 0.159 ms | 0.151 ms | 0.176 ms |
| Face detection | 20 | 31.082 ms | 30.970 ms | 31.794 ms |
| Landmark encoding | 20 | 32.019 ms | 31.866 ms | 34.146 ms |
| Full face processing | 20 | 61.468 ms | 61.023 ms | 64.824 ms |
| Candidate ranking | 100 | 4.061 ms | 3.770 ms | 4.969 ms |
| Search-response SHA-256 | 200 | 0.355 ms | 0.344 ms | 0.430 ms |
| Merkle construction | 200 | 0.810 ms | 0.754 ms | 1.144 ms |
| Verify all 10 Merkle proofs | 200 | 0.057 ms | 0.056 ms | 0.060 ms |
| Complete evidence provenance stage | 100 | 5.649 ms | 5.485 ms | 7.320 ms |

## Live Search

| Metric | Value |
|---|---:|
| Provider-reported Google Lens processing | 2.9 s |
| Returned exact matches | 400 |
| Dynamically extracted social candidates | 180 |
| Client image-upload latency | not captured |
| Client Lens round-trip latency | not captured |

These figures come from the saved real Google Lens response captured at `2026-09-07 06:16:18 UTC`. The release audit did not repeat the sensitive image upload without explicit disclosure approval. Search timing varies with network conditions, provider load, cache behavior, and index coverage.

## Blockchain

| Metric | Hardhat | Sepolia |
|---|---:|---:|
| Chain ID | 31337 | 11155111 |
| Deployment gas | 224,896 | 224,896 |
| Attestation gas | 46,190 | 46,190 |
| Deployment block | per fresh run | 11,653,057 |
| Attestation block | per fresh run | 11,653,060 |
| Confirmation latency | n/a | not captured |

| Hardhat operation | Runs | Mean | p50 | p95 |
|---|---:|---:|---:|---:|
| Registry deployment | 3 | 33.023 ms | 34.397 ms | 36.787 ms |
| Merkle-root attestation | 3 | 76.929 ms | 80.804 ms | 88.717 ms |
| Recompute, proof-check, and contract read | 3 | 50.152 ms | 51.197 ms | 55.411 ms |

The Sepolia gas figures come from confirmed public transaction receipts. Confirmation latency was not captured and is deliberately not estimated. Gas units are stable for these contract paths, while fee paid and confirmation time depend on network conditions.

## End-to-End

One complete local replay took **242.0 ms**: face processing → load and rank the saved real provider response → evidence → Merkle tree → fresh Hardhat deployment → attestation → proof recomputation and contract verification. It passed verification. This figure deliberately excludes the external image upload and Google Lens request, whose client-side latency was not captured.

## Interpretation

On this machine, local face processing is the largest deterministic CPU stage; hashing and Merkle verification are sub-millisecond to low-millisecond operations. In a live run, external search dominates wall-clock time. Hardhat latency is useful for repeatable development testing but must not be treated as a public-chain latency prediction.
