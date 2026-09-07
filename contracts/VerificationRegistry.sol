// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title VerificationRegistry
 * @notice On-chain registry for cryptographic evidence attestations.
 * @dev Stores only a 32-byte cryptographic commitment. The application attests
 * the SHA-256 Merkle root derived from selected evidence fields.
 * Zero raw biometric features, face encodings, images, or personally identifiable data
 * are persisted on-chain, preserving biometric privacy while guaranteeing tamper-proof
 * verification of external attestations.
 */
contract VerificationRegistry {
    // Mapping from a bytes32 commitment to its block timestamp of attestation
    mapping(bytes32 => uint256) public attestations;

    event EvidenceAttested(
        bytes32 indexed evidenceHash,
        address indexed attester,
        uint256 timestamp
    );

    /**
     * @notice Attest a new cryptographic commitment to the blockchain.
     * @param evidenceHash The bytes32 commitment (a Merkle root in this application).
     */
    function attest(bytes32 evidenceHash) external {
        require(
            attestations[evidenceHash] == 0,
            "already attested"
        );

        attestations[evidenceHash] = block.timestamp;

        emit EvidenceAttested(
            evidenceHash,
            msg.sender,
            block.timestamp
        );
    }

    /**
     * @notice Check whether a commitment has been attested.
     * @param evidenceHash The bytes32 commitment to verify.
     * @return True if the commitment exists in the registry.
     */
    function exists(bytes32 evidenceHash)
        external
        view
        returns (bool)
    {
        return attestations[evidenceHash] != 0;
    }
}
