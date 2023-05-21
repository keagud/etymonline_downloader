"""
download_pages
"""

# 2023-05-21


from concurrent import futures
from bs4 import BeautifulSoup
import requests
from typing import Final, Iterator

from typing import NamedTuple

from pathlib import Path


SAVE_DIR: Final = Path(__file__).parent.joinpath("pages/")


class EntryPage(NamedTuple):
    page: BeautifulSoup
    letter: str
    number: int


def get_letter_pages_count(soup: BeautifulSoup) -> int:
    selected = soup.select("ul.ant-pagination li")

    final_page_title = selected[-2].text

    if not final_page_title.isnumeric():
        raise TypeError("Could not get page count")

    return int(final_page_title)


def get_page(url: str) -> BeautifulSoup:
    res = requests.get(url)
    res.raise_for_status()

    soup = BeautifulSoup(res.content, "http.parser")
    return soup


def iter_letter_pages(letter: str) -> Iterator[EntryPage]:
    print(f"Fetching pages for {letter}")
    base_url = "https://www.etymonline.com/search?q="
    index_url = base_url + letter
    soup = get_page(index_url)

    numbered_page_url = index_url + "&page={n}"

    pages_count = get_letter_pages_count(soup)

    def make_page_entry(_url, _letter, _n):
        return EntryPage(get_page(_url), _letter, _n)

    page_futures: list[futures.Future[EntryPage]] = []
    failed = []

    with futures.ProcessPoolExecutor() as executor:
        for n in range(1, pages_count + 1):
            page_url = numbered_page_url.format(n=n)

            page_futures.append(executor.submit(make_page_entry, page_url, letter, n))

    for f in futures.as_completed(page_futures):
        page_exception = f.exception()
        if page_exception is not None:
            failed.append(page_exception)
            continue

        yield f.result()


def save_page(content: str, letter: str, page_number: int) -> None:
    target_path = SAVE_DIR.joinpath(letter.lower())

    if not target_path.exists():
        target_path.mkdir(parents=True, exist_ok=True)

    target_filename = f"{page_number:03d}_{letter.lower()}.html"

    with open(target_path.joinpath(target_filename), "w") as outfile:
        outfile.write(content)


def main():
    pass


if __name__ == "__main__":
    main()
