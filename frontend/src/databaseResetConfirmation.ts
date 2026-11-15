export function confirmDatabaseReset(confirm: (message: string) => boolean): boolean {
  return confirm("Möchtest du die gesamte Datenbank löschen? Alle Profile, Lebensmittel, Rezepte, Vorräte, Trainings- und Kalenderdaten werden entfernt.")
    && confirm("Letzte Sicherheitsabfrage: Wirklich ALLE Daten unwiderruflich löschen? Es wird keine automatische Sicherung erstellt. Bei Bedarf vorher die Datenbank herunterladen.");
}
