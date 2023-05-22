"""
words_process
"""

# 2023-05-22

import re
import sqlite3
from concurrent import futures
from contextlib import suppress
from pathlib import Path
from typing import FrozenSet, Iterator, NamedTuple, Optional

from bs4 import BeautifulSoup
from download_pages import SAVE_DIR
from rich.progress import track


class WordEntry(NamedTuple):
    name: str
    content: str
    pos: str | None = None


def format_pos(token: str | None):
    if token is None:
        return None

    def strip_nonalnum(t: str):
        return "".join([c for c in t if c.isalnum()])

    if "," in token:
        elements = token.split(",")
        return ", ".join(strip_nonalnum(e) for e in elements)

    return strip_nonalnum(token)


def clean_html_content(content: str):
    chars_replaced = re.sub(r"\\x\S*", "", content.strip())

    whitespace_cleaned = re.sub(r"\s+", " ", chars_replaced)

    return re.sub(r"\n+", "\n", whitespace_cleaned)


def iter_page_words(soup: BeautifulSoup):
    words_matches = soup.select('div[class^="word"]')

    for word in words_matches:
        name_sel = word.select('a[class^="word__name"]')
        name = name_sel[0].text

        pos = None

        if "(" in name:
            entry_parts = name.split("(")
            name = entry_parts[0]

            pos = format_pos(entry_parts[1])

        content_sel = word.select("p")

        content_cleaned = [c.text.replace("\n", "") for c in content_sel]
        content = "\n".join(content_cleaned)

        name = clean_html_content(name)

        content = clean_html_content(content)

        yield WordEntry(name, content, pos)


def iter_local_paths(start_dir: Path | str = SAVE_DIR) -> Iterator[Path]:
    start_dir = Path(start_dir)
    for item in start_dir.iterdir():
        if item.is_dir():
            yield from iter_local_paths(start_dir=item)
            continue

        yield item


def words_from_file(filepath: Path):
    with open(filepath, "r") as infile:
        soup = BeautifulSoup(infile, "html.parser")

    words = frozenset(iter_page_words(soup))
    return words


class DbWriter:
    insert_query = "INSERT INTO words (name, content, pos) VALUES (?, ?, ?)"

    def __init__(
        self,
        db_path: Optional[Path | str] = None,
        ignore_duplicate: bool = True,
    ) -> None:
        if db_path is None:
            db_path = Path(__file__).parent.joinpath("words.db")
        else:
            db_path = Path(db_path)

        self.db_path = db_path
        self.ignore_duplicate = ignore_duplicate

        print(f"Saving words to {db_path}")

    def __enter__(self):
        self.connection = sqlite3.connect(self.db_path)
        self.cursor = self.connection.cursor()

        try:
            self.cursor.execute(
                """
            CREATE TABLE words (
                name TEXT,
                content TEXT,
                pos TEXT,
                UNIQUE (name, content, pos)
            );
            """
            )
        except sqlite3.OperationalError:
            pass

        self.connection.commit()
        return self

    def __exit__(self, exc_type: type, exc_value: BaseException, traceback):
        if self.ignore_duplicate and isinstance(exc_value, sqlite3.IntegrityError):
            return True

        self.connection.commit()
        self.connection.close()

        return False

    def write_single_word(self, word: WordEntry):
        if not self.ignore_duplicate:
            self.cursor.execute(self.insert_query, word)
            return

        with suppress(sqlite3.IntegrityError):
            self.cursor.execute(self.insert_query, word)

    def write_words(self, words: FrozenSet[WordEntry]):
        for word in words:
            self.write_single_word(word)


def scrape_words():
    with futures.ProcessPoolExecutor() as executor:
        processes = [
            executor.submit(words_from_file, file) for file in iter_local_paths()
        ]

        with DbWriter() as db:
            for result in track(
                futures.as_completed(processes),
                total=len(processes),
                description="Parsing words into database...",
            ):
                db.write_words(result.result())


def main():
    scrape_words()


if __name__ == "__main__":
    main()
