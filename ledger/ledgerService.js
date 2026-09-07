const crypto = require("crypto");
const { ethers } = require("ethers");

/**
 * Generates a SHA-256 hash from postData attributes (postUrl, author, contentHash).
 * @param {Object} postData
 * @param {string} postData.postUrl
 * @param {string} postData.author
 * @param {string} postData.contentHash
 * @returns {string} Hex-encoded SHA-256 hash
 */
function generatePostHash(postData) {
  if (!postData) {
    throw new Error("postData is required");
  }
  const postUrl = postData.postUrl || "";
  const author = postData.author || "";
  const contentHash = postData.contentHash || "";
  const payload = `${postUrl}${author}${contentHash}`;
  return crypto.createHash("sha256").update(payload).digest("hex");
}

/**
 * Anchors post data on-chain using the FaceVerificationLedger smart contract.
 * @param {ethers.Contract} contractInstance
 * @param {Object} postData
 * @returns {Promise<{ transactionHash: string, txHash: string, dataHash: string, receipt: any }>}
 */
async function anchorPostData(contractInstance, postData) {
  if (!contractInstance) {
    throw new Error("contractInstance is required");
  }
  if (!postData) {
    throw new Error("postData is required");
  }

  const dataHash = generatePostHash(postData);
  const tx = await contractInstance.anchorRecord(postData.postUrl, dataHash);
  const receipt = await tx.wait();

  return {
    transactionHash: tx.hash,
    txHash: tx.hash,
    dataHash,
    receipt,
  };
}

/**
 * Re-computes post hash and verifies existence and metadata on-chain.
 * @param {ethers.Contract} contractInstance
 * @param {Object} postData
 * @returns {Promise<{ isVerified: boolean, postUrl: string, timestamp: any, tampered: boolean }>}
 */
async function verifyOnChain(contractInstance, postData) {
  if (!contractInstance) {
    throw new Error("contractInstance is required");
  }
  if (!postData) {
    throw new Error("postData is required");
  }

  const dataHash = generatePostHash(postData);
  const result = await contractInstance.verifyRecord(dataHash);

  let isVerified = false;
  let postUrl = "";
  let timestamp = 0n;

  if (result) {
    if (typeof result.exists === "boolean") {
      isVerified = result.exists;
    } else if (typeof result[0] === "boolean") {
      isVerified = result[0];
    } else if (typeof result.isVerified === "boolean") {
      isVerified = result.isVerified;
    }

    if (result.record) {
      postUrl = result.record.postUrl || "";
      timestamp = result.record.timestamp || 0n;
    } else if (result[1] && typeof result[1] === "object" && "postUrl" in result[1]) {
      postUrl = result[1].postUrl || "";
      timestamp = result[1].timestamp || 0n;
    } else {
      postUrl = result.postUrl || (typeof result[1] === "string" ? result[1] : "");
      timestamp = result.timestamp || (typeof result[2] === "bigint" || typeof result[2] === "number" ? result[2] : 0n);
    }
  }

  return {
    isVerified,
    postUrl,
    timestamp,
    tampered: !isVerified,
  };
}

module.exports = {
  generatePostHash,
  anchorPostData,
  verifyOnChain,
};
