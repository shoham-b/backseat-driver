from backseat_driver.reporting.report_template import TEMPLATE


def test_page_grid_cannot_be_widened_by_the_no_wrap_metrics_table() -> None:
    # A bare `display: grid` track grows to fit the table's min-content, so the page scrolled sideways on phones
    # instead of the table scrolling inside its own wrapper.
    assert "grid-template-columns: minmax(0, 1fr)" in TEMPLATE


def test_page_declares_an_icon_so_browsers_do_not_request_a_favicon() -> None:
    assert '<link rel="icon"' in TEMPLATE
