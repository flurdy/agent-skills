# Pair-programming evidence

Run `make test-pair-programming` from the repository root (Python 3.10+, standard
library only). These are offline instruction/fixture contracts, not model-behavior
execution tests. They check opt-in discovery, step boundaries, existing workflow
ownership, safety, exit, upstream attribution, scenario structure and suite wiring.
No test invokes a provider, installs a skill, or modifies user configuration.

`scenarios.json` contains synthetic manual behavioral inputs and authored acceptance
oracles. Observation turns are supplied fixtures, not results from a live repository.
Expected-assistant turns illustrate the second step of the redirect case; they are
not a captured model transcript. Static assertions cannot prove a model follows prose.

## Manual scenario review

1. Read the skill and each case's input turns, keeping its oracle separate.
2. Produce the next response and state what actions would be taken or withheld.
   Do not execute fixture commands or invent real test results.
3. Compare with `expected` and `reject`. For `bounded-loop-and-redirect`, continue
   through the additional turns: discuss the policy question without editing, then
   implement only the newly requested step, discuss its supplied result, and wait.
4. Check that the response actually returns control, not merely promises a pause
   before continuing automatically. Also check that routine work inside the agreed
   step does not acquire unnecessary approval gates.
5. Record outcomes and limitations in the owning task. A same-session self-review
   is not an independent or fresh-session model trial. Investigate disagreements;
   do not rewrite the oracle merely to make a response pass.

A separately authorized fresh-session provider trial can consume the same inputs,
subject to the selected route's privacy, read-only and billing rules. Neither the
skill nor its test target launches one automatically. Installation and client discovery
are separate from these checks; repository dry-run/apply/doctor policy still applies.
