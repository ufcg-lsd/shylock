#!/usr/bin/env python3.7

import json, argparse

from scraper import Scraper
from processor import Processor
from reporter import Reporter

def main():
  parser = argparse.ArgumentParser()

  parser.add_argument("--start_date", help="Enter the start date in format year-month-day")
  parser.add_argument("--end_date", help="Enter the end date in format year-month-day")
  parser.add_argument("--option", help="Select your report type(summary, utilization_summary or default separeted by ,)")

  args = parser.parse_args()

  scraper = Scraper()
  processor = Processor()
  reporter = Reporter()
    
  # #Year-Month-Day
  start_date = args.start_date
  end_date = args.end_date
  option = args.option.split(",")

  scraper.scrape(start_date, end_date)
  processor.process(start_date, end_date)
  reporter.report(option, start_date)
    

if __name__ == "__main__":
    main()