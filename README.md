# Open SLEIGH

Community-maintained SLEIGH processor specifications for
[Ghidra](https://github.com/NationalSecurityAgency/ghidra),
collected in one place and made available ahead of upstream merge.

Open SLEIGH is an unofficial community project and is not affiliated with or
endorsed by the National Security Agency or the Ghidra project.

## Why this exists

Ghidra has a careful review process, and processor-specification changes
can take time to review and merge.

Some useful processor-specification fixes and additions remain open as pull
requests for a long time before they are merged upstream.

Open SLEIGH tracks useful community contributions so users can access newer
SLEIGH specifications before they land in upstream Ghidra.

## Scope

This repository contains SLEIGH-related files derived from Ghidra and community
contributions originally submitted to Ghidra.

The goal is **not** to fork Ghidra as a full reverse-engineering platform.
The goal is to provide an **easy-to-consume staging area** for community
SLEIGH specifications.

## Status

Specifications in this repository are provided on a best-effort basis and may
be untested.

A specification being present here does not mean it has been reviewed, tested,
or accepted by upstream Ghidra. Use these files with care and report issues if
you find problems.

## Requesting imports

If you have opened a SLEIGH-related pull request against Ghidra and would like
it to be included here, please open an issue or pull request with a link to the
original Ghidra pull request.

When importing contributions, we try to preserve attribution to the original
author and link back to the upstream contribution.

## Attribution

We import contributions with attribution to the original author whenever
possible.

If attribution is missing or incorrect, please open an issue and we will
correct it.

## License

Open SLEIGH is distributed under the Apache License 2.0.

This repository contains files derived from Ghidra, which is also distributed
under the Apache License 2.0. Original Ghidra copyright, license, and notice
information is preserved where applicable.

See [`LICENSE`](./LICENSE) and [`NOTICE`](./NOTICE).