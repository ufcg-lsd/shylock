import json, argparse

from scraper import Scraper

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--start_date", help="Enter the start date in format year-month-day")
  parser.add_argument("--end_date", help="Enter the end date in format year-month-day")
  args = parser.parse_args()

  scrap = Scraper()
    
  # #Year-Month-Day
  start_date = args.start_date
  end_date = args.end_date

  scrap.scrape(start_date, end_date)
    

if __name__ == "__main__":
    main()