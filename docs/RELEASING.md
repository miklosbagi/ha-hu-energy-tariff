# Releasing

Versioning follows `major.minor.patch` (e.g. `1.2.3`), driven entirely by labels on the PR that gets merged into `main`. No manual tagging. **Gitea is the sole authority that decides version numbers** - see "Mirrored to/from a private Gitea instance" below for why, and what that actually means day to day.

## How it works

1. **Every new PR gets `Tag/Patch` automatically** (`label-pr.yml`, fires on PR open, on both platforms).
2. Before merging, the author can:
   - leave it as-is → a **patch** release (`x.y.Z`),
   - swap it for `Tag/Minor` → a **minor** release (`x.Y.0`),
   - swap it for `Tag/Major` → a **major** release (`X.0.0`),
   - or **remove every `Tag/*` label** → merging creates **no tag and no release** at all.
3. On merge to `main` **on Gitea** (`.gitea/workflows/release-and-promote.yml`, triggered by `pull_request: closed` with `merged == true` - this never runs from the agent or CI merging anything, only from a human clicking merge):
   - reads the merged PR's labels (precedence `Tag/Major` > `Tag/Minor` > `Tag/Patch` if more than one is somehow present),
   - finds the latest existing `major.minor.patch` tag (`0.0.0` if none exist yet),
   - computes the next tag and creates the release **on Gitea**, immediately,
   - pushes that same tag to GitHub too, as a bare ref - **inert on its own**, since a tag with no Release wrapping it doesn't make anything installable (HACS and most tooling watch Releases, not tags),
   - promotes the same content to GitHub as a PR.
4. Once a human merges that promoted PR **on GitHub** too, `.github/workflows/promote-release.yml` finds the already-pushed tag by walking git history - any semver tag that's now an ancestor of the merge and has no GitHub Release yet - and creates the matching Release for it. It never computes a version itself; it never even reads the PR body. This is the step that actually makes the version installable via HACS.

## The human/agent follow-up step

The generated release notes are a commit-log changelog, not a summary - they list individual commits, not what actually changed for a user. **After each automated release, a maintainer (or an agent asked to do so) should edit the release description** (on whichever platform - ideally both) to add a short, human-readable "what's new" paragraph above the generated list. This is intentionally not automated further: judging what's worth highlighting in a release isn't something the tagging workflow can do, and trying to heuristically extract it from commit messages tends to produce worse summaries than either the raw changelog alone or a two-minute human pass.

## Manifest version - bump it in *every* PR that keeps its `Tag/*` label

`custom_components/hu_energy_tariff/manifest.json`'s `version` field is **not** automatically kept in sync with the release tag - bumping it would require the workflow to commit back to a protected `main` branch, so there's no automation for it. This has already caused real drift once (it sat frozen at `0.1.0` through eight actual releases before anyone noticed) precisely because "bump it as part of a normal PR" was easy to read past as a footnote.

**The actual rule, stated plainly**: if your PR keeps a `Tag/*` label (i.e. it *will* trigger a release when merged), bump `manifest.json`'s `version` in the same PR, to whatever the resulting tag will be:

- `Tag/Patch` → bump the patch number
- `Tag/Minor` → bump the minor number, patch to `0`
- `Tag/Major` → bump the major number, minor and patch to `0`

If you removed every `Tag/*` label (no release from this PR), leave the manifest alone. If HACS-installed users need to see the version match what they installed, this is the only thing that keeps that true - skipping it is invisible short-term and confusing long-term (exactly what happened before).

## Blocking a merge: the `DO_NOT_MERGE` label

Labeling a PR `DO_NOT_MERGE` actually blocks it from merging, not just a visual flag - `do-not-merge.yml` is a required status check (`check-do-not-merge`) that fails whenever the label is present and passes otherwise, on both platforms. The workflow re-runs on label add/remove *and* on new commits, so it's always evaluated against the PR's current state - removing the label re-runs the check and unblocks the merge; a label added after the last push still gets caught because `opened`/`synchronize`/`reopened` also trigger it, not just `labeled`/`unlabeled`.

This is the tool to reach for when a PR needs to stay open and visible (e.g. a Renovate bump that fails CI for a reason worth tracking, or work deliberately paused mid-review) without it being mergeable by accident - a plain label alone can't stop someone from clicking merge, but a failing required check can.

## Mirrored to/from a private Gitea instance

Day-to-day development happens on a private, self-hosted Gitea instance (`gitea.mb`); this GitHub repo is public, HACS-facing, and also accepts community contributions directly. **Gitea is the sole authority that decides version numbers** - both platforms independently computing "next patch from latest tag" was tried first and caused a real incident (a fix merged on GitHub while a Gitea PR for the same area was still in flight, and the two histories briefly disagreed on what `main` even contained); GitHub-sole-authority was tried next, but that meant no version existed until a *second*, separate GitHub review pass happened, which was too slow for local testing against Gitea directly. Gitea-sole-authority fixes both: a version exists immediately on merge, and there's still only ever one place deciding what it is.

Three Gitea Actions workflows (plus one on GitHub) make this work, all with the same rule: **only ever open a PR, never merge one** - a human always clicks merge, on both platforms, always.

- **`.gitea/workflows/release-and-promote.yml`** (on every Gitea PR merge to `main`): computes the version from the merged PR's `Tag/*` label and creates the release **on Gitea immediately** (see "How it works" above), pushes that same tag to GitHub as a bare ref (inert until wrapped in a Release), then pushes the merge as a new GitHub branch (`gitea-promote/pr-<N>`) and opens a matching GitHub PR - same title/body, `Tag/*` label copied across (purely informational at this point, see below). `.github/workflows/label-pr.yml` skips its own default-`Tag/Patch` add for these branches specifically, so it doesn't end up stacked next to the copied one.
- **`.github/workflows/promote-release.yml`** (on every `gitea-promote/*` PR merge to `main`, on GitHub): walks the tag list for any semver tag that's now an ancestor of the merge and has no GitHub Release yet, and creates the Release for it - the tag itself already exists (pushed by the step above), this just wraps it in a Release, which is what actually makes it installable via HACS. Never reads the PR body and never computes its own version - purely finds what Gitea already decided and published as a bare tag. A PR whose merge doesn't complete any such tag (all `Tag/*` labels were removed on Gitea) creates nothing here either.
- **`.gitea/workflows/sync-from-github.yml`** (scheduled every 30 minutes plus manual trigger): whenever GitHub `main` is ahead of Gitea `main` - typically a community PR merged directly on GitHub, since Gitea is private and that's the only way external contributors can reach the project - opens a Gitea PR from GitHub's current tip. Merge it using Gitea's **"Fast Forward"** merge style specifically (not the default squash), since that's what keeps the two platforms' commit history actually shared rather than just content-identical (mismatched history has caused real merge conflicts in later PRs before - see the repo's git history). Content-only, no tags - a plain community PR has no Gitea-decided version to backfill; it just becomes ordinary Gitea content, released next time a maintainer merges something there. This job originally tried to auto-merge its own PR too (reasoning: a fast-forward is lossless, so it seemed safe) but doesn't, because Gitea's own permissions already enforce a human-must-merge rule for this repo regardless of what the job attempts. If the two histories have genuinely diverged (both sides have commits the other lacks - shouldn't normally happen, but did once during an earlier restructuring, see the repo's git history for that reconciliation), the job fails loudly instead of guessing at a resolution.

**One real consequence of Gitea being sole authority**: a plain community PR merged directly on GitHub does *not* get an immediate release, even with a `Tag/*` label on it - `promote-release.yml` only fires for `gitea-promote/*` branches. That content needs to flow into Gitea first (via `sync-from-github.yml`) before a maintainer merging something there mints the next version. This is an accepted tradeoff of Gitea-sole-authority, not a bug. Dependency-bump PRs don't hit this gap at all, since `renovate.yml` opens them on Gitea directly - see "Dependency updates and SAST run on Gitea, not GitHub" below.

## Dependency updates and SAST run on Gitea, not GitHub

Both used to run on GitHub (Dependabot, CodeQL) but neither fit once Gitea became sole release authority:

- **Dependabot -> `renovate.yml`** (scheduled daily + manual trigger): a Dependabot PR opened on GitHub is a plain community PR from `promote-release.yml`'s point of view (see the consequence noted above) - it wouldn't get an immediate release even with a `Tag/*` label. Renovate opens the same kind of PR directly on Gitea instead, so dependency bumps flow through the normal Gitea-authority pipeline like any other change. Uses this fleet's existing shared `renovate` Gitea bot account and OpenBao-backed credentials (the same pattern `the_collective/reference-service-repo` uses for every service repo) - since this repo isn't part of that org, the `renovate` bot needs collaborator access granted here specifically, and `RENOVATE_OPENBAO_ROLE_ID`/`RENOVATE_OPENBAO_SECRET_ID` need to be repository secrets (not inherited org secrets). Config lives in `renovate.json` at the repo root.
- **CodeQL -> `semgrep.yml`** (on every PR/push to `main`, plus a weekly scan): CodeQL is tied to GitHub's own Code Scanning API and has no Gitea/Forgejo equivalent - there was nothing to "port," so this is Semgrep OSS instead, pinned by Docker image digest and OSV-checked before each run, matching the pinned-and-verified pattern `secret-scan.yml`'s gitleaks step already established for security tooling in this repo.

GitHub's own `ci.yml` no longer duplicates the coverage-floor/coverage-drop checks - that machinery is expensive to run twice and every change that actually ships already passed it on Gitea first. GitHub's copy still runs plain `pytest tests/unit` as a safety net, since that's the one gap Gitea genuinely can't cover: a community PR opened directly on GitHub never touches Gitea until after it's already merged.

## Why labels instead of, say, Conventional Commits

The repo's commit history isn't currently structured enough to reliably infer patch/minor/major from commit messages (squash-merged PRs mean one commit per change, but message conventions weren't enforced from day one). A label is an explicit, visible, easily-overridden decision made once per PR - visible in review, not inferred after the fact.
