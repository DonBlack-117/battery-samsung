import re

from playwright.sync_api import Page, expect

from tests.e2e.pages import DashboardPage


def test_shows_current_health(page: Page, app_url):
    d = DashboardPage(page, app_url)
    d.goto()
    expect(d.gauge_pct).to_have_text("99.6%")
    expect(d.gauge_label).to_have_text("Excelente")
    expect(d.gauge_mah).to_have_text("4981 mAh")
    expect(d.level).to_have_text("80")
    expect(d.temp).to_have_text("31.2")
    expect(d.status).to_have_text("teléfono conectado")
    expect(d.error_banner).to_be_hidden()


def test_detected_model_is_selected(page: Page, app_url):
    d = DashboardPage(page, app_url)
    d.goto()
    expect(d.model_select).to_have_value("S24 Ultra")
    expect(d.export_link).to_have_attribute("href", re.compile(r"model=S24\+Ultra"))


def test_protect_battery_alert(page: Page, app_url):
    d = DashboardPage(page, app_url)
    d.goto()
    expect(d.alerts).to_contain_text("Proteger batería")


def test_renovation_panel(page: Page, app_url):
    d = DashboardPage(page, app_url)
    d.goto()
    expect(d.reno_level).to_have_text("Bajo")
    expect(d.reno_summary).to_contain_text("Sin verificar: ciclos de carga")
    expect(page.get_by_test_id("reno-risks")).to_have_text("Ninguna.")


def test_phone_disconnected_shows_error(page: Page, app_url, fake_shell):
    from battery_sam.adb import DeviceNotConnectedError

    fake_shell.error = DeviceNotConnectedError("No se detectó ningún teléfono.")
    d = DashboardPage(page, app_url)
    d.goto()
    expect(d.error_banner).to_be_visible()
    expect(d.error_banner).to_contain_text("No se detectó ningún teléfono.")
    expect(d.status).to_have_text("sin conexión")
    expect(d.gauge_pct).to_have_text("—")


def test_recovers_after_reconnect(page: Page, app_url, fake_shell):
    from battery_sam.adb import DeviceNotConnectedError

    fake_shell.error = DeviceNotConnectedError("No se detectó ningún teléfono.")
    d = DashboardPage(page, app_url)
    d.goto()
    expect(d.error_banner).to_be_visible()
    fake_shell.error = None
    d.refresh()
    expect(d.error_banner).to_be_hidden()
    expect(d.gauge_pct).to_have_text("99.6%")


def test_low_battery_explains_missing_health(page: Page, app_url, fake_shell):
    dumpsys = fake_shell.values["dumpsys"].replace("level: 80", "level: 12")
    fake_shell.values["dumpsys"] = dumpsys
    d = DashboardPage(page, app_url)
    d.goto()
    expect(d.gauge_pct).to_have_text("—")
    expect(d.gauge_note).to_be_visible()
    expect(d.gauge_note).to_contain_text("menos de 20 %")


def test_session_chart_then_history(page: Page, app_url):
    d = DashboardPage(page, app_url)
    d.goto()
    expect(d.chart).to_be_visible()
    expect(d.chart_subtitle).to_contain_text("1 lectura")
    d.refresh()
    expect(d.chart_subtitle).to_contain_text("2 lecturas")

    d.show_tab("tab-30")
    expect(page.get_by_test_id("tab-30")).to_have_attribute("aria-selected", "true")
    expect(d.chart_subtitle).to_contain_text("lecturas guardadas en 1 día")
    expect(d.chart).to_be_visible()


def test_history_counter_grows(page: Page, app_url):
    d = DashboardPage(page, app_url)
    d.goto()
    expect(d.total).not_to_have_text("—")
    before = int(d.total.inner_text())
    d.refresh()
    expect(d.total).to_have_text(str(before + 1))
    expect(d.trend_note).to_contain_text("al menos 2 días")


def test_changing_model_reloads(page: Page, app_url):
    d = DashboardPage(page, app_url)
    d.goto()
    with page.expect_response(lambda r: "/api/current" in r.url and "S23" in r.url):
        d.model_select.select_option("S23")
    # 4981 mAh contra 3900 de fábrica da más de 101 %: se descarta
    expect(d.gauge_pct).to_have_text("—")
    expect(d.gauge_note).to_contain_text("valor imposible")


def test_no_external_requests(page: Page, app_url):
    external = []
    page.on("request", lambda r: external.append(r.url) if not r.url.startswith(app_url) else None)
    d = DashboardPage(page, app_url)
    d.goto()
    expect(d.gauge_pct).to_have_text("99.6%")
    assert external == []


def test_mobile_layout_has_no_horizontal_scroll(page: Page, app_url):
    page.set_viewport_size({"width": 375, "height": 800})
    d = DashboardPage(page, app_url)
    d.goto()
    expect(d.gauge_pct).to_have_text("99.6%")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_unknown_samsung_model_is_not_saved(page: Page, app_url, fake_shell):
    from tests.fakes import S24_ULTRA

    fake_shell.values = {**S24_ULTRA, "marketname": "", "model": "SM-X999"}
    d = DashboardPage(page, app_url)
    d.goto()
    expect(page.get_by_test_id("device-chip")).to_contain_text("SM-X999 no reconocido")
    expect(d.total).not_to_have_text("—")
    before = d.total.inner_text()
    d.refresh()
    expect(d.total).to_have_text(before)
    # Al elegir el modelo a mano sí se guarda
    with page.expect_response(lambda r: "/api/stats" in r.url):
        d.model_select.select_option("S24 Ultra")
    expect(d.total).to_have_text(str(int(before) + 1))
