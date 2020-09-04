#!/usr/bin/env python3.7

import jinja2, json, argparse

parser = argparse.ArgumentParser()
parser.add_argument("--option", help="Select your report type(summary or default or both separeted by ,)")
parser.add_argument("--date", help="Enter the start date")
args = parser.parse_args()
option = args.option.split(",")

with open("processed_data.json", "r") as json_file:
    processed_data = json.load(json_file)

if "summary" in option:
    with open("templates/summary_report_template.html") as template:
        template = template.read()
    report = jinja2.Template(template).render(data = processed_data, date = args.date)
    
    with open("reports/summary_report.html", "w") as html_file:
        html_file.write(report)

if "default" in option:
    with open("templates/default_report_template.html") as template:
        template = template.read()
    
    for sponsor in processed_data:

        report = jinja2.Template(template).render(data = processed_data[sponsor], date = args.date)
    
        with open("reports/%s.html" % (sponsor), "w") as html_file:
            html_file.write(report)
            
