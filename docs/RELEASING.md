# Releasing

Versioning follows `major.minor.patch` (e.g. `1.2.3`), driven entirely by labels on the PR that gets merged into `main`. No manual tagging.

## How it works

1. **Every new PR gets `Tag/Patch` automatically** (`.github/workflows/label-pr.yml`, fires on PR open).
2. Before merging, the author can:
   - leave it as-is → a **patch** release (`x.y.Z`),
   - swap it for `Tag/Minor` → a **minor** release (`x.Y.0`),
   - swap it for `Tag/Major` → a **major** release (`X.0.0`),
   - or **remove every `Tag/*` label** → merging creates **no tag and no release** at all.
3. On merge to `main` (`.github/workflows/release.yml`, triggered by `pull_request: closed` with `merged == true` - this never runs from the agent or CI merging anything, only from a human clicking merge):
   - reads the merged PR's labels (precedence `Tag/Major` > `Tag/Minor` > `Tag/Patch` if more than one is somehow present),
   - finds the latest existing `major.minor.patch` tag (`0.0.0` if none exist yet),
   - computes and pushes the next tag,
   - creates a GitHub Release for that tag with **auto-generated notes** (`gh release create --generate-notes`, i.e. GitHub's own commit/PR-based changelog).

## The human/agent follow-up step

Auto-generated release notes are a changelog, not a summary - they list merged PRs, not what actually changed for a user. **After each automated release, a maintainer (or an agent asked to do so) should edit the release description** to add a short, human-readable "what's new" paragraph above the auto-generated list. This is intentionally not automated further: judging what's worth highlighting in a release isn't something the tagging workflow can do, and trying to heuristically extract it from commit messages tends to produce worse summaries than either the raw changelog alone or a two-minute human pass.

## Manifest version

`custom_components/hu_energy_tariffs/manifest.json`'s `version` field is **not** automatically kept in sync with the release tag by this workflow - bumping it would require the workflow to commit back to a protected `main` branch. Bump it manually as part of a normal PR when preparing a release, or pick it up as a documented follow-up if this becomes a recurring source of drift.

## Blocking a merge: the `DO_NOT_MERGE` label

Labeling a PR `DO_NOT_MERGE` actually blocks it from merging, not just a visual flag - `.github/workflows/do-not-merge.yml` is a required status check (`check-do-not-merge`, added to the `main` ruleset's `required_status_checks` rule) that fails whenever the label is present and passes otherwise. The workflow re-runs on label add/remove *and* on new commits, so it's always evaluated against the PR's current state - removing the label re-runs the check and unblocks the merge; a label added after the last push still gets caught because `opened`/`synchronize`/`reopened` also trigger it, not just `labeled`/`unlabeled`.

This is the tool to reach for when a PR needs to stay open and visible (e.g. a Dependabot bump that fails CI for a reason worth tracking, or work deliberately paused mid-review) without it being mergeable by accident - a plain label alone can't stop someone from clicking merge, but a failing required check can.

## Why labels instead of, say, Conventional Commits

The repo's commit history isn't currently structured enough to reliably infer patch/minor/major from commit messages (squash-merged PRs mean one commit per change, but message conventions weren't enforced from day one). A label is an explicit, visible, easily-overridden decision made once per PR - visible in review, not inferred after the fact.
