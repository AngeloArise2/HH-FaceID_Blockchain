// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract FaceVerificationLedger {
    struct Record {
        string postUrl;
        string dataHash;
        uint256 timestamp;
        address registeredBy;
    }

    mapping(string => Record) public records;

    event RecordAnchored(
        string postUrl,
        string dataHash,
        uint256 timestamp,
        address indexed registeredBy
    );

    /**
     * @notice Anchors a record containing post URL and evidence data hash.
     * @param _postUrl The URL of the discovered public post.
     * @param _dataHash The SHA-256 fingerprint of the normalized evidence.
     */
    function anchorRecord(string memory _postUrl, string memory _dataHash) external {
        require(bytes(_dataHash).length > 0, "Data hash cannot be empty");
        require(records[_dataHash].timestamp == 0, "Record already exists");

        Record memory newRecord = Record({
            postUrl: _postUrl,
            dataHash: _dataHash,
            timestamp: block.timestamp,
            registeredBy: msg.sender
        });

        records[_dataHash] = newRecord;

        emit RecordAnchored(_postUrl, _dataHash, block.timestamp, msg.sender);
    }

    /**
     * @notice Verifies if a record with the given data hash exists and returns its metadata.
     * @param _dataHash The SHA-256 data hash to verify.
     * @return exists True if the record exists on-chain, false otherwise.
     * @return record The Record struct holding the record metadata.
     */
    function verifyRecord(string memory _dataHash)
        external
        view
        returns (bool exists, Record memory record)
    {
        Record memory r = records[_dataHash];
        if (r.timestamp == 0) {
            return (false, r);
        }
        return (true, r);
    }
}
