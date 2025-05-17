import json
import re
from copy import deepcopy
import logging # Added
import pytz # Added

from bs4 import BeautifulSoup
from dateutil.parser import parse
from dateparser import parse as dt_parse
from datetime import datetime

# Assuming abstract_extractor is in the same directory or installed
# from.abstract_extractor import AbstractExtractor
# For standalone execution, let's define a dummy AbstractExtractor
class AbstractExtractor:
    def __init__(self):
        self.name = "abstract_extractor"

# Initialize logger
logger = logging.getLogger(__name__)
# Configure basic logging if no other configuration is present
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


# to improve performance, regex statements are compiled only once per module
re_pub_date = re.compile(
    r'([\./\-_]{0,1}(19|20)\d{2})[\./\-_]{0,1}(([0-3]{0,1}[0-9][\./\-_])|(\w{3,5}[\./\-_]))([0-3]{0,1}[0-9][\./\-]{0,1})?'
)
re_class = re.compile("pubdate|timestamp|article_date|articledate|date", re.IGNORECASE)

spanish_pub_date = re.compile(r'(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})(\s*[–-]\s*(\d{1,2}:\d{2}(:\d{2})?))?', re.I) # Added ñ, optional seconds

MONTHS_ES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5,
    'junio': 6, 'julio': 7, 'agosto': 8, 'septiembre': 9,
    'setiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
}

# Preferred meta tags for extraction, ordered by preference
# Each dict: 'attr_type' (name, property, itemprop, http-equiv), 'attr_value', 'content_key' (usually 'content')
PREFERRED_META_TAGS =


class DateExtractor(AbstractExtractor):
    """This class implements ArticleDateExtractor as an article extractor. ArticleDateExtractor is
    a subclass of ExtractorInterface.
    """

    def __init__(self):
        super().__init__() # Ensure base class __init__ is called if it exists
        self.name = "date_extractor"
        # Define a default timezone for naive datetimes, e.g., for Argentinian sites
        self.default_timezone = pytz.timezone('America/Argentina/Buenos_Aires')


    def _publish_date(self, item):
        """Returns the publish_date of the extracted article."""
        url = item.get('url')
        html_body = item.get('spider_response', {}).get('body') # Safely get body
        publish_date = None

        if not url:
            logger.error("No URL provided in item.")
            return None

        html_soup = None
        try:
            if html_body is None:
                logger.warning(f"HTML content is None for URL: {url}. Attempting to fetch.")
                try:
                    request = urllib2.Request(url)
                    # Using a browser user agent
                    request.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
                    response = urllib2.build_opener().open(request, timeout=10) # Added timeout
                    html_content = response.read()
                    html_soup = BeautifulSoup(html_content, "lxml")
                except urllib2.URLError as e:
                    logger.error(f"Failed to fetch URL {url}: {e}")
                    return None
                except Exception as e:
                    logger.error(f"Unexpected error fetching URL {url}: {e}", exc_info=True)
                    return None
            else:
                # If html_body is already a BeautifulSoup object, use it directly
                if isinstance(html_body, BeautifulSoup):
                    html_soup = html_body
                else:
                    # If it's a string (e.g. from item['spider_response'].body), parse it
                    html_soup = BeautifulSoup(deepcopy(html_body), "lxml")


            if not html_soup:
                logger.error(f"HTML content could not be processed for URL: {url}")
                return None

            logger.info(f"Attempting HTML Tag extraction for {url}")
            publish_date = self._extract_from_html_tag(html_soup)
            if publish_date:
                logger.info(f"Date found via HTML Tags for {url}: {publish_date}")
                return publish_date

            logger.info(f"Attempting JSON-LD extraction for {url}")
            publish_date = self._extract_from_json(html_soup)
            if publish_date:
                logger.info(f"Date found via JSON-LD for {url}: {publish_date}")
                return publish_date

            logger.info(f"Attempting Meta Tag extraction for {url}")
            publish_date = self._extract_from_meta(html_soup)
            if publish_date:
                logger.info(f"Date found via Meta Tags for {url}: {publish_date}")
                return publish_date
            
            logger.info(f"Attempting URL extraction for {url}")
            publish_date = self._extract_from_url(url)
            if publish_date:
                logger.info(f"Date found via URL for {url}: {publish_date}")
                return publish_date

        except Exception as e:
            logger.error(f"General error in _publish_date for {url}: {e}", exc_info=True)
            publish_date = None

        if not publish_date:
            logger.warning(f"Could not extract date for URL: {url}")
        return publish_date


    def parse_date_str(self, s: str) -> str | None:
        if not s or not isinstance(s, str): # Added type check
            logger.debug(f"Invalid input to parse_date_str: {s}")
            return None
        
        s = s.strip()
        if not s:
            logger.debug("Empty string after strip in parse_date_str")
            return None

        dt = None
        # 1) try dateparser (handles various languages and relative dates)
        try:
            logger.debug(f"Attempting dateparser.parse for: '{s}'")
            dt = dt_parse(s, languages=['es'])
            if dt:
                logger.debug(f"dateparser success: '{s}' -> {dt}")
        except Exception as e:
            logger.warning(f"dateparser.parse failed for string: '{s}'. Error: {e}", exc_info=True)
            dt = None # Ensure dt is None if parsing fails

        # 2) pattern “13 de mayo de 2025 - 20:05” (Spanish specific)
        if not dt:
            try:
                logger.debug(f"Attempting spanish_pub_date regex for: '{s}'")
                m = spanish_pub_date.search(s.lower())
                if m:
                    d, m_es, y, _, hm_group, _ = m.groups() # Adjusted for optional seconds
                    hm = hm_group.strip() if hm_group else '00:00:00'
                    time_parts = hm.split(':')
                    h = int(time_parts)
                    mi = int(time_parts[1]) if len(time_parts) > 1 else 0
                    sec = int(time_parts[2]) if len(time_parts) > 2 else 0
                    
                    month_num = MONTHS_ES.get(m_es.lower())
                    if month_num:
                        dt = datetime(int(y), month_num, int(d), h, mi, sec)
                        logger.debug(f"spanish_pub_date regex success: '{s}' -> {dt}")
                    else:
                        logger.warning(f"Spanish month not recognized: {m_es} in '{s}'")
            except Exception as e:
                logger.warning(f"spanish_pub_date regex processing failed for string: '{s}'. Error: {e}", exc_info=True)
                dt = None


        # 3) fallback dateutil (general English-centric parser)
        if not dt:
            try:
                logger.debug(f"Attempting dateutil.parser.parse for: '{s}'")
                dt = parse(s)
                logger.debug(f"dateutil.parser success: '{s}' -> {dt}")
            except Exception: # More specific: except (ValueError, TypeError):
                logger.debug(f"dateutil.parser.parse failed for string: '{s}'") # Not a warning, as it's a fallback
                return None
        
        if dt:
            # Timezone handling: If naive, assume default_timezone (e.g., local time of the website's origin)
            # Then convert to UTC for standardization.
            if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
                logger.debug(f"Naive datetime {dt}, localizing with {self.default_timezone.zone}")
                dt = self.default_timezone.localize(dt, is_dst=None) # is_dst=None handles ambiguity
            
            logger.debug(f"Converting datetime {dt} to UTC")
            dt_utc = dt.astimezone(pytz.utc)
            return dt_utc.strftime('%Y-%m-%d %H:%M:%S')

        logger.debug(f"Could not parse date string: '{s}' with any method.")
        return None


    def _extract_from_url(self, url):
        """Try to extract from the article URL - simple but might work as a fallback"""
        logger.debug(f"Attempting to extract date from URL: {url}")
        m = re.search(re_pub_date, url)
        if m:
            date_str_from_url = m.group(0)
            logger.debug(f"Found potential date string in URL: {date_str_from_url}")
            parsed_date = self.parse_date_str(date_str_from_url)
            if parsed_date:
                return parsed_date
        logger.debug(f"No date found in URL: {url}")
        return None

    def _extract_from_json(self, html_soup):
        date = None
        try:
            scripts = html_soup.find_all('script', type='application/ld+json')
            if not scripts:
                logger.debug("No JSON-LD script tags found.")
                return None

            for script in scripts:
                if not script.string:
                    logger.debug("JSON-LD script tag found but is empty.")
                    continue
                
                try:
                    data = json.loads(script.string)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON-LD parsing failed: {e}. Content snippet: {script.string[:200]}...")
                    continue

                # Check for @graph structure
                graph_data = data.get('@graph',)
                if isinstance(graph_data, list) and graph_data:
                    for item_in_graph in graph_data:
                        if isinstance(item_in_graph, dict):
                            # Prioritize NewsArticle or Article types
                            if item_in_graph.get('@type') in ['NewsArticle', 'Article', 'WebPage']:
                                date = self.parse_date_str(item_in_graph.get('datePublished'))
                                if date: break
                                date = self.parse_date_str(item_in_graph.get('dateCreated'))
                                if date: break
                    if date: break 
                
                # Standard keys if not in @graph or if @graph parsing failed
                if not date:
                    date = self.parse_date_str(data.get('datePublished'))
                if not date:
                    date = self.parse_date_str(data.get('dateCreated'))
                
                if date: # Found date in one of the scripts
                    break 
            
            if date:
                logger.debug(f"Date extracted from JSON-LD: {date}")
            else:
                logger.debug("No parsable date found in JSON-LD script tags.")

        except Exception as e:
            logger.error(f"Error extracting from JSON-LD: {e}", exc_info=True)
            return None
        return date

    def _extract_from_meta(self, html_soup):
        logger.debug("Attempting to extract date from meta tags.")
        
        # Iterate through preferred meta tags
        for tag_spec in PREFERRED_META_TAGS:
            meta_tags = html_soup.find_all("meta", {tag_spec['attr_type']: re.compile(r'^\s*' + re.escape(tag_spec['attr_value']) + r'\s*$', re.I)})
            for meta in meta_tags:
                date_content = meta.get(tag_spec['content_key'], '').strip()
                if date_content:
                    logger.debug(f"Found potential date in meta tag ({tag_spec['attr_type']}='{tag_spec['attr_value']}'): '{date_content}'")
                    parsed_date = self.parse_date_str(date_content)
                    if parsed_date:
                        logger.info(f"Successfully parsed date from meta tag: {tag_spec['attr_type']}='{tag_spec['attr_value']}' -> {parsed_date}")
                        return parsed_date
        
        # Special handling for 'og:image' or 'image' itemprop if it contains a date in URL
        logger.debug("Checking 'og:image' and 'itemprop=image' meta tags for dates in URLs.")
        for meta in html_soup.find_all("meta"):
            meta_property = meta.get('property', '').lower()
            item_prop = meta.get('itemprop', '').lower()

            if meta_property == 'og:image' or item_prop == 'image':
                url_from_meta = meta.get('content', '').strip()
                if url_from_meta:
                    logger.debug(f"Found image URL in meta tag: {url_from_meta}. Checking for embedded date.")
                    possible_date_from_image_url = self._extract_from_url(url_from_meta)
                    if possible_date_from_image_url:
                        logger.info(f"Date extracted from image URL in meta tag: {possible_date_from_image_url}")
                        return possible_date_from_image_url
        
        logger.debug("No date found in meta tags using preferred list or image URLs.")
        return None


    def _extract_from_html_tag(self, html_soup):
        logger.debug("Attempting to extract date from HTML tags (<time>, specific itemprops, common classes).")
        # <time> element
        for time_tag in html_soup.find_all("time"):
            datetime_attr = time_tag.get('datetime', '').strip()
            if datetime_attr:
                logger.debug(f"Found <time datetime='{datetime_attr}'>")
                parsed_date = self.parse_date_str(datetime_attr)
                if parsed_date: return parsed_date

            # Fallback for <time> content if datetime attribute is missing/unparsable
            # Example: <time class="timestamp">Actual date string</time>
            time_text = time_tag.get_text(strip=True)
            if time_text: # Check if class indicates it's a timestamp
                tag_classes = time_tag.get('class',)
                if any(cls.lower() == "timestamp" for cls in tag_classes): # Check if "timestamp" is one of the classes
                    logger.debug(f"Found <time class='...timestamp...'>{time_text}</time>")
                    parsed_date = self.parse_date_str(time_text)
                    if parsed_date: return parsed_date
        
        # Specific itemprop spans
        tag = html_soup.find("span", {"itemprop": "datePublished"})
        if tag:
            date_string = tag.get("content") or tag.get_text(strip=True)
            if date_string:
                logger.debug(f"Found <span itemprop='datePublished'>: {date_string}")
                parsed_date = self.parse_date_str(date_string)
                if parsed_date: return parsed_date

        # Common class names
        # Using find_all with a function to check text content for potential date patterns
        # can be more robust but also slower. Sticking to re_class for now.
        for tag in html_soup.find_all(['span', 'p', 'div'], class_=re_class):
            date_string = tag.get_text(strip=True) # Use get_text() for robustness
            if date_string:
                # Basic sanity check: does it contain at least one digit?
                if not any(char.isdigit() for char in date_string):
                    continue

                logger.debug(f"Found tag with class matching re_class ('{tag.name}' class='{tag.get('class')}'): {date_string}")
                parsed_date = self.parse_date_str(date_string)
                if parsed_date:
                    return parsed_date
        
        logger.debug("No date found in common HTML tags.")
        return None
