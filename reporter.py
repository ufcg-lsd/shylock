import jinja2, json


class Reporter:

    def __init__(self):
        pass

    def report(self, option_type, start_date):
        print("starting reporter")    

        with open("processed_data.json", "r") as json_file:
            processed_data = json.load(json_file)

        if "summary" in option:
            with open("templates/summary_report_template.html") as template:
                template = template.read()
            report = jinja2.Template(template).render(data = processed_data, date = args.date)
            
            with open("reports/summary_report.html", "w") as html_file:
                html_file.write(report)

        if "default" in option:
            with open("templates/report_template.html") as template:
                template = template.read()
            
            for sponsor in processed_data:

                report = jinja2.Template(template).render(data = processed_data[sponsor], date = args.date)
            
                with open("reports/%s.html" % (sponsor), "w") as html_file:
                    html_file.write(report)

        if "utilization_summary" in option:
            with open("templates/utilization_summary_report_template.html") as template:
                template = template.read()
            report = jinja2.Template(template).render(data = processed_data, date = args.date)
            
            with open("reports/utilization_summary_report.html", "w") as html_file:
                html_file.write(report)
