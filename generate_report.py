#!bin/bin/python3.5

from datetime import datetime, timedelta
import json

#reading the date
date1 = datetime.fromisoformat(input("date1 Year-Month-Day"))
date2 = datetime.fromisoformat(input("date2 Year-Month-Day"))

#reading the html body template and full template
html_body = open("templates/body_template.txt", "r").read()
html_full = open("templates/report_template.html", "r").read()

#reading the sponsors list
project_sponsors = open("templates/full_sponsors.csv", "r").read().strip().replace(" ", "").split("\n")[1:-1]
project_sponsors = {line.split(",")[0]:line.split(",")[-2] for line in project_sponsors}
print(project_sponsors)
sponsors = {sponsor:"" for sponsor in project_sponsors.values()}
sponsors["joabsilva@lsd.ufcg.edu.br"] = ""

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
	total = timedelta(days = 0)

	to_on_states = ['create', 'rebuild', 'restore', 'start', 'reboot', 'revertResize', 'confirmResize', 'unpause', 'resume', 'suspend', 'unrescue', 'unshelve']
	to_off_states = ['softDelete', 'forceDelete', 'delete', 'stop', 'shelve', 'error']
	
	try:
		last = datetime.fromisoformat(log_list[0][4])
	
	except IndexError:
		#print("-------------------index error------------------------")
		return total
		
	on = False
	init = False

	for line in log_list:
		if datetime.fromisoformat( line[4]) >= date2:
			break

		if not init:
			if last >= date1:
				if on:
					total += (date1 - last)
				
				init = True
		
		else:
			if on:
				total += (datetime.fromisoformat(line[4]) - last)
			
		if line[0] in to_on_states:
			on = True

		elif line[0] in to_off_states:
			on  = False

		last = datetime.fromisoformat(line[4])
	
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
		#print(project["Volume"])
		
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
	report = open("reports/%s.html" % sponsor, "w")
	report.write(html_full.replace("$body$", sponsors[sponsor]))
