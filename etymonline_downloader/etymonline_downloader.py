"""Main module."""


import json
import re
from concurrent import futures
from string import ascii_lowercase
from typing import FrozenSet, Iterator, NamedTuple

import requests
from bs4 import BeautifulSoup


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
    return re.sub(r"\\x\S*", "", content.strip())


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


def get_page(url: str, **kwargs) -> BeautifulSoup:
    req = requests.get(url, **kwargs)
    req.raise_for_status()
    return BeautifulSoup(req.content, "html.parser")


def get_letter_pages_count(soup: BeautifulSoup) -> int:
    selected = soup.select("ul.ant-pagination li")

    final_page_title = selected[-2].text

    if not final_page_title.isnumeric():
        raise TypeError("Could not get page count")

    return int(final_page_title)


def iter_letter_pages(letter: str) -> Iterator[BeautifulSoup]:
    print(f"Fetching pages for {letter}")
    base_url = "https://www.etymonline.com/search?q="
    index_url = base_url + letter
    soup = get_page(index_url)

    numbered_page_url = index_url + "&page={n}"

    pages_count = get_letter_pages_count(soup)

    pages = [numbered_page_url.format(n=n) for n in range(1, pages_count + 1)]

    for page in pages:
        yield get_page(page)


def get_letter_words(letter: str):
    for page in iter_letter_pages(letter.lower()):
        for word in iter_page_words(page):
            print(f"Got data for {word.name}")
            yield word


def fetch_letter_words_async(letter: str) -> frozenset:
    return frozenset(word for word in get_letter_words(letter))


def fetch_words_async():
    fetched_word_entries = []

    with futures.ProcessPoolExecutor() as executor:
        results = [
            executor.submit(fetch_letter_words_async, letter)
            for letter in ascii_lowercase
        ]

    for word_future in futures.as_completed(results):
        try:
            words: FrozenSet[WordEntry] = word_future.result()
            fetched_word_entries.extend(words)
            print(f"fetched {len(words)} words")

        except Exception as e:
            print(e)

    return fetched_word_entries


def main():
    entries = fetch_words_async()

    with open("entries.json", "w") as outfile:
        json.dump(entries, outfile)


if __name__ == "__main__":
    main()
