# Releasing a new version of chatmail relay

For example, to release version 1.13.0 of chatmail relay, do the following steps.

1. Update the changelog: `git cliff --unreleased --tag 1.13.0 --prepend CHANGELOG.md` or `git cliff -u -t 1.13.0 -p CHANGELOG.md`.

2. Open the changelog in the editor, edit it if required.

3. Commit the changes to the changelog with a commit message `chore(release): prepare for 1.9.0`.

4. Open a PR with the new commit, merge it to main after review.

5. In the web interface, create a GitHub release, tell it to create a new tag.

## Releasing filtermail

filtermail is versioned independently and released from the same repo,
using `filtermail-` prefixed tags. To release filtermail 0.7.5:

1. Switch to `filtermail/` directory: `cd filtermail`

2. Update the changelog:
   `git cliff u -t filtermail-0.7.5 -p CHANGELOG.md`

3. Bump `version` in `Cargo.toml` and commit `Cargo.lock`.

4. Commit with the message: `feat(release): prepare filtermail for 0.7.5`

5. Open a PR with the new commit, merge it to main after review.

6. In the web interface, create a GitHub release, tell it to create a new tag `filtermail-0.7.5`. Do not push the tag by hand: the release must exist before the upload job runs.

7. Bump the pinned version and sha256sums in `cmdeploy/src/cmdeploy/filtermail/deployer.py`.
