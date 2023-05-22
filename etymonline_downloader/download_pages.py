"""
download_pages
"""

# 2023-05-21


import sys
from concurrent import futures
from functools import cache
from os import PathLike
from pathlib import Path
from string import ascii_lowercase
from typing import Final, Iterator, NamedTuple

import requests
from bs4 import BeautifulSoup
from rich.progress import Progress, track

SAVE_DIR: Final = Path(__file__).parent.joinpath("pages/")


class EntryPage(NamedTuple):
    content: str
    letter: str
    number: int


class DownloadUpdate(NamedTuple):
    letter: str
    page_number: int
    pages_total: int


def get_soup_from_file(filename: PathLike | str) -> BeautifulSoup:
    path = Path(filename)

    with open(path, "r") as infile:
        text = infile.read()

    return BeautifulSoup(text, "html.parser")


def get_letter_pages_count(soup: BeautifulSoup) -> int:
    selected = soup.select("ul.ant-pagination li")

    final_page_title = selected[-2].text

    if not final_page_title.isnumeric():
        raise TypeError("Could not get page count")

    return int(final_page_title)


def index_page_urls() -> list[str]:
    base_url = "https://www.etymonline.com/search?q="
    return [base_url + letter for letter in ascii_lowercase]


@cache
def make_filepath(letter: str, page_number: int) -> Path:
    return SAVE_DIR.joinpath(letter, f"{page_number:03d}_{letter.lower().strip()}.html")


def download_index(letter: str):
    if make_filepath(letter, 1).exists():
        # print(f"Using cached page for '{letter}'")
        return
    base_url = "https://www.etymonline.com/search?q="
    get_page(base_url + letter)
    save_page(letter)


def fetch_index_pages():
    failed: list[BaseException] = []

    with futures.ProcessPoolExecutor() as exec:
        downloads = [exec.submit(download_index, letter) for letter in ascii_lowercase]

        for completed in futures.as_completed(downloads):
            process_err = completed.exception()

            if process_err is not None:
                failed.append(process_err)
                print(process_err)
                continue

        futures.wait(downloads)

    return failed if failed else None


def parse_index_pages() -> dict[str, BeautifulSoup]:
    fetch_index_pages()
    processed_pages: dict[str, BeautifulSoup] = {}

    parse_futures: dict[futures.Future[BeautifulSoup], str] = {}
    failed = []

    with futures.ProcessPoolExecutor() as executor:
        for path in (_path for _path in SAVE_DIR.iterdir() if _path.is_dir()):
            index_letter = path.name.strip()
            letter_page_path = path.joinpath(f"001_{index_letter}.html")
            process = executor.submit(get_soup_from_file, letter_page_path)

            parse_futures[process] = index_letter

    for done in track(
        futures.as_completed(parse_futures), description="Parsing indicies..."
    ):
        parse_failure = done.exception()

        if parse_failure is not None:
            print(parse_failure, file=sys.stderr)
            failed.append(parse_failure)
            continue

        key = parse_futures[done]

        processed_pages[key] = done.result()

    return processed_pages


def parse_index_pages_sync() -> dict[str, BeautifulSoup]:
    fetch_index_pages()

    pages = {}

    for path in (_path for _path in SAVE_DIR.iterdir() if _path.is_dir()):
        index_letter = path.name.strip()
        letter_page_path = make_filepath(index_letter, page_number=1)

        pages[index_letter] = get_soup_from_file(letter_page_path)

    return pages


@cache
def get_url(letter: str, page_number: int = 1) -> str:
    return f"https://www.etymonline.com/search?q={letter}&page={page_number}"


@cache
def get_page(letter: str, page_number: int = 1) -> str:
    url = get_url(letter, page_number=page_number)
    res = requests.get(url)
    res.raise_for_status()
    return res.content.decode("utf-8")


@cache
def count_all_pages():
    pages = parse_index_pages_sync()
    return {k: get_letter_pages_count(v) for k, v in pages.items()}


@cache
def save_page(letter: str, page_number: int = 1) -> None:
    target_path = SAVE_DIR.joinpath(letter.lower())

    content = get_page(letter, page_number=page_number)

    if not target_path.exists():
        target_path.mkdir(parents=True, exist_ok=True)

    target_filename = f"{page_number:03d}_{letter.lower().strip()}.html"

    with open(target_path.joinpath(target_filename), "w") as outfile:
        outfile.write(content)


def save_all_pages() -> Iterator[DownloadUpdate]:
    fetch_index_pages()

    page_counts = count_all_pages()

    dl_futures: dict[futures.Future[None], tuple[str, int]] = {}

    failed = []

    with futures.ProcessPoolExecutor() as exec:
        for letter, pages_count in page_counts.items():
            # print(f"Fetching {letter} with {pages_count} pages")

            for n in range(1, pages_count + 1):
                page_future = exec.submit(save_page, letter, n)
                dl_futures[page_future] = (letter, n)

                # print(f"\tSubmitting {letter}, page {n} of {pages_count}")

        for done in futures.as_completed(dl_futures):
            process_err = done.exception()

            if process_err is not None:
                failed.append(process_err)
                print(process_err, file=sys.stderr)
                continue

            done_letter, done_n = dl_futures[done]

            yield DownloadUpdate(done_letter, done_n, page_counts[done_letter])

            # print(f"Fetched {done_letter} {done_n}/{page_counts[done_letter]}")


def full_download():
    fetch_index_pages()
    index_pages = parse_index_pages_sync()
    page_counts = {k: get_letter_pages_count(v) for k, v in index_pages.items()}

    overall_sum = sum(page_counts.values())

    with Progress() as progress:
        task = progress.add_task(description="Downloading entries", total=overall_sum)
        for result in save_all_pages():
            result_percent = (result.page_number / result.pages_total) * 100

            update_template = (
                "Downloading section '{letter}' {n:03d}/{total:03d} ({percent:04.02f}%)"
            )

            update_msg = update_template.format(
                letter=result.letter,
                n=result.page_number,
                total=result.pages_total,
                percent=result_percent,
            )

            progress.update(task, description=update_msg, advance=1)


def main():
    full_download()


if __name__ == "__main__":
    main()
