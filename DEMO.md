# FaceTrace — Recording Runbook

Target length: roughly 3–5 minutes. Keep all result counts, URLs, hashes, addresses, and transactions dynamic; do not rehearse fixed values.

## Pre-check

- `.env` contains a working `SERPAPI_API_KEY` and is not shown on screen.
- `examples/demo.jpg` exists.
- Python and npm dependencies are installed.
- `npx hardhat compile` succeeds.
- Port 8545 is free so the recording begins with a fresh Hardhat chain.
- A browser is ready for the selected public result.

## Recording

### Terminal 1

```bash
npx hardhat node
```

Show the JSON-RPC endpoint and explain that this is a fresh local EVM with chain ID 31337. Do not present its accounts, addresses, or transactions as permanent infrastructure.

### Terminal 2

```bash
python demo.py examples/demo.jpg
```

As the pipeline runs, show:

1. Exactly one face detected.
2. The 1,434-dimensional facial landmark encoding and source/encoding hashes.
3. The live SerpApi image upload and Google Lens query.
4. The returned result count and dynamically extracted social-candidate count.
5. The selected platform, post URL, and provider position.
6. The search-response, matched-post, and canonical-evidence hashes.
7. The 10-leaf Merkle root.
8. The registry address, attestation transaction, and block number.
9. All displayed Merkle proofs passing.
10. The on-chain lookup and final end-to-end banner passing.

Open the selected social URL in the browser. Visually confirm that it is a specific post and that its media matches the input image. If it does not match, do not submit that recording.

Return to Terminal 2 and run:

```bash
python blockchain_cli.py verify
python blockchain_cli.py tamper-test
```

Show the recomputed hashes, Merkle proofs, on-chain `FOUND` result, and all four mutations rejected while the disk manifest remains untouched. Optionally show `output/verification_receipt.json` with `verified`, `blockchain_verified`, and `merkle_proofs_verified` set to `true`.
