# Verification evidence

Verified locally on 31 October 2026 using Python 3.12, Node.js 24 and Chromium through Playwright.

| Check                                                               | Observed result                                            |
| ------------------------------------------------------------------- | ---------------------------------------------------------- |
| Python domain/storage/HTTP suite                                    | 33 passing tests                                           |
| TypeScript and Vite production build                                | Pass                                                       |
| Browser sign-off → production rehearsal → evidence export → restore | Pass                                                       |
| Browser new candidate → manual evidence → failing staging health    | Pass; previous artifact preserved                          |
| Desktop inspection                                                  | Entry and workbench at 1440 px width                       |
| Mobile inspection                                                   | Workbench at 390 px; no document-level horizontal overflow |

The domain suite covers sign-off, evidence freshness/replacement, changed staging prerequisites, environment locks/generations, operation versions, invalid/terminal transitions, health failures, cancellation, restoration targets, digest stability, numeric version order, immutable version registration and migration declarations.

Storage tests check workspace isolation, harmless replay, changed-payload rejection, rollback after forced failure during the final environment commit, tampered identity/generation detection, idle expiry and file-backed restart persistence.

HTTP tests cover authentication, cookie properties, CSRF, Origin rejection, complete promotion/restore, evidence export, malformed input, streamed body limits, cross-workspace release lookup, manual provenance and rejection of actor injection.

The two browser scenarios exercise successful and failed transitions through visible controls. Screenshots are `entry.png`, `workbench.png`, `operation.png` and `mobile.png`. Sample evidence and deployments are explicitly labeled fixtures. Application tests in this repository are distinct from the manually recorded unit/API/security outcomes displayed inside the product.

The test client dependency emits a Starlette/httpx deprecation warning; checks still pass. These tests are not a production IAM audit, external deployment integration test, security scan, load benchmark or validation of real migration safety.
