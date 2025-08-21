from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional
from .core import Studiengang, Semester, Modul, Kurs, Pruefungsleistung
from .goals import (
    Ziel, Studienzeitziel, Notenziel, ExzellenzZiel,
    KursdauerZiel,
    KursdauerKlausurZiel,
    KursdauerSonstigeZiel,
)
from typing import cast

def parse_date(s: str | None) -> Optional[date]:
    """Parse 'YYYY-MM-DD' to date or return None on failure/empty."""
    if not s:
        return None
    try:
        y, m, d = (int(x) for x in s.strip().split("-"))
        return date(y, m, d)
    except Exception:
        return None

class JsonPersistence:
    @staticmethod
    def save(path: str | Path, studiengang: Studiengang) -> None:
        data = {
            "name": studiengang.name,
            "startdatum": studiengang.startdatum.isoformat(),
            "semester": [
                {
                    "nummer": semester.nummer,
                    "module": [
                        {
                            "name": modul.name,
                            "kurse": [
                                {
                                    "name": kurs.name,
                                    "ects": kurs.ects,
                                    "startdatum": kurs.startdatum.isoformat() if kurs.startdatum else None,
                                    "leistung": {
                                        "art": kurs.leistung.art,
                                        "note": kurs.leistung.note,
                                        "datum": kurs.leistung.datum.isoformat() if kurs.leistung.datum else None,
                                        "bestanden": kurs.leistung.bestanden,   # <-- add this
                                    },
                                }
                                for kurs in modul.kurse
                            ],
                        }
                        for modul in semester.module
                    ],
                }
                for semester in studiengang.semester
            ],
        }
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))

    @staticmethod
    def load(path: str | Path) -> Studiengang:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        studiengang = Studiengang(data["name"], date.fromisoformat(data["startdatum"]))
        for s in data.get("semester", []):
            sem = Semester(s["nummer"])
            for m in s.get("module", []):
                modul = Modul(m["name"])
                for kurs in m.get("kurse", []):
                    pl = kurs.get("leistung", {})
                    sd = kurs.get("startdatum")
                    k = Kurs(
                        kurs["name"],
                        float(kurs["ects"]),
                        Pruefungsleistung(
                            pl.get("art", "Klausur"),
                            pl.get("note", None),
                            date.fromisoformat(pl["datum"]) if pl.get("datum") else None,
                            pl.get("bestanden", None),        # <-- add this
                        ),
                        date.fromisoformat(sd) if sd else None,
                    )
                    modul.kurse.append(k)
                sem.module.append(modul)
            studiengang.semester.append(sem)
        return studiengang

class KonfigManager:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
    def load_config(self) -> Dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}
    def save_config(self, data: Dict) -> None:
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    def get_targets(self) -> Dict:
        cfg = self.load_config() or {}
        z = (cfg.get("ziele") or {}) if isinstance(cfg.get("ziele"), dict) else {}
        s = (cfg.get("studiengang") or {}) if isinstance(cfg.get("studiengang"), dict) else {}
        return {
            "ziel_max_jahre":                 z.get("studienzeitziel", {}).get("max_jahre", 3),
            "ziel_max_durchschnitt":          z.get("notenziel", {}).get("max_durchschnitt", 1.9),
            "ziel_max_tage_klausur":          z.get("kursdauerziel", {}).get("max_tage_klausur", 21),
            "ziel_max_tage_sonstige":         z.get("kursdauerziel", {}).get("max_tage_sonstige", 42),
            "ziel_exzellenz_mindestanteil":   z.get("exzellenzziel", {}).get("mindestanteil", 0.10),
            "studiengang_name":               s.get("name", "B.Sc. Softwareentwicklung"),
            "studiengang_startdatum":         s.get("startdatum", "2023-12-05"),
            "total_ects":                     s.get("total_ects", 180),
            "total_exams":                    s.get("total_exams", 36),
        }


class GoalFactory:
    _map = {
        "studienzeitziel":          Studienzeitziel,
        "notenziel":                Notenziel,
        "exzellenzziel":            ExzellenzZiel,
        # New explicit keys (optional if you later split config):
        "kursdauer_klausur_ziel":   KursdauerKlausurZiel,
        "kursdauer_sonstige_ziel":  KursdauerSonstigeZiel,
        # Legacy combined (kept for BC; UI won’t use it)
        "kursdauerziel":            KursdauerZiel,
    }

    @classmethod
    def from_config(cls, cfg: dict) -> List[Ziel]:
        zcfg = (cfg.get("ziele") or {}) if isinstance(cfg.get("ziele"), dict) else {}
        goals: List[Ziel] = []

        explicit_klausur = "kursdauer_klausur_ziel" in zcfg
        explicit_sonstige = "kursdauer_sonstige_ziel" in zcfg

        # 1) Explicit specialized goals (preferred)
        if explicit_klausur:
            goals.append(KursdauerKlausurZiel(**zcfg["kursdauer_klausur_ziel"]))
        if explicit_sonstige:
            goals.append(KursdauerSonstigeZiel(**zcfg["kursdauer_sonstige_ziel"]))

        # 2) Legacy combined -> only fan-out if explicit ones aren't present
        if "kursdauerziel" in zcfg and not (explicit_klausur and explicit_sonstige):
            kd = zcfg["kursdauerziel"] or {}
            goals.append(KursdauerKlausurZiel(max_tage=kd.get("max_tage_klausur", 21)))
            goals.append(KursdauerSonstigeZiel(max_tage=kd.get("max_tage_sonstige", 42)))

        # 3) Remaining mapped goals
        for key, val in zcfg.items():
            if key in {"kursdauer_klausur_ziel", "kursdauer_sonstige_ziel", "kursdauerziel"}:
                continue
            if key in cls._map:
                goals.append(cls._map[key](**val))

        return goals


class GoalEvaluator:
    def __init__(self, ziele: List[Ziel]) -> None:
        self.ziele = ziele
    def bewerte(self, studiengang: Studiengang):
        return {z.__class__.__name__: z.pruefe(studiengang) for z in self.ziele}

class CourseManager:
    @staticmethod
    def _find_semester(studiengang: Studiengang, sem_nr: int) -> Optional[Semester]:
        for s in studiengang.semester:
            if s.nummer == sem_nr:
                return s
        return None

    @staticmethod
    def _find_modul(sem: Semester, modul_name: str) -> Optional[Modul]:
        for m in sem.module:
            if m.name == modul_name:
                return m
        return None

    @staticmethod
    def _find_kurs(modul: Modul, kurs_name: str) -> Optional[Kurs]:
        for k in modul.kurse:
            if k.name == kurs_name:
                return k
        return None

    @staticmethod
    def add_modul(studiengang: Studiengang, sem_nr: int, modul_name: str) -> Modul:
        sem = CourseManager._find_semester(studiengang, sem_nr)
        if sem is None:
            sem = Semester(sem_nr)
            studiengang.semester.append(sem)
        existing = CourseManager._find_modul(sem, modul_name)
        if existing is not None:
            return existing
        m = Modul(modul_name)
        sem.module.append(m)
        return m

    @staticmethod
    def add_kurs(modul: Modul, name: str, ects: float, art: str = "Klausur", startdatum: Optional[date] = None) -> Kurs:
        existing = CourseManager._find_kurs(modul, name)
        if existing is not None:
            return existing
        kurs = Kurs(name, ects, Pruefungsleistung(art), startdatum)
        modul.kurse.append(kurs)
        return kurs
    
    @staticmethod
    def find_kurs(studiengang: Studiengang, sem_nr: int, modul_name: str, kurs_name: str) -> Optional[Kurs]:
        """Find a specific course in the studiengang."""
        sem = CourseManager._find_semester(studiengang, sem_nr)
        if sem is None:
            return None
        modul = CourseManager._find_modul(sem, modul_name)
        if modul is None:
            return None
        return CourseManager._find_kurs(modul, kurs_name)
    
    @staticmethod
    def move_kurs(studiengang: Studiengang,
                  from_sem: int, from_mod: str, kurs_name: str,
                  to_sem: int, to_mod: str) -> Optional[Kurs]:
        """Move a course between semesters/modules, returning the course or None."""
        kurs = CourseManager.find_kurs(studiengang, from_sem, from_mod, kurs_name)
        if kurs is None:
            return None

        # Remove from old module
        old_sem = CourseManager._find_semester(studiengang, from_sem)
        if old_sem:
            old_mod = CourseManager._find_modul(old_sem, from_mod)
            if old_mod:
                old_mod.kurse = [k for k in old_mod.kurse if k.name != kurs_name]
                # optionally clean up empties
                if len(old_mod.kurse) == 0:
                    old_sem.module = [m for m in old_sem.module if m.name != from_mod]
                    if len(old_sem.module) == 0:
                        studiengang.semester = [s for s in studiengang.semester if s.nummer != from_sem]

        # Add into destination module
        dest_sem = CourseManager._find_semester(studiengang, to_sem)
        if dest_sem is None:
            dest_sem = Semester(to_sem)
            studiengang.semester.append(dest_sem)

        dest_mod = CourseManager._find_modul(dest_sem, to_mod)
        if dest_mod is None:
            dest_mod = Modul(to_mod)
            dest_sem.module.append(dest_mod)

        dest_mod.kurse.append(kurs)
        return kurs


    @staticmethod
    def record_grade(kurs: Kurs, note: float) -> None:
        kurs.leistung.note = note
        kurs.leistung.bestanden = None  # Clear bestanden when grade is set
    
    @staticmethod
    def record_passed(kurs: Kurs, bestanden: bool) -> None:
        """Mark a course as passed/failed without a grade"""
        kurs.leistung.bestanden = bestanden

    @staticmethod
    def record_grade_and_date(kurs: Kurs, note: Optional[float] = None, datum: Optional[date] = None) -> None:
        """Record grade and/or date for a course."""
        if note is not None:
            kurs.leistung.note = note
        if datum is not None:
            kurs.leistung.datum = datum

    @staticmethod
    def delete_kurs(studiengang: Studiengang, sem_nr: int, modul_name: str, kurs_name: str) -> bool:
        """Delete a specific course from the studiengang. Returns True if deleted, False if not found."""
        sem = CourseManager._find_semester(studiengang, sem_nr)
        if sem is None:
            return False
        
        modul = CourseManager._find_modul(sem, modul_name)
        if modul is None:
            return False
        
        # Find and remove the course
        original_count = len(modul.kurse)
        modul.kurse = [k for k in modul.kurse if k.name != kurs_name]
        
        # If module is now empty, optionally remove it
        if len(modul.kurse) == 0:
            sem.module = [m for m in sem.module if m.name != modul_name]
            
            # If semester is now empty, optionally remove it
            if len(sem.module) == 0:
                studiengang.semester = [s for s in studiengang.semester if s.nummer != sem_nr]
        
        return len(modul.kurse) < original_count