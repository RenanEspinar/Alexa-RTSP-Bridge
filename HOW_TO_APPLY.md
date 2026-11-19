# Repository branches

The original project is on `main`. The configurable build lives on `review/reproducible-rc1-20261118`.

If you are setting up a camera from scratch, use the [RC1 installation guide](docs/INSTALL.md) on a separate test host. It walks through camera secrets, Compose generation, signed URLs and HTTPS routing.

Don't copy files into the author's live Ubuntu server or replace its containers with this branch. RC1 still needs Docker and Alexa integration testing.

Run the checks after any code change:

```bash
python3 -m compileall -q controller lambda tools
python3 -m unittest discover -s tests -v
bash -n ffmpeg/start-camera.sh
```

Before committing, check `git diff --cached`, look for private RTSP URLs or signing keys, and verify that `local/`, `.env` and `config/cameras.json` are ignored.
