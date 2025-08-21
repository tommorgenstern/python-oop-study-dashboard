from __future__ import annotations
from datetime import date
from pathlib import Path
from flask import Blueprint, render_template, redirect, url_for, request

from ..services.core import Studiengang
from ..services.services import (
    CourseManager,
    JsonPersistence,
    KonfigManager,
    GoalFactory,
    GoalEvaluator,
    parse_date
)

bp = Blueprint("main", __name__)

DATA_DIR = Path(".data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
STUDIENGANG_FILE = DATA_DIR / "studiengang.json"
CFG_FILE = DATA_DIR / "config.json"


# ---------------------- helpers ----------------------

def _load_studiengang() -> Studiengang:
    if STUDIENGANG_FILE.exists():
        return JsonPersistence.load(STUDIENGANG_FILE)
    return Studiengang("Softwareentwicklung", date(2023, 12, 5))

def _save_studiengang(studiengang: Studiengang) -> None:
    JsonPersistence.save(STUDIENGANG_FILE, studiengang)

def _load_goals():
    km = KonfigManager(CFG_FILE)
    cfg = km.load_config() or {"ziele": {}}
    return GoalFactory.from_config(cfg)

# ---------------------- KPI computation ----------------------

def compute_dashboard_metrics(studiengang: Studiengang, targets: dict) -> dict:
    total_courses = 0
    graded_courses = 0
    completed_courses = 0
    ects_earned = 0.0
    ones = 0

    klausur_durations: list[int] = []
    sonstige_durations: list[int] = []

    for semester in studiengang.semester:
        for modul in semester.module:
            for kurs in modul.kurse:
                total_courses += 1

                if kurs.leistung.note is not None:
                    graded_courses += 1
                    if kurs.leistung.note == 1.0:
                        ones += 1

                if kurs.ist_bestanden:
                    completed_courses += 1
                    ects_earned += kurs.ects

                if kurs.startdatum and kurs.leistung and kurs.leistung.datum and kurs.ist_abgeschlossen:
                    dur = (kurs.leistung.datum - kurs.startdatum).days
                    if (kurs.leistung.art or "").strip().lower() == "klausur":
                        klausur_durations.append(dur)
                    else:
                        sonstige_durations.append(dur)

    avg_klausur_days = round(sum(klausur_durations) / len(klausur_durations)) if klausur_durations else None
    avg_sonstige_days = round(sum(sonstige_durations) / len(sonstige_durations)) if sonstige_durations else None

    excell_ratio = (ones / graded_courses) if graded_courses > 0 else 0.0
    avg = studiengang.durchschnitt

    ects_total = targets["total_ects"]
    exams_total = targets["total_exams"]
    ects_progress = round((ects_earned / ects_total * 100)) if ects_total > 0 else 0

    return {
        "total_courses": total_courses,
        "graded_courses": graded_courses,
        "completed_courses": completed_courses,
        "ects_earned": ects_earned,
        "ects_total": ects_total,
        "ects_progress": ects_progress,
        "exams_total": exams_total,
        "ones": ones,
        "avg_klausur_days": avg_klausur_days,
        "avg_sonstige_days": avg_sonstige_days,
        "excell_ratio": excell_ratio,
        "avg": avg,
    }

# ---------------------- routes ----------------------

@bp.get("/")
def index():
    studiengang = _load_studiengang()

    # First-run demo seed to avoid empty dashboard
    #if not studiengang.semester:
    #    m = CourseManager.add_modul(studiengang, 1, "Data Science und Python")
    #    CourseManager.add_kurs(m, "Objektorientierte Programmierung mit Python", ects=5, art="Klausur")
    #    _save_studiengang(studiengang)

    ziele = _load_goals()
    evaluator = GoalEvaluator(ziele)
    ziel_status = evaluator.bewerte(studiengang)

    km = KonfigManager(CFG_FILE)
    targets = km.get_targets()
    metrics = compute_dashboard_metrics(studiengang, targets)

    return render_template(
        "index.html",
        studiengang=studiengang,
        date=date,  # let Jinja call date.today()
        ziel_status=ziel_status,
        # thresholds
        **targets,
        # metrics
        **metrics,
    )

@bp.get("/seed")
def seed_demo():
    studiengang = Studiengang("Softwareentwicklung", date(2023, 12, 5))
    m = CourseManager.add_modul(studiengang, 1, "Bachelormodul")
    k1 = CourseManager.add_kurs(m, "Thesis", ects=9, art="Hausarbeit")
    k2 = CourseManager.add_kurs(m, "Kolloquium", ects=1, art="Mündlich")

    # demo data for averages
    CourseManager.record_grade(k1, 1.7)
    CourseManager.record_grade(k2, 1.3)
    k1.startdatum = date(2025, 4, 1)
    k2.startdatum = date(2025, 7, 1)
    k1.leistung.datum = date(2025, 7, 20)
    k2.leistung.datum = date(2025, 7, 25)

    _save_studiengang(studiengang)

    km = KonfigManager(CFG_FILE)
    km.save_config({
        "ziele": {
            "studienzeitziel": {"max_jahre": 3},
            "notenziel": {"max_durchschnitt": 1.9},
            "kursdauerziel": {"max_tage_klausur": 21, "max_tage_sonstige": 42},
            "exzellenzziel": {"mindestanteil": 0.10},
        },
        "studiengang": {
            "name": "B.Sc. Softwareentwicklung",
            "startdatum": "2023-12-05",
            "total_ects": 180,
            "total_exams": 36
        }
    })
    return redirect(url_for("main.index"))

@bp.post("/add_modul")
def add_modul():
    studiengang = _load_studiengang()
    sem_nr = int(request.form["sem_nr"])
    modul_name = (request.form.get("modul_name") or "").strip()
    CourseManager.add_modul(studiengang, sem_nr, modul_name)
    _save_studiengang(studiengang)
    return redirect(url_for("main.index"))


@bp.post("/add_kurs")
def add_kurs():
    studiengang = _load_studiengang()
    sem_nr = int(request.form["sem_nr"])
    modul_name = (request.form.get("modul_name") or "").strip()
    kurs_name = request.form["kurs_name"].strip()
    ects = float(request.form["ects"])
    art = request.form.get("art", "Klausur")
    start_dt = parse_date(request.form.get("startdatum"))


    # resolve/create module
    modul = None
    for s in studiengang.semester:
        if s.nummer == sem_nr:
            for m in s.module:
                if m.name == modul_name:
                    modul = m
                    break
    if modul is None:
        modul = CourseManager.add_modul(studiengang, sem_nr, modul_name)

    kurs = CourseManager.add_kurs(modul, kurs_name, ects, art=art, startdatum=start_dt)

    _save_studiengang(studiengang)
    return redirect(url_for("main.index"))

@bp.post("/record_grade")
def record_grade():
    studiengang = _load_studiengang()
    sem_nr = int(request.form["sem_nr"])
    modul_name = request.form["modul_name"].strip()
    kurs_name = request.form["kurs_name"].strip()
    
    # Find the course
    kurs = CourseManager.find_kurs(studiengang, sem_nr, modul_name, kurs_name)
    if kurs is None:
        return redirect(url_for("main.index"))  # Course not found
    
    # Check if passed without grade
    passed_without_grade = 'passed_without_grade' in request.form
    
    # Parse date
    datum = parse_date(request.form.get("datum"))
    
    if passed_without_grade:
        # Mark as passed without grade
        CourseManager.record_passed(kurs, True)
        if datum:
            kurs.leistung.datum = datum
    else:
        # Parse and record grade
        note_raw = (request.form.get("note") or "").strip()
        if note_raw:
            try:
                note = float(note_raw)
                CourseManager.record_grade(kurs, note)
                if datum:
                    kurs.leistung.datum = datum
            except ValueError:
                pass
    
    _save_studiengang(studiengang)
    return redirect(url_for("main.index"))

@bp.post("/set_config")
def set_config():
    km = KonfigManager(CFG_FILE)
    
    # Parse form data
    config = {
        "ziele": {
            "studienzeitziel": {"max_jahre": float(request.form.get("max_jahre", 3))},
            "notenziel": {"max_durchschnitt": float(request.form.get("max_durchschnitt", 1.9))},
            "kursdauerziel": {
                "max_tage_klausur": int(request.form.get("max_tage_klausur", 21)),
                "max_tage_sonstige": int(request.form.get("max_tage_sonstige", 42))
            },
            "exzellenzziel": {"mindestanteil": float(request.form.get("exzellenz_mindestanteil", 10)) / 100}  # Convert percentage to decimal
        },
        "studiengang": {
            "name": request.form.get("studiengang_name", "B.Sc. Softwareentwicklung"),
            "startdatum": request.form.get("studiengang_startdatum", "2023-12-05"),
            "total_ects": int(request.form.get("total_ects", 180)),
            "total_exams": int(request.form.get("total_exams", 36))
        }
    }
    
    km.save_config(config)
    return redirect(url_for("main.index"))

@bp.post("/edit_kurs")
def edit_kurs():
    studiengang = _load_studiengang()
    
    # Original course identification
    original_sem_nr = int(request.form["original_sem_nr"])
    original_modul_name = request.form["original_modul_name"].strip()
    original_kurs_name = request.form["original_kurs_name"].strip()
    
    # New values
    new_sem_nr = int(request.form["sem_nr"])
    new_modul_name = request.form["modul_name"].strip()
    new_kurs_name = request.form["kurs_name"].strip()
    new_ects = float(request.form["ects"])
    new_art = request.form.get("art", "Klausur")
    
    # Parse dates
    new_startdatum = parse_date(request.form.get("startdatum"))
    new_datum = parse_date(request.form.get("datum"))
    
    new_note = None
    note_raw = (request.form.get("note") or "").strip()
    if note_raw:
        try:
            new_note = float(note_raw)
        except Exception:
            pass
    
    # Find original course
    original_kurs = CourseManager.find_kurs(studiengang, original_sem_nr, original_modul_name, original_kurs_name)    
    if original_kurs is None:
        return redirect(url_for("main.index"))  # Course not found
    
    # If location changed, delegate the move
    if original_sem_nr != new_sem_nr or original_modul_name != new_modul_name:
        moved = CourseManager.move_kurs(
            studiengang,
            original_sem_nr, original_modul_name, original_kurs_name,
            new_sem_nr, new_modul_name
        )
        if moved is None:
            return redirect(url_for("main.index"))
        original_kurs = moved  # keep working with the moved instance

    
    # Update course attributes
    original_kurs.name = new_kurs_name
    original_kurs.ects = new_ects
    original_kurs.startdatum = new_startdatum
    original_kurs.leistung.art = new_art
    original_kurs.leistung.datum = new_datum
    original_kurs.leistung.note = new_note
    
    _save_studiengang(studiengang)
    return redirect(url_for("main.index"))

@bp.post("/delete_kurs")
def delete_kurs():
    studiengang = _load_studiengang()
    
    sem_nr = int(request.form["sem_nr"])
    modul_name = request.form["modul_name"].strip()
    kurs_name = request.form["kurs_name"].strip()
    
    # Delete the course
    success = CourseManager.delete_kurs(studiengang, sem_nr, modul_name, kurs_name)
    
    if success:
        _save_studiengang(studiengang)
    
    return redirect(url_for("main.index"))