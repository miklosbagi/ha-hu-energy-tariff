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

## Manifest version - bump it in *every* PR that keeps its `Tag/*` label

`custom_components/hu_energy_tariff/manifest.json`'s `version` field is **not** automatically kept in sync with the release tag - bumping it would require the workflow to commit back to a protected `main` branch, so there's no automation for it. This has already caused real drift once (it sat frozen at `0.1.0` through eight actual releases before anyone noticed) precisely because "bump it as part of a normal PR" was easy to read past as a footnote.

**The actual rule, stated plainly**: if your PR keeps a `Tag/*` label (i.e. it *will* trigger a release when merged), bump `manifest.json`'s `version` in the same PR, to whatever the resulting tag will be:

- `Tag/Patch` → bump the patch number
- `Tag/Minor` → bump the minor number, patch to `0`
- `Tag/Major` → bump the major number, minor and patch to `0`

If you removed every `Tag/*` label (no release from this PR), leave the manifest alone. If HACS-installed users need to see the version match what they installed, this is the only thing that keeps that true - skipping it is invisible short-term and confusing long-term (exactly what happened before).

## Blocking a merge: the `DO_NOT_MERGE` label

Labeling a PR `DO_NOT_MERGE` actually blocks it from merging, not just a visual flag - `.github/workflows/do-not-merge.yml` is a required status check (`check-do-not-merge`, added to the `main` ruleset's `required_status_checks` rule) that fails whenever the label is present and passes otherwise. The workflow re-runs on label add/remove *and* on new commits, so it's always evaluated against the PR's current state - removing the label re-runs the check and unblocks the merge; a label added after the last push still gets caught because `opened`/`synchronize`/`reopened` also trigger it, not just `labeled`/`unlabeled`.

This is the tool to reach for when a PR needs to stay open and visible (e.g. a Dependabot bump that fails CI for a reason worth tracking, or work deliberately paused mid-review) without it being mergeable by accident - a plain label alone can't stop someone from clicking merge, but a failing required check can.

## Mirrored to a private Gitea instance

Day-to-day development happens on a private, self-hosted Gitea instance; this GitHub repo is where a human actually merges and where the version tag/release gets minted - **GitHub is the sole release authority**. Gitea no longer runs its own `release.yml`: cutting a tag/release independently on both sides risked the two computing different version numbers for the same change (this happened once - a fix merged on GitHub while a Gitea PR for the same area was still in flight, and the two histories briefly disagreed on what `main` even contained).

`.gitea/workflows/` still carries `label-pr.yml` and `do-not-merge.yml` (Gitea Actions equivalents, since Gitea PRs still get the same `Tag/*`-labeling and merge-blocking treatment during review there) - just not `release.yml`.

Two more Gitea Actions workflows bridge the two platforms - both only ever open (or reuse) a PR, never merge one themselves, so a human always clicks merge on both platforms, same as everywhere else in this project:

- **`promote-to-github.yml`** (Gitea → GitHub, on every Gitea PR merge to `main`): pushes that merge as a new GitHub branch (`gitea-promote/pr-<N>`) and opens a matching GitHub PR - same title/body, plus the originating PR's `Tag/*` label copied across (`.github/workflows/label-pr.yml` skips its own default-`Tag/Patch` add for these branches specifically, so it doesn't end up stacked next to the copied one). This is the direction that touches the public, canonical repo, so a human review/merge there is what actually triggers the release, per the section above.
- **`sync-from-github.yml`** (GitHub → Gitea, scheduled every 30 minutes plus manual trigger): backfills any release tags GitHub has that Gitea doesn't (plain refs, no PR needed - existing tags are never moved, only new ones added), then, whenever GitHub `main` is ahead of Gitea `main` - typically a community PR merged directly on GitHub - opens a Gitea PR from GitHub's current tip. Merge it using Gitea's **"Fast Forward"** merge style specifically (not the default squash), since that's what keeps the two platforms' commit history actually shared rather than just content-identical (mismatched history has caused real merge conflicts in later PRs before - see the repo's git history). A fast-forward merge would in principle be safe to complete automatically (it can never rewrite history or discard anything), and this job originally tried to; it doesn't, because Gitea's own permissions already enforce a human-must-merge rule for this repo regardless of what the job attempts. If the two histories have genuinely diverged (both sides have commits the other lacks - shouldn't normally happen, but did once during this restructuring, see the repo's git history for that reconciliation), the job fails loudly instead of guessing at a resolution.

## Why labels instead of, say, Conventional Commits

The repo's commit history isn't currently structured enough to reliably infer patch/minor/major from commit messages (squash-merged PRs mean one commit per change, but message conventions weren't enforced from day one). A label is an explicit, visible, easily-overridden decision made once per PR - visible in review, not inferred after the fact.
