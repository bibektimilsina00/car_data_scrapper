import scrapy


class CarsSpider(scrapy.Spider):
    name = "cars"
    start_urls = ["https://www.cars24.com/new-cars"]

    def parse(self, response):
        for brand_card in response.css("a.TopBrands_brand-title__G7tjI"):
            brand_name = brand_card.css("span::text").get().strip()
            brand_url = response.urljoin(brand_card.attrib["href"])
            print(brand_name, brand_url)

            yield scrapy.Request(
                brand_url, callback=self.parse_cars, meta={"brand_name": brand_name}
            )

    def parse_cars(self, response):
        brand_name = response.meta["brand_name"]

        for car_card in response.css("div.model-card"):

            detail_url = response.urljoin(car_card.css("a::attr(href)").get())

            car_name = (
                car_card.css("span.font-medium.text-black")
                .xpath("string()")
                .get()
                .strip()
            )
            price_range = (
                car_card.css("p.font-medium.text-lg.whitespace-nowrap")
                .xpath("string()")
                .get()
                .strip()
            )

            specs = car_card.css("div.flex.justify-between.mt-3 div.flex.flex-col")
            specs_data = {}

            for spec in specs:
                label = spec.css("p.text-\\[10px\\]::text").get().strip()
                value = spec.css("p.font-medium::text").get().strip()
                specs_data[label.lower()] = value

            key_features = car_card.css(
                "a.key-specs span.text-xs.font-small::text"
            ).getall()

            images = car_card.css(
                "img.w-full.h-full.object-contain::attr(src)"
            ).getall()

            video_thumbnail = car_card.css(
                "img#youtube-video-thumbnail::attr(src)"
            ).get()

            yield {
                "brand": brand_name,
                "name": car_name,
                "detail_url": detail_url,
                "price_range": price_range,
                "specifications": specs_data,
                "key_features": key_features,
                "images": images,
                "video_thumbnail": video_thumbnail,
            }

        next_page = response.css("a.next-page::attr(href)").get()
        if next_page:
            yield response.follow(
                next_page, callback=self.parse_cars, meta={"brand_name": brand_name}
            )
