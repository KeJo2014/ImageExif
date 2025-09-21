import argparse
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import piexif
from tqdm import tqdm

# --- Configuration ---
SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".heic",
    ".tif",
    ".tiff",
    ".bmp",
    ".mov",
    ".mp4",
    ".3gp",
    ".avi",
    ".mkv",
    ".webm",
    ".mpg",
    ".m4v",
    ".raw",
    ".dng",
    ".cr2",
    ".nef",
}
EXIF_SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".tif", ".tiff"}


# --- NEW: Helper function for GPS coordinate conversion ---
def convert_decimal_to_dms(
    decimal_degrees: float,
) -> Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]:
    """Converts decimal degrees to a DMS (Degrees, Minutes, Seconds) tuple for EXIF."""
    degrees = int(abs(decimal_degrees))
    minutes_float = (abs(decimal_degrees) - degrees) * 60
    minutes = int(minutes_float)
    seconds_float = (minutes_float - minutes) * 60
    # Represent seconds with a precision of 1000 for the rational number
    seconds_numerator = int(seconds_float * 1000)
    seconds_denominator = 1000
    return (degrees, 1), (minutes, 1), (seconds_numerator, seconds_denominator)


# --- Core Functions (find_json_for_media and infer_date_from_name are unchanged) ---
def find_json_for_media(media_path: Path) -> Optional[Path]:
    """Finds the corresponding JSON metadata file for a given media file."""
    json_path = media_path.with_suffix(media_path.suffix + ".json")
    if json_path.exists():
        return json_path
    if "-edited" in media_path.stem or "-editada" in media_path.stem:
        original_stem = media_path.stem.replace("-edited", "").replace("-editada", "")
        json_path = media_path.with_name(original_stem + media_path.suffix + ".json")
        if json_path.exists():
            return json_path
    match = re.search(r"(\(\d+\))$", media_path.stem)
    if match:
        num_suffix = match.group(1)
        base_stem = media_path.stem.removesuffix(num_suffix)
        json_path = media_path.with_name(
            f"{base_stem}{media_path.suffix}{num_suffix}.json"
        )
        if json_path.exists():
            return json_path
    if len(media_path.stem) > 46:
        truncated_stem = media_path.stem[:46]
        json_path = media_path.with_name(truncated_stem + media_path.suffix + ".json")
        if json_path.exists():
            return json_path
    return None


def infer_date_from_name(path_str: str) -> Optional[datetime]:
    """Tries to guess the creation date from a file's name or its parent directory."""
    filename = Path(path_str).stem
    patterns = [
        re.compile(r"(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})"),
        re.compile(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})"),
        re.compile(r"_(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})_"),
        re.compile(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})"),
    ]
    for pattern in patterns:
        match = pattern.search(filename)
        if match:
            try:
                parts = [int(p) for p in match.groups()]
                return datetime(*parts)
            except ValueError:
                continue
    dir_match = re.search(r"Photos from (\d{4})", path_str)
    if dir_match:
        try:
            return datetime(int(dir_match.group(1)), 1, 1)
        except ValueError:
            pass
    return None


def handle_file_collision(target_path: Path) -> Path:
    """If a file already exists, find a new name by appending a number."""
    if not target_path.exists():
        return target_path
    counter = 1
    while True:
        new_name = f"{target_path.stem}_{counter}{target_path.suffix}"
        new_path = target_path.with_name(new_name)
        if not new_path.exists():
            return new_path
        counter += 1


# --- MODIFIED: EXIF function now handles both Date and GPS data ---
def set_exif_data(
    target_path: Path, date: datetime, geo_data: Optional[Dict[str, Any]]
):
    """Writes the creation date and GPS data to the EXIF of an image file."""
    try:
        try:
            exif_dict = piexif.load(str(target_path))
        except piexif.InvalidImageDataError:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

        # 1. Set Date/Time tags
        timestamp_str = date.strftime("%Y:%m:%d %H:%M:%S").encode("utf-8")
        exif_dict["0th"][piexif.ImageIFD.DateTime] = timestamp_str
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = timestamp_str
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = timestamp_str

        # 2. Set GPS tags if geo_data is available
        if geo_data:
            lat = geo_data.get("latitude")
            lon = geo_data.get("longitude")
            alt = geo_data.get("altitude")

            if lat is not None and lon is not None:
                # Convert to DMS and set EXIF GPS fields
                lat_dms = convert_decimal_to_dms(lat)
                lon_dms = convert_decimal_to_dms(lon)

                gps_ifd = {
                    piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S",
                    piexif.GPSIFD.GPSLatitude: lat_dms,
                    piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W",
                    piexif.GPSIFD.GPSLongitude: lon_dms,
                }
                if alt is not None:
                    alt_rational = (int(abs(alt) * 100), 100)
                    gps_ifd[piexif.GPSIFD.GPSAltitudeRef] = 0 if alt >= 0 else 1
                    gps_ifd[piexif.GPSIFD.GPSAltitude] = alt_rational

                exif_dict["GPS"] = gps_ifd

        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, str(target_path))

    except Exception:
        # Fails silently if EXIF writing is not possible
        pass


def process_takeout(input_dir: Path, output_dir: Path):
    """Main function to process the Google Photos Takeout directory."""
    print(f"🔍 Scanning for media files in: {input_dir}")
    all_files = list(input_dir.rglob("*.*"))
    media_files = [f for f in all_files if f.suffix.lower() in SUPPORTED_EXTENSIONS]

    if not media_files:
        print("❌ No supported media files found.")
        return

    print(f"✅ Found {len(media_files)} media files to process.")

    processed_count, no_meta_count, error_count = 0, 0, 0

    for media_path in tqdm(media_files, desc="Processing files", unit="file"):
        try:
            creation_date = None
            geo_data = None

            # --- MODIFIED: Load JSON once to get both date and geo-data ---
            json_path = find_json_for_media(media_path)
            if json_path:
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # Get timestamp
                    timestamp_str = data.get("photoTakenTime", {}).get("timestamp")
                    if timestamp_str:
                        creation_date = datetime.fromtimestamp(int(timestamp_str))

                    # Get geo-data
                    raw_geo = data.get("geoDataExif")
                    # Check for valid data; Google often uses (0,0,0) as null
                    if raw_geo and raw_geo.get("latitude") != 0.0:
                        geo_data = raw_geo
                except (json.JSONDecodeError, KeyError, ValueError):
                    pass

            # If no date from JSON, infer from name or use file modification time
            if not creation_date:
                creation_date = infer_date_from_name(str(media_path))
            if not creation_date:
                no_meta_count += 1
                creation_date = datetime.fromtimestamp(media_path.stat().st_mtime)
                tqdm.write(
                    f"⚠️ No metadata for {media_path.name}, using file modification time."
                )

            # Determine target directory and handle collisions
            year, month = creation_date.strftime("%Y"), creation_date.strftime("%m")
            target_dir = output_dir / year / month
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = handle_file_collision(target_dir / media_path.name)

            # Copy file, set EXIF data, and update modification time
            shutil.copy2(media_path, target_path)

            if media_path.suffix.lower() in EXIF_SUPPORTED_EXTENSIONS:
                set_exif_data(target_path, creation_date, geo_data)

            timestamp = creation_date.timestamp()
            os.utime(target_path, (timestamp, timestamp))

            processed_count += 1

        except Exception as e:
            tqdm.write(f"❌ Error processing {media_path.name}: {e}")
            error_count += 1

    # --- Final Summary ---
    print("\n--- 🎊 Processing Complete! 🎊 ---")
    print(f"Total files processed: {processed_count}")
    print(f"Files without valid metadata: {no_meta_count}")
    print(f"Errors: {error_count}")
    print(f"✅ Your organized photos and videos are in: {output_dir}")


# --- Command-Line Interface (unchanged) ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Organize Google Photos Takeout exports, fixing date and GPS metadata.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "input_dir",
        type=str,
        help="Path to the 'Google Photos' directory from your Takeout.",
    )
    parser.add_argument(
        "output_dir", type=str, help="Path to save the organized files."
    )
    args = parser.parse_args()

    input_path, output_path = Path(args.input_dir), Path(args.output_dir)

    if not input_path.is_dir():
        print(f"Error: Input directory not found at '{input_path}'")
    else:
        process_takeout(input_path, output_path)
