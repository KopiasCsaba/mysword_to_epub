# MySword to EPUB Converter

A Python tool that converts MySword Bible databases into EPUB 2.0 format files optimized for e-readers.

## Features

- ✅ Converts MySword `.bbl.mybible` text databases to EPUB format
- ✅ Uses MySword `.lang.mybible` language databases for book names
- ✅ EPUB 2.0 compliant output with OEBPS structure
- ✅ Optimized for e-readers (tested with KoReader)
- ✅ Generates clean, minimal HTML with proper navigation
- ✅ Supports cross-references (optional)

<img src="docs/kjvepub.gif" alt="Preview in KOReader" width="250" />

## Requirements

- Python 3.6+
- MySword Bible databases (`.bbl.mybible` and `.lang.mybible` files)

## Installation

```bash
git clone https://github.com/KopiasCsaba/mysword-to-epub.git
cd mysword-to-epub
```

## Usage
### Download modules
You can install the mysword android app and use it to download modules, then use files from your /sdcard/mysword.

Or:
 * Download a language file:
    * https://mysword.info/download-mysword/languages
    * Make sure to unzip, to get a `*.lang.mybible` file
    * If you need the english language, you can find it [here](https://raw.githubusercontent.com/KopiasCsaba/mysword_to_epub/refs/heads/main/docs/en-US-English.lang.mybible). 
 * [Download mysword modules](https://duckduckgo.com/?q=mysword+modules&t=brave&ia=web)
    * Make sure to have `*.bbl.mybible` files.
 
### Basic Usage

Convert a single Bible translation:

```bash
python3 mysword_to_epub.py \
 --bbl mysword/bibles/kjv2000.bbl.mybible \
 --lang docs/en-US-English.lang.mybible \
 --output /tmp/kjv2000.epub \
```

To enable crossreferences, you need an `*.xrefs.twm` file. 
Mysword puts it under mysword/mydata/default.xrefs.twm, you may find [other modules](https://duckduckgo.com/?q=download+.xrefs.twm+bible+references&t=brave&ia=web) providing this as well.

```bash
python3 mysword_to_epub.py \
 --bbl mysword/bibles/kjv2000.bbl.mybible \
 --lang docs/en-US-English.lang.mybible \
 --xrefs mysword/mydata/default.xrefs.twm \
 --output /tmp/kjv2000.epub \
 --title "KJV 2000 With Refs"
```

### Command Line Options

```bash
python3 mysword_to_epub.py --help

usage: mysword_to_epub.py [-h] --bbl BBL --lang LANG [--xrefs XREFS] [--title TITLE] [--output OUTPUT]

Generate EPUB from SQLite bibles.

options:
  -h, --help       show this help message and exit
  --bbl BBL        Path to .bbl.mybible SQLite file
  --lang LANG      Path to .lang.mybible SQLite file
  --xrefs XREFS    (optional) Path to .xrefs.twm SQLite cross-reference file 
  --title TITLE    (optional) Title for the EPUB (defaults to basename of --bbl without .bbl.mybible extension)
  --output OUTPUT  (optional) Output EPUB file (defaults to "<title>.epub")
```


## MySword Resources

- [MySword Modules Format Documentation](https://mysword.info/modules-format)
- MySword databases can be downloaded from various online repositories

## Example

```bash
# Convert KJV Bible to EPUB
python3 mysword_to_epub.py \
  --text-db mysword/bibles/kjv.bbl.mybible \
  --books-db mysword/languages/en-English.lang.mybible \
  --output kjv-bible.epub
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is released into the public domain. See the [LICENSE](LICENSE) file for details.

