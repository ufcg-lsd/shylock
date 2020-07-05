#!/usr/bin/env python3.7

from datetime import datetime, timedelta
from collections import defaultdict
import json, argparse

parser = argparse.ArgumentParser()
parser.add_argument("--start_date", help="Enter the start date in format year-month-day")
parser.add_argument("--end_date", help="Enter the end date in format year-month-day")
args = parser.parse_args()

#reading the date
start_date = datetime.fromisoformat(args.start_date)
end_date = datetime.fromisoformat(args.end_date)
	
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
to_on_states = ['create', 'restore', 'start', 'reboot', 'unpause', 'resume', 'unrescue', 'unshelve', 'pause']
to_off_states = ['softDelete', 'forceDelete', 'delete', 'stop', 'shelve', 'suspend', 'error']


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

sponsors = {sponsor:{} for sponsor in project_sponsors.values()}
sponsors["joabsilva@lsd.ufcg.edu.br"] = {} #joab is the sponsor for the support services and he is not in the csv file

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
	return  "%s Dias, %s Horas e %s Minutos" % (days, hours, minutes)

#this function is to extract actions from the instance's logs that are in the nova cli output format
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
		if datetime.fromisoformat(line[name_to_idx['date']]) > end_date:
			break
		
		if line[name_to_idx['action']] == 'pause':
			status = "Ativa(Pausada)"

		elif line[name_to_idx['action']] in to_on_states:
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
	on = False
	last = start_date

	for line in log_list:
		date = datetime.fromisoformat(line[name_to_idx['date']])
		
		if date > end_date:
			break

		if date > start_date:
			if on:
				total += date - last
			last = date

		if line[name_to_idx['action']] in to_on_states:
			on = True
		elif line[name_to_idx['action']] in to_off_states:
			on = False
	if on:
		total += end_date - last
	return total

def is_not_empty(instance):
	return extract_actions(instance["Log"]) != []

def is_valid(instance):
	return is_not_empty(instance) and get_create_date(instance) < end_date

def get_instance_memory(project ,instance):
	return int(project["Flavors"][instance["Flavor"]]["ram"]) // 1024

def get_instance_vcpus(project ,instance):
	return int(project["Flavors"][instance["Flavor"]]["vcpus"])

for domain_name in data:

	domain = data[domain_name]

	for project in domain.values():

		if project["Name"].strip() == "":
			project["Name"] = empty_value

		sponsor = project_sponsors[project["Name"]]

		total_mem_usage = 0
		total_vcpu_usage = 0
		
		valid_instances = filter(is_valid, project["Instances"].values())
		project["Instances"] = sorted(valid_instances, key = get_create_date)
		print(project["Instances"])
		for instance in project["Instances"]:
			print(instance)
			instance_log = extract_actions(instance["Log"])
			time_use = total_time(instance_log)
			
			instance_mem_usage = get_instance_memory(project, instance) * time_use.total_seconds()
			total_mem_usage += instance_mem_usage
			instance_vcpu_usage = get_instance_vcpus(project, instance) * time_use.total_seconds()
			total_vcpu_usage += instance_vcpu_usage

			status = get_status(instance_log)
			
			instance["Create_Date"] = date_br_format(get_create_date(instance).date())
			instance["Time_Use"] = days_hours_minutes(time_use)
			instance["Status"] = status

			if instance["Name"].strip() == "":
				instance["Name"] = empty_value

		project["Total_Mem_Usage"] = total_mem_usage
		project["Total_Vcpu_Usage"] = total_vcpu_usage 

		project["Domain"] = domain_name
		
		sponsors[sponsor][project["Name"]] = project
		sponsors[sponsor][project["Name"]]["Domain"] = domain_name

with open("processed_data.json", "w") as json_file:
	json_file.write(json.dumps(sponsors))
