import json
import os
import unittest

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from tools.qml_smoke import FakeBridge


class NavigationBridge(FakeBridge):
    openMaintenanceRequested = Signal()


class UnifiedSettingsNavigationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlEngine()
        self.bridge = NavigationBridge()
        self.engine.rootContext().setContextProperty("bridge", self.bridge)
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "components", "AppShell.qml")
        self.component = QQmlComponent(self.engine, QUrl.fromLocalFile(path))
        self.assertFalse(self.component.isError(), [error.toString() for error in self.component.errors()])
        self.shell = self.component.create()
        self.assertIsNotNone(self.shell)
        self.shell.setProperty("width", 1920)
        self.shell.setProperty("height", 720)
        self.app.processEvents()

    def tearDown(self):
        self.engine.deleteLater()

    def test_rail_is_permanent_and_routes_do_not_build_history(self):
        rail = self.shell.findChild(QObject, "settingsNavigationRail")
        self.assertIsNotNone(rail)
        self.assertEqual(rail.property("width"), 288.0)
        self.assertIsNone(self.shell.property("history"))

        for requested, canonical in (
            ("menu", "driving"), ("appearance", "appearance"),
            ("diagnostic", "vehicle"), ("services", "advanced"),
            ("maintenance", "system"),
        ):
            self.shell.openRoute(requested)
            self.assertEqual(self.shell.property("route"), canonical)

        self.shell.openRoute("home")
        self.assertEqual(self.shell.property("route"), "home")

    def test_map_route_is_fullscreen_and_returns_to_cockpit(self):
        self.shell.openRoute("map")
        self.app.processEvents()
        self.assertEqual(self.shell.property("route"), "map")
        page = self.shell.findChild(QObject, "mapPage")
        self.assertIsNotNone(page)
        settings = self.shell.findChild(QObject, "unifiedSettingsShell")
        self.assertFalse(settings.property("visible"))

        page.cockpitRequested.emit()
        self.app.processEvents()
        self.assertEqual(self.shell.property("route"), "home")
        self.assertFalse(self.shell.findChild(QObject, "mapLoader").property("active"))

    def test_live_page_adds_tiles_and_saves_limits(self):
        def saved_tiles():
            return json.loads(self.bridge._config["ui"]["live_tiles"])

        self.shell.openRoute("data")
        self.app.processEvents()
        self.assertEqual(self.shell.property("route"), "live")
        page = self.shell.findChild(QObject, "liveDataPage")
        self.assertIsNotNone(page)
        initial = len(page.property("tiles").toVariant())

        page.addTile("navigation", "gps_speed")
        self.app.processEvents()
        tiles = saved_tiles()
        self.assertEqual(len(tiles), initial + 1)
        self.assertEqual(tiles[-1]["key"], "gps_speed")

        page.setLimits(0, "", "6500,5")
        tiles = saved_tiles()
        self.assertIsNone(tiles[0]["low"])
        self.assertEqual(tiles[0]["high"], 6500.5)

        page.moveTile(0, 1)
        page.removeTile(0)
        self.assertEqual(len(saved_tiles()), initial)

    def test_legacy_maintenance_signal_opens_storage(self):
        self.bridge.openMaintenanceRequested.emit()
        self.app.processEvents()
        self.assertEqual(self.shell.property("route"), "system")
        self.assertEqual(self.shell.property("requestedRoute"), "maintenance")

    def test_alias_within_same_section_switches_the_visible_tab(self):
        self.shell.openRoute("appearance")
        self.app.processEvents()
        appearance = self.shell.findChild(QObject, "appearanceSettingsPage")
        self.assertIsNotNone(appearance)
        self.assertEqual(appearance.property("tab"), 0)

        self.shell.openRoute("accent")
        self.app.processEvents()
        self.assertEqual(appearance.property("tab"), 1)

        self.shell.openRoute("system")
        self.app.processEvents()
        system = self.shell.findChild(QObject, "systemSettingsPage")
        self.assertIsNotNone(system)
        self.shell.openRoute("updates")
        self.app.processEvents()
        self.assertEqual(system.property("tab"), 1)

    def test_services_tab_reuses_expandable_parameter_rows(self):
        self.shell.openRoute("services")
        self.app.processEvents()
        QTest.qWait(50)
        page = self.shell.findChild(QObject, "servicesSettingsPage")
        self.assertIsNotNone(page)
        self.assertTrue(page.property("embedded"))

        self.assertFalse(page.serviceExpanded("CAN_Engine"))
        self.assertTrue(page.toggleServiceDetails("CAN_Engine"))
        self.app.processEvents()
        self.assertTrue(page.serviceExpanded("CAN_Engine"))


if __name__ == "__main__":
    unittest.main()
