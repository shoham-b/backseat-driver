"""Browser fixtures: the real `backseat-driver ui` server in a subprocess, driven by headless Chrome via Selenium.

Set CHROME_BIN / CHROMEDRIVER to use a specific browser and driver; otherwise Selenium Manager finds or downloads
them. A browser that cannot start fails the test run on purpose — a silently skipped UI suite proves nothing.
"""

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from backseat_driver.models import SceneDescription

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver

SCENES = [
    ("scene-0061", "Parked truck, construction ahead"),
    ("scene-0103", "Wait at intersection, peds crossing"),
    ("scene-0553", "Night, rain, turn right"),
]
DESCRIPTIONS = {
    "blip-base": ["a truck parked on the street", "a street with cars", "a dark road"],
    "claude-haiku": [
        "A parked truck beside construction cones on a city road.",
        "Intersection with pedestrians crossing in front of the car.",
        "Night driving in rain; road curves to the right.",
    ],
}
PHONE = (390, 800)
DESKTOP = (1200, 900)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def result_files(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    root = tmp_path_factory.mktemp("ui-results")
    images = []
    for index, (name, _) in enumerate(SCENES):
        image = root / f"{name}.jpg"
        Image.new("RGB", (64, 36), (40 + index * 60, 90, 140)).save(image)
        images.append(image)
    files = []
    for model, descriptions in DESCRIPTIONS.items():
        rows = [
            SceneDescription(
                scene_token=f"token-{i}",
                scene_name=name,
                camera_channel="CAM_FRONT",
                image_path=str(images[i]),
                description=description,
                model_name=model,
                reference_description=reference,
            ).model_dump(mode="json")
            for i, ((name, reference), description) in enumerate(zip(SCENES, descriptions, strict=True))
        ]
        path = root / f"{model}.json"
        path.write_text(json.dumps(rows))
        files.append(path)
    return files


def _serve_ui(result_files: list[Path]) -> Iterator[str]:
    port = _free_port()
    env = {**os.environ, "BACKSEAT_DRIVER_UI_PORT": str(port)}  # exercises the Settings -> command wiring too
    command = [sys.executable, "-m", "backseat_driver.cli", "ui", "--no-open", *map(str, result_files)]
    server = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if server.poll() is not None:
                pytest.fail(
                    f"`ui` exited early ({server.returncode}):\n{server.stdout.read() if server.stdout else ''}"
                )
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.2)
        else:
            pytest.fail("`ui` did not start listening within 30s")
        yield f"http://127.0.0.1:{port}/"
    finally:
        server.terminate()
        server.wait(timeout=10)
        if server.stdout:
            server.stdout.close()


@pytest.fixture(scope="session")
def _driver() -> Iterator["WebDriver"]:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    options = Options()
    options.add_argument("--headless=new")
    # Containers and CI runners usually lack the user namespaces Chrome's sandbox needs.
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    if chrome := os.environ.get("CHROME_BIN"):
        options.binary_location = chrome
    service = Service(executable_path=os.environ["CHROMEDRIVER"]) if "CHROMEDRIVER" in os.environ else Service()
    driver = webdriver.Chrome(options=options, service=service)
    try:
        yield driver
    finally:
        driver.quit()


@pytest.fixture
def page(_driver: "WebDriver", ui_url: str) -> "WebDriver":
    """The report, freshly loaded at desktop size with an empty browser log."""
    _driver.set_window_size(*DESKTOP)
    _driver.get(ui_url)
    _driver.get_log("browser")  # reading drains it, so a test only sees errors from its own interactions
    return _driver


@pytest.fixture(scope="session")
def ui_url(result_files: list[Path]) -> Iterator[str]:
    yield from _serve_ui(result_files)


@pytest.fixture(scope="session")
def multi_camera_result_files(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """One model describing the first scene through the front and the back-left cameras."""
    root = tmp_path_factory.mktemp("ui-multi-camera")
    name, reference = SCENES[0]
    rows = []
    for index, channel in enumerate(["CAM_FRONT", "CAM_BACK_LEFT"]):
        image = root / f"{channel}.jpg"
        Image.new("RGB", (64, 36), (40 + index * 90, 90, 140)).save(image)
        rows.append(
            SceneDescription(
                scene_token="token-0",
                scene_name=name,
                camera_channel=channel,
                image_path=str(image),
                description=f"a view from {channel}",
                model_name="blip-base",
                reference_description=reference,
            ).model_dump(mode="json")
        )
    path = root / "blip-base.json"
    path.write_text(json.dumps(rows))
    return [path]


@pytest.fixture(scope="session")
def multi_camera_url(multi_camera_result_files: list[Path]) -> Iterator[str]:
    yield from _serve_ui(multi_camera_result_files)


@pytest.fixture
def multi_camera_page(_driver: "WebDriver", multi_camera_url: str) -> "WebDriver":
    _driver.set_window_size(*DESKTOP)
    _driver.get(multi_camera_url)
    return _driver
