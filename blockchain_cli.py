import os
import sys
import json
from blockchain_client import (
    deploy_contract,
    attest_commitment,
    verify_evidence_on_chain,
    run_multi_tamper_test,
    load_evidence,
    hash_evidence,
    build_merkle_evidence,
)

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def cli_deploy():
    print("==================================================")
    print("      DEPLOYING SMART CONTRACT REGISTRY")
    print("==================================================")
    dep = deploy_contract()
    print("Contract deployed successfully!")
    print(f"  Network:          {dep['network']}")
    print(f"  RPC URL:          {dep['rpc_url']}")
    print(f"  Contract Address: {dep['contract_address']}")
    print(f"  Deployer Address: {dep['deployer_address']}")
    print(f"  Deployment Tx:    {dep['deployment_tx_hash']}")
    print(f"  Block Number:     {dep['block_number']}")


def cli_attest(evidence_path: str = "output/evidence.json"):
    print("==================================================")
    print("        ATTESTING MERKLE ROOT TO BLOCKCHAIN")
    print("==================================================")
    evidence = load_evidence(evidence_path)
    merkle_data = build_merkle_evidence(evidence, save_path="output/merkle_evidence.json")
    merkle_root = merkle_data["merkle_root"]

    print(f"Canonical Evidence SHA-256: {hash_evidence(evidence)}")
    print(f"Search Response SHA-256:    {evidence.get('search_response_sha256')}")
    print(f"Matched Post SHA-256:       {evidence.get('matched_post_sha256')}")
    print(f"Merkle Root Commitment:     {merkle_root}")

    res = attest_commitment(merkle_root)
    if res["already_attested"]:
        print("\nNotice: This Merkle root is already attested on-chain.")
        print(f"  Merkle Root:      {res['commitment_hash']}")
        print(f"  Block Timestamp:  {res['timestamp']}")
    else:
        print("\nMerkle Root Attestation confirmed on-chain!")
        print(f"  Merkle Root:      {res['commitment_hash']}")
        print(f"  Transaction Hash: {res['tx_hash']}")
        print(f"  Block Number:     {res['block_number']}")
        print(f"  Gas Used:         {res['gas_used']}")
        print(f"  Attester:         {res['attester']}")
        print(f"  Block Timestamp:  {res['timestamp']}")


def cli_verify(evidence_path: str = "output/evidence.json"):
    print("==================================================")
    print("         END-TO-END ON-CHAIN VERIFICATION")
    print("==================================================")
    res = verify_evidence_on_chain(evidence_path)

    print(f"EVIDENCE SHA-256:")
    print(f"  {res['evidence_sha256']}\n")

    print(f"SEARCH RESPONSE SHA-256:")
    print(f"  {res['search_response_sha256']}\n")

    print(f"MATCHED POST SHA-256:")
    print(f"  {res['matched_post_sha256']}\n")

    print(f"MERKLE ROOT:")
    print(f"  {res['merkle_root']}\n")

    print(f"ON-CHAIN COMMITMENT:")
    print(f"  {'FOUND' if res['on_chain_exists'] else 'NOT FOUND'}\n")

    print(f"MERKLE PROOFS:")
    for fld, passed in res["proof_checks"].items():
        print(f"  {fld}: {'PASS' if passed else 'FAIL'}")

    print(f"\nBLOCKCHAIN VERIFICATION:")
    print(f"  {'PASS' if res['verified'] else 'FAIL'}")
    print(f"\nVerification receipt saved to: {res['receipt_file']}")
    print("==================================================")


def cli_tamper_test(evidence_path: str = "output/evidence.json"):
    print("==================================================")
    print("    MULTI-CASE CRYPTOGRAPHIC TAMPER DEMONSTRATION")
    print("==================================================")
    res = run_multi_tamper_test(evidence_path)

    print(f"Original Merkle Root:     {res['original_merkle_root']}")
    print(f"Original On-Chain Exists: {res['original_on_chain']}\n")

    for case_id, info in res["cases"].items():
        print(f"[{case_id.upper()}] Tampered Field: {info['tampered_field']}")
        print(f"  Tampered Root:           {info['tampered_root']}")
        print(f"  Roots Differ:            {info['roots_differ']}")
        print(f"  On-Chain Exists:         {info['on_chain_exists']}")
        print(f"  Rejected By Blockchain:  {'PASS (REJECTED)' if info['rejected_by_blockchain'] else 'FAIL'}\n")

    print(f"Disk Manifest Untouched:    {res['disk_intact']}")
    if res["all_tamper_cases_rejected"] and res["disk_intact"]:
        print("\nALL TAMPER CASES REJECTED (PASS)")
    else:
        print("\nTAMPER TEST FAILED")
    print("==================================================")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python blockchain_cli.py <deploy|attest|verify|tamper-test> [path_to_evidence.json]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    target_path = sys.argv[2] if len(sys.argv) > 2 else "output/evidence.json"

    if cmd == "deploy":
        cli_deploy()
    elif cmd == "attest":
        cli_attest(target_path)
    elif cmd == "verify":
        cli_verify(target_path)
    elif cmd == "tamper-test":
        cli_tamper_test(target_path)
    else:
        print(f"Unknown command: {cmd}")
        print("Supported: deploy, attest, verify, tamper-test")
        sys.exit(1)
