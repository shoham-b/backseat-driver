from backseat_driver.reporting.html_report_writer import load_template


def test_page_grid_cannot_be_widened_by_the_no_wrap_metrics_table() -> None:
    template = load_template()

    # A bare `display: grid` track grows to fit the table's min-content, so the page scrolled sideways on phones
    # instead of the table scrolling inside its own wrapper.
    assert "grid-template-columns: minmax(0, 1fr)" in template


def test_page_declares_an_icon_so_browsers_do_not_request_a_favicon() -> None:
    template = load_template()

    assert '<link rel="icon"' in template
