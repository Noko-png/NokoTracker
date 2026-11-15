"""Convert a MacroFactor XLSX export into a separate NokoTracker import DB.

Run with the backend virtualenv. Existing output files are never overwritten.
No writes are made to the application's live database.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app import models
from app.routers.backups import validate_sqlite_database
from app.services.nutrition_service import calculate_recipe_nutrition

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
MACROS = {'Calories (kcal)': 'calories', 'Protein (g)': 'protein',
          'Fat (g)': 'fat', 'Carbs (g)': 'carbs'}


def read_workbook(path):
    sheets = {}
    with zipfile.ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(t.text or '' for t in e.findall('.//m:t', NS))
                       for e in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        book = ET.fromstring(archive.read('xl/workbook.xml'))
        props = book.find('m:workbookPr', NS)
        epoch = datetime(1904, 1, 1) if props is not None and props.get('date1904') in ('1', 'true') else datetime(1899, 12, 30)
        relationships = {e.get('Id'): e.get('Target') for e in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        for sheet in book.find('m:sheets', NS):
            target = relationships[sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')]
            target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
            headers, data = {}, []
            for row in ET.fromstring(archive.read(target)).findall('.//m:sheetData/m:row', NS):
                values = {}
                for cell in row:
                    col = re.sub(r'\d', '', cell.get('r'))
                    value = cell.find('m:v', NS)
                    value = value.text if value is not None else None
                    kind = cell.get('t')
                    if kind == 's' and value is not None:
                        value = strings[int(value)]
                    elif kind == 'inlineStr':
                        value = ''.join(t.text or '' for t in cell.findall('.//m:t', NS))
                    elif kind == 'e':
                        raise ValueError(f'Excel error in {sheet.get("name")} {cell.get("r")}')
                    elif value is not None and kind not in ('str', 'b'):
                        value = float(value)
                    if value is not None and value != '':
                        values[col] = value
                if not headers:
                    headers = values
                    continue
                if values:
                    record = {headers[k]: v for k, v in values.items() if k in headers}
                    if 'Date' in record:
                        record['Date'] = (epoch + timedelta(days=record['Date'])).isoformat()
                    data.append(record)
            sheets[sheet.get('name')] = data
    return sheets


def number(record, key, default=None):
    value = record.get(key, default)
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f'Invalid {key}: {value}')
    return value


def food_key(name):
    return ' '.join(name.split()).casefold()


def ingredient_names(data):
    for recipe in data.get('Recipes', []):
        for line in (recipe.get('Ingredients') or '').splitlines():
            # The export suffix describes the amount, not part of the food name.
            name = re.sub(r'\s+\((?=[0-9¼½¾]).*\)$', '', line).strip()
            if name:
                yield name


def import_foods(session, data, report):
    """Keep every name, distinguish missing nutrition, retain conflicting variants."""
    by_name = {}
    report['food_mapping'] = []
    report['foods_needing_nutrition'] = []

    def remember(name, food, source):
        report['food_mapping'].append({'source': source, 'original_name': name,
                                       'food_name': food.name})

    for source in ('Custom Foods', 'Favorites'):
        for row in data.get(source, []):
            name = row['Food Name'].strip()
            key = food_key(name)
            weight = number(row, 'Serving Weight (g)')
            complete = bool(weight) and all(k in row for k in MACROS)
            values = {field + '_per_100g': (number(row, k, 0) * 100 / weight if weight else 0)
                      for k, field in MACROS.items()}
            extra = {
                'fiber_per_100g': number(row, 'Fiber (g)', 0) * 100 / weight if weight else 0,
                'sugar_per_100g': number(row, 'Sugars (g)', 0) * 100 / weight if weight else 0,
                'caffeine_mg_per_100g': number(row, 'Caffeine (mg)') * 100 / weight
                    if weight and 'Caffeine (mg)' in row else None,
            }
            previous = by_name.get(key)
            if previous is not None:
                if not complete or (previous.category == 'MacroFactor Import' and
                    previous.serving_size == weight and all(getattr(previous, k) == v for k, v in {**values, **extra}.items())):
                    remember(name, previous, source)
                    continue
                # Keep distinct nutritional variants instead of silently discarding them.
                suffix = 2
                variant = f'{name} (MF {suffix})'
                while food_key(variant) in by_name:
                    suffix += 1
                    variant = f'{name} (MF {suffix})'
                name = variant
            suspicious = complete and values['calories_per_100g'] > 1000
            category = ('MacroFactor - Naehrwerte fehlen' if not complete else
                        'MacroFactor - Angaben pruefen' if suspicious else 'MacroFactor Import')
            food = models.Food(name=name[:200], brand='MacroFactor', category=category,
                emoji='🍽️', purchase_date=None, serving_size=weight or 100, serving_unit='g',
                is_archived=suspicious, **values, **extra)
            session.add(food)
            by_name[food_key(name)] = food
            if previous is None or (complete and previous.category == 'MacroFactor - Naehrwerte fehlen'):
                by_name[key] = food
            remember(row['Food Name'], food, source)
            if not complete:
                report['foods_needing_nutrition'].append(food.name)
            if suspicious:
                report['warnings'].append(f'Unplausible source serving weight/calories, archived: {name}')

    names = [('History', r['Food Name']) for r in data.get('History', [])]
    names += [('Recipe ingredient', name) for name in ingredient_names(data)]
    for source, original in names:
        name = original.strip()
        key = food_key(name)
        if not key:
            continue
        if key not in by_name:
            food = models.Food(name=name[:200], brand='MacroFactor',
                category='MacroFactor - Naehrwerte fehlen', emoji='🍽️',
                purchase_date=None, serving_size=100, serving_unit='g')
            session.add(food)
            by_name[key] = food
            report['foods_needing_nutrition'].append(food.name)
        remember(original, by_name[key], source)
    session.flush()
    assert all(item['food_name'] for item in report['food_mapping'])


def convert(source, output, username):
    if output.exists():
        raise FileExistsError(output)
    data = read_workbook(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    archive_path = output.with_suffix('.source.json')
    report_path = output.with_suffix('.report.json')
    if archive_path.exists() or report_path.exists():
        raise FileExistsError('Companion output already exists')
    report = {'profile': username, 'source': source.name,
              'source_rows': {k: len(v) for k, v in data.items()}, 'warnings': [],
              'recipes_without_nutrition': []}
    engine = create_engine('sqlite:///' + output.resolve().as_posix())
    models.Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        user = models.User(username=username, password='!')
        session.add(user)
        session.flush()
        micros = {r['Date']: r for r in data.get('Micronutrients', [])}
        for row in data['Scale Weight']:
            weight = number(row, 'Weight (kg)')
            if weight is None:
                continue
            if weight <= 0:
                raise ValueError('Non-positive weight')
            notes = 'MacroFactor: gemessenes Gewicht.'
            if 'Fat Percent' in row:
                notes += f' Koerperfett (Originalwert): {row["Fat Percent"]}.'
            session.add(models.WeightEntry(user_id=user.id, measured_at=datetime.fromisoformat(row['Date']), weight_kg=weight, notes=notes))
        for row in data['Calories & Macros']:
            if not any(key in row for key in MACROS):
                continue
            # Missing macros stay NULL; zero is a measured/exported zero.
            notes = 'MacroFactor-Tagesgesamtwerte; keine einzelnen Mahlzeiten oder Uhrzeiten exportiert. Datum unveraendert, Anzeigezeit 12:00.'
            micro = micros.get(row['Date'])
            if micro:
                notes += '\nMikronaehrstoffe (Original): ' + json.dumps(micro, ensure_ascii=False)
            session.add(models.MealLog(user_id=user.id,
                eaten_at=datetime.fromisoformat(row['Date']).replace(hour=12),
                quick_add_name='MacroFactor Tagesgesamt', quantity=1, unit='serving',
                meal_source='manual', notes=notes,
                **{'quick_' + field: number(row, key) for key, field in MACROS.items()}))
        import_foods(session, data, report)
        recipe_names = set()
        for index, row in enumerate(data.get('Recipes', []), 1):
            servings = number(row, 'Serving Qty') or 1
            weight = number(row, 'Total Weight (g)')
            complete = bool(weight) and all(key in row for key in MACROS)
            description = (row.get('Description') or '') + '\nMacroFactor-Import. Originalzutaten:\n' + (row.get('Ingredients') or '')
            description += '\nOriginaldaten: ' + json.dumps(row, ensure_ascii=False)
            if not complete:
                description += '\nNICHT ZUM TRACKEN: Gesamtgewicht oder Naehrwerte fehlen. Zutaten und Naehrwerte vor Nutzung vervollstaendigen.'
                report['recipes_without_nutrition'].append(row['Recipe Name'])
            else:
                description += '\nNaehrwerte ueber Gesamtgericht abgebildet. Originalzutaten nur als Text; kein zutatenweiser Vorratsabzug.'
            name = row['Recipe Name'].strip()
            if name in recipe_names:
                name = f'{name} (MacroFactor {index})'
            recipe_names.add(name)
            recipe = models.Recipe(name=name, description=description,
                instructions='\n'.join(str(row[f'Step {i}']) for i in range(1, 100) if row.get(f'Step {i}')),
                servings=servings, created_by_user_id=user.id, is_archived=not complete,
                emoji='🍲', tags=['MacroFactor'],
                prep_time_minutes=number(row, 'Preparation Time (min)'),
                cook_time_minutes=number(row, 'Cooking Time (min)'))
            session.add(recipe)
            if complete:
                food = models.Food(name=f'MF Gesamtgericht {index}: {row["Recipe Name"]}'[:200],
                    brand='MacroFactor Rezept', category='MacroFactor Gesamtgericht',
                    emoji='🍲', purchase_date=None, serving_size=weight / servings, serving_unit='g',
                    **{field + '_per_100g': number(row, key) * 100 / weight for key, field in MACROS.items()})
                session.add(food)
                recipe.ingredients.append(models.RecipeIngredient(food=food, quantity=weight, unit='g',
                    notes='Gesamtgericht aus Export; Originalzutaten stehen in der Beschreibung.'))
                session.flush()
                actual = calculate_recipe_nutrition(recipe)
                for key, field in MACROS.items():
                    assert abs(actual[field] - row[key]) <= .011, (recipe.name, field)
    engine.dispose()
    counts, warnings = validate_sqlite_database(output)
    report['counts'] = {k: v for k, v in counts.items() if v}
    report['warnings'].extend(warnings)
    report['instructions'] = 'Einstellungen > Import und Export > Ausgewaehlte Datenbereiche ersetzen. Profil muss exakt ' + username + ' heissen. Gewicht, Mahlzeiten, Lebensmittel und Rezepte sind enthalten. Ausgewaehlte Bereiche werden ersetzt, nicht angehaengt. Nicht gesamte Datenbank ersetzen.'
    report['limitations'] = ['Schritte, Gewichtstrend, Verbrauch, Koerpermasse bleiben im source.json-Archiv; keine nativen NokoTracker-Felder.', 'Rezepte ohne Gesamtgewicht sind archiviert und vor Nutzung zu vervollstaendigen.', 'Fehlende Ballaststoff-/Zuckerwerte bei Lebensmitteln verwenden den NokoTracker-Standard 0; Original-Fehlwerte stehen im Archiv.', 'Lebensmittel ohne Naehrwerte sind aktive Platzhalter mit Kategorie MacroFactor - Naehrwerte fehlen. Numerische Nullwerte und 100-g-Portionen sind App-Standardwerte, keine Messwerte. Vor Tracking ergaenzen.', 'Keine persoenlichen Zielwerte aus Verbrauch geschaetzt; Profil verwendet App-Standardwerte. Teilimport behaelt vorhandene Profileinstellungen.']
    archive_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--username', required=True)
    args = parser.parse_args()
    convert(args.source, args.output, args.username)
