#!bin/bin/python3.7

from datetime import datetime
import json

#reading the date
date = input("Year-Month-Day")

#read the json file
with open("json_file.json", "r") as json_file:
	data = json.load(json_file)

#this function is to format the time for output  
def days_hours_minutes(total):
	return (total.days, total.seconds/3600, total.seconds%60)

#this function is to format the instance's logs because the nova cli does not format
def format_instance_log(log):
	
	#here the result  indices are [Action, Request_ID, Message, Start_Time, Update_Time]
	return [line.replace("|", " ").split() for line in log.split("\n")[3:-1]]


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
		print(project["Volume"])
		
		temporary_report = open("domains/%s/%s/Relatorio_%s.txt" % (domain_name, project["Name"], project["Name"]),  "w")
		temporary_report.write("Volumes:\n")
		for volume in project["Volume"]:
			temporary_report.write("%s %sGb\n" % (volume["Name"], volume["Size"])) 
					
			#temporary_report.write(project["Volume"])
		temporary_report.close()
		for instance in project["Instances"].values():
			for line in format_instance_log(instance["Log"]):
				pass	
				

	
