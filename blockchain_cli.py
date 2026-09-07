import argparse
import sys
from decimal import Decimal

from blockchain_client import (
    BlockedOnFundsError,
    SEPOLIA_CHAIN_ID,
    attest_commitment,
    attest_commitment_sepolia,
    build_merkle_evidence,
    deploy_contract,
    deploy_sepolia_contract,
    hash_evidence,
    load_evidence,
    run_multi_tamper_test,
    verify_evidence_on_chain,
    verify_evidence_on_sepolia,
)

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _format_eth(balance_wei: int) -> str:
    return f"{Decimal(balance_wei) / Decimal(10**18):f} ETH"


def cli_deploy(network: str = "local"):
    print("==================================================")
    print("      DEPLOYING SMART CONTRACT REGISTRY")
    print("==================================================")
    if network == "sepolia":
        dep = deploy_sepolia_contract()
        print("Sepolia contract deployed successfully!")
        print(f"  Network:          {dep['network']}")
        print(f"  Chain ID:         {dep['chain_id']}")
        print(f"  Deployer Address: {dep['deployer_address']}")
        print(f"  Balance:          {_format_eth(dep['balance_wei'])}")
        print(f"  Contract Address: {dep['contract_address']}")
        print(f"  Deployment Tx:    {dep['deployment_tx']}")
        print(f"  Block Number:     {dep['deployment_block']}")
        print(f"  Etherscan Address:{dep['etherscan_address_url']}")
        print(f"  Etherscan Tx:     {dep['etherscan_deployment_tx_url']}")
        return

    dep = deploy_contract()
    print("Contract deployed successfully!")
    print(f"  Network:          {dep['network']}")
    print(f"  RPC URL:          {dep['rpc_url']}")
    print(f"  Contract Address: {dep['contract_address']}")
    print(f"  Deployer Address: {dep['deployer_address']}")
    print(f"  Deployment Tx:    {dep['deployment_tx_hash']}")
    print(f"  Block Number:     {dep['block_number']}")


def cli_attest(evidence_path: str = "output/evidence.json", network: str = "local"):
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

    if network == "sepolia":
        res = attest_commitment_sepolia(merkle_root)
    else:
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

    if network == "sepolia":
        print(f"  Balance:          {_format_eth(res['balance_wei'])}")
        print(f"  Etherscan Address:{res['etherscan_address_url']}")
        if res.get("etherscan_tx_url"):
            print(f"  Etherscan Tx:     {res['etherscan_tx_url']}")


def cli_verify(evidence_path: str = "output/evidence.json", network: str = "local"):
    print("==================================================")
    print("         END-TO-END ON-CHAIN VERIFICATION")
    print("==================================================")
    if network == "sepolia":
        res = verify_evidence_on_sepolia(evidence_path)
    else:
        res = verify_evidence_on_chain(evidence_path)

    print("EVIDENCE SHA-256:")
    print(f"  {res['evidence_sha256']}\n")
    print("SEARCH RESPONSE SHA-256:")
    print(f"  {res['search_response_sha256']}\n")
    print("MATCHED POST SHA-256:")
    print(f"  {res['matched_post_sha256']}\n")
    print("MERKLE ROOT:")
    print(f"  {res['merkle_root']}\n")
    print("ON-CHAIN COMMITMENT:")
    print(f"  {'FOUND' if res['on_chain_exists'] else 'NOT FOUND'}\n")
    print("MERKLE PROOFS:")
    for fld, passed in res["proof_checks"].items():
        print(f"  {fld}: {'PASS' if passed else 'FAIL'}")
    print("\nBLOCKCHAIN VERIFICATION:")
    print(f"  {'PASS' if res['verified'] else 'FAIL'}")
    print(f"\nVerification receipt saved to: {res['receipt_file']}")
    if network == "sepolia":
        print(f"Chain ID: {res['chain_id']}")
        print(f"Etherscan Address: {res['etherscan_address_url']}")
        if res.get("etherscan_tx_url"):
            print(f"Etherscan Tx: {res['etherscan_tx_url']}")
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


def parse_args():
    parser = argparse.ArgumentParser(description="FaceTrace blockchain commands")
    parser.add_argument("command", choices=("deploy", "attest", "verify", "tamper-test"))
    parser.add_argument("evidence_path", nargs="?", default="output/evidence.json")
    parser.add_argument(
        "--network",
        choices=("local", "sepolia"),
        default="local",
        help="Blockchain network; defaults to the local Hardhat EVM.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        if args.command == "deploy":
            cli_deploy(args.network)
        elif args.command == "attest":
            cli_attest(args.evidence_path, args.network)
        elif args.command == "verify":
            cli_verify(args.evidence_path, args.network)
        elif args.command == "tamper-test":
            if args.network != "local":
                raise RuntimeError("tamper-test supports the local Hardhat network only.")
            cli_tamper_test(args.evidence_path)
    except BlockedOnFundsError as exc:
        print("\nBLOCKED_ON_FUNDS")
        print(f"  Chain ID: {SEPOLIA_CHAIN_ID}")
        print(f"  Deployer: {exc.address}")
        print(f"  Balance:  {_format_eth(exc.balance_wei)}")
        if exc.required_wei is not None:
            print(f"  Estimated required balance: {_format_eth(exc.required_wei)}")
        print(f"  Reason:   {exc}")
        sys.exit(2)
    except Exception as exc:
        if args.network == "sepolia" and not isinstance(
            exc, (RuntimeError, ConnectionError, FileNotFoundError)
        ):
            print(f"\nERROR: Sepolia operation failed ({type(exc).__name__}).")
        else:
            print(f"\nERROR: {exc}")
        sys.exit(1)
