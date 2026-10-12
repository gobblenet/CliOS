"""Panneau de contrôle graphique complet pour la simulation et le moteur physique de CliOS."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QComboBox, QTabWidget, QProgressBar, QGroupBox, QGridLayout,
    QLineEdit, QCheckBox
)


class MockControlPanel(QWidget):
    """Fenêtre de débogage et de contrôle multi-onglets pour la simulation véhicule."""

    def __init__(self, physics_mock):
        super().__init__()
        self.mock = physics_mock
        self.setWindowTitle("CliOS - Simulation & Physics Control Panel")
        self.resize(520, 560)

        # Active la réception du focus clavier pour le pilotage
        self.setFocusPolicy(Qt.StrongFocus)

        main_layout = QVBoxLayout()
        self.tabs = QTabWidget()

        # Construction des 5 onglets
        self._init_tab_driving()
        self._init_tab_body_lights()
        self._init_tab_scenarios()
        self._init_tab_diagnostics()
        self._init_tab_telemetry()

        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        # Timer de rafraîchissement télémétrie UI à 10 Hz
        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._refresh_telemetry_ui)
        self._ui_timer.start(100)

        # Branchement du callback de scénario
        self.mock.scenario_runner.set_progress_callback(self._on_scenario_progress)

    # =========================================================================
    # ONGLET 1 : PILOTAGE & DYNAMIQUE
    # =========================================================================

    def _init_tab_driving(self):
        tab = QWidget()
        layout = QVBoxLayout()

        # Contact et Starter
        pwr_group = QGroupBox("Power & Engine")
        pwr_layout = QHBoxLayout()

        self.btn_ignition = QPushButton("Ignition: ON")
        self.btn_ignition.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 6px;")
        self.btn_ignition.clicked.connect(self._toggle_ignition)
        pwr_layout.addWidget(self.btn_ignition)

        self.btn_starter = QPushButton("Starter")
        self.btn_starter.setStyleSheet("background-color: #f0ad4e; color: white; font-weight: bold; padding: 6px;")
        self.btn_starter.pressed.connect(lambda: self.mock.set_starter(True))
        self.btn_starter.released.connect(lambda: self.mock.set_starter(False))
        pwr_layout.addWidget(self.btn_starter)

        pwr_group.setLayout(pwr_layout)
        layout.addWidget(pwr_group)

        # Boîte de vitesses et Handbrake
        trans_group = QGroupBox("Transmission & Parking")
        trans_layout = QHBoxLayout()

        trans_layout.addWidget(QLabel("Gear:"))
        self.combo_gear = QComboBox()
        self.combo_gear.addItems(["R (Reverse)", "N (Neutral)", "1st", "2nd", "3rd", "4th", "5th", "6th"])
        self.combo_gear.setCurrentIndex(1)  # N par défaut
        self.combo_gear.currentIndexChanged.connect(self._on_gear_selected)
        trans_layout.addWidget(self.combo_gear)

        self.chk_handbrake = QCheckBox("Handbrake")
        self.chk_handbrake.toggled.connect(lambda val: setattr(self.mock, 'handbrake', val))
        trans_layout.addWidget(self.chk_handbrake)

        trans_group.setLayout(trans_layout)
        layout.addWidget(trans_group)

        # Pédales
        pedals_group = QGroupBox("Pedals & Steering")
        pedals_layout = QGridLayout()

        # Accélérateur
        pedals_layout.addWidget(QLabel("Throttle (0-100%):"), 0, 0)
        self.slider_throttle = QSlider(Qt.Horizontal)
        self.slider_throttle.setRange(0, 100)
        self.slider_throttle.valueChanged.connect(lambda val: setattr(self.mock, 'throttle', float(val)))
        self.lbl_throttle = QLabel("0%")
        self.slider_throttle.valueChanged.connect(lambda val: self.lbl_throttle.setText(f"{val}%"))
        pedals_layout.addWidget(self.slider_throttle, 0, 1)
        pedals_layout.addWidget(self.lbl_throttle, 0, 2)

        # Frein
        pedals_layout.addWidget(QLabel("Brake (0-100%):"), 1, 0)
        self.slider_brake = QSlider(Qt.Horizontal)
        self.slider_brake.setRange(0, 100)
        self.slider_brake.valueChanged.connect(lambda val: setattr(self.mock, 'brake', float(val)))
        self.lbl_brake = QLabel("0%")
        self.slider_brake.valueChanged.connect(lambda val: self.lbl_brake.setText(f"{val}%"))
        pedals_layout.addWidget(self.slider_brake, 1, 1)
        pedals_layout.addWidget(self.lbl_brake, 1, 2)

        # Embrayage
        pedals_layout.addWidget(QLabel("Clutch (0-100%):"), 2, 0)
        self.slider_clutch = QSlider(Qt.Horizontal)
        self.slider_clutch.setRange(0, 100)
        self.slider_clutch.valueChanged.connect(lambda val: setattr(self.mock, 'clutch', float(val)))
        self.lbl_clutch = QLabel("0%")
        self.slider_clutch.valueChanged.connect(lambda val: self.lbl_clutch.setText(f"{val}%"))
        pedals_layout.addWidget(self.slider_clutch, 2, 1)
        pedals_layout.addWidget(self.lbl_clutch, 2, 2)

        # Direction / Volant
        pedals_layout.addWidget(QLabel("Steering (-180° to +180°):"), 3, 0)
        self.slider_steer = QSlider(Qt.Horizontal)
        self.slider_steer.setRange(-180, 180)
        self.slider_steer.setValue(0)
        self.slider_steer.valueChanged.connect(lambda val: setattr(self.mock, 'steering', float(val)))
        self.lbl_steer = QLabel("0°")
        self.slider_steer.valueChanged.connect(lambda val: self.lbl_steer.setText(f"{val}°"))
        pedals_layout.addWidget(self.slider_steer, 3, 1)
        pedals_layout.addWidget(self.lbl_steer, 3, 2)

        pedals_group.setLayout(pedals_layout)
        layout.addWidget(pedals_group)

        # Bouton remise à zéro
        btn_reset_pedals = QPushButton("Release all pedals and center the wheel")
        btn_reset_pedals.clicked.connect(self._reset_all_controls)
        layout.addWidget(btn_reset_pedals)

        layout.addStretch()
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Driving")

    # =========================================================================
    # ONGLET 2 : CARROSSERIE & FEUX
    # =========================================================================

    def _init_tab_body_lights(self):
        tab = QWidget()
        layout = QVBoxLayout()

        # Éclairage
        lights_group = QGroupBox("Lighting & Signals")
        lights_layout = QGridLayout()

        self.chk_pos = QCheckBox("Parking lights")
        self.chk_pos.toggled.connect(lambda v: setattr(self.mock.engine.state, 'pos_lights', v))
        lights_layout.addWidget(self.chk_pos, 0, 0)

        self.chk_low = QCheckBox("Low beam")
        self.chk_low.toggled.connect(lambda v: setattr(self.mock.engine.state, 'low_beam', v))
        lights_layout.addWidget(self.chk_low, 0, 1)

        self.chk_high = QCheckBox("High beam")
        self.chk_high.toggled.connect(lambda v: setattr(self.mock.engine.state, 'high_beam', v))
        lights_layout.addWidget(self.chk_high, 0, 2)

        self.chk_fog_f = QCheckBox("Front fog lights")
        self.chk_fog_f.toggled.connect(lambda v: setattr(self.mock.engine.state, 'fog_front', v))
        lights_layout.addWidget(self.chk_fog_f, 1, 0)

        self.chk_fog_r = QCheckBox("Rear fog light")
        self.chk_fog_r.toggled.connect(lambda v: setattr(self.mock.engine.state, 'fog_rear', v))
        lights_layout.addWidget(self.chk_fog_r, 1, 1)

        self.chk_hazard = QCheckBox("Hazard lights")
        self.chk_hazard.toggled.connect(lambda v: setattr(self.mock.engine.state, 'hazard', v))
        lights_layout.addWidget(self.chk_hazard, 1, 2)

        self.chk_turn_l = QCheckBox("Left turn signal")
        self.chk_turn_l.toggled.connect(lambda v: setattr(self.mock.engine.state, 'turn_left', v))
        lights_layout.addWidget(self.chk_turn_l, 2, 0)

        self.chk_turn_r = QCheckBox("Right turn signal")
        self.chk_turn_r.toggled.connect(lambda v: setattr(self.mock.engine.state, 'turn_right', v))
        lights_layout.addWidget(self.chk_turn_r, 2, 1)

        lights_group.setLayout(lights_layout)
        layout.addWidget(lights_group)

        # Portières et Sécurité
        doors_group = QGroupBox("Doors & Cabin")
        doors_layout = QGridLayout()

        self.chk_d_fl = QCheckBox("Front left door")
        self.chk_d_fl.toggled.connect(lambda v: setattr(self.mock.engine.state, 'door_fl_open', v))
        doors_layout.addWidget(self.chk_d_fl, 0, 0)

        self.chk_d_fr = QCheckBox("Front right door")
        self.chk_d_fr.toggled.connect(lambda v: setattr(self.mock.engine.state, 'door_fr_open', v))
        doors_layout.addWidget(self.chk_d_fr, 0, 1)

        self.chk_d_rl = QCheckBox("Rear left door")
        self.chk_d_rl.toggled.connect(lambda v: setattr(self.mock.engine.state, 'door_rl_open', v))
        doors_layout.addWidget(self.chk_d_rl, 1, 0)

        self.chk_d_rr = QCheckBox("Rear right door")
        self.chk_d_rr.toggled.connect(lambda v: setattr(self.mock.engine.state, 'door_rr_open', v))
        doors_layout.addWidget(self.chk_d_rr, 1, 1)

        self.chk_trunk = QCheckBox("Trunk open")
        self.chk_trunk.toggled.connect(lambda v: setattr(self.mock.engine.state, 'trunk_open', v))
        doors_layout.addWidget(self.chk_trunk, 2, 0)

        self.chk_belt = QCheckBox("Seatbelt unbuckled")
        self.chk_belt.toggled.connect(lambda v: setattr(self.mock.engine.state, 'driver_unbelted', v))
        doors_layout.addWidget(self.chk_belt, 2, 1)

        doors_group.setLayout(doors_layout)
        layout.addWidget(doors_group)

        # Météo et Température extérieure
        env_group = QGroupBox("Environment")
        env_layout = QHBoxLayout()
        env_layout.addWidget(QLabel("Outside temperature (-20°C to 45°C):"))
        self.slider_ext_temp = QSlider(Qt.Horizontal)
        self.slider_ext_temp.setRange(-20, 45)
        self.slider_ext_temp.setValue(21)
        self.lbl_ext_temp = QLabel("21°C")
        self.slider_ext_temp.valueChanged.connect(self._on_ext_temp_changed)
        env_layout.addWidget(self.slider_ext_temp)
        env_layout.addWidget(self.lbl_ext_temp)
        env_group.setLayout(env_layout)
        layout.addWidget(env_group)

        layout.addStretch()
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Body & Lights")

    # =========================================================================
    # ONGLET 3 : SCÉNARIOS & PILOTE AUTO
    # =========================================================================

    def _init_tab_scenarios(self):
        tab = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Select an automated test scenario:"))

        self.combo_scenarios = QComboBox()
        for s_name in self.mock.scenarios.keys():
            self.combo_scenarios.addItem(s_name)
        self.combo_scenarios.currentIndexChanged.connect(self._on_scenario_selected)
        layout.addWidget(self.combo_scenarios)

        self.lbl_scenario_desc = QLabel("")
        self.lbl_scenario_desc.setWordWrap(True)
        self.lbl_scenario_desc.setStyleSheet("color: #666; font-style: italic; margin: 6px 0;")
        layout.addWidget(self.lbl_scenario_desc)
        self._on_scenario_selected(0)

        # Boutons d'action
        btn_layout = QHBoxLayout()
        self.btn_run_scenario = QPushButton("Run scenario")
        self.btn_run_scenario.setStyleSheet("background-color: #2d5b88; color: white; font-weight: bold; padding: 8px;")
        self.btn_run_scenario.clicked.connect(self._toggle_run_scenario)
        btn_layout.addWidget(self.btn_run_scenario)

        layout.addLayout(btn_layout)

        # Progression et état
        layout.addWidget(QLabel("Progress:"))
        self.progress_scenario = QProgressBar()
        self.progress_scenario.setRange(0, 100)
        self.progress_scenario.setValue(0)
        layout.addWidget(self.progress_scenario)

        self.lbl_scenario_step = QLabel("Waiting to start.")
        self.lbl_scenario_step.setStyleSheet("font-weight: bold; margin-top: 5px;")
        layout.addWidget(self.lbl_scenario_step)

        layout.addStretch()
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Scenarios")

    # =========================================================================
    # ONGLET 4 : DIAGNOSTIC & PANNES (OBD)
    # =========================================================================

    def _init_tab_diagnostics(self):
        tab = QWidget()
        layout = QVBoxLayout()

        dtc_group = QGroupBox("Fault Code Injection (OBD-II DTCs)")
        dtc_layout = QVBoxLayout()

        dtc_layout.addWidget(QLabel("Select codes or type new ones (space-separated):"))

        input_layout = QHBoxLayout()
        self.txt_dtc_input = QLineEdit("P0300 P0115")
        input_layout.addWidget(self.txt_dtc_input)

        btn_apply_dtcs = QPushButton("Inject DTCs")
        btn_apply_dtcs.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold;")
        btn_apply_dtcs.clicked.connect(self._apply_dtcs)
        input_layout.addWidget(btn_apply_dtcs)

        btn_clear_dtcs = QPushButton("Clear DTCs")
        btn_clear_dtcs.clicked.connect(self._clear_dtcs)
        input_layout.addWidget(btn_clear_dtcs)

        dtc_layout.addLayout(input_layout)

        # Raccourcis de pannes courantes
        quick_layout = QHBoxLayout()
        btn_p0300 = QPushButton("+ P0300 (Misfire)")
        btn_p0300.clicked.connect(lambda: self._append_dtc("P0300"))
        quick_layout.addWidget(btn_p0300)

        btn_p0115 = QPushButton("+ P0115 (Temp sensor)")
        btn_p0115.clicked.connect(lambda: self._append_dtc("P0115"))
        quick_layout.addWidget(btn_p0115)

        btn_p0420 = QPushButton("+ P0420 (Catalyst)")
        btn_p0420.clicked.connect(lambda: self._append_dtc("P0420"))
        quick_layout.addWidget(btn_p0420)

        dtc_layout.addLayout(quick_layout)

        self.lbl_active_dtcs = QLabel("Active DTCs in the ECU: none")
        self.lbl_active_dtcs.setStyleSheet("color: #d9534f; font-weight: bold; margin-top: 6px;")
        dtc_layout.addWidget(self.lbl_active_dtcs)

        dtc_group.setLayout(dtc_layout)
        layout.addWidget(dtc_group)

        # Forçage d'états critiques
        crit_group = QGroupBox("Force Alert States")
        crit_layout = QGridLayout()

        btn_overheat = QPushButton("Force overheating (110°C)")
        btn_overheat.clicked.connect(lambda: setattr(self.mock.engine.state, 'engine_temp_c', 110.0))
        crit_layout.addWidget(btn_overheat, 0, 0)

        btn_low_fuel = QPushButton("Force low fuel (3 L)")
        btn_low_fuel.clicked.connect(lambda: setattr(self.mock.engine.state, 'fuel_level_l', 3.0))
        crit_layout.addWidget(btn_low_fuel, 0, 1)

        btn_normal_temp = QPushButton("Normalize temperature (85°C)")
        btn_normal_temp.clicked.connect(lambda: setattr(self.mock.engine.state, 'engine_temp_c', 85.0))
        crit_layout.addWidget(btn_normal_temp, 1, 0)

        btn_fill_tank = QPushButton("Fill tank (50 L)")
        btn_fill_tank.clicked.connect(lambda: setattr(self.mock.engine.state, 'fuel_level_l', 50.0))
        crit_layout.addWidget(btn_fill_tank, 1, 1)

        crit_group.setLayout(crit_layout)
        layout.addWidget(crit_group)

        layout.addStretch()
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Diagnostic")

    # =========================================================================
    # ONGLET 5 : TÉLÉMÉTRIE EN DIRECT
    # =========================================================================

    def _init_tab_telemetry(self):
        tab = QWidget()
        layout = QVBoxLayout()

        grid = QGridLayout()

        self.lbl_live_speed = QLabel("0.0 km/h")
        self.lbl_live_rpm = QLabel("0 RPM")
        self.lbl_live_power = QLabel("0 hp (0.0 kW)")
        self.lbl_live_torque = QLabel("0.0 N·m")
        self.lbl_live_temp = QLabel("0.0 °C")
        self.lbl_live_fuel = QLabel("0.0 L")
        self.lbl_live_conso = QLabel("0.0 L/100")
        self.lbl_live_voltage = QLabel("0.0 V")
        self.lbl_live_wheels = QLabel("FL: 0 | FR: 0 | RL: 0 | RR: 0")

        grid.addWidget(QLabel("<b>Vehicle speed:</b>"), 0, 0)
        grid.addWidget(self.lbl_live_speed, 0, 1)

        grid.addWidget(QLabel("<b>Engine speed:</b>"), 1, 0)
        grid.addWidget(self.lbl_live_rpm, 1, 1)

        grid.addWidget(QLabel("<b>Engine torque:</b>"), 2, 0)
        grid.addWidget(self.lbl_live_torque, 2, 1)

        grid.addWidget(QLabel("<b>Estimated power:</b>"), 3, 0)
        grid.addWidget(self.lbl_live_power, 3, 1)

        grid.addWidget(QLabel("<b>Coolant temperature:</b>"), 4, 0)
        grid.addWidget(self.lbl_live_temp, 4, 1)

        grid.addWidget(QLabel("<b>Fuel level:</b>"), 5, 0)
        grid.addWidget(self.lbl_live_fuel, 5, 1)

        grid.addWidget(QLabel("<b>Instant consumption:</b>"), 6, 0)
        grid.addWidget(self.lbl_live_conso, 6, 1)

        grid.addWidget(QLabel("<b>Battery voltage:</b>"), 7, 0)
        grid.addWidget(self.lbl_live_voltage, 7, 1)

        grid.addWidget(QLabel("<b>Wheel speeds:</b>"), 8, 0)
        grid.addWidget(self.lbl_live_wheels, 8, 1)

        layout.addLayout(grid)
        layout.addStretch()
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Telemetry")

    # =========================================================================
    # ACTIONS ET ÉVÉNEMENTS
    # =========================================================================

    def _toggle_ignition(self):
        new_state = not self.mock.engine.state.ignition_on
        self.mock.set_ignition(new_state)
        if new_state:
            self.btn_ignition.setText("Ignition: ON")
            self.btn_ignition.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 6px;")
        else:
            self.btn_ignition.setText("Ignition: OFF")
            self.btn_ignition.setStyleSheet("background-color: #5cb85c; color: white; font-weight: bold; padding: 6px;")

    def _on_gear_selected(self, index: int):
        gear_map = [ -1, 0, 1, 2, 3, 4, 5, 6 ]
        if 0 <= index < len(gear_map):
            self.mock.gear = gear_map[index]

    def _on_ext_temp_changed(self, value: int):
        self.lbl_ext_temp.setText(f"{value}°C")
        self.mock.engine.state.outside_temp_c = float(value)

    def _reset_all_controls(self):
        self.slider_throttle.setValue(0)
        self.slider_brake.setValue(0)
        self.slider_clutch.setValue(0)
        self.slider_steer.setValue(0)
        self.mock.throttle = 0.0
        self.mock.brake = 0.0
        self.mock.clutch = 0.0
        self.mock.steering = 0.0

    def _on_scenario_selected(self, index: int):
        s_name = self.combo_scenarios.currentText()
        sc = self.mock.scenarios.get(s_name)
        if sc:
            self.lbl_scenario_desc.setText(f"{sc.description} (Estimated duration: {sc.total_duration_s:.1f}s)")

    def _toggle_run_scenario(self):
        if self.mock.scenario_runner.is_running:
            self.mock.scenario_runner.stop()
            self.btn_run_scenario.setText("Run scenario")
            self.btn_run_scenario.setStyleSheet("background-color: #2d5b88; color: white; font-weight: bold; padding: 8px;")
            self.lbl_scenario_step.setText("Scenario stopped manually.")
        else:
            s_name = self.combo_scenarios.currentText()
            sc = self.mock.scenarios.get(s_name)
            if sc:
                self.btn_run_scenario.setText("Stop scenario")
                self.btn_run_scenario.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 8px;")
                self.mock.scenario_runner.start_scenario(sc)

    def _on_scenario_progress(self, current: int, total: int, desc: str, pct: float):
        # Callback thread-safe via QTimer
        def update_ui():
            self.progress_scenario.setValue(int(pct))
            self.lbl_scenario_step.setText(f"Step {current}/{total}: {desc}")
            if not self.mock.scenario_runner.is_running:
                self.btn_run_scenario.setText("Run scenario")
                self.btn_run_scenario.setStyleSheet("background-color: #2d5b88; color: white; font-weight: bold; padding: 8px;")
        QTimer.singleShot(0, update_ui)

    def _apply_dtcs(self):
        raw = self.txt_dtc_input.text().strip()
        codes = [c.upper() for c in raw.split() if c]
        self.mock.inject_dtcs(codes)
        self._update_dtc_label()

    def _clear_dtcs(self):
        self.mock.clear_dtcs()
        self.txt_dtc_input.setText("")
        self._update_dtc_label()

    def _append_dtc(self, code: str):
        cur = self.txt_dtc_input.text().strip()
        if code not in cur:
            new_val = f"{cur} {code}".strip()
            self.txt_dtc_input.setText(new_val)
            self._apply_dtcs()

    def _update_dtc_label(self):
        dtcs = self.mock.engine.state.active_dtcs
        if dtcs:
            self.lbl_active_dtcs.setText(f"Active DTCs in the ECU: {', '.join(dtcs)}")
        else:
            self.lbl_active_dtcs.setText("Active DTCs in the ECU: none")

    def _refresh_telemetry_ui(self):
        state = self.mock.engine.state
        power_kw = max(0.0, state.engine_torque_nm * state.rpm / 9549.0)
        power_ch = power_kw * 1.35962

        self.lbl_live_speed.setText(f"{state.speed_kmh:.1f} km/h (Cluster: {state.speed_dashboard_kmh:.1f} km/h)")
        self.lbl_live_rpm.setText(f"{int(state.rpm)} RPM" + (" [REV LIMITER]" if state.rev_limiter_active else ""))
        self.lbl_live_torque.setText(f"{state.engine_torque_nm:.1f} N·m (Demand: {state.driver_torque_request:.1f}%)")
        self.lbl_live_power.setText(f"{power_ch:.1f} hp ({power_kw:.1f} kW)")
        fan_str = " [RADIATOR FAN ON]" if state.radiator_fan_active else ""
        self.lbl_live_temp.setText(f"{state.engine_temp_c:.1f} °C{fan_str}")
        self.lbl_live_fuel.setText(f"{state.fuel_level_l:.1f} L (Total used: {state.fuel_used_total_l:.3f} L)")
        self.lbl_live_conso.setText(f"{state.instant_l_100km:.1f} L/100 ({state.fuel_flow_lph:.2f} L/h)")
        self.lbl_live_voltage.setText(f"{state.battery_voltage:.2f} V")
        self.lbl_live_wheels.setText(
            f"FL: {state.wheel_fl_speed:.1f} | FR: {state.wheel_fr_speed:.1f} | "
            f"RL: {state.wheel_rl_speed:.1f} | RR: {state.wheel_rr_speed:.1f}"
        )
        self._update_dtc_label()

    # =========================================================================
    # CONTRÔLES CLAVIER POUR LE PILOTAGE
    # =========================================================================

    def keyPressEvent(self, event):
        key = event.key()

        # Accélérateur (Z / Flèche Haut)
        if key in (Qt.Key_Z, Qt.Key_Up):
            new_val = min(100, self.slider_throttle.value() + 15)
            self.slider_throttle.setValue(new_val)
            event.accept()

        # Frein (S / Flèche Bas)
        elif key in (Qt.Key_S, Qt.Key_Down):
            new_val = min(100, self.slider_brake.value() + 20)
            self.slider_brake.setValue(new_val)
            event.accept()

        # Braquage Gauche (Q / Flèche Gauche)
        elif key in (Qt.Key_Q, Qt.Key_Left):
            new_val = max(-180, self.slider_steer.value() - 25)
            self.slider_steer.setValue(new_val)
            event.accept()

        # Braquage Droit (D / Flèche Droite)
        elif key in (Qt.Key_D, Qt.Key_Right):
            new_val = min(180, self.slider_steer.value() + 25)
            self.slider_steer.setValue(new_val)
            event.accept()

        # Embrayage (C)
        elif key == Qt.Key_C:
            self.slider_clutch.setValue(100)
            event.accept()

        # Handbrake (Espace)
        elif key == Qt.Key_Space:
            self.chk_handbrake.toggle()
            event.accept()

        # Monter un rapport (E)
        elif key == Qt.Key_E:
            cur = self.combo_gear.currentIndex()
            if cur < self.combo_gear.count() - 1:
                self.combo_gear.setCurrentIndex(cur + 1)
            event.accept()

        # Rétrograder (A)
        elif key == Qt.Key_A:
            cur = self.combo_gear.currentIndex()
            if cur > 0:
                self.combo_gear.setCurrentIndex(cur - 1)
            event.accept()

        # Contact (I)
        elif key == Qt.Key_I:
            self._toggle_ignition()
            event.accept()

        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        key = event.key()
        # Relâchement progressif accélérateur / frein / embrayage
        if key in (Qt.Key_Z, Qt.Key_Up):
            self.slider_throttle.setValue(0)
            event.accept()
        elif key in (Qt.Key_S, Qt.Key_Down):
            self.slider_brake.setValue(0)
            event.accept()
        elif key == Qt.Key_C:
            self.slider_clutch.setValue(0)
            event.accept()
        elif key in (Qt.Key_Q, Qt.Key_Left, Qt.Key_D, Qt.Key_Right):
            self.slider_steer.setValue(0)
            event.accept()
        else:
            super().keyReleaseEvent(event)
