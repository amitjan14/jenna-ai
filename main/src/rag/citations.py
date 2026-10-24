"""Render requested source details from trusted retrieval metadata, not model guesses."""
import re
from main.src.utils import regex_constants as rx


def requests_source_details(question):
    return bool(re.search(rx.SOURCE_PAGE_REQUEST, question, re.I)
                or re.search(rx.SOURCE_QUOTE_REQUEST, question, re.I))


def valid_page(page):
    return type(page) is int and page > 0


def add_source_details(question, answer, support, sources):
    if not requests_source_details(question):
        return answer
    blocks = []
    quotes = []
    for item in support:
        source = sources[item['source_id']]
        quote = item['quote']
        quotes.append(quote)
        citation = source.get('filename') or 'Source'
        if valid_page(source.get('page')):
            citation += f", page {source['page']}"
        elif re.search(rx.SOURCE_PAGE_REQUEST, question, re.I):
            citation += ', page number unavailable'
        if source.get('url'):
            citation += ' · ' + source['url']
        blocks.append('Supporting quotation:\n' + '\n'.join('> ' + line for line in quote.splitlines())
                      + f"\n\nSource: {citation} [{item['source_id'] + 1}]")
    # The extractive answer is already the quotation; avoid printing it twice.
    if answer.strip() == '\n\n'.join(quotes).strip():
        return '\n\n'.join(blocks)
    return answer + '\n\n' + '\n\n'.join(blocks)
