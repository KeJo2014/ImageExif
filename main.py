# File Traverser for Keller photos
# copyright Jonas Keller

import argparse
import piexif
import xlwt
import os

from PIL import Image
from pathlib import Path
from dateutil.parser import parse


class Traverser:
    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "mode",
            choices=["verifyDate", "addMissingDate", "setImageDate", "help"],
            help="Modus auswählen",
        )
        parser.add_argument(
            "params", nargs="*", help="Parameter für den gewählten Modus"
        )
        args = parser.parse_args()

        if args.mode == "verifyDate":
            if len(args.params) < 1:
                print("Fehlendes Argument: Ordner")
                return
            folder = args.params[0]
            self.verifyDate(folder)
        elif args.mode == "addMissingDate":
            if len(args.params) < 2:
                print("Fehlende Argumente: Ordner und Datum")
                return
            folder, date_str = args.params
            try:
                date = parse(date_str)
                date_str = date.strftime("%d.%m.%Y")
                print(f"Verarbeitetes Datum: {date_str}")
            except Exception as e:
                print(f"Fehler beim Parsen des Datums: {e}")
            self.addMissingDate(folder, date)
        elif args.mode == "setImageDate":
            if len(args.params) < 2:
                print("Fehlende Argumente: Datei und Datum")
                return
            picture, date_str = args.params
            try:
                date = parse(date_str)
                date_str = date.strftime("%d.%m.%Y")
                print(f"Verarbeitetes Datum: {date_str}")
            except Exception as e:
                print(f"Fehler beim Parsen des Datums: {e}")
            self.setImageDate(picture, date, override=True)
        elif args.mode == "help":
            print(
                """Dies ist ein tool zum einfachen Prüfen und Bearbeiten des Aufnahmedatums von Bilddateien.
Modi:
- verifyDate <Folder>: Durchsucht alle Dateien in einem Ordner und erstellt ein Excel Sheet mit allen Bildern ohne Exif Data
- addMissingDate <Folder> <Date>: Durchsucht alle Dateien im Ordner und schreibt gegf. das angegebene Datum in das Bild (Falls png Konvertierung in jpeg)
- setImageDate <Picture> <Date>: Ersetzt/Schreibt das Aufnahmedatum für das angegebene Bild"""
            )
        else:
            print("Ungültiges Argument")

    def verifyDate(self, folder):
        print("Start Date Verifying...")
        files_without_exif = []
        count = 0
        for path in self.__traverseImages__(folder):
            count += 1
            exif = Image.open(path)._getexif()
            if not exif:
                files_without_exif.append(path)
        print(
            f"Es wurden {count} viele Bilder gefunden, davon hatten {len(files_without_exif)} kein exif Datum ({round(len(files_without_exif)/count, 3)*100}%)"
        )
        self.__write_to_excel__("files_without_date", files_without_exif)

    def setImageDate(self, path, date, override):
        date = date.strftime("%Y:%m:%d %H:%M:%S")
        img = Image.open(path)
        exif = img._getexif()
        resp = 0
        if not exif or override:
            resp = 1
            exif_dict = {
                "0th": {},
                "Exif": {},
                "GPS": {},
                "1st": {},
                "thumbnail": None,
            }
            exif_dict["0th"][piexif.ImageIFD.DateTime] = date
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date

            exif_bytes = piexif.dump(exif_dict)
            path2 = path
            if img.format != "JPEG":
                jpg_path = str(path.with_suffix(".jpg"))
                img = img.convert("RGB")
                img.save(jpg_path, "JPEG")
                path = jpg_path
            piexif.insert(exif_bytes, str(path))
            if path != path2:
                os.remove(path2)
        return resp

    def addMissingDate(self, folder, date):
        print("Start Date Addition...")
        count = 0
        count_added = 0
        for path in self.__traverseImages__(folder):
            count += 1
            count_added += self.setImageDate(path, date, override=False)
        print(
            f"Es wurden {count} viele Bilder gefunden, davon erhielten {count_added} das exif Datum {date}"
        )

    def __traverseImages__(self, folder):
        types = ("png", "jpg", "jpeg")
        files_grabbed = []
        for typ in types:
            files_grabbed.extend(Path(folder).glob("**/*." + typ))
        return files_grabbed

    def __write_to_excel__(self, filename, data):
        book = xlwt.Workbook(encoding="utf-8")

        sheet1 = book.add_sheet("Dateien")

        sheet1.write(0, 0, "Pfad")

        i = 1
        for n in data:
            i = i + 1
            sheet1.write(i, 0, str(n))
        book.save(filename + ".xls")


Traverser()