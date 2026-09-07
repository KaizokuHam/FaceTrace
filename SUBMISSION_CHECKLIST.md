# Submission Checklist

## Code

- [ ] `git status` contains only intended release changes
- [ ] `npm ci`, `npx hardhat compile`, and `pip check` pass
- [ ] All 28 named regression checks pass on a fresh Hardhat chain
- [ ] End-to-end local verification and all four tamper cases pass
- [ ] Benchmark results are real, reproducible, and accurately labeled
- [ ] Secret scan and tracked-file audit pass
- [ ] Selected target URL, username, and post ID are not hardcoded

## GitHub

- [ ] Repository is pushed
- [ ] `.env` is absent
- [ ] `output/`, caches, and dependency directories are absent
- [ ] README renders correctly
- [ ] Setup is reproducible from a clean clone
- [ ] No license is claimed unless a `LICENSE` file is added
- [ ] Sepolia contract and transaction links open successfully

## Demo

- [ ] Selected post is visually confirmed
- [ ] Hardhat chain is fresh
- [ ] Full demo is recorded
- [ ] Tamper test is recorded
- [ ] Optional Sepolia verification is shown or clearly omitted
- [ ] No secret, wallet key, or Hardhat private key appears on screen
- [ ] Video link works in an incognito window

## Submission

- [ ] GitHub link works in an incognito window
- [ ] Video link works in an incognito window
- [ ] Submission form is checked carefully
- [ ] Repository and video links point to the final versions
- [ ] Submit once; assume resubmission is unavailable
