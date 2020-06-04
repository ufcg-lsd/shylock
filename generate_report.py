#!/usr/bin/env python3.7

from datetime import datetime, timedelta
from collections import defaultdict
import json

#reading the date
start_date = datetime.fromisoformat(input("start_date Year-Month-Day"))
end_date = datetime.fromisoformat(input("end_date Year-Month-Day"))

#reading the html body template and full template
with open("templates/body_template.txt") as body_template:
	html_body = body_template.read()
with open("templates/report_template.html") as report_template:
	html_full = report_template.read()
	
name_to_idx = {
	#indexes of the fields from the sponsors file
	"project" : 0,
	"sponsor" : 13,
	
	#here are the named indexes of the logs
	"action" : 0, 
	"date" : 4,  
	"first_line" : 0
}

#here we have all the relevant state changes to know if the instance is active or inactive so we can check it later
to_on_states = ['create', 'rebuild', 'restore', 'start', 'reboot', 'revertResize', 'confirmResize', 'unpause', 'resume', 'suspend', 'unrescue', 'unshelve']
to_off_states = ['softDelete', 'forceDelete', 'delete', 'stop', 'shelve', 'error']


empty_value = "-------"
maximum_date = datetime(year = 9999, month = 12, day = 31)

#reading the sponsors list
csv_file = open("templates/full_sponsors.csv", "r")
with open("templates/full_sponsors.csv") as csv_file:
	project_sponsors = csv_file.read().strip().replace(" ", "").split("\n")[1:-1]

def line_to_project(line):
	return line[name_to_idx['project']]

def line_to_sponsor(line):
	return line[name_to_idx['sponsor']]

def split_by_comma(line):
	return line.split(',')

project_sponsors = defaultdict(lambda: "joabsilva@lsd.ufcg.edu.br", { line_to_project(line): line_to_sponsor(line) for line in map(split_by_comma, project_sponsors) })


sponsors = {sponsor:"" for sponsor in project_sponsors.values()}
sponsors["joabsilva@lsd.ufcg.edu.br"] = "" #joab is the sponsor for the support services and he is not in the csv file

#read the json file
with open("json_file.json", "r") as json_file:
	data = json.load(json_file)

#this function is to get the instance create date
def get_create_date(instance):
	return datetime.fromisoformat(extract_actions(instance["Log"])[name_to_idx['first_line']][name_to_idx['date']])

#this function is to format the usage time for output  
def days_hours_minutes(total):
	days = total.days
	hours = int(total.seconds/3600)
	minutes = int(total.seconds/60)%60
	return  "%s Dias, %s Horas e %s Segundos" % (days, hours, minutes)

#this function is to format the instance's logs because the nova cli does not format
def extract_actions(log):
	
	#here the result  indices are [Action, Request_ID, Message, Start_Time, Update_Time]
	return [line.replace('|', " ").split() for line in log.split("\n")[3:-1]]

#this function is to format the date for output
def date_br_format(date):
	return "%02d-%02d-%d" % (date.day, date.month, date.year)

#this function is to get the last status of an instance
def get_status(log_list):
	status = "Ativa"
	for line in log_list:
		if line[name_to_idx['action']] in to_on_states:
			status = "Ativa"
		
		elif line[name_to_idx['action']] in to_off_states:
			status = "Inativa"

	return status

#this function is to calculate the total time of instance use
def total_time(log_list):

	#first we need an accumulator
	total = timedelta(days = 0)
	
	'''
	the algorithm here is to go through all the actions taken by the instance and always look back
	to see if we need to increase the time of using the instance, if the instance was created 
	before the initial consultation date and is turned on when the initial date is exceeded, we will
	also need to increase the time from this date until the first action taken within the consulted
	time interval or until the end date of the consultation
	'''
	last = datetime.fromisoformat(log_list[name_to_idx['first_line']][name_to_idx['date']])


	on = False
	init = False

	for line in log_list:
		if datetime.fromisoformat( line[name_to_idx['date']]) >= end_date:
			break

		if not init:
			if last >= start_date:
				if on:
					total += (last - start_date)
				
				init = True
		
		else:
			if on:
				total += (datetime.fromisoformat(line[name_to_idx['date']]) - last)
			
		if line[name_to_idx['action']] in to_on_states:
			on = True

		elif line[name_to_idx['action']] in to_off_states:
			on  = False

		last = datetime.fromisoformat(line[name_to_idx['date']])
	
	if (not init) and on:
		total += (end_date - start_date)
	elif on:
		total += (end_date - last)

	return total

def is_not_empty(instance):
	return extract_actions(instance["Log"]) != []

def is_valid(instance):
	return is_not_empty(instance) and get_create_date(instance) < end_date
	
'''this code snippet is where we access all subdivisions of the cloud first we accesses
the domains data["<Domain_Name>"], the value of each key is another dictionary, in this
time the values of keys are dictionarys represeting projects ex. data["<Domain_Name>"]["<Project_Name>"]
and so on as in the file get_data.py.
example of use:
	format_instance_log(data["Default"]["admin"]["Instances"]["969630a1-8f3d-4504-b634-bbecc564b8cf"]["Log"])
'''
for domain_name in data:

	domain = data[domain_name]
	
	for project in domain.values():
		if project["Name"].strip() == "":
			project["Name"] = empty_value

		body = html_body
		body = body.replace("$tit$", "%02d/%d-%s/%s" % (start_date.month, start_date.year, domain_name, project["Name"]))

		volumes = ""
		for volume in project["Volume"]:
			if volume["Name"].strip() == "":
				volume["Name"] = empty_value
			volumes += ("\t\t<tr> <td>%s</td> <td>%sGB</td> </tr>\n" % (volume["Name"], volume["Size"]))
		
		body = body.replace("$vol$", volumes)
			
		instances = ""
		valid_instances = filter(is_valid, project["Instances"].values())
		for instance in sorted(valid_instances, key = get_create_date):
			print(instance["ID"],)
			
			instance_log = extract_actions(instance["Log"])
			time_use = total_time(instance_log)
			time_use = days_hours_minutes(time_use)
			status = get_status(instance_log)
			print(get_create_date(instance))
			print(time_use)

			if instance["Name"].strip() == "":
				instance["Name"] = empty_value

			instances += ("\t\t<tr> <td>%s</td> <td>%s</td> <td>%s</td> <td>%s</td> <td>%s</td> </tr>\n" % (instance["Name"], instance["Flavor"], time_use, date_br_format(get_create_date(instance).date()), status))

		body = body.replace("$inst$", instances)

		flavors = ""
		for flavor in project["Flavors"].values():
			flavors += ("\t\t<tr> <td>%s</td> <td>%s</td> <td>%sMB</td> <td>%sGB</td> </tr>\n" % (flavor["name"], flavor["vcpus"], flavor["ram"], flavor["disk"]))

		body = body.replace("$flav$", flavors)
		sponsors[project_sponsors[project["Name"]]] += body

print(sponsors.keys())
for sponsor in sponsors:

	with open("reports/%02d-%d/%s.html" % (start_date.month, start_date.year, sponsor), "w") as report:
		report.write(html_full.replace("$body$", sponsors[sponsor]))
