"""Page Object del dashboard."""

from playwright.sync_api import Page


class DashboardPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url
        tid = page.get_by_test_id
        self.gauge_pct = tid("gauge-pct")
        self.gauge_label = tid("gauge-label")
        self.gauge_note = tid("gauge-note")
        self.gauge_mah = tid("gauge-mah")
        self.level = tid("m-level")
        self.temp = tid("m-temp")
        self.error_banner = tid("error-banner")
        self.status = tid("status-dot")
        self.model_select = tid("model-select")
        self.refresh_btn = tid("refresh-btn")
        self.reno_level = tid("reno-level")
        self.reno_summary = tid("reno-summary")
        self.chart = tid("health-chart")
        self.chart_empty = tid("chart-empty")
        self.chart_subtitle = tid("chart-subtitle")
        self.total = tid("s-total")
        self.trend_note = tid("trend-note")
        self.alerts = tid("alerts-list")
        self.export_link = tid("export-link")

    def goto(self):
        with self.page.expect_response(lambda r: "/api/renovation" in r.url):
            self.page.goto(self.base_url)

    def refresh(self):
        with self.page.expect_response(lambda r: "/api/stats" in r.url):
            self.refresh_btn.click()

    def show_tab(self, testid: str):
        with self.page.expect_response(lambda r: "/api/history" in r.url):
            self.page.get_by_test_id(testid).click()
