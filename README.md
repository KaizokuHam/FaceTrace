# FaceTrace

### Tamper-evident social-media provenance from a face scan

---

## 1. Problem Overview

FaceTrace is a verifiable evidence pipeline for **Hacker House Goa 2026 — Task 3**. It detects and encodes a face, discovers a public social-media result through genuine web search, binds the resulting evidence into a Merkle tree, anchors only the root on an EVM chain, and later recomputes the entire proof.
1. **Face Scan & Feature Extraction**: Process a local input image, detect a face, and generate a deterministic facial representation.
2. **Reverse Image Search & Social Discovery**: Execute a live reverse image search over public web indexes to dynamically discover genuine social media posts featuring the face.
3. **Cryptographic Provenance**: Bind the source image, facial encoding, raw search response, and the selected social post into a tamper-evident evidence structure.
4. **Blockchain Attestation & Re-Verification**: Anchor the cryptographic commitment on an Ethereum-compatible EVM ledger and verify inclusion and tamper resistance.

---

## 2. What FaceTrace Does

```
+------------------+     +------------------------+     +---------------------------+
| Local Input Image| --> | MediaPipe Face Mesh    | --> | 1434-D Landmark Encoding  |
|  (demo.jpg)      |     | (Single-Face Validator)|     | (Normalized (x,y,z) mesh) |
+------------------+     +------------------------+     +---------------------------+
                                                                      |
                                                                      v
+------------------+     +------------------------+     +---------------------------+
| Ranked Candidates| <-- | Live Google Lens Search| <-- | Image Upload to SerpApi   |
| (output/ranked)  |     | (Exact Matches Engine) |     | (Direct binary payload)   |
+------------------+     +------------------------+     +---------------------------+
         |
         v
+------------------+     +------------------------+     +---------------------------+
| Deterministic    | --> | Merkle Evidence Tree   | --> | VerificationRegistry.sol  |
| Post Selection   |     | (10 Lexicographical    |     | (Local Hardhat EVM: 31337)|
| (x.com / status) |     |  Canonical Leaves)     |     | (Stores bytes32 Merkle)   |
+------------------+     +------------------------+     +---------------------------+
                                                                      |
                                                                      v
                                                        +---------------------------+
                                                        | On-Chain Re-Verification  |
                                                        | & Multi-Case Tamper Audit |
                                                        +---------------------------+
```

1. **Face Scan**: Validates that the input is readable and confirms exactly one detectable face is present.
2. **Facial Feature Encoding**: Computes a deterministic 1434-dimensional vector from 478 MediaPipe 3D face mesh landmarks, hashed with SHA-256.
3. **Live Web Search**: Uploads the image binary to SerpApi and queries the live Google Lens index with `type=exact_matches`.
4. **Social Post Discovery**: Extracts social media candidate URLs (`x.com`, `linkedin.com`, `facebook.com`, `reddit.com`, `tiktok.com`) from provider matches.
5. **Deterministic Candidate Selection**: Scores candidates using validated structural signals (specific post bonus, platform priority, provider rank, penalty for profiles/trending) without scraping or fabricating text.
6. **Search Provenance & Post Fingerprinting**:
   - `search_response_sha256`: Cryptographically binds the raw provider payload.
   - `matched_post_sha256`: Computes a compact canonical SHA-256 fingerprint of `{platform, provider_position, title, url}`.
7. **Merkle Provenance**: Constructs a 10-leaf Merkle tree containing all constituent evidence fields.
8. **Blockchain Attestation**: Commits the `merkle_root` to `VerificationRegistry.sol` on an EVM-compatible chain (Hardhat Local Chain ID 31337).
9. **On-Chain Re-Verification**: Reconstructs leaves, verifies Merkle inclusion proofs, and queries the smart contract to confirm immutable existence.

---

## 3. Architecture & Provenance Guarantees

### Why Search Is Genuine
- **No preselected result in application code**: The runtime does not contain a target username, post URL, or status ID. Test fixtures use synthetic example URLs only.
- **Live upload**: Every run uploads the image binary to SerpApi's CDN and retrieves an ephemeral `image_id`.
- **Live Google Lens query**: Google Lens returns hundreds of raw results; FaceTrace parses provider results dynamically.
- **Deterministic selection receipt**: `output/ranked_candidates.json` records scores and selection breakdown for every candidate.
- **Search response integrity**: `output/phase0_exact_matches.json` is hashed (`search_response_sha256`) directly from disk bytes.

### Face Processing Accuracy & Scope
- **Framework**: MediaPipe Face Mesh (`v0.10.x`) with refine_landmarks enabled.
- **Extraction**: 478 3D landmarks yield 1,434 floating-point coordinates. The implementation subtracts the coordinate centroid and L2-normalizes the flattened vector before deterministic `float32` serialization.
- **Technical clarification**: This is a **facial landmark encoding**, not a face-recognition identity embedding such as FaceNet or ArcFace. MediaPipe landmarks do not establish real-world identity.

### Candidate Selection Scoring Formula
Candidates are evaluated deterministically using validated provider signals:
$$\text{Score} = \text{Post Bonus} + \text{Platform Weight} + \text{Position Score} - \text{Penalty}$$
- **Specific Post Bonus (+50.0)**: URL points to an individual status, post, permalink, or comment (`/status/`, `/posts/`, `/photos/`, `/comments/`).
- **Platform Weight**: `x.com`/`twitter.com` (+40.0), `linkedin.com` (+30.0), `facebook.com` (+25.0), `reddit.com` (+20.0), `tiktok.com` (+15.0).
- **Position Score**: Linear provider rank decay $\max(0, 50 - \text{pos} \times 0.2)$.
- **Penalties (-50.0 / -30.0)**: Generic search, trending (`/i/trending`), hashtags, or root profile directories.

### Merkle Tree Leaves
Leaves are computed as $\text{SHA256}(\text{UTF8}(\text{field\_name} + \text{":"} + \text{canonical\_value}))$, sorted alphabetically:
1. `face_encoding_sha256`
2. `matched_platform`
3. `matched_post_sha256`
4. `matched_title`
5. `matched_url`
6. `provider_position`
7. `search_provider`
8. `search_response_sha256`
9. `search_type`
10. `source_image_sha256`

---

## 4. Blockchain Architecture & Privacy

- **Default network**: Local Hardhat EVM (chain ID `31337`) for deterministic, zero-cost reproduction.
- **Optional public network**: Ethereum Sepolia (chain ID `11155111`) using locally signed transactions and an explicit preflight balance check.
- **Smart Contract**: `VerificationRegistry.sol` (Solidity `^0.8.20`).
  - `attest(bytes32 evidenceHash)`: Records the commitment with `block.timestamp`. Emits `EvidenceAttested(evidenceHash, msg.sender, timestamp)`.
  - `exists(bytes32 commitment)`: Constant lookup returning whether a commitment was attested.
- **Privacy by Design**:
  - Raw face images are **never** stored on-chain.
  - Raw facial landmark coordinates are **never** stored on-chain.
  - Social media text is **never** stored on-chain.
  - Only a 32-byte Merkle root (`bytes32`) is committed to the blockchain.

The blockchain records that a particular evidence commitment existed by a block timestamp and allows later integrity checks. It does **not** prove a person's real-world identity, the truth of social content, the authenticity of a social account, or the correctness of Google Lens results.

### Confirmed public deployment

- Registry: [`0xfBd087eB04b071b41273ADA33A3bA1b8f152CDB7`](https://sepolia.etherscan.io/address/0xfBd087eB04b071b41273ADA33A3bA1b8f152CDB7)
- Deployment transaction: [`0xf82b…b3d4`](https://sepolia.etherscan.io/tx/0xf82b13a5ad94939987746bb9b6dc566bf55f1ce6a975e8b77b4bb3494712b3d4)
- Attestation transaction: [`0xd886…1f2`](https://sepolia.etherscan.io/tx/0xd886165eaed339545d57c23507d36187007dc19cc437d5645038bc9090ea41f2)

The public contract and transactions are independently inspectable; the ignored local receipt contains the complete proof material.

---

## 5. Tamper Demonstration

FaceTrace implements a 4-case in-memory cryptographic tamper verification test:

| Case | Field Tampered | Resulting Effect | Blockchain Verification |
|---|---|---|---|
| **Case A** | `matched_url` | Alters `matched_post_sha256` & URL leaf $\rightarrow$ New Merkle Root | **REJECTED (False)** |
| **Case B** | `matched_title` | Alters `matched_post_sha256` & Title leaf $\rightarrow$ New Merkle Root | **REJECTED (False)** |
| **Case C** | `source_image_sha256` | Alters Source Image leaf $\rightarrow$ New Merkle Root | **REJECTED (False)** |
| **Case D** | `search_response_sha256` | Alters Search Provenance leaf $\rightarrow$ New Merkle Root | **REJECTED (False)** |

Disk manifests are never modified during tamper tests.

---

## 6. Installation & Setup

### Prerequisites
- Python 3.10+
- Node.js 22.13+ and npm (required by the pinned Hardhat release)

### 1. Install Dependencies
```bash
# Install Python dependencies
python -m pip install -r requirements.txt

# Install Node.js / Hardhat dependencies
npm ci
```

### 2. Configure Environment
Create `.env` in the project root:
```ini
SERPAPI_API_KEY=your_serpapi_key_here
SEPOLIA_RPC_URL=your_sepolia_rpc_url_here
SEPOLIA_PRIVATE_KEY=your_testnet_private_key_here
```
The two Sepolia values are optional and only needed for the opt-in public-testnet commands. Never use a wallet containing mainnet funds. A placeholder-only `.env.example` is provided.

---

## 7. Running the Pipeline

### Terminal 1: Start Hardhat Local EVM Node
```bash
npx hardhat compile
npx hardhat node
```
This spawns a local Ethereum node at `http://127.0.0.1:8545` with 20 pre-funded test accounts.

### Terminal 2: Run End-to-End Demo
```bash
python demo.py examples/demo.jpg
```

### Terminal 2 (Alternative): Standalone Blockchain CLI
```bash
# Deploy registry
python blockchain_cli.py deploy

# Attest current evidence Merkle root
python blockchain_cli.py attest

# Verify on-chain existence & Merkle proofs
python blockchain_cli.py verify

# Run multi-case tamper test
python blockchain_cli.py tamper-test
```

### Optional Sepolia Deployment

The local Hardhat flow remains the default. To attest the same Merkle root publicly on Ethereum Sepolia, configure `SEPOLIA_RPC_URL` and `SEPOLIA_PRIVATE_KEY` in the ignored `.env`, then run:

```bash
python blockchain_cli.py deploy --network sepolia
python blockchain_cli.py attest --network sepolia
python blockchain_cli.py verify --network sepolia
```

Sepolia operations enforce chain ID `11155111`, derive the deployer from the configured testnet key, check its balance before writes, and sign transactions locally. A zero or insufficient balance stops with `BLOCKED_ON_FUNDS` before broadcasting. Deployment and verification metadata are written separately to `output/deployment_sepolia.json` and `output/verification_receipt_sepolia.json`; successful writes print public Sepolia Etherscan address and transaction URLs. The private key is never printed or persisted.

### Benchmarks

With Hardhat running, collect reproducible local measurements:

```bash
python benchmark.py examples/demo.jpg
```

Use `--live` only when you are authorized to upload the supplied face image to SerpApi and intentionally want to consume search quota. Measured results, methodology, limitations, local latency, gas use, and the real provider timing captured by the saved search artifact are documented in [BENCHMARKS.md](BENCHMARKS.md).

| Measured stage | Result |
|---|---:|
| Face detection p50 / p95 | 30.970 / 31.794 ms |
| Landmark encoding p50 / p95 | 31.866 / 34.146 ms |
| Complete evidence provenance p50 / p95 | 5.485 / 7.320 ms |
| Local replay end-to-end | 242.0 ms |
| Provider-reported Lens processing | 2.9 s |
| Deployment / attestation gas | 224,896 / 46,190 |

---

## 8. Automated Test Suites

FaceTrace includes comprehensive test coverage across 3 dedicated test suites:

```bash
# Phase 1: Face detection, landmarks, and domain filters (7 tests)
python test_phase1.py

# Phase 3 & 4: Evidence canonicalization and blockchain registry (9 tests)
python test_phase3_4.py

# Phase 6: Differentiators, Merkle proofs, and tamper rejection (12 checks)
python test_differentiators.py
```

The three scripts contain 24 executable test functions covering 28 named checks. Blockchain lifecycle checks use the live local Hardhat EVM. The multiple-face rejection branch uses one controlled mock to force a two-detection result; zero-face and single-face cases run MediaPipe on real images.

---

## 9. Project Structure

```text
face_processor.py                 face detection and facial landmark encoding
reverse_search.py                 live image upload, Google Lens query, candidate extraction
evidence_manager.py               ranking, canonical hashes, Merkle tree and proofs
blockchain_client.py              contract deployment, attestation, verification, tamper checks
blockchain_cli.py                 deploy/attest/verify/tamper-test commands
benchmark.py                      repeatable local, evidence, chain, and optional live timings
demo.py                           final end-to-end demo
contracts/VerificationRegistry.sol  bytes32 commitment registry
test_phase1.py                    face and social-domain tests
test_phase3_4.py                  evidence and live-EVM registry tests
test_differentiators.py           ranking, Merkle, tamper, and lifecycle tests
```

## 10. Generated Artifacts

All outputs are saved to the `output/` directory (gitignored):
- `output/phase0_exact_matches.json`: Complete raw JSON returned by SerpApi Google Lens.
- `output/ranked_candidates.json`: Ranked list of all social candidates with transparent scoring breakdown.
- `output/evidence.json`: Full canonical evidence manifest.
- `output/merkle_evidence.json`: 10 canonical leaves, Merkle root, and inclusion proofs.
- `output/deployment.json`: Active registry contract address and deployment transaction hash.
- `output/verification_receipt.json`: Portable audit receipt including all hashes, tx receipts, and proof verification statuses.
- `output/deployment_sepolia.json`: Optional Sepolia deployment and attestation metadata.
- `output/verification_receipt_sepolia.json`: Optional Sepolia re-verification receipt.
- `output/benchmark_results.json`: Raw benchmark environment, samples summary, and gas measurements.

All generated outputs, credentials, caches, compiled contracts, and dependency directories are excluded from Git. `.env.example` contains placeholders only; `.env` is ignored.

## Security Notes

- Treat face images and raw search responses as sensitive local evidence. A live search sends the selected image to SerpApi.
- Use only a dedicated testnet wallet for Sepolia. Transactions are signed locally; the private key is never logged or persisted by FaceTrace.
- Review ignored `output/` receipts before sharing them because they contain the discovered public post URL and provenance metadata.
- The bundled Hardhat accounts and keys are public development fixtures and must never receive real funds.

---

## 11. Known Limitations

1. **Search Index Coverage**: Reverse image search results depend entirely on Google Lens indexing and public availability.
2. **Provider Availability**: SerpApi availability, quotas, and rate limits can prevent a live run.
3. **Post Ephemerality**: Social-media posts can be deleted, made private, or modified after discovery.
4. **Landmark Encoding**: MediaPipe landmarks are not identity-recognition embeddings and the project does not establish real-world identity.
5. **Scope of Blockchain Proof**: The contract proves existence and integrity of a submitted commitment, not the truth of the social content, account authenticity, or Google Lens correctness.
6. **Demonstration EVM**: The local Hardhat chain (`chain_id: 31337`) resets when restarted. Its addresses and transactions are not permanent infrastructure.
