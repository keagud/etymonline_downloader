"""Main module."""


from .download_pages import full_download
from .words_process import scrape_words


def main():
    full_download()
    scrape_words()


if __name__ == "__main__":
    main()
