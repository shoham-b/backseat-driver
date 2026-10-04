"""Drives the model-comparison page in a real browser, the way a person would."""

import pytest

pytest.importorskip("selenium", reason="selenium is not installed")

from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait

from tests.uitests.conftest import PHONE, SCENES


def _scene_titles(page: WebDriver) -> list[str]:
    return [h.text for h in page.find_elements(By.CSS_SELECTOR, "#scenes .scene h3")]


def _summary_rows(page: WebDriver) -> list[list[str]]:
    rows = page.find_elements(By.CSS_SELECTOR, "#summary tr")[1:]  # the first row is the header
    return [[cell.text for cell in row.find_elements(By.TAG_NAME, "td")] for row in rows]


def _model_checkbox(page: WebDriver, model: str):
    return page.find_element(By.XPATH, f"//div[@id='models']//label[normalize-space()='{model}']/input")


def _severe_console_messages(page: WebDriver) -> list[str]:
    return [entry["message"] for entry in page.get_log("browser") if entry["level"] in {"SEVERE", "ERROR"}]


def test_page_lists_every_scene_and_summarises_the_models(page: WebDriver) -> None:
    assert page.title == "Backseat Driver Report"
    assert page.find_element(By.ID, "subtitle").text == "3 scenes · 2 model(s)"
    assert _scene_titles(page) == [name for name, _ in SCENES]
    assert page.find_element(By.CSS_SELECTOR, "#scenes .scene .ref").text == f"Reference: {SCENES[0][1]}"


def test_metrics_table_ranks_models_by_f1_best_first(page: WebDriver) -> None:
    rows = _summary_rows(page)

    assert [row[0] for row in rows] == ["claude-haiku", "blip-base"]
    assert rows[0][1] == "3/3 scored"
    assert float(rows[0][4].rstrip("%")) > float(rows[1][4].rstrip("%"))


def test_matching_words_are_highlighted_against_the_reference_label(page: WebDriver) -> None:
    first_scene = page.find_element(By.CSS_SELECTOR, "#scenes .scene")

    highlighted = {mark.text.lower() for mark in first_scene.find_elements(By.TAG_NAME, "mark")}

    assert {"truck", "parked", "construction"} <= highlighted


def test_keyframe_images_are_inlined_and_actually_load(page: WebDriver) -> None:
    WebDriverWait(page, 5).until(
        lambda d: all(i.get_property("complete") for i in d.find_elements(By.CSS_SELECTOR, "#scenes img"))
    )

    sizes = [img.get_property("naturalWidth") for img in page.find_elements(By.CSS_SELECTOR, "#scenes img")]

    assert sizes == [64, 64, 64]
    assert all(
        (img.get_attribute("src") or "").startswith("data:image/")
        for img in page.find_elements(By.CSS_SELECTOR, "#scenes img")
    )


def test_scene_filter_shows_one_scene_and_rescopes_the_metrics(page: WebDriver) -> None:
    Select(page.find_element(By.ID, "scene")).select_by_visible_text("scene-0103")

    assert _scene_titles(page) == ["scene-0103"]
    assert page.find_element(By.ID, "metrics-scope").text == "· selected scene"
    assert [row[1] for row in _summary_rows(page)] == ["1/1 scored", "1/1 scored"]

    Select(page.find_element(By.ID, "scene")).select_by_visible_text("All scenes")

    assert len(_scene_titles(page)) == 3


def test_search_filters_descriptions_and_leaves_unmatched_models_with_nothing_scored(page: WebDriver) -> None:
    page.find_element(By.ID, "search").send_keys("pedestrian")

    assert _scene_titles(page) == ["scene-0103"]
    assert [row[:2] for row in _summary_rows(page)] == [
        ["claude-haiku", "1/1 scored"],
        ["blip-base", "0/0 scored"],  # blip never said "pedestrian"
    ]


def test_unticking_a_model_hides_it_everywhere(page: WebDriver) -> None:
    _model_checkbox(page, "blip-base").click()

    entries = [e.text for e in page.find_elements(By.CSS_SELECTOR, "#scenes .entry .model")]

    assert set(entries) == {"claude-haiku"}
    assert [row[0] for row in _summary_rows(page)] == ["claude-haiku"]


def test_filters_that_match_nothing_show_an_empty_state(page: WebDriver) -> None:
    page.find_element(By.ID, "search").send_keys("zebra crossing")

    assert page.find_element(By.CSS_SELECTOR, "#scenes .empty").text == "No descriptions match the current filters."


def test_clearing_the_search_restores_every_scene(page: WebDriver) -> None:
    search = page.find_element(By.ID, "search")
    search.send_keys("pedestrian")

    search.send_keys(Keys.CONTROL, "a", Keys.BACKSPACE)  # `clear()` fires `change`, which real typing never does

    assert len(_scene_titles(page)) == 3


def test_the_page_logs_no_console_errors_through_a_full_interaction(page: WebDriver) -> None:
    Select(page.find_element(By.ID, "scene")).select_by_index(1)
    page.find_element(By.ID, "search").send_keys("road")
    _model_checkbox(page, "claude-haiku").click()

    assert _severe_console_messages(page) == []


def test_the_page_does_not_scroll_sideways_on_a_phone(page: WebDriver) -> None:
    page.set_window_size(*PHONE)

    overflow = page.execute_script("return document.documentElement.scrollWidth - window.innerWidth")

    assert overflow <= 0
    assert page.find_element(By.CSS_SELECTOR, "#summary").is_displayed()


def test_phone_layout_stacks_the_image_above_the_text(page: WebDriver) -> None:
    page.set_window_size(*PHONE)
    scene = page.find_element(By.CSS_SELECTOR, "#scenes .scene")

    image, heading = scene.find_element(By.TAG_NAME, "img"), scene.find_element(By.TAG_NAME, "h3")

    assert heading.location["y"] > image.location["y"] + image.size["height"] - 1


def _camera_badges(page: WebDriver) -> list[str]:
    return [b.text for b in page.find_elements(By.CSS_SELECTOR, "#scenes .scene .camera")]


def test_every_scene_card_names_the_camera_position(page: WebDriver) -> None:
    assert _camera_badges(page) == ["Front"] * len(SCENES)
    assert not page.find_element(By.ID, "cameras-filter").is_displayed()


def test_several_cameras_of_a_scene_share_one_card_with_a_tab_each_and_a_filter(multi_camera_page: WebDriver) -> None:
    page = multi_camera_page

    assert page.find_element(By.ID, "subtitle").text == "1 scenes · 1 model(s) · 2 cameras"
    assert _scene_titles(page) == [SCENES[0][0]]
    assert _camera_badges(page) == ["Back left", "Front"]
    assert len(page.find_elements(By.CSS_SELECTOR, "#scene optgroup[label='Single scene'] option")) == 1


def test_the_camera_filter_hides_the_unticked_cameras(multi_camera_page: WebDriver) -> None:
    page = multi_camera_page

    page.find_element(By.XPATH, "//div[@id='cameras']//label[normalize-space()='Front']/input").click()

    assert _camera_badges(page) == ["Back left"]


def test_picking_a_camera_tab_switches_the_image_of_that_scene(multi_camera_page: WebDriver) -> None:
    page = multi_camera_page
    before = page.find_element(By.CSS_SELECTOR, "#scenes .scene img").get_attribute("alt")

    tab = page.find_element(By.XPATH, "//div[@id='scenes']//button[normalize-space()='Front']")
    page.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'instant'})", tab)
    tab.click()

    after = page.find_element(By.CSS_SELECTOR, "#scenes .scene img").get_attribute("alt")
    assert before.startswith("Back left")
    assert after.startswith("Front")
