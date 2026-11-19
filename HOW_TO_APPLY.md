# How to apply this release-candidate package

1. **Do not overwrite the running Ubuntu server**. These are public-reference source files, not a migration patch for your production containers.
2. Download/clone the existing `RenanEspinar/Alexa-RTSP-Bridge` repository into a separate working directory.
3. Create a new working Git branch (e.g. `feature/reproducible-deployment`).
4. Overlay the package contents into the repository **except `.gitignore`**: merge the new ignore rules into the existing `.gitignore` so original exclusions remain. Keep the existing `LICENSE` and `images/` content, and keep previous scripts under a `legacy/` path if you want historical reproducibility.
5. The new package includes a replacement README and complete new `controller/`, `ffmpeg/`, `lambda/`, `nginx/`, `tools/`, `config/`, `docs/`, `tests/` directories. It does not overwrite the actual Home Assistant server configuration.
6. Run tests and Docker Compose validation on an isolated test environment, not the live home server.
7. Use `git status`, inspect `git diff --cached`, check for credentials with a secret scanner, and push to a review PR. Do **not** merge as stable until live Alexa validation passes.
8. Recheck that links in the new README point to files present in the actual public repository, especially `images/banner.png` and `LICENSE`.

**Why no direct GitHub edit?** The connected GitHub integration returned a 403 when attempting to create a branch. This package is a prepared review overlay; no changes have been pushed to your repository.

**Outstanding facts required:** actual deployed AWS Lambda configuration/code; independent first-frame timings; security review of Docker control; confirmation of one clean-room install; photographs/video of a safe demo.
