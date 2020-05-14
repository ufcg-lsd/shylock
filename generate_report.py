#!/usr/bin/env python3.7

from datetime import datetime, timedelta
import json

#reading the date
date1 = datetime.fromisoformat(input("date1 Year-Month-Day"))
date2 = datetime.fromisoformat(input("date2 Year-Month-Day"))

#reading the html body template and full template
body_template = open("templates/body_template.txt", "r")
html_body = body_template.read()
report_template = open("templates/report_template.html", "r")
html_full = report_template.read()
body_template.close()
report_template.close()

name_to_idx = {
	#here are the indexes of the sponsors
	"project_colum" : 0, "sponsor" : 13,
	
	#here are the indexes of the logs
	"action" : 0, "date" : 4,  "first_line" : 0
}

#reading the sponsors list
csv_file = open("templates/full_sponsors.csv", "r")
project_sponsors = csv_file.read().strip().replace(" ", "").split("\n")[1:-1]
csv_file.close()
project_sponsors = {line.split(",")[name_to_idx['project']]:line.split(",")[name_to_idx['sponsor']] for line in project_sponsors}
print(project_sponsors)
sponsors = {sponsor:"" for sponsor in project_sponsors.values()}
sponsors["joabsilva@lsd.ufcg.edu.br"] = "" #joab is the sponsor for the support services and he is not in the csv file

#read the json file
with open("json_file.json", "r") as json_file:
	data = json.load(json_file)

#this function is to format the time for output  
def days_hours_minutes(total):
	days = total.days
	minutes = int(total.seconds/3600)
	seconds = total.seconds%60
	return  "%s Dias, %s Horas e %s Segundos" % (days, minutes, seconds)

#this function is to format the instance's logs because the nova cli does not format
def format_log(log):
	
	#here the result  indices are [Action, Request_ID, Message, Start_Time, Update_Time]
	return [line.replace("|", " ").split() for line in log.split("\n")[3:-1]]

#this function is to calculate the total time of instance use
def total_time(log_list):

	#first we need an accumulator
	total = timedelta(days = 0)

	#here we have all the relevant state changes to know if the instance is active or inactive so we can check it later
	to_on_states = ['create', 'rebuild', 'restore', 'start', 'reboot', 'revertResize', 'confirmResize', 'unpause', 'resume', 'suspend', 'unrescue', 'unshelve']
	to_off_states = ['softDelete', 'forceDelete', 'delete', 'stop', 'shelve', 'error']
	
	'''
	the algorithm here is to go through all the actions taken by the instance and always look back
	to see if we need to increase the time of using the instance, if the instance was created 
	before the initial consultation date and is turned on when the initial date is exceeded, we will
	also need to increase the time from this date until the first action taken within the consulted
	time interval or until the end date of the consultation
	'''
	try:
		last = datetime.fromisoformat(log_list[name_to_idx['first_line']][name_to_idx['date']])
	
	except IndexError:
		return total

	on = False
	init = False

	for line in log_list:
		if datetime.fromisoformat( line[name_to_idx['date']]) >= date2:
			break

		if not init:
			if last >= date1:
				if on:
					total += (last - date1)
				
				init = True
		
		else:
			if on:
				total += (datetime.fromisoformat(name_to_idx['date']) - last)
			
		if line[name_to_idx['action']] in to_on_states:
			on = True

		elif line[name_to_idx['action']] in to_off_states:
			on  = False

		last = datetime.fromisoformat(line[name_to_idx['date']])
	
	if (not init) and on:
		total += (date2 - date1)
	elif on:
		total += (date2 - last)

	return total
		
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
		
		body = html_body
		body = body.replace("$tit$", "04/2020-%s/%s" % (domain_name, project["Name"]))

		volumes = ""
		for volume in project["Volume"]:
			volumes += ("\t\t<tr> <td>%s</td> <td>%sGB</td> </tr>\n" % (volume["Name"], volume["Size"]))
		
		body = body.replace("$vol$", volumes)
			
		instances = ""
		for instance in project["Instances"].values():
			print(instance["ID"],)
			
			time_use = total_time( format_log(instance["Log"]))
			time_use = days_hours_minutes(time_use)
			print(time_use)

			instances += ("\t\t<tr> <td>%s</td> <td>%s</td> <td>%s</td> </tr>\n" % (instance["Name"], instance["Flavor"], time_use ))

		body = body.replace("$inst$", instances)

		flavors = ""
		for flavor in project["Flavors"].values():
			flavors += ("\t\t<tr> <td>%s</td> <td>%s</td> <td>%sMB</td> <td>%sGB</td> </tr>\n" % (flavor["name"], flavor["vcpus"], flavor["ram"], flavor["disk"]))

		body = body.replace("$flav$", flavors)
		try:

			sponsors[project_sponsors[project["Name"]]] += body
		except KeyError:
			sponsors["joabsilva@lsd.ufcg.edu.br"] += body

		
print(sponsors.keys())
for sponsor in sponsors:
	if date1.month > 9:
		report = open("reports/%s-%s/%s.html" % (date1.month, date1.year, sponsor), "w")

	else:
		report = open("reports/0%s-%s/%s.html" % (date1.month, date1.year, sponsor), "w")
	report.write(html_full.replace("$body$", sponsors[sponsor]))
	report.close()
