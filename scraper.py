#!/usr/bin/env python

import bleach
from bs4 import BeautifulSoup
from collections import OrderedDict
from dateutil import parser
import regex
import requests
import scraperwiki
import urlparse


class Page:
    def __init__(self, path, basename, encoding):
        self.path = path
        self.basename = basename
        self.encoding = encoding
        self.url = path + basename


class Archive(Page):
    def __init__(self, path, basename, encoding):
        Page.__init__(self, path, basename, encoding)

    @property
    def links(self):
        link_re = 'ap[0-9]+\.html'
        soup = make_soup(self.url, self.encoding, parser='html.parser')
        return soup.find_all(href=regex.compile(link_re))


class Entry(Page):
    def __init__(self, path, basename, encoding, link):
        Page.__init__(self, path, basename, encoding)
        self.link = link

    @property
    def entry_url(self):
        return self.url

    @property
    def date(self):
        date_raw = self.link.previous_sibling[:-3]
        date = parser.parse(date_raw).strftime('%Y-%m-%d')
        return unicode(date, 'UTF-8')

    @property
    def title(self):
        return self.link.text

    @property
    def credit(self):
        soup = self.get_soup()
        html = str(soup)
        # The credit information is always below the title. Sometimes the title
        # on the picture page is slightly different from the title on the index
        # page, however, so fuzzy matching is used here to account for any
        # differences.
        match = regex.search('<b>\s*?(?:{0}){{e<={1}}}\s*?<(?:\/b|br.*?)>(.*?)<p>'.format(regex.escape(self.link.text.encode('UTF-8')), int(float(len(self.link.text)) * 0.25)), html, regex.DOTALL | regex.IGNORECASE)
        if not match:
            # If the above fails for some reason, one last attempt will be made
            # to locate the credit information by searching between the title
            # and the explanation.
            match = regex.search('<b>.*?<(?:\/b|br.*?)>(.*?)<p>.*?<(?:b|h3)>\s*?Explanation(?::)?\s*?<\/(?:b|h3)>(?::)?', html, regex.DOTALL | regex.IGNORECASE)
        if match:
            # Remove all tags except the anchor tags, and remove all excess
            # whitespace characters.
            credit = ' '.join(bleach.clean(match.group(1), tags=['a'], attributes={'a': ['href']}, strip=True).split())
        else:
            credit = '';
        return credit

    @property
    def explanation(self):
        soup = self.get_soup()
        html = str(soup)
        match = regex.search('<(?:b|h3)>\s*?Explanation(?::)?\s*?<\/(?:b|h3)>(?::)?(.*?)<p>', html, regex.DOTALL | regex.IGNORECASE)
        if match:
            explanation = ' '.join(bleach.clean(match.group(1), tags=['a'], attributes={'a': ['href']}, strip=True).split())
        else:
            explanation = ''
        return explanation

    @property
    def picture_thumbnail_url(self):
        soup = self.get_soup()
        picture_thumbail_link = soup.find('img', src=regex.compile('image/'))

        # Check if there is a smaller version of the picture on the page.
        if picture_thumbail_link:
            picture_thumbnail_url = self.path + picture_thumbail_link['src']
        else:
            picture_thumbnail_url = ''

        return unicode(picture_thumbnail_url, 'UTF-8')

    @property
    def picture_url(self):
        soup = self.get_soup()
        picture_link = soup.find('a', href=regex.compile(self.path.replace('.', '\.') + 'image/'))

        # Check if there is a higher-resolution link to the picture.
        if picture_link:
            picture_url = picture_link['href']
        else:
            picture_url = ''

        return unicode(picture_url, 'UTF-8')

    @property
    def video_url(self):
        soup = self.get_soup()
        video_link = soup.find('iframe')

        if video_link:
            video_url = video_link['src']
        else:
            video_url = ''

        return unicode(video_url, 'UTF-8')

    # Cache the soup.
    def get_soup(self):
        if not hasattr(self, 'soup'):
            self.soup = make_soup(self.url, self.encoding, True, self.path)

        return self.soup


def make_soup(url, encoding, absolute=False, base='', parser='lxml'):
    html = requests.get(url)

    if parser:
        soup = BeautifulSoup(html.content, parser, from_encoding=encoding)
    else:
        soup = BeautifulSoup(html.content, from_encoding=encoding)

    # Make all links absolute.
    # http://stackoverflow.com/a/4468467/715866
    if absolute:
        for a in soup.find_all('a', href=True):
            a['href'] = urlparse.urljoin(base, a['href'])

    return soup


def save(url, date, title, credit, explanation, picture_thumbnail_url, picture_url, video_url, data_version):
    data = OrderedDict()
    data['url'] = url;
    data['date'] = date;
    data['title'] = title;
    data['credit'] = credit;
    data['explanation'] = explanation;
    data['picture_thumbnail_url'] = picture_thumbnail_url;
    data['picture_url'] = picture_url;
    data['video_url'] = video_url;

    data_versions = OrderedDict()
    data_versions['url'] = url;
    data_versions['data_version'] = data_version;

    scraperwiki.sql.save(['url'], data)
    scraperwiki.sql.save(['url'], data_versions, table_name='data_versions')


def table_exists(table):
    try:
        scraperwiki.sql.select('* FROM %s' % table)
        return True
    except:
        return False


def main():
    # Change this number when the scraping algorithm changes. All pages will be
    # re-scraped.
    version = '1.1.1'

    path = 'http://apod.nasa.gov/apod/'
    site_encoding = 'windows-1252'

    archive = Archive(path, 'archivepix.html', site_encoding)
    versions = table_exists('data_versions')

    for link in archive.links:
        entry = Entry(path, link['href'], site_encoding, link)

        if versions:
            result = scraperwiki.sql.select('url, data_version FROM data_versions WHERE url = "%s" LIMIT 1' % entry.entry_url)

        # Only scrape and save the page if it contains a picture or video and
        # if it has not already been scraped at this version.
        if (not versions or not result or result[0]['data_version'] != version) and (entry.picture_thumbnail_url or entry.video_url):
            save(entry.entry_url, entry.date, entry.title, entry.credit, entry.explanation, entry.picture_thumbnail_url, entry.picture_url, entry.video_url, data_version=version)


if __name__ == '__main__':
    main()
