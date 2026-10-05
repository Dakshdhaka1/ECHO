"""MLOps helpers: MLflow tracking + registry, promotion gate and artifact export (ML_PIPELINE §7).

Tracking URI: MLFLOW_TRACKING_URI if set (e.g. the docker-compose MLflow server, http://localhost:5000),
otherwise a local SQLite store in ml-service/mlruns/. The inference service never needs MLflow: it
loads the exported artifacts under artifacts/<model>/<version>/.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib

from pipelines.common import ARTIFACTS_DIR, ML_ROOT, SEED

log = logging.getLogger("echo.mlops")

REQUIRED_CARD_FIELDS = ("name", "version", "kind", "trained_at", "metrics", "baseline", "primary_metric",
                        "intended_use", "limitations", "data", "licences")


os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


try:
    from mlflow.pyfunc import PythonModel as _PythonModel
except ImportError:  # serving image does not install mlflow
    _PythonModel = object


class EchoExportModel(_PythonModel):
    """MLflow pyfunc wrapper around an exported ECHO artifact directory, so every run registers a real model."""

    def load_context(self, context) -> None:
        directory = Path(context.artifacts["export"])
        self.model = joblib.load(directory / "model.joblib") if (directory / "model.joblib").exists() else None

    def predict(self, context, model_input, params=None):
        for method in ("predict_proba", "score", "predict"):
            if self.model is not None and hasattr(self.model, method):
                return getattr(self.model, method)(model_input)
        raise NotImplementedError("use the ECHO inference service for this artifact")


def tracking_uri() -> str:
    uri = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
    if uri:  # docker-compose sets http://mlflow:5000 for the ml-service container
        return uri
    (ML_ROOT / "mlruns").mkdir(exist_ok=True)
    return f"sqlite:///{(ML_ROOT / 'mlruns' / 'mlflow.db').as_posix()}"


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ML_ROOT, capture_output=True,
                              text=True, timeout=5).stdout.strip() or "uncommitted"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


@dataclass
class TrainingRun:
    """Everything a training module produces; consumed by `finish_run`."""

    model_name: str
    kind: str                         # "ML" | "Stat"
    primary_metric: str               # key in metrics (higher is better unless lower_is_better)
    metrics: dict[str, float]         # test-set metrics of the selected model
    baseline: dict[str, Any]          # {"name": ..., "metrics": {...}} on the same test set
    params: dict[str, Any]
    data: dict[str, Any]              # dataset names, sizes, split definition, manifest hash
    intended_use: str
    limitations: str
    licences: dict[str, str]
    save: Callable[[Path], None]      # writes the model files into an export directory
    smoke_test: Callable[[Path], None]  # loads the exported files and predicts; raises on failure
    lower_is_better: bool = False
    figures: dict[str, Path] = field(default_factory=dict)
    tables: dict[str, Any] = field(default_factory=dict)
    gate_margin: float = 0.0


def _better(a: float, b: float, lower: bool, margin: float) -> bool:
    return a < b - margin if lower else a > b + margin


def current_champion(model_name: str) -> dict | None:
    pointer = ARTIFACTS_DIR / model_name / "CHAMPION"
    if not pointer.exists():
        return None
    card = ARTIFACTS_DIR / model_name / pointer.read_text().strip() / "model_card.json"
    return json.loads(card.read_text()) if card.exists() else None


def gate(run: TrainingRun, card: dict, export_dir: Path) -> tuple[bool, list[str]]:
    """Promotion gate (ML_PIPELINE §7.3). Returns (passed, reasons)."""
    reasons, ok = [], True
    value = run.metrics[run.primary_metric]
    base = run.baseline.get("metrics", {}).get(run.primary_metric)
    if base is not None and not _better(value, base, run.lower_is_better, 0.0):
        ok = False
        reasons.append(f"{run.primary_metric}={value:.4f} does not beat baseline {run.baseline['name']} ({base:.4f})")
    champion = current_champion(run.model_name)
    if champion is not None:
        champ_value = champion.get("metrics", {}).get(run.primary_metric)
        if champ_value is not None and not _better(value, champ_value, run.lower_is_better, run.gate_margin):
            ok = False
            reasons.append(f"does not beat champion v{champion['version']} ({champ_value:.4f}) by margin {run.gate_margin}")
    missing = [f for f in REQUIRED_CARD_FIELDS if not card.get(f)]
    if missing:
        ok = False
        reasons.append(f"model card incomplete: {missing}")
    try:
        run.smoke_test(export_dir)
    except Exception as exc:  # any failure to load/predict blocks promotion
        ok = False
        reasons.append(f"inference smoke test failed: {exc!r}")
    if ok:
        reasons.append("passed: beats baseline" + (" and champion" if champion else "") + "; card complete; smoke test ok")
    return ok, reasons


def _next_version(model_name: str) -> int:
    root = ARTIFACTS_DIR / model_name
    versions = [int(p.name) for p in root.glob("*") if p.is_dir() and p.name.isdigit()] if root.exists() else []
    return max(versions, default=0) + 1


def finish_run(run: TrainingRun, config: dict, *, promote: bool | None = None) -> dict:
    """Export artifacts + card, log everything to MLflow, register, and apply the promotion gate."""
    import mlflow

    promote = config.get("promote", True) if promote is None else promote
    version = _next_version(run.model_name)
    export_dir = ARTIFACTS_DIR / run.model_name / str(version)
    export_dir.mkdir(parents=True, exist_ok=True)
    run.save(export_dir)
    for name, path in run.figures.items():
        shutil.copy(path, export_dir / f"{name}{Path(path).suffix}")
    if run.tables:
        (export_dir / "evaluation.json").write_text(json.dumps(run.tables, indent=2, default=float))

    card = {
        "name": run.model_name, "version": str(version), "kind": run.kind,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"), "git_sha": git_sha(),
        "hardware": f"cpu ({platform.processor() or platform.machine()})", "seed": SEED,
        "primary_metric": run.primary_metric, "lower_is_better": run.lower_is_better,
        "metrics": {k: float(v) for k, v in run.metrics.items()},
        "baseline": run.baseline, "params": run.params, "data": run.data,
        "intended_use": run.intended_use, "limitations": run.limitations, "licences": run.licences,
        "config": config,
    }

    mlflow.set_tracking_uri(tracking_uri())
    mlflow.set_experiment(f"echo-{run.model_name}")
    with mlflow.start_run(run_name=f"{run.model_name}-v{version}") as active:
        mlflow.set_tags({"git_sha": card["git_sha"], "kind": run.kind,
                         "data_manifest_sha256": str(run.data.get("manifest_sha256", ""))})
        mlflow.log_params({k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                           for k, v in {**run.params, "seed": SEED}.items()})
        mlflow.log_metrics({f"test_{k}": float(v) for k, v in run.metrics.items()})
        mlflow.log_metrics({f"baseline_{k}": float(v) for k, v in run.baseline.get("metrics", {}).items()})
        card["mlflow_run_id"] = active.info.run_id
        passed, reasons = gate(run, card, export_dir)
        card["gate"] = {"passed": passed, "reasons": reasons}
        (export_dir / "model_card.json").write_text(json.dumps(card, indent=2, default=str))
        mlflow.log_artifacts(str(export_dir), artifact_path="export")
        mlflow.set_tag("gate_passed", str(passed))
        for path in run.figures.values():
            mlflow.log_artifact(str(path), artifact_path="figures")
        try:
            info = mlflow.pyfunc.log_model(name="model", python_model=EchoExportModel(),
                                           artifacts={"export": str(export_dir)})
            mv = mlflow.register_model(info.model_uri, run.model_name)
            client = mlflow.MlflowClient()
            client.set_registered_model_alias(run.model_name, "challenger", mv.version)
            if passed and promote:
                client.set_registered_model_alias(run.model_name, "champion", mv.version)
            card["mlflow_registry_version"] = mv.version
        except Exception as exc:  # registry is best-effort; export is the source of truth for serving
            log.warning("MLflow registry update failed: %s", exc)

    card["stage"] = "champion" if passed and promote else "challenger"
    (export_dir / "model_card.json").write_text(json.dumps(card, indent=2, default=str))
    if passed and promote:
        (ARTIFACTS_DIR / run.model_name / "CHAMPION").write_text(str(version))
        log.info("%s v%d promoted to champion", run.model_name, version)
    else:
        log.warning("%s v%d NOT promoted: %s", run.model_name, version, "; ".join(reasons))
    return card


def save_joblib(obj: Any, filename: str = "model.joblib") -> Callable[[Path], None]:
    def _save(directory: Path) -> None:
        joblib.dump(obj, directory / filename, compress=3)
    return _save


def promote(model_name: str, version: str, reason: str, by: str = "maintainer") -> dict:
    """Audited manual promotion for changes the gate's primary metric cannot see (e.g. better topic labels at an
    equal classification score). The reason is written into the model card and the MLflow alias is moved.

        python -m pipelines.mlops promote <model> <version> --reason "..."
    """
    export_dir = ARTIFACTS_DIR / model_name / str(version)
    card_path = export_dir / "model_card.json"
    if not card_path.exists():
        raise FileNotFoundError(card_path)
    card = json.loads(card_path.read_text())
    if not card.get("gate", {}).get("passed") and not any("champion" in r for r in card.get("gate", {}).get("reasons", [])):
        raise ValueError("refusing to promote: this version failed a check other than 'beat the champion'")
    card["stage"] = "champion"
    card["manual_promotion"] = {"by": by, "reason": reason, "at": datetime.now(UTC).isoformat(timespec="seconds")}
    card_path.write_text(json.dumps(card, indent=2, default=str))
    (ARTIFACTS_DIR / model_name / "CHAMPION").write_text(str(version))
    try:
        import mlflow

        mlflow.set_tracking_uri(tracking_uri())
        reg_version = card.get("mlflow_registry_version")
        if reg_version:
            mlflow.MlflowClient().set_registered_model_alias(model_name, "champion", reg_version)
    except Exception as exc:  # the export pointer is the source of truth for serving
        log.warning("MLflow alias not updated: %s", exc)
    log.info("%s v%s manually promoted: %s", model_name, version, reason)
    return card


if __name__ == "__main__":
    import argparse

    from pipelines.common import setup_logging

    setup_logging()
    parser = argparse.ArgumentParser(description="MLOps maintenance commands")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("promote", help="audited manual promotion of an exported model version")
    p.add_argument("model")
    p.add_argument("version")
    p.add_argument("--reason", required=True)
    p.add_argument("--by", default="maintainer")
    args = parser.parse_args()
    promote(args.model, args.version, args.reason, args.by)
