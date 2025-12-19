# Releasing a new version of chatmail relay

For example, to release version 1.9.0 of chatmail relay, do the following steps.

1. Update the changelog: `git cliff --unreleased --tag 1.9.0 --prepend CHANGELOG.md` or `git cliff -u -t 1.9.0 -p CHANGELOG.md`.

2. Open the changelog in the editor, edit it if required.

3. Commit the changes to the changelog with a commit message `chore(release): prepare for 1.9.0`.

3. Tag the release: `git tag --annotate 1.9.0`.

4. Push the release tag: `git push origin 1.9.0`.

5. Create a GitHub release: `gh release create 1.9.0`.
