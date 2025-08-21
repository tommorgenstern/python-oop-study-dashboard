from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

@dataclass
class Pruefungsleistung:
    art: str
    note: Optional[float] = None
    datum: Optional[date] = None
    bestanden: Optional[bool] = None  # True = passed without grade, False = failed, None = not yet evaluated

@dataclass
class Kurs:
    name: str
    ects: float
    leistung: Pruefungsleistung = field(default_factory=lambda: Pruefungsleistung("Klausur"))
    startdatum: Optional[date] = None

    @property
    def note(self) -> Optional[float]:
        return self.leistung.note
    
    @property
    def ist_bestanden(self) -> bool:
        """Returns True if course is passed (either with grade <= 4.0 or explicitly marked as passed)"""
        if self.leistung.note is not None:
            return self.leistung.note <= 4.0
        return self.leistung.bestanden is True
    
    @property
    def ist_abgeschlossen(self) -> bool:
        """Returns True if course is completed (either graded or marked as passed/failed)"""
        return self.leistung.note is not None or self.leistung.bestanden is not None

@dataclass
class Modul:
    name: str
    kurse: List[Kurs] = field(default_factory=list)

    @property
    def ects(self) -> float:
        return sum(k.ects for k in self.kurse)

    @property
    def durchschnitt(self) -> Optional[float]:
        werte = [(k.note, k.ects) for k in self.kurse if k.note is not None]
        if not werte:
            return None
        return sum(n * e for n, e in werte) / sum(e for _, e in werte)

@dataclass
class Semester:
    nummer: int
    module: List[Modul] = field(default_factory=list)

@dataclass
class Studiengang:
    name: str
    startdatum: date
    semester: List[Semester] = field(default_factory=list)

    @property
    def durchschnitt(self) -> Optional[float]:
        """
        Calculate ECTS-weighted average grade for bachelor's degree.
        Each individual course grade is weighted by its ECTS credits.
        """
        total_weighted_points = 0.0
        total_ects = 0.0
        
        for semester in self.semester:
            for modul in semester.module:
                for kurs in modul.kurse:
                    # Only include courses with actual grades
                    if kurs.note is not None:
                        total_weighted_points += kurs.note * kurs.ects
                        total_ects += kurs.ects
        
        if total_ects == 0:
            return None
        
        return round(total_weighted_points / total_ects, 2)