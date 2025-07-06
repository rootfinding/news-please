from copy import deepcopy

from readability import Document

from .abstract_extractor import AbstractExtractor
from ..article_candidate import ArticleCandidate


class ReadabilityExtractor(AbstractExtractor):
    """This class implements Readability as an article extractor. Readability is
    a subclass of Extractors and newspaper.Article.

    """

    def __init__(self):
        self.name = "readability"

    def extract(self, item):
        """Creates an readability document and returns an ArticleCandidate containing article title and text.

        :param item: A NewscrawlerItem to parse.
        :return: ArticleCandidate containing the recovered article data.
        """

        html = getattr(item["spider_response"], "text", None)
        if html is None or isinstance(html, (bytes, bytearray)):
            body = getattr(item["spider_response"], "body", b"")
            encoding = getattr(item["spider_response"], "encoding", None) or "utf-8"
            try:
                html = body.decode(encoding, errors="replace")
            except Exception:
                html = body.decode("utf-8", errors="replace")
        if not isinstance(html, str):
            html = str(html)

        doc = Document(html)
        try:
            description = doc.summary()
        except Exception:
            description = ""

        article_candidate = ArticleCandidate()
        article_candidate.extractor = self._name
        article_candidate.title = doc.short_title()
        article_candidate.description = description
        article_candidate.text = self._text(item)
        article_candidate.topimage = self._topimage(item)
        article_candidate.author = self._author(item)
        article_candidate.publish_date = self._publish_date(item)
        article_candidate.language = self._language(item)

        return article_candidate
