const hre = require("hardhat");

async function main() {
  console.log("Compiling and deploying FaceVerificationLedger...");

  const FaceVerificationLedger = await hre.ethers.getContractFactory("FaceVerificationLedger");
  const ledger = await FaceVerificationLedger.deploy();

  await ledger.waitForDeployment();

  const contractAddress = await ledger.getAddress();
  console.log(`FaceVerificationLedger deployed to: ${contractAddress}`);

  return contractAddress;
}

if (require.main === module) {
  main()
    .then(() => process.exit(0))
    .catch((error) => {
      console.error(error);
      process.exit(1);
    });
}

module.exports = { main };
