import scrapy


class BrandsSpider(scrapy.Spider):
    name = "brands"
    start_urls = ["https://www.cars24.com/new-cars/"]

    def parse(self, response):

        for brand_card in response.css("a.TopBrands_brand-title__G7tjI"):
            yield {
                "name": brand_card.css("span::text").get().strip(),
                "url": brand_card.attrib["href"],
                "logo": brand_card.css("img::attr(src)").get(),
            }
