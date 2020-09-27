from .basecomicspider import BaseComicSpider, font_color, ComicspiderItem


class BaseComicSpider2(BaseComicSpider):
    """2nd baseclass for those Websites with only secondary page frames"""

    def parse_section(self, response):
        self.step = 'parse section'
        self.step_put(self.step)

        title = response.meta.get('title')
        self.print_Q.put(f'<br>{"=" * 15} 《{title}》')
        results = self.frame_section(response)  # {1: url1……}
        for page, url in results.items():
            item = ComicspiderItem()
            item['title'] = title
            item['page'] = str(page)
            item['section'] = 'meaningless'
            item['image_urls'] = [f'{url}']
            self.total += 1
            yield item
        self.step = 'fin'
        self.step_put(self.step)
