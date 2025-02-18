from playwright.sync_api import sync_playwright, TimeoutError
from dataclasses import dataclass, asdict, field
import pandas as pd
import argparse
import os
import sys
import time

@dataclass
class Business:
    """holds business data"""
    name: str = None
    address: str = None
    website: str = None
    phone_number: str = None
    reviews_count: int = None
    reviews_average: float = None
    latitude: float = None
    longitude: float = None
    url: str = None

@dataclass
class BusinessList:
    """holds list of Business objects,
    and save to both excel and csv
    """
    business_list: list[Business] = field(default_factory=list)
    save_at = 'output'

    def dataframe(self):
        """transform business_list to pandas dataframe

        Returns: pandas dataframe
        """
        return pd.json_normalize(
            (asdict(business) for business in self.business_list), sep="_"
        )

    def save_to_excel(self, filename):
        """saves pandas dataframe to excel (xlsx) file

        Args:
            filename (str): filename
        """
        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_excel(f"output/{filename}.xlsx", index=False)

def extract_coordinates_from_url(url: str) -> tuple[float, float]:
    """helper function to extract coordinates from url"""
    coordinates = url.split('/@')[-1].split('/')[0]
    # return latitude, longitude
    return float(coordinates.split(',')[0]), float(coordinates.split(',')[1])

def main():
    ########
    # input 
    ########
    
    # read search from arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--search", type=str)
    parser.add_argument("-t", "--total", type=int)
    args = parser.parse_args()
    
    if args.search:
        search_list = [args.search]
        
    if args.total:
        total = args.total
    else:
        # if no total is passed, we set the value to random big number
        total = 1_000_000

    if not args.search:
        search_list = []
        # read search from input.txt file
        input_file_name = 'input.txt'
        # Get the absolute path of the file in the current working directory
        input_file_path = os.path.join(os.getcwd(), input_file_name)
        # Check if the file exists
        if os.path.exists(input_file_path):
            # Open the file in read mode
            with open(input_file_path, 'r') as file:
                # Read all lines into a list
                search_list = [line.strip() for line in file.readlines()]
                
        if len(search_list) == 0:
            print('Error occurred: You must either pass the -s search argument, or add searches to input.txt')
            sys.exit()
    
    ###########
    # scraping
    ###########
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Set default timeout to 30 seconds instead of 60
        page.set_default_timeout(30000)

        # Navigate to Google Maps
        try:
            page.goto("https://www.google.com/maps", timeout=30000)
            page.wait_for_timeout(3000)
        except TimeoutError:
            print("Error: Could not load Google Maps. Please check your internet connection.")
            browser.close()
            sys.exit(1)

        for search_for_index, search_for in enumerate(search_list):
            print(f"-----\n{search_for_index} - {search_for}".strip())
            
            try:
                # Clear the search box first
                search_box = page.locator('//input[@id="searchboxinput"]')
                search_box.click()
                search_box.press("Control+A")
                search_box.press("Backspace")
                
                # Fill and search
                search_box.fill(search_for)
                page.wait_for_timeout(2000)
                page.keyboard.press("Enter")
                
                # Wait for either search results or "No results found" message
                try:
                    page.wait_for_selector('//a[contains(@href, "https://www.google.com/maps/place")] | //div[contains(text(), "No results found")]', timeout=30000)
                except TimeoutError:
                    print(f"Warning: No results found for '{search_for}'. Skipping to next search.")
                    continue

                # Check if we got any results
                if page.locator('//div[contains(text(), "No results found")]').count() > 0:
                    print(f"No results found for '{search_for}'. Skipping to next search.")
                    continue

                # Wait for the first result and try hovering
                first_result = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').first
                first_result.hover()
                
                # Rest of the scrolling logic
                previously_counted = 0
                max_scroll_attempts = 10  # Prevent infinite scrolling
                scroll_attempts = 0
                
                while scroll_attempts < max_scroll_attempts:
                    page.mouse.wheel(0, 10000)
                    page.wait_for_timeout(2000)
                    
                    current_count = page.locator(
                        '//a[contains(@href, "https://www.google.com/maps/place")]'
                    ).count()
                    
                    if current_count >= total:
                        listings = page.locator(
                            '//a[contains(@href, "https://www.google.com/maps/place")]'
                        ).all()[:total]
                        listings = [listing.locator("xpath=..") for listing in listings]
                        print(f"Total Scraped: {len(listings)}")
                        break
                    
                    if current_count == previously_counted:
                        scroll_attempts += 1
                    else:
                        previously_counted = current_count
                        print(f"Currently Scraped: {current_count}")
                        scroll_attempts = 0  # Reset counter if we found new items
                
                business_list = BusinessList()
                
                # Scraping individual listings with better error handling
                for listing in listings:
                    try:
                        listing.click()
                        page.wait_for_timeout(3000)
                        
                        name_xpath = '//div[contains(@class, "fontHeadlineSmall")]'
                        address_xpath = '//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]'
                        website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
                        phone_number_xpath = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'
                        reviews_span_xpath = '//span[@role="img"]'

                        business = Business()

                        if listing.locator(name_xpath).count() > 0:
                            business.name = listing.locator(name_xpath).all()[0].inner_text()
                        else:
                            business.name = ""
                        if page.locator(address_xpath).count() > 0:
                            business.address = page.locator(address_xpath).all()[0].inner_text()
                        else:
                            business.address = ""
                        if page.locator(website_xpath).count() > 0:
                            business.website = page.locator(website_xpath).all()[0].inner_text()
                        else:
                            business.website = ""
                        if page.locator(phone_number_xpath).count() > 0:
                            business.phone_number = page.locator(phone_number_xpath).all()[0].inner_text()
                        else:
                            business.phone_number = ""
                        if listing.locator(reviews_span_xpath).count() > 0:
                            business.reviews_average = float(
                                listing.locator(reviews_span_xpath).all()[0]
                                .get_attribute("aria-label")
                                .split()[0]
                                .replace(",", ".")
                                .strip()
                            )
                            business.reviews_count = int(
                                listing.locator(reviews_span_xpath).all()[0]
                                .get_attribute("aria-label")
                                .split()[2]
                                .replace(',','')
                                .strip()
                            )
                        else:
                            business.reviews_average = ""
                            business.reviews_count = ""
                        
                        business.latitude, business.longitude = extract_coordinates_from_url(page.url)
                        business.url = page.url

                        business_list.business_list.append(business)
                    except Exception as e:
                        print(f'Error processing listing: {str(e)}')
                        continue
                
                # Save results
                if business_list.business_list:
                    business_list.save_to_excel(f"google_maps_data_{search_for}".replace(' ', '_'))
                else:
                    print(f"Warning: No data was collected for '{search_for}'")
                
            except Exception as e:
                print(f"Error processing search '{search_for}': {str(e)}")
                continue

        browser.close()

if __name__ == "__main__":
    main()