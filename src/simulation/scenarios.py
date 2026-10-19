"""Scénarios de conduite automatisés et séquences de test pour la simulation CliOS."""

import time
import threading
from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class ScenarioStep:
    """Étape individuelle au sein d'un scénario de conduite."""
    description: str
    duration_s: float
    throttle: float = 0.0
    brake: float = 0.0
    clutch: float = 0.0
    gear: int = 0
    steering: float = 0.0
    ignition: bool = True
    starter: bool = False
    handbrake: bool = False
    turn_left: bool = False
    turn_right: bool = False
    hazard: bool = False
    pos_lights: bool = False
    low_beam: bool = False
    high_beam: bool = False
    dtcs: list[str] | None = None
    force_temp: float | None = None
    force_fuel: float | None = None
    custom_action: Callable[[Any], None] | None = None


class Scenario:
    """Définition d'un scénario complet composé d'étapes ordonnées."""

    def __init__(self, name: str, description: str, steps: list[ScenarioStep]):
        self.name = name
        self.description = description
        self.steps = steps

    @property
    def total_duration_s(self) -> float:
        return sum(s.duration_s for s in self.steps)


class ScenarioRunner:
    """Orchestrateur de scénarios exécuté dans un thread dédié."""

    def __init__(self, mock_provider):
        self.provider = mock_provider
        self._thread = None
        self._stop_event = threading.Event()
        self._current_step_index = 0
        self._is_running = False
        self._progress_callback = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    def set_progress_callback(self, callback: Callable[[int, int, str, float], None]):
        """Définit la fonction de rappel appelée à chaque progression d'étape."""
        self._progress_callback = callback

    def start_scenario(self, scenario: Scenario):
        """Lance l'exécution d'un scénario."""
        self.stop()
        self._stop_event.clear()
        self._is_running = True
        self._thread = threading.Thread(
            target=self._run,
            args=(scenario,),
            name=f"Scenario-{scenario.name}",
            daemon=True
        )
        self._thread.start()

    def stop(self):
        """Interrompt immédiatement le scénario en cours."""
        self._stop_event.set()
        self._is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None

    def _run(self, scenario: Scenario):
        total_steps = len(scenario.steps)
        total_time = scenario.total_duration_s
        elapsed_scenario = 0.0

        try:
            for idx, step in enumerate(scenario.steps):
                if self._stop_event.is_set():
                    break

                self._current_step_index = idx

                # Application des commandes physiques
                self.provider.engine.state.ignition_on = step.ignition
                self.provider.engine.state.key_run = step.ignition
                self.provider.engine.state.key_acc = step.ignition
                self.provider.engine.state.starter_active = step.starter
                self.provider.engine.state.selected_gear = step.gear
                self.provider.engine.state.clutch_pedal = step.clutch
                self.provider.engine.state.throttle_pedal = step.throttle
                self.provider.engine.state.brake_pedal = step.brake
                self.provider.engine.state.handbrake = step.handbrake
                self.provider.engine.state.steering_angle_deg = step.steering
                self.provider.engine.state.turn_left = step.turn_left
                self.provider.engine.state.turn_right = step.turn_right
                self.provider.engine.state.hazard = step.hazard
                self.provider.engine.state.pos_lights = step.pos_lights
                self.provider.engine.state.low_beam = step.low_beam
                self.provider.engine.state.high_beam = step.high_beam

                if step.dtcs is not None:
                    self.provider.engine.state.active_dtcs = list(step.dtcs)
                if step.force_temp is not None:
                    self.provider.engine.state.engine_temp_c = step.force_temp
                if step.force_fuel is not None:
                    self.provider.engine.state.fuel_level_l = step.force_fuel

                if step.custom_action:
                    step.custom_action(self.provider)

                # Émission de la notification de progression
                progress_pct = (elapsed_scenario / max(1.0, total_time)) * 100.0
                if self._progress_callback:
                    self._progress_callback(idx + 1, total_steps, step.description, progress_pct)

                # Attente fluide de la durée de l'étape
                step_elapsed = 0.0
                while step_elapsed < step.duration_s and not self._stop_event.is_set():
                    chunk = min(0.05, step.duration_s - step_elapsed)
                    time.sleep(chunk)
                    step_elapsed += chunk
                    elapsed_scenario += chunk

            if not self._stop_event.is_set() and self._progress_callback:
                self._progress_callback(total_steps, total_steps, "Scenario completed successfully", 100.0)

        finally:
            self._is_running = False


# =============================================================================
# SCÉNARIOS PRÉDÉFINIS
# =============================================================================

def get_builtin_scenarios() -> list[Scenario]:
    """Retourne la bibliothèque des scénarios de simulation disponibles."""

    # 1. Trajet Urbain
    city_steps = [
        ScenarioStep("1. Ignition on and low beams on", duration_s=1.0, ignition=True, low_beam=True),
        ScenarioStep("2. Starter (engine start)", duration_s=1.2, ignition=True, starter=True, low_beam=True),
        ScenarioStep("3. Engine idling, clutch in and 1st gear engaged", duration_s=1.0, clutch=100.0, gear=1, low_beam=True),
        ScenarioStep("4. Standing start and moderate acceleration", duration_s=3.0, clutch=0.0, throttle=40.0, gear=1, low_beam=True),
        ScenarioStep("5. Clutch in and shift to 2nd", duration_s=0.6, clutch=100.0, throttle=0.0, gear=2, low_beam=True),
        ScenarioStep("6. Accelerate to 50 km/h", duration_s=3.5, clutch=0.0, throttle=50.0, gear=2, low_beam=True),
        ScenarioStep("7. Clutch in and shift to 3rd", duration_s=0.6, clutch=100.0, throttle=0.0, gear=3, low_beam=True),
        ScenarioStep("8. Steady 50 km/h in town", duration_s=4.0, clutch=0.0, throttle=18.0, gear=3, low_beam=True),
        ScenarioStep("9. Left turn signal and gentle turn", duration_s=2.5, throttle=15.0, gear=3, steering=-35.0, turn_left=True, low_beam=True),
        ScenarioStep("10. Straight line, turn signal off", duration_s=2.0, throttle=18.0, gear=3, steering=0.0, turn_left=False, low_beam=True),
        ScenarioStep("11. Slowing, braking and clutch in (red light)", duration_s=3.0, throttle=0.0, brake=45.0, clutch=100.0, gear=3, low_beam=True),
        ScenarioStep("12. Full stop in neutral with handbrake", duration_s=2.0, brake=0.0, clutch=0.0, gear=0, handbrake=True, low_beam=True),
        ScenarioStep("13. Ignition off", duration_s=1.0, ignition=False, low_beam=False, handbrake=True),
    ]
    city_scenario = Scenario("City Trip", "Full city trip simulation with stops, gear changes and lights.", city_steps)

    # 2. Autoroute & Régulateur
    highway_steps = [
        ScenarioStep("1. Engine start", duration_s=1.5, ignition=True, starter=True, clutch=100.0, gear=0),
        ScenarioStep("2. Brisk merge in 1st", duration_s=2.5, clutch=0.0, throttle=75.0, gear=1),
        ScenarioStep("3. Shift to 2nd", duration_s=0.5, clutch=100.0, throttle=0.0, gear=2),
        ScenarioStep("4. Full acceleration in 2nd", duration_s=3.0, clutch=0.0, throttle=85.0, gear=2),
        ScenarioStep("5. Shift to 3rd", duration_s=0.5, clutch=100.0, throttle=0.0, gear=3),
        ScenarioStep("6. Rev up in 3rd to 90 km/h", duration_s=3.5, clutch=0.0, throttle=80.0, gear=3),
        ScenarioStep("7. Shift to 4th", duration_s=0.5, clutch=100.0, throttle=0.0, gear=4),
        ScenarioStep("8. Accelerate in 4th to 120 km/h", duration_s=4.0, clutch=0.0, throttle=75.0, gear=4),
        ScenarioStep("9. Shift to 5th", duration_s=0.5, clutch=100.0, throttle=0.0, gear=5),
        ScenarioStep("10. Cruising at 130 km/h (cruise control on)", duration_s=6.0, clutch=0.0, throttle=32.0, gear=5),
        ScenarioStep("11. Braking for the toll booth", duration_s=4.0, throttle=0.0, brake=60.0, clutch=100.0, gear=5),
        ScenarioStep("12. Full stop in neutral", duration_s=2.0, brake=20.0, clutch=0.0, gear=0),
    ]
    highway_scenario = Scenario("Highway & Cruise Control", "Sustained acceleration to 130 km/h and cruise control.", highway_steps)

    # 3. Circuit & Sport
    sport_steps = [
        ScenarioStep("1. Launch control start (high rpm in 1st)", duration_s=1.5, ignition=True, clutch=100.0, throttle=95.0, gear=1),
        ScenarioStep("2. Hard clutch drop and wheelspin", duration_s=2.5, clutch=0.0, throttle=100.0, gear=1),
        ScenarioStep("3. Rev limiter in 1st and lightning shift to 2nd", duration_s=0.4, clutch=100.0, throttle=100.0, gear=2),
        ScenarioStep("4. Full load in 2nd", duration_s=2.5, clutch=0.0, throttle=100.0, gear=2),
        ScenarioStep("5. Shift to 3rd", duration_s=0.4, clutch=100.0, throttle=100.0, gear=3),
        ScenarioStep("6. Pit straight at 150 km/h", duration_s=4.0, clutch=0.0, throttle=100.0, gear=3),
        ScenarioStep("7. Heavy braking at the end of the straight (ABS active)", duration_s=2.5, throttle=0.0, brake=95.0, clutch=100.0, gear=3),
        ScenarioStep("8. Tight right turn in 2nd with lateral acceleration", duration_s=3.0, clutch=0.0, throttle=65.0, gear=2, steering=85.0),
        ScenarioStep("9. Corner exit and back on the throttle", duration_s=3.0, clutch=0.0, throttle=90.0, gear=2, steering=0.0),
        ScenarioStep("10. Cool-down lap and slowing", duration_s=3.0, throttle=0.0, brake=40.0, clutch=100.0, gear=0),
    ]
    sport_scenario = Scenario("Track & Performance", "Extreme sport driving: launch control, rev limiter and ABS braking.", sport_steps)

    # 4. Surchauffe & Alertes
    stress_steps = [
        ScenarioStep("1. Engine running normally", duration_s=2.0, ignition=True, throttle=20.0, gear=2, force_temp=85.0),
        ScenarioStep("2. Sustained heavy load and rising temperature", duration_s=3.0, throttle=90.0, gear=3, force_temp=98.0),
        ScenarioStep("3. Engine overheating alert (>105°C - radiator fan max)", duration_s=4.0, throttle=60.0, gear=3, force_temp=108.0),
        ScenarioStep("4. Low fuel alert (reserve level < 15%)", duration_s=3.0, throttle=20.0, gear=3, force_temp=95.0, force_fuel=3.5),
        ScenarioStep("5. Clutch released and accidental stall", duration_s=2.5, throttle=0.0, clutch=0.0, brake=100.0, gear=3),
        ScenarioStep("6. Restore baseline parameters", duration_s=1.0, ignition=True, gear=0, force_temp=88.0, force_fuel=40.0),
    ]
    stress_scenario = Scenario("Stress & Alerts", "Triggers critical alerts: overheating, low fuel and stall.", stress_steps)

    # 5. Injection Diagnostic OBD2
    diag_steps = [
        ScenarioStep("1. Vehicle with ignition on", duration_s=1.5, ignition=True),
        ScenarioStep("2. Inject fault code P0300 (misfire)", duration_s=2.0, ignition=True, dtcs=["P0300"]),
        ScenarioStep("3. Inject multiple fault codes (P0300, P0115, P0420)", duration_s=4.0, ignition=True, dtcs=["P0300", "P0115", "P0420"]),
        ScenarioStep("4. Ready for the OBD-II scan in CliOS", duration_s=5.0, ignition=True, dtcs=["P0300", "P0115", "P0420"]),
    ]
    diag_scenario = Scenario("OBD Diagnostics & Faults", "Injects DTC fault codes to test the diagnostic service.", diag_steps)

    return [city_scenario, highway_scenario, sport_scenario, stress_scenario, diag_scenario]
