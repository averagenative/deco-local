# deco-local tasks. There is no CI: run `make check` before you push.
PY ?= python3

.PHONY: check web demo desktop docker docker-build publish-image appimage install uninstall

check:
	$(PY) -m py_compile deco_api.py deco_demo.py deco_features.py deco_log.py deco_rest.py deco_snapshot.py deco_disruptive_test.py \
	    deco_desktop/*.py deco_desktop/screens/*.py
	sh -n packaging/install.sh
	sh -n packaging/appimage/AppRun
	bash -n packaging/build-appimage.sh
	bash -n packaging/appimage/build-appdir.sh
	bash -n packaging/publish-image.sh
	@echo "check: ok"

# Web UI + REST API on http://127.0.0.1:8777/ (needs fastapi, uvicorn, paramiko).
web:
	$(PY) deco_rest.py

# The same, against an in-memory demo mesh (no Deco needed).
demo:
	DECO_DEMO=1 $(PY) deco_rest.py

# The GTK desktop app from source (needs PyGObject with GTK 4, and paramiko).
desktop:
	./deco-desktop

# Web UI + REST API in a container (needs deco.env; see deco.env.example). Pulls the image.
docker:
	docker compose up -d

# Build the container image locally under the published name.
docker-build:
	docker build -t ghcr.io/averagenative/deco-local:latest .

# Build for amd64 + arm64 and push to ghcr.io (run from a clean deco-local checkout).
publish-image:
	packaging/publish-image.sh

# dist/DecoDesktop-<version>-x86_64.AppImage, built in a Debian 13 container.
appimage: check
	packaging/build-appimage.sh

# Copy the newest AppImage to ~/Applications and add it to the app menu.
install:
	packaging/install.sh

uninstall:
	packaging/install.sh --uninstall
