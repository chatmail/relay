# Releasing a new version of chatmail relay

For example, to release version 1.13.0 of chatmail relay, do the following steps.

1. Update the changelog: `git cliff --unreleased --tag 1.13.0 --prepend CHANGELOG.md` or `git cliff -u -t 1.13.0 -p CHANGELOG.md`.

2. Open the changelog in the editor, edit it if required.

3. Commit the changes to the changelog with a commit message `chore(release): prepare for 1.9.0`.

4. Open a PR with the new commit, merge it to main after review.

5. In the web interface, create a GitHub release, tell it to create a new tag.
