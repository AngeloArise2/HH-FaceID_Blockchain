const { expect } = require("chai");
const hre = require("hardhat");
const { ethers } = hre;
const {
  generatePostHash,
  anchorPostData,
  verifyOnChain,
} = require("../ledgerService");

if (typeof describe !== "undefined") {
  describe("FaceVerificationLedger Integration Tests", function () {
  let ledger;
  let owner;
  let addr1;

  const samplePost = {
    postUrl: "https://twitter.com/example/status/1234567890",
    author: "janedoe",
    contentHash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  };

  beforeEach(async function () {
    [owner, addr1] = await ethers.getSigners();
    const FaceVerificationLedger = await ethers.getContractFactory("FaceVerificationLedger");
    ledger = await FaceVerificationLedger.deploy();
    await ledger.waitForDeployment();
  });

  describe("Smart Contract Core Functionality", function () {
    it("should anchor a record and emit RecordAnchored event", async function () {
      const dataHash = generatePostHash(samplePost);
      await expect(ledger.anchorRecord(samplePost.postUrl, dataHash))
        .to.emit(ledger, "RecordAnchored");

      const [exists, record] = await ledger.verifyRecord(dataHash);
      expect(exists).to.be.true;
      expect(record.postUrl).to.equal(samplePost.postUrl);
      expect(record.dataHash).to.equal(dataHash);
      expect(record.registeredBy).to.equal(owner.address);
      expect(record.timestamp).to.be.gt(0n);
    });

    it("should return exists: false for unanchored dataHash", async function () {
      const [exists] = await ledger.verifyRecord("nonexistenthash");
      expect(exists).to.be.false;
    });

    it("should revert if dataHash is empty", async function () {
      await expect(ledger.anchorRecord(samplePost.postUrl, "")).to.be.revertedWith(
        "Data hash cannot be empty"
      );
    });

    it("should revert on duplicate record anchor", async function () {
      const dataHash = generatePostHash(samplePost);
      await ledger.anchorRecord(samplePost.postUrl, dataHash);
      await expect(
        ledger.anchorRecord(samplePost.postUrl, dataHash)
      ).to.be.revertedWith("Record already exists");
    });
  });

  describe("ledgerService Integration (Valid vs Tampered)", function () {
    it("should anchor sample social search metadata", async function () {
      const result = await anchorPostData(ledger, samplePost);
      expect(result).to.have.property("transactionHash");
      expect(result).to.have.property("dataHash");
      expect(result.dataHash).to.equal(generatePostHash(samplePost));
    });

    it("should verify that original data returns isVerified: true and tampered: false", async function () {
      await anchorPostData(ledger, samplePost);

      const verification = await verifyOnChain(ledger, samplePost);
      expect(verification.isVerified).to.be.true;
      expect(verification.tampered).to.be.false;
      expect(verification.postUrl).to.equal(samplePost.postUrl);
      expect(verification.timestamp).to.be.gt(0n);
    });

    it("should verify that modified data returns isVerified: false and tampered: true", async function () {
      await anchorPostData(ledger, samplePost);

      // Tamper postUrl
      const tamperedUrl = { ...samplePost, postUrl: "https://tampered.com/fake" };
      const verifyUrl = await verifyOnChain(ledger, tamperedUrl);
      expect(verifyUrl.isVerified).to.be.false;
      expect(verifyUrl.tampered).to.be.true;

      // Tamper author
      const tamperedAuthor = { ...samplePost, author: "attacker" };
      const verifyAuthor = await verifyOnChain(ledger, tamperedAuthor);
      expect(verifyAuthor.isVerified).to.be.false;
      expect(verifyAuthor.tampered).to.be.true;

      // Tamper contentHash
      const tamperedContent = {
        ...samplePost,
        contentHash: "0000000000000000000000000000000000000000000000000000000000000000",
      };
      const verifyContent = await verifyOnChain(ledger, tamperedContent);
      expect(verifyContent.isVerified).to.be.false;
      expect(verifyContent.tampered).to.be.true;
    });
  });
});
}

if (require.main === module) {
  (async () => {
    console.log("Starting standalone testLedger execution...");
    const [deployer] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("FaceVerificationLedger");
    const testLedger = await Factory.deploy();
    await testLedger.waitForDeployment();

    const sample = {
      postUrl: "https://example.com/post/42",
      author: "alice",
      contentHash: "abcd1234ef5678",
    };

    console.log("Anchoring sample post...");
    const anchorResult = await anchorPostData(testLedger, sample);
    console.log("Anchored:", anchorResult.dataHash);

    console.log("Testing original data verification...");
    const originalRes = await verifyOnChain(testLedger, sample);
    console.log("Original result:", originalRes);
    if (!originalRes.isVerified || originalRes.tampered) {
      throw new Error("Failed: original data was not verified");
    }

    console.log("Testing tampered data verification...");
    const tampered = { ...sample, author: "eve" };
    const tamperedRes = await verifyOnChain(testLedger, tampered);
    console.log("Tampered result:", tamperedRes);
    if (tamperedRes.isVerified || !tamperedRes.tampered) {
      throw new Error("Failed: tampered data was incorrectly verified");
    }

    console.log("Standalone integration test PASSED!");
  })()
    .then(() => process.exit(0))
    .catch((err) => {
      console.error(err);
      process.exit(1);
    });
}
