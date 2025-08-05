#!/usr/bin/env python3
"""
Generate an EPUB file using the OEBPS directory structure from two SQLite databases:
 - Text database (.bbl.mybible) with table `Bible(Book INT, Chapter INT, Verse INT, Scripture TEXT)`
 - Books database (.lang.mybible) with table `biblebooks(id INT PRIMARY KEY, name TEXT, abbreviation TEXT, alternateabbreviations TEXT, tts_name TEXT)`

Usage:
    python3 v8.py --text-db path/to/text.db --books-db path/to/books.db [--output output.epub]
Produces an EPUB 2.0 file with minimal markup, organized under OEBPS/ for fast loading on e-readers.
"""
import argparse
import re
import sqlite3
import zipfile
import uuid
import logging
import sys
import os

# EPUB templates
CONTAINER_XML = '''<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>'''

CONTENT_OPF_TEMPLATE = '''<?xml version="1.0"?>
<package version="2.0" unique-identifier="BookId" xmlns="http://www.idpf.org/2007/opf">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>{title}</dc:title>
<dc:language>en</dc:language>
<dc:identifier id="BookId">{uuid}</dc:identifier>
</metadata>
<manifest>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
<item id="css" href="styles.css" media-type="text/css"/>
{manifest_items}
</manifest>
<spine toc="ncx">
{spine_items}
</spine>
</package>'''

TOC_NCX_TEMPLATE_HEAD = '''<?xml version="1.0"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head><meta name="dtb:uid" content="{uuid}"/></head>
<docTitle><text>{title}</text></docTitle>
<navMap>'''
TOC_NCX_TEMPLATE_TAIL = '''</navMap>
</ncx>'''

CHAPTER_TEMPLATE_FOOT = '''
</body>
</html>'''

# Global CSS for all XHTML files (KoReader-compatible)
# CSS class mappings: c=chaptertoc, b=booktoc, x=xref-indicator
GLOBAL_CSS = '''
.c a{display:inline-block;padding:.1em;font-weight:bold;margin:.1em;border:1px solid #888;min-width:2em;text-align:center;text-decoration:none}
.c{margin-bottom:1em}
.b{width:100%;border-collapse:collapse;margin-bottom:1em}
.b td{border:1px solid #888;margin:0;padding:0;text-align:center;width:25%}
.b a{display:block;text-decoration:none;font-weight:bold;font-family:Arial;font-size:.8em;text-transform:uppercase;margin:0;padding:4px 0}
#books{margin:0 0 0 5px;font-size:.7em}
.x{font-size:.9em;color:#cfcfcf;text-decoration:none;font-weight:bold;padding:0 2px;margin:0 1px;background-color:#f0f8ff;border-radius:2px}
.x:hover{color:#0044aa;text-decoration:underline;background-color:#e6f3ff}
'''

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )


def check_table_exists(conn, table_name):
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE (type='table' OR type='view') AND name=?;", (table_name,)
    )
    return cur.fetchone() is not None


def fetch_books(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM biblebooks ORDER BY id;")
    return {row[0]: row[1] for row in cur.fetchall()}


def fetch_verses(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT Book, Chapter, Verse, Scripture FROM Bible ORDER BY Book, Chapter, Verse;"
    )
    verses = {}
    for book, chap, verse, text in cur.fetchall():
        verses.setdefault(book, {}).setdefault(chap, []).append((verse, text))
    return verses


def fetch_cross_references(xrefs_conn):
    """Load and organize cross-references by verse"""
    if not xrefs_conn:
        return {}, {}
    
    try:
        cur = xrefs_conn.cursor()
        cur.execute("""
            SELECT fbi, fci, fvi, tbi, tci, tvi 
            FROM xrefs_bcv 
            ORDER BY fbi, fci, fvi
        """)
        
        xrefs_from = {}  # {(book, chapter, verse): [(to_book, to_chapter, to_verse), ...]}
        xrefs_to = {}    # {(book, chapter, verse): [(from_book, from_chapter, from_verse), ...]}
        
        # Process each cross-reference bidirectionally
        for from_book, from_chap, from_verse, to_book, to_chap, to_verse in cur.fetchall():
            from_key = (from_book, from_chap, from_verse)
            to_key = (to_book, to_chap, to_verse)
            
            # Add forward reference (from -> to)
            if from_key not in xrefs_from:
                xrefs_from[from_key] = []
            xrefs_from[from_key].append((to_book, to_chap, to_verse))
            
            # Add backward reference (to <- from)
            if to_key not in xrefs_to:
                xrefs_to[to_key] = []
            xrefs_to[to_key].append((from_book, from_chap, from_verse))
        
        logging.info(f"Loaded {len(xrefs_from)} verses with outgoing cross-references and {len(xrefs_to)} verses with incoming cross-references")
        return xrefs_from, xrefs_to
    
    except sqlite3.Error as e:
        logging.error(f"Error loading cross-references: {e}")
        return {}, {}


def generate_verse_indicators(book_id, chapter, verse, xrefs_from, xrefs_to):
    """Generate visual indicators for cross-references"""
    if not xrefs_from and not xrefs_to:
        return ''
    
    verse_key = (book_id, chapter, verse)
    has_from = xrefs_from and verse_key in xrefs_from
    has_to = xrefs_to and verse_key in xrefs_to
    
    if has_from and has_to:
        # return f' <a href="xrefs.xhtml#xref_b{book_id}c{chapter}v{verse}" class="xref-indicator">⊕ &nbsp; ⊗</a>'
        return f'<a href="x.html#x{book_id}-{chapter}-{verse}" class="x">⊗</a>'
    elif has_from:
        # return f' <a href="xrefs.xhtml#xref_b{book_id}c{chapter}v{verse}" class="xref-indicator">⊕</a>'
        return f'<a href="x.html#x{book_id}-{chapter}-{verse}" class="x">⊗</a>'
    elif has_to:
        return f'<a href="x.html#x{book_id}-{chapter}-{verse}" class="x">⊗</a>'
    else:
        return ''


def generate_cross_reference_section(books, xrefs_from, xrefs_to):
    """Generate comprehensive cross-reference section"""
    if not xrefs_from and not xrefs_to:
        return None
    
    # Collect all verses that have cross-references
    all_xref_verses = set()
    if xrefs_from:
        all_xref_verses.update(xrefs_from.keys())
    if xrefs_to:
        all_xref_verses.update(xrefs_to.keys())
    
    if not all_xref_verses:
        return None
    
    # Sort by book, chapter, verse
    sorted_verses = sorted(all_xref_verses)
    
    # Generate HTML content
    content = ['<html><head><title>X</title><link rel="stylesheet" href="styles.css"/></head><body><h1 id="c">X</h1>']
    
    for book_id, chapter, verse in sorted_verses:
        book_name = books.get(book_id, f"Book {book_id}")
        book_name = book_title_formatter(book_name)
        
        content.append(f'<h2 id="x{book_id}-{chapter}-{verse}"><a href="b{book_id}c{chapter}.html#{verse}">↩</a> {book_name} {chapter}:{verse} <a href="i.html#b">⇑</a></h2>')
        
        # References from this verse
        verse_key = (book_id, chapter, verse)
        if xrefs_from and verse_key in xrefs_from:
            content.append('<h4>From</h4>')
            content.append('<ul>')
            for to_book, to_chap, to_verse in xrefs_from[verse_key]:
                to_book_name = books.get(to_book, f"Book {to_book}")
                to_book_name = book_title_formatter(to_book_name)
                content.append(f'<li><a href="b{to_book}c{to_chap}.html#{to_verse}">{to_book_name} {to_chap}:{to_verse}</a></li>')
            content.append('</ul>')
        
        # References to this verse
        if xrefs_to and verse_key in xrefs_to:
            content.append('<h3>To</h3>')
            content.append('<ul>')
            for from_book, from_chap, from_verse in xrefs_to[verse_key]:
                from_book_name = books.get(from_book, f"Book {from_book}")
                from_book_name = book_title_formatter(from_book_name)
                content.append(f'<li><a href="b{from_book}c{from_chap}.html#{from_verse}">{from_book_name} {from_chap}:{from_verse}</a></li>')
            content.append('</ul>')
    
    content.append('</body></html>')
    return ''.join(content)


def create_epub(books, verses, output_path, title="Bible", xrefs_from=None, xrefs_to=None):
    book_uuid = f"urn:uuid:{uuid.uuid4()}"
    try:
        epub = zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_STORED)
        epub.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        epub.writestr('META-INF/container.xml', minify(CONTAINER_XML))
        epub.writestr('OEBPS/styles.css', GLOBAL_CSS)

        # Global books index: table layout with 3 columns, 22 rows
        book_list = [
            (bid, sorted(verses[bid].keys())[0], books[bid])
            for bid in sorted(verses.keys()) if books.get(bid)
        ]
        table_rows = ''
        for i in range(0, len(book_list), 4):
            row = book_list[i:i+4]
            # build the real cells
            cells = [
                f'<td><a href="b{bid}c{first}.html">{book_title_formatter(name)}</a></td>'
                for bid, first, name in row
            ]
            # pad up to 4 cells
            cells += ['<td></td>'] * (4 - len(cells))

            table_rows += '<tr>' + ''.join(cells) + '</tr>'
        index_table = f'<table class="b">{table_rows}</table>'

        index_page = f'<html><head><title>Books</title><link rel="stylesheet" href="styles.css"/></head><body><a id="b"/>{index_table}</body></html>'
        epub.writestr('OEBPS/i.html', index_page)

        manifest_items = ['<item id="index" href="i.html" media-type="application/xhtml+xml"/>']
        spine_items = ['<itemref idref="index"/>']
        toc_nav = []
        play_order = 1

        for book_id in sorted(verses.keys()):
            book_name = books.get(book_id)
            if not book_name: continue
            book_name = book_title_formatter(book_name)
            chapters = sorted(verses[book_id].keys())
            first = chapters[0]

            toc_nav.append(f'<navPoint id="{book_id}" playOrder="{play_order}"><navLabel><text>{book_name}</text></navLabel><content src="b{book_id}c{first}.html"/>')
            play_order += 1

            toc_links = ''.join(f'<a href="b{book_id}c{c}.html">{c}</a>' for c in chapters)
            for chap in chapters:
                fname = f'b{book_id}c{chap}.html'
                item_id = f'{book_id}-{chap}'
                manifest_items.append(f'<item id="{item_id}" href="{fname}" media-type="application/xhtml+xml"/>')
                spine_items.append(f'<itemref idref="{item_id}"/>')

                toc_nav.append(f'<navPoint id="{book_id}-{chap}" playOrder="{play_order}"><navLabel><text>{book_name} {chap}</text></navLabel><content src="{fname}"/>')
                play_order += 1

                for vnum, _ in verses[book_id][chap]:
                    toc_nav.append(f'<navPoint id="{book_id}-{chap}-{vnum}" playOrder="{play_order}"><navLabel><text>{book_name} {chap}:{vnum}</text></navLabel><content src="{fname}#{vnum}"/></navPoint>')
                    play_order += 1

                toc_nav.append('</navPoint>')

                if chap == first:
                    heading = f'<html><head><title>{book_name} {chap}</title><link rel="stylesheet" href="styles.css"/></head><body><h1 id="toc">{book_name}</h1><div class="c">{toc_links}</div><h2>{book_name} {chap} <a href="i.html#b">⇑</a> <a href="#toc">↑</a></h2>'
                else:
                    heading = f'<html><head><title>{book_name} {chap}</title><link rel="stylesheet" href="styles.css"/></head><body><h2>{book_name} {chap} <a href="i.html#b">⇑</a> <a href="b{book_id}c{first}.html#toc">↑</a></h2>'
                content = [heading]
                for vnum, text in verses[book_id][chap]:
                    # Handle NULL/empty text
                    safe_text = text if text is not None else ""
                    # Strip MySword formatting tags
                    clean_text = strip_mysword_tags(safe_text)
                    # Escape HTML entities
                    escaped_verse = clean_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    indicators = generate_verse_indicators(book_id, chap, vnum, xrefs_from, xrefs_to)
                    content.append(f'<a href="#{vnum}" id="{vnum}">{vnum}</a> {escaped_verse} {indicators}<br/>')
                content.append(CHAPTER_TEMPLATE_FOOT)
                epub.writestr(f'OEBPS/{fname}', ''.join(content))

            toc_nav.append('</navPoint>')

        # Generate cross-reference section if cross-references are available
        xref_content = generate_cross_reference_section(books, xrefs_from, xrefs_to)
        if xref_content:
            epub.writestr('OEBPS/x.html', xref_content)
            manifest_items.append('<item id="xrefs" href="x.html" media-type="application/xhtml+xml"/>')
            spine_items.append('<itemref idref="xrefs"/>')
            
            # Add cross-reference section to TOC
            toc_nav.append(f'<navPoint id="x" playOrder="{play_order}"><navLabel><text>Cross References</text></navLabel><content src="x.html#c"/></navPoint>')
            
            logging.info("Cross-reference section added to EPUB")

        epub.writestr('OEBPS/content.opf', 
            CONTENT_OPF_TEMPLATE.format(
                title=title,
                uuid=book_uuid,
                manifest_items=''.join(manifest_items),
                spine_items=''.join(spine_items)
            )
        )
        epub.writestr('OEBPS/toc.ncx', ''.join([TOC_NCX_TEMPLATE_HEAD.format(title=title, uuid=book_uuid)] + toc_nav + [TOC_NCX_TEMPLATE_TAIL]))
        epub.close()
        logging.info(f"EPUB successfully created: {output_path}")
    except Exception as e:
        logging.error(f"Failed to create EPUB: {e}")
        sys.exit(1)


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Generate EPUB from SQLite bibles.")
    parser.add_argument('--bbl', required=True, help='Path to .bbl.mybible SQLite file')
    parser.add_argument('--lang', required=True, help='Path to .lang.mybible SQLite file')
    parser.add_argument('--xrefs', help='Path to .xrefs.twm SQLite cross-reference file (optional)')
    parser.add_argument('--title', help='Title for the EPUB (optional, defaults to basename of --bbl without .bbl.mybible extension)')
    parser.add_argument('--output', help='Output EPUB file (optional, defaults to "<title>.epub")')
    args = parser.parse_args()
    
    # Determine title if not provided
    if not args.title:
        bbl_basename = os.path.basename(args.bbl)
        if bbl_basename.endswith('.bbl.mybible'):
            args.title = bbl_basename[:-12]  # Remove .bbl.mybible extension
        else:
            args.title = bbl_basename
    
    # Determine output filename if not provided
    if not args.output:
        args.output = f"{args.title}.epub"

    try:
        text_conn = sqlite3.connect(args.bbl)
        books_conn = sqlite3.connect(args.lang)
        
        xrefs_conn = None
        if args.xrefs:
            try:
                xrefs_conn = sqlite3.connect(args.xrefs)
                logging.info(f"Cross-reference database loaded: {args.xrefs}")
            except sqlite3.Error as e:
                logging.warning(f"Unable to open cross-reference database: {e}. Continuing without cross-references.")
                xrefs_conn = None
    except sqlite3.Error as e:
        logging.error(f"Unable to open required databases: {e}")
        sys.exit(1)

    if not check_table_exists(text_conn, 'Bible'):
        logging.error("Table 'Bible' not found in text DB.")
        sys.exit(1)
    if not check_table_exists(books_conn, 'biblebooks'):
        logging.error("Table 'biblebooks' not found in books DB.")
        sys.exit(1)
    
    if xrefs_conn and not check_table_exists(xrefs_conn, 'xrefs_bcv'):
        logging.warning("Table/view 'xrefs_bcv' not found in cross-reference DB. Continuing without cross-references.")
        xrefs_conn.close()
        xrefs_conn = None

    books = fetch_books(books_conn)
    verses = fetch_verses(text_conn)
    xrefs_from, xrefs_to = fetch_cross_references(xrefs_conn)

    # Close database connections
    text_conn.close()
    books_conn.close()
    if xrefs_conn:
        xrefs_conn.close()

    create_epub(books, verses, args.output, args.title, xrefs_from, xrefs_to)



def minify(xml_or_html: str) -> str:
    return re.sub(r'>\s+<', '><', xml_or_html).strip()

def strip_mysword_tags(text: str) -> str:
    """
    Remove MySword Bible formatting tags from text.
    
    MySword Bible tags (currently stripped, may implement in future):
    - <CM> - paragraph end marker
    - <FI>...</FI> - Italicized words (added words)
    - <FR>...</FR> - words of Jesus in Red
    - <FU>...</FU> - underlined words
    - <WG#> - Strong Greek number tag
    - <WH#> - Strong Hebrew number tag  
    - <WT#> - Morphological tag
    - <RF>...</RF> - Translators' notes
    - <RX#> - Cross-reference
    - <TS>...</TS> - Title
    - <PF#> - first line indent (0-7)
    - <PI#> - indent (0-7)
    - <Q>...</Q> - Interlinear block
    - <E>...</E> - English translation
    - <X>...</X> - Transliteration
    """
    if not text:
        return text
    
    # Remove paragraph markers
    text = re.sub(r'<CM>', '', text)
    
    # Remove paired formatting tags (keep inner content)
    text = re.sub(r'<FI>(.*?)<Fi>', r'\1', text, flags=re.IGNORECASE)  # Italics
    text = re.sub(r'<FR>(.*?)<Fr>', r'\1', text, flags=re.IGNORECASE)  # Red letters (Jesus)  
    text = re.sub(r'<FU>(.*?)<Fu>', r'\1', text, flags=re.IGNORECASE)  # Underlined
    text = re.sub(r'<RF>(.*?)<Rf>', r'', text, flags=re.IGNORECASE)    # Remove translator notes
    text = re.sub(r'<TS>(.*?)</TS>', r'\1', text)  # Keep title content
    text = re.sub(r'<Q>(.*?)</Q>', r'\1', text)    # Keep interlinear content
    text = re.sub(r'<E>(.*?)</E>', r'\1', text)    # Keep English translation
    text = re.sub(r'<X>(.*?)</X>', r'\1', text)    # Keep transliteration
    
    # Remove Strong's numbers and morphological tags
    text = re.sub(r'<WG\d+>', '', text)  # Greek Strong's numbers
    text = re.sub(r'<WH\d+>', '', text)  # Hebrew Strong's numbers
    text = re.sub(r'<WT\d+>', '', text)  # Morphological tags
    text = re.sub(r'<RX\d+>', '', text)  # Cross-references
    
    # Remove indentation tags
    text = re.sub(r'<PF\d>', '', text)   # First line indent
    text = re.sub(r'<PI\d>', '', text)   # Paragraph indent
    
    # Clean up any remaining unknown tags (safety net)
    text = re.sub(r'<[^>]*>', '', text)
    
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def book_title_formatter(s: str) -> str:
    """
    If the string starts with one or more digits immediately followed by
    a non-digit, non-dot, non-space character, insert a '. ' after the digits.
    """
    return re.sub(r'^(\d+)(?=[^\d\.\s])', r'\1. ', s)

if __name__ == '__main__':
    main()
