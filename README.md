# Simple Tool for verifying / editing Image Exif Data

## Getting started
### Setup project
1. Create Python env with: `python3 -m venv env`
2. Activate Environment: `.\env\Scripts\activate`
3. Install requirements: `pip install -r requirements.txt`
And you are done 🚀

### Usage
#### Log all Files without exif data
**Command:** `python3 main.py verifyDate <Path to Folder>`
**Result:** Programs analyzes all png, jpg and jpeg images. If no exif data is found. It will be added to the created excel sheet.

#### Add specific date if no information for image is available
**Command:** `python3 main.py addMissingDate <Path to Folder> <default Date>`
**Result:** Programms adds default date to images if there is no exif data present.
This will also convert all png images to jpg format! ⚠️

#### Add specific date if no information for image is available
**Command:** `python3 main.py setImageDate <Path to Image> <Date>`
**Result:** Programms overrides exif date for image. If image has currently no exif data, the program will add it.
This will also convert all png images to jpg format! ⚠️