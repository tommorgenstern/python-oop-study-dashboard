from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import date
from typing import List
from .core import Studiengang
from typing import Callable

class Ziel(ABC):
    @abstractmethod
    def pruefe(self, studiengang: Studiengang) -> bool: ...

class Studienzeitziel(Ziel):
    def __init__(self, max_jahre: int) -> None:
        self.max_jahre = max_jahre
    def pruefe(self, studiengang: Studiengang) -> bool:
        dauer = (date.today() - studiengang.startdatum).days / 365.25  # Use leap year average
        return dauer <= self.max_jahre

class Notenziel(Ziel):
    def __init__(self, max_durchschnitt: float) -> None:
        self.max_durchschnitt = max_durchschnitt
    def pruefe(self, studiengang: Studiengang) -> bool:
        avg = studiengang.durchschnitt
        if avg is None:
            return False
        # Round both values to 1 decimal place for consistent comparison
        return round(avg, 1) <= round(self.max_durchschnitt, 1)

class ExzellenzZiel(Ziel):
    def __init__(self, mindestanteil: float = 0.10) -> None:
        self.mindestanteil = mindestanteil
    def pruefe(self, studiengang: Studiengang) -> bool:
        einsen = 0
        gesamt = 0
        for sem in studiengang.semester:
            for modul in sem.module:
                for kurs in modul.kurse:
                    # Use leistung.note instead of kurs.note for consistency
                    if kurs.leistung.note is not None:
                        gesamt += 1
                        if kurs.leistung.note == 1.0:
                            einsen += 1
        return gesamt > 0 and (einsen / gesamt) >= self.mindestanteil

class _KursdauerBasisZiel(Ziel):
    """Template method: shared iteration/logic; subclasses inject predicate and limit."""
    def __init__(self, max_tage: int, predicate: Callable[[str], bool]) -> None:
        self.max_tage = max_tage
        self._predicate = predicate

    def pruefe(self, studiengang: Studiengang) -> bool:
        for sem in studiengang.semester:
            for modul in sem.module:
                for kurs in modul.kurse:
                    # Only check completed courses with dates
                    if kurs.startdatum is None or kurs.leistung.datum is None:
                        continue
                    if not kurs.ist_abgeschlossen:
                        continue

                    art = (kurs.leistung.art or "").strip().lower()
                    if not self._predicate(art):
                        continue

                    delta = (kurs.leistung.datum - kurs.startdatum).days
                    if delta > self.max_tage:
                        return False
        return True

class KursdauerKlausurZiel(_KursdauerBasisZiel):
    """Checks only courses of art == 'klausur'."""
    def __init__(self, max_tage: int = 21) -> None:
        super().__init__(max_tage=max_tage, predicate=lambda art: art == "klausur")

class KursdauerSonstigeZiel(_KursdauerBasisZiel):
    """Checks only courses where art != 'klausur' (Hausarbeit, Projekt, ...)."""
    def __init__(self, max_tage: int = 42) -> None:
        super().__init__(max_tage=max_tage, predicate=lambda art: art != "klausur")

class KursdauerZiel(Ziel):
    """
    Backward-compatible adapter for old 'kursdauerziel' config blocks.
    Succeeds only if BOTH specialized goals pass.
    """
    def __init__(self, max_tage_klausur: int = 21, max_tage_sonstige: int = 42) -> None:
        self.klausur = KursdauerKlausurZiel(max_tage=max_tage_klausur)
        self.sonstige = KursdauerSonstigeZiel(max_tage=max_tage_sonstige)

    def pruefe(self, studiengang: Studiengang) -> bool:
        return self.klausur.pruefe(studiengang) and self.sonstige.pruefe(studiengang)
