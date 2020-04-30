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

print(format_instance_log(data["Default"]["admin"]["Instances"]["969630a1-8f3d-4504-b634-bbecc564b8cf"]["Log"]))

logs_lsd = {}

for domain in data.values():
	
	for project in domain.values():
		for instance in project["Instances"].values():
			for line in format_instance_log(instance["Log"]):
				logs_lsd[line[0]] = "new"

print(logs_lsd.keys())
	
