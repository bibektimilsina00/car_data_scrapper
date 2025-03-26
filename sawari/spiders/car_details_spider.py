import json

import scrapy
from scrapy.exceptions import DropItem


class CarDetailsSpider(scrapy.Spider):
    name = "car_details"
    custom_settings = {
        "CONCURRENT_REQUESTS": 8,
        "DOWNLOAD_DELAY": 1,
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 3,
    }

    def start_requests(self):
        """Start with the cars from cars_data.json"""
        try:
            with open("cars_data.json") as f:
                cars = json.load(f)
                for car in cars:
                    # Create a new data object for each car
                    car_data = {
                        "base_info": car,
                        "price": None,
                        "specifications": None,
                        "variants": None,
                        "colours": None,
                        "mileage": None,
                        "reviews": None,
                        "gallery": None,
                        "_pending_tabs": set(),
                    }

                    # Start with price page since we're skipping overview
                    yield scrapy.Request(
                        car["detail_url"].replace(
                            "/overview", "/price"
                        ),  # Start with price page
                        callback=self.parse_first_page,
                        meta={"car_data": car_data},
                        errback=self.handle_error,
                        dont_filter=True,
                    )
        except FileNotFoundError:
            self.logger.error("cars_data.json not found. Run cars spider first.")
        except json.JSONDecodeError:
            self.logger.error("Invalid JSON in cars_data.json")

    def parse_first_page(self, response):
        """Parse first page and dispatch requests for other tabs"""
        car_data = response.meta["car_data"]

        # Update tab mapping to handle all possible tab types
        tab_mapping = {
            "specs": ("specifications", self.parse_specifications),
            "price": ("price", self.parse_price),
            "variants": ("variants", self.parse_variants),
            "colours": ("colours", self.parse_colours),
            "reviews": ("reviews", self.parse_reviews),
            "gallery": ("gallery", self.parse_gallery),
            "mileage": ("mileage", self.parse_mileage),
            "range": ("mileage", self.parse_mileage),
            "model": ("base_info", None),
            "compare": ("compare", None),
        }

        # Process each available tab
        for tab in response.css("ul.flex.gap-9 li a"):
            tab_id = tab.css("::attr(id)").get()

            # Skip tabs we don't want to process
            if tab_id in ["model", "compare"]:
                continue

            tab_url = response.urljoin(tab.css("::attr(href)").get())
            data_key, parser = tab_mapping.get(tab_id, (tab_id, self.parse_unknown))

            # Only process if we have a parser for this tab
            if parser:
                # Add to pending tabs
                car_data["_pending_tabs"].add(data_key)

                yield scrapy.Request(
                    tab_url,
                    callback=parser,
                    meta={"car_data": car_data, "data_key": data_key},
                    errback=self.handle_error,
                    dont_filter=True,
                )

    def finalize_car_data(self, car_data):
        """Check if all tabs are processed and prepare final output"""
        if not car_data["_pending_tabs"]:
            # Remove internal tracking data
            final_data = dict(car_data)
            final_data.pop("_pending_tabs")

            # Merge base info with collected data
            result = {**final_data["base_info"], **final_data}
            result.pop("base_info")

            return result
        return None

    def process_tab(self, response, parser_func):
        """Generic tab processing helper"""
        car_data = response.meta["car_data"]
        data_key = response.meta["data_key"]

        # Parse the tab data
        car_data[data_key] = parser_func(response)

        # Remove from pending
        car_data["_pending_tabs"].remove(data_key)

        # Check if complete
        final_data = self.finalize_car_data(car_data)
        if final_data:
            yield final_data

    def parse_unknown(self, response):
        """Handle unknown tab types"""
        self.logger.warning(f"Unknown tab type encountered: {response.url}")
        yield from self.process_tab(response, lambda r: {"error": "Unknown tab type"})

    # Tab-specific parsers
    def parse_price(self, response):
        yield from self.process_tab(response, self._extract_price_data)

    def parse_specifications(self, response):
        yield from self.process_tab(response, self._extract_specifications_data)

    def parse_variants(self, response):
        yield from self.process_tab(response, self._extract_variants_data)

    def parse_colours(self, response):
        yield from self.process_tab(response, self._extract_colours_data)

    def parse_mileage(self, response):
        yield from self.process_tab(response, self._extract_mileage_data)

    def parse_reviews(self, response):
        yield from self.process_tab(response, self._extract_reviews_data)

    def parse_gallery(self, response):
        yield from self.process_tab(response, self._extract_gallery_data)

    def handle_error(self, failure):
        """Handle request failures"""
        car_data = failure.request.meta["car_data"]
        data_key = failure.request.meta["data_key"]

        # Log error
        self.logger.error(f"Request failed for {data_key}: {failure.value}")

        # Mark tab as failed but processed
        car_data[data_key] = {"error": str(failure.value), "url": failure.request.url}
        car_data["_pending_tabs"].remove(data_key)

        # Check if complete despite error
        final_data = self.finalize_car_data(car_data)
        if final_data:
            yield final_data

    def _extract_price_data(self, response):
        """Extract detailed price information"""
        price_data = {
            "ex_showroom": None,
            "rto": None,
            "insurance": None,
            "other_charges": {"total": None, "breakdown": {}},
            "on_road": None,
            "city": "New Delhi",
        }

        price_mapping = {
            "price-ex-showroom": "ex_showroom",
            "price-rto": "rto",
            "price-insurance": "insurance",
            "price-other-charges": "other_charges.total",
            "price-on-road": "on_road",
        }

        for html_id, data_key in price_mapping.items():
            selector = f"div#{html_id} p#price-item-value::text"
            value = response.css(selector).get()
            if value:
                # Clean and store the price value
                value = value.strip().replace("₹", "").strip()
                if "." in data_key:
                    # Handle nested dictionary keys
                    main_key, sub_key = data_key.split(".")
                    price_data[main_key][sub_key] = value
                else:
                    price_data[data_key] = value

        # Extract other charges breakdown
        for charge in response.css("div[id^='other-charges-']"):
            label = charge.css("div#price-item-label::text").get("").strip()
            value = charge.css("p#price-item-value::text").get("").strip()
            if label and value:
                price_data["other_charges"]["breakdown"][label.lower()] = value

        return price_data

    def _extract_specifications_data(self, response):
        return {
            "engine": self.extract_spec_section(response, "engine"),
            "dimensions": self.extract_spec_section(response, "dimensions"),
            "transmission": self.extract_spec_section(response, "transmission"),
            "features": self.extract_spec_section(response, "features"),
        }

    def _extract_variants_data(self, response):
        """Extract variant details from the variants section"""
        variants = []
        for variant in response.css("div#car-variants"):
            # Extract basic variant info
            name = variant.css("h2::text").get("").strip()
            price = variant.css("div.bg-transparent p::text").get("").strip()

            # Extract specifications
            specs = {}
            for spec in variant.css("div.grid.grid-cols-3 div.flex.flex-col"):
                value = spec.css("p.font-medium::text").get("").strip()
                label = spec.css("p.text-grey::text").get("").strip()
                if value and label:
                    specs[label.lower()] = value

            # Extract features
            features = []
            for feature in variant.css(
                "div.flex.flex-wrap span.flex.items-center::text"
            ).getall():
                if feature:
                    features.append(feature.strip())

            # Get total features count
            more_features = variant.css("button#all-feature-sheet-undefined::text").get(
                ""
            )
            if more_features:
                try:
                    total_features = int(
                        more_features.split("+")[1].split()[0].strip()
                    ) + len(features)
                except:
                    total_features = len(features)
            else:
                total_features = len(features)

            # Add special tags (Base/Top Variant)
            tag = variant.css("div.bg-black.text-white::text").get("").strip()

            variants.append(
                {
                    "name": name,
                    "price": price,
                    "specifications": specs,
                    "features": features,
                    "total_features": total_features,
                    "tag": tag if tag else None,
                }
            )

        return variants

    def _extract_colours_data(self, response):
        """Extract color names and images"""
        colours = []

        # Get all color sections
        for color_section in response.css("div[data-selected]"):
            # Extract color name from <p> tag or id attribute
            name = color_section.css("p::text").get("").strip()
            if not name:
                name = color_section.css("::attr(id)").get("").strip()

            # Extract image URL
            img = color_section.css("img")
            img_url = img.css("::attr(src)").get("")
            srcset = img.css("::attr(srcset)").get("")

            # Get high quality image URL from srcset if available
            hq_url = ""
            if srcset:
                try:
                    hq_url = srcset.split(",")[-1].split(" ")[0].strip()
                except:
                    hq_url = img_url

            if name and img_url:
                colours.append(
                    {
                        "name": name,
                        "image": img_url,
                        "hq_image": hq_url if hq_url else img_url,
                    }
                )

        return colours

    def _extract_mileage_data(self, response):
        """Extract mileage information from the table"""
        mileage_data = {
            "petrol": {"manual": None, "automatic": None},
            "cng": {"manual": None},
            "overview": None,
            "fuel_tank_capacity": None,
        }

        # Extract overview text
        overview = response.css("#mileage-stat-title p::text").get("")
        if overview:
            mileage_data["overview"] = overview.strip()

        # Extract from table rows
        for row in response.css("tr[id^='tr-']"):
            # Get fuel type and transmission
            fuel_cell = row.css("#td-fuel-engine::text").get("")
            transmission = row.css("#td-transmission::text").get("")
            mileage = row.css("#td-aria-mileage::text").get("")

            if fuel_cell and transmission and mileage:
                fuel_type = fuel_cell.lower().strip()
                transmission = transmission.lower().strip()

                # Clean up fuel type (remove cc info)
                if "(" in fuel_type:
                    fuel_type = fuel_type.split("(")[0].strip()

                # Store in appropriate location
                if (
                    fuel_type in mileage_data
                    and transmission in mileage_data[fuel_type]
                ):
                    mileage_data[fuel_type][transmission] = mileage.strip()

        return mileage_data

    def _extract_reviews_data(self, response):
        """Extract review statistics and individual reviews"""
        review_data = {
            "statistics": {
                "interiors": None,
                "fuel_economy": None,
                "looks": None,
                "comfort": None,
                "overall": None,
            },
            "reviews": [],
        }

        # Extract review statistics
        stat_mapping = {
            "interiors": "#mini-stat-interiors::text",
            "fuel_economy": "#mini-stat-fuel-economy::text",
            "looks": "#mini-stat-looks::text",
            "comfort": "#mini-stat-comfort::text",
            "overall": "#mini-stat-overall::text",
        }

        for key, selector in stat_mapping.items():
            value = response.css(selector).get("")
            if value:
                try:
                    review_data["statistics"][key] = float(value.strip())
                except ValueError:
                    review_data["statistics"][key] = None

        # Extract individual reviews if any
        for review in response.css("div.review-card"):
            review_item = {
                "user": review.css("span.user-name::text").get("").strip(),
                "rating": review.css("div.rating::text").get("").strip(),
                "date": review.css("span.review-date::text").get("").strip(),
                "content": review.css("div.review-content::text").get("").strip(),
                "pros": [
                    pro.strip()
                    for pro in review.css("div.pros li::text").getall()
                    if pro.strip()
                ],
                "cons": [
                    con.strip()
                    for con in review.css("div.cons li::text").getall()
                    if con.strip()
                ],
            }
            review_data["reviews"].append(review_item)

        return review_data

    def _extract_gallery_data(self, response):
        """Extract gallery images including interior, exterior and color variants"""
        gallery_data = {"exterior": [], "interior": [], "colors": []}

        # Extract exterior images with simpler selector
        exterior_images = response.css(
            'h2[id=""] + div.grid img'
        )  # Find images under Exterior heading
        for img in exterior_images:
            image_data = {
                "url": img.css("::attr(src)").get(""),
                "alt": img.css("::attr(alt)").get(""),
                "hq_url": (
                    img.css("::attr(srcset)")
                    .get("")
                    .split(",")[-1]  # Get the last URL (highest quality)
                    .split(" ")[0]  # Get just the URL part
                    .strip()
                ),
            }
            if image_data["url"]:  # Only add if URL exists
                gallery_data["exterior"].append(image_data)

        # Extract interior images with corrected selector
        interior_selector = 'h2:contains("Interior") + div.grid img'
        interior_images = response.css(interior_selector)
        for img in interior_images:
            image_data = {
                "url": img.css("::attr(src)").get(""),
                "alt": img.css("::attr(alt)").get(""),
                "hq_url": (
                    img.css("::attr(srcset)")
                    .get("")
                    .split(",")[-1]
                    .split(" ")[0]
                    .strip()
                ),
            }
            if image_data["url"]:  # Only add if URL exists
                gallery_data["interior"].append(image_data)

        # Extract color variant images
        color_images = response.css("div[data-selected] img")
        for img in color_images:
            image_data = {
                "url": img.css("::attr(src)").get(""),
                "alt": img.css("::attr(alt)").get(""),
                "color_name": img.css("::attr(alt)")
                .get("")
                .split("Alto K10")[-1]
                .strip(),
                "hq_url": (
                    img.css("::attr(srcset)")
                    .get("")
                    .split(",")[-1]
                    .split(" ")[0]
                    .strip()
                ),
            }
            if image_data["url"]:  # Only add if URL exists
                gallery_data["colors"].append(image_data)

        # Alternative approach using XPath for more precise selection
        if not gallery_data["exterior"]:
            exterior_images = response.xpath(
                '//h2[text()="Exterior"]/following-sibling::div[1]//img'
            )
            for img in exterior_images:
                image_data = {
                    "url": img.attrib.get("src", ""),
                    "alt": img.attrib.get("alt", ""),
                    "hq_url": (
                        img.attrib.get("srcset", "")
                        .split(",")[-1]
                        .split(" ")[0]
                        .strip()
                    ),
                }
                if image_data["url"]:
                    gallery_data["exterior"].append(image_data)

        if not gallery_data["interior"]:
            interior_images = response.xpath(
                '//h2[text()="Interior"]/following-sibling::div[1]//img'
            )
            for img in interior_images:
                image_data = {
                    "url": img.attrib.get("src", ""),
                    "alt": img.attrib.get("alt", ""),
                    "hq_url": (
                        img.attrib.get("srcset", "")
                        .split(",")[-1]
                        .split(" ")[0]
                        .strip()
                    ),
                }
                if image_data["url"]:
                    gallery_data["interior"].append(image_data)

        return gallery_data

    def extract_spec_section(self, response, section):
        specs = {}
        section_selector = f"div.{section}-specifications"

        for item in response.css(f"{section_selector} tr"):
            key = item.css("td:first-child::text").get()
            value = item.css("td:last-child::text").get()
            if key and value:
                specs[key.strip()] = value.strip()

        return specs

    def closed(self, reason):
        """Log spider completion status"""
        self.logger.info(f"Spider closed: {reason}")
        """Log spider completion status"""
        self.logger.info(f"Spider closed: {reason}")
